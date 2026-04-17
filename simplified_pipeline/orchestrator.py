"""
Simplified pipeline orchestrator.

Runs the minimal pipeline: Step1 → Step3A → Step3B → Step4
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .models import (
    PipelineResult,
    SectionBundle,
    StructuredSpec,
)
from .llm_client import LLMConfig

from .clarification.models import ClarificationContext
from .clarification.structural_models import SectionGuidance
from .llm_client import LLMClient, SessionUsage
from .steps import (
    run_step1_structure_extraction,
    run_step3a_variable_extraction,
    run_step3b_workflow_analysis,
    run_step4_spl_emission,
)

logger = logging.getLogger(__name__)


class PipelineConfig:
    """Configuration for the simplified pipeline."""

    def __init__(
        self,
        merged_doc_text: str,
        skill_id: str = "unnamed_skill",
        output_dir: Optional[str] = None,
        llm_config: Optional[LLMConfig] = None,
        save_checkpoints: bool = True,
        # HITL Configuration
        enable_clarification: bool = False,
        clarification_sensitivity: str = "medium",
        clarification_max_iterations: int = 5,
        clarification_ui: Optional[str] = "console",
    ):
        """
        Args:
            merged_doc_text: The merged document text (previously from merged_doc_text)
            skill_id: Optional identifier for the skill
            output_dir: Where to write output (defaults to ./.simplified_output)
            llm_config: LLM configuration
            save_checkpoints: Whether to save intermediate results
            enable_clarification: Enable/disable HITL clarification step
            clarification_sensitivity: Detection sensitivity ("low", "medium", "high")
            clarification_max_iterations: Max clarification iterations (1-10)
            clarification_ui: UI type ("console" or None for headless)
        """
        self.merged_doc_text = merged_doc_text
        self.skill_id = skill_id
        self.output_dir = output_dir or f"./.simplified_output/{skill_id}"
        self.llm_config = llm_config or LLMConfig()
        self.save_checkpoints = save_checkpoints
        # HITL Configuration
        self.enable_clarification = enable_clarification
        self.clarification_sensitivity = clarification_sensitivity
        self.clarification_max_iterations = clarification_max_iterations
        self.clarification_ui = clarification_ui


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """
    Execute the simplified skill-to-CNL-P pipeline.

    Pipeline stages:
    1. Step 0: Structural Clarification (NEW - before Step 1)
    2. Step 1: Structure Extraction → SectionBundle (5 sections)
    3. Step 3A: Variable Extraction → list[VariableSpec]
    4. Step 3B: Workflow Analysis → StructuredSpec
    5. Step 4: SPL Emission → SPLSpec (simplified, no APIs/no files)

    Args:
        config: PipelineConfig with merged_doc_text and options

    Returns:
        PipelineResult with all intermediate and final outputs
    """
    session_usage = SessionUsage()
    client = LLMClient(config=config.llm_config, session_usage=session_usage)

    logger.info(f"=== Simplified pipeline start: {config.skill_id} ===")

    # ── Use provided merged document text ────────────────────────────────
    skill_id = config.skill_id
    merged_doc_text = config.merged_doc_text
    logger.info(f"[P0] Using {len(merged_doc_text)} chars of merged document text")

    # ═════════════════════════════════════════════════════════════════════════
    # STEP 0: Structural Clarification (NEW - runs BEFORE Step 1)
    # ═════════════════════════════════════════════════════════════════════════
    structural_guidance: Optional["SectionGuidance"] = None
    if config.enable_clarification:
        from .clarification.step0_orchestrator import run_step0_structural_clarification
        from .clarification.structural_ui import ConsoleStructuralClarificationUI

        logger.info("[Step 0] Running structural clarification...")
        structural_guidance = run_step0_structural_clarification(
            merged_doc_text=merged_doc_text,
            ui=ConsoleStructuralClarificationUI(),
            max_questions=config.clarification_max_iterations,
        )
        _save_checkpoint(config, "step0_guidance", structural_guidance)
        if structural_guidance.clarification_applied:
            logger.info(
                f"[Step 0] Generated guidance with {len(structural_guidance.section_overrides)} overrides"
            )
        else:
            logger.info("[Step 0] No clarification needed")
    else:
        logger.info("[Step 0] Structural clarification disabled")

    # ── Step 1: Structure Extraction ────────────────────────────────────
    logger.info("[Step 1] Extracting structure...")
    bundle = run_step1_structure_extraction(
        merged_doc_text=merged_doc_text,
        client=client,
        guidance=structural_guidance,  # NEW: Pass guidance from Step 0
    )
    _save_checkpoint(config, "step1_bundle", bundle)

    # ── Step 3A: Variable Extraction ────────────────────────────────────
    logger.info("[Step 3A] Extracting variables...")
    variables = run_step3a_variable_extraction(
        bundle=bundle,
        client=client,
    )
    
    # ── Step 3B: Workflow Analysis ──────────────────────────────────────
    logger.info("[Step 3B] Analyzing workflow...")
    spec_partial = run_step3b_workflow_analysis(
        bundle=bundle,
        var_ids=[v.var_id for v in variables],
        client=client,
    )
    
    # Combine into full StructuredSpec
    structured_spec = StructuredSpec(
        variables=variables,
        workflow_steps=spec_partial.workflow_steps,
        alternative_flows=spec_partial.alternative_flows,
        exception_flows=spec_partial.exception_flows,
    )
    _save_checkpoint(config, "step3_spec", structured_spec)
    
    # ── Step 4: SPL Emission ────────────────────────────────────────────
    logger.info("[Step 4] Emitting SPL...")
    spl_spec = run_step4_spl_emission(
        skill_id=skill_id,
        bundle=bundle,
        spec=structured_spec,
        client=client,
    )
    _write_final_output(spl_spec, config.output_dir)
    
    # ── Log token usage ─────────────────────────────────────────────────
    _log_token_usage(session_usage)

    result = PipelineResult(
        skill_id=skill_id,
        section_bundle=bundle,
        structured_spec=structured_spec,
        spl_spec=spl_spec,
        structural_guidance=structural_guidance if config.enable_clarification else None,  # NEW: SectionGuidance from Step 0
    )

    logger.info(f"=== Pipeline complete: {skill_id} ===")
    return result


def _save_checkpoint(config: PipelineConfig, stage: str, data: object) -> None:
    """Save intermediate result to disk."""
    if not config.save_checkpoints:
        return
    
    out = Path(config.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    
    path = out / f"{stage}.json"
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(_to_jsonable(data), fh, indent=2, ensure_ascii=False)
        logger.debug(f"[checkpoint] saved {stage} → {path}")
    except Exception as exc:
        logger.warning(f"[checkpoint] could not save {stage}: {exc}")


def _to_jsonable(obj: object) -> object:
    """Convert dataclasses to JSON-serializable objects."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}  # type: ignore
    if isinstance(obj, list):
        return [_to_jsonable(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def _write_final_output(spl_spec, output_dir: str) -> None:
    """Write the final SPL output to disk."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    
    spl_path = out / f"{spl_spec.skill_id}.spl"
    spl_path.write_text(spl_spec.spl_text, encoding="utf-8")
    logger.info(f"[output] SPL spec written → {spl_path}")


def _log_token_usage(session_usage: SessionUsage) -> None:
    """Log token usage summary."""
    for step, usage in session_usage.by_step.items():
        logger.info(f"[tokens] {step}: in={usage.input_tokens} out={usage.output_tokens}")
    total = session_usage.total
    logger.info(f"[tokens] TOTAL: in={total.input_tokens} out={total.output_tokens} ({total.total})")


# Convenience function for quick usage
def run_simplified_pipeline(
    merged_doc_text: str,
    skill_id: str = "unnamed_skill",
    output_dir: Optional[str] = None,
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    enable_clarification: bool = False,  # NEW
    clarification_sensitivity: str = "medium",  # NEW
) -> PipelineResult:
    """
    Quick entry point for running the simplified pipeline.

    Args:
        merged_doc_text: The merged document text to process
        skill_id: Optional identifier for the skill
        output_dir: Where to write output (defaults to ./.simplified_output/{skill_id})
        model: LLM model name
        api_key: OpenAI API key (optional, can use env var)
        enable_clarification: Enable HITL clarification step (default: False)
        clarification_sensitivity: Detection sensitivity ("low", "medium", "high")

    Returns:
        PipelineResult with spl_spec.spl_text containing the generated SPL
    """
    llm_config = LLMConfig(model=model, api_key=api_key)
    config = PipelineConfig(
        merged_doc_text=merged_doc_text,
        skill_id=skill_id,
        output_dir=output_dir,
        llm_config=llm_config,
        save_checkpoints=True,
        enable_clarification=enable_clarification,
        clarification_sensitivity=clarification_sensitivity,
    )
    return run_pipeline(config)
