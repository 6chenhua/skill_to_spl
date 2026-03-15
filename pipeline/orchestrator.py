"""
skill-to-CNL-P pipeline orchestrator.

Wires all stages together in the correct order and handles:
  - Checkpoint saving (save intermediate results to disk to enable rerun from any stage)
  - Capability profile injection (optional environment model for Step 2B)
  - Consolidated logging and token usage reporting

Pipeline stage order:
    P1 (code)  → FileReferenceGraph
    P2 (LLM)   → FileRoleMap
    P3 (code)  → SkillPackage
    Step 1 (LLM)  → SectionBundle
    Step 2A (LLM) → list[RawClause]
    Step 2B (code) → list[ClassifiedClause]
    Step 3 (LLM)  → StructuredSpec
    Step 4 (LLM)  → SPLSpec
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Any

from models.data_models import (
    Classification,
    PipelineResult,
    RawClause,
    SectionBundle,
    SectionItem,
)
from pipeline.llm_client import LLMClient, LLMConfig, SessionUsage
from pipeline.step2b_classifier import classify_all
from pipeline.llm_steps import (
    make_p3_summarize_fn,
    run_p2_file_role_resolver,
    run_step1_structure_extraction,
    run_step2a_clause_extraction,
    run_step3_interface_inference,
    run_step4_spl_emission,
)
from pre_processing.p1_reference_graph import build_reference_graph
from pre_processing.p3_assembler import assemble_skill_package

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline configuration
# ─────────────────────────────────────────────────────────────────────────────

class PipelineConfig:
    """
    Configuration for a single pipeline run.

    Args:
        skill_root:          Path to the skill directory (must contain SKILL.md).
        output_dir:          Where to write intermediate and final outputs.
                             Defaults to <skill_root>/.cnlp_output/
        llm_config:          LLM model and retry settings.
        capability_profile:  Optional environment capability model for Step 2B.
                             Shape: {"available_effects": ["READ", "EXEC", ...]}
        save_checkpoints:    If True, save each stage output as JSON to output_dir.
        resume_from:         If set, load checkpoints up to (but not including) this
                             stage and resume from there. Useful for reruns after
                             prompt changes.
                             Values: "p2" | "step1" | "step2a" | "step3" | "step4"
    """

    def __init__(
            self,
            skill_root: str,
            output_dir: Optional[str] = None,
            llm_config: Optional[LLMConfig] = None,
            capability_profile: Optional[dict] = None,
            save_checkpoints: bool = True,
            resume_from: Optional[str] = None,
    ):
        self.skill_root = skill_root
        self.output_dir = output_dir or str(Path(skill_root) / ".cnlp_output")
        self.llm_config = llm_config or LLMConfig()
        self.capability_profile = capability_profile
        self.save_checkpoints = save_checkpoints
        self.resume_from = resume_from


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint helpers
# ─────────────────────────────────────────────────────────────────────────────

class _Checkpointer:
    def __init__(self, output_dir: str, enabled: bool):
        self._dir = Path(output_dir)
        self._enabled = enabled
        if enabled:
            self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, stage: str, data: object) -> None:
        if not self._enabled:
            return
        path = self._dir / f"{stage}.json"
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(_to_jsonable(data), fh, indent=2, ensure_ascii=False)
            logger.debug("[checkpoint] saved %s → %s", stage, path)
        except Exception as exc:
            logger.warning("[checkpoint] could not save %s: %s", stage, exc)

    def load(self, stage: str) -> Optional[dict]:
        if not self._enabled:
            return None
        path = self._dir / f"{stage}.json"
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
                # Validate and migrate old checkpoint format if needed
                return _validate_checkpoint_integrity(data, stage)
        except Exception as exc:
            logger.warning("[checkpoint] could not load %s: %s", stage, exc)
            return None


def _validate_checkpoint_integrity(data: Any, stage: str) -> Any:
    """
    Validate checkpoint data integrity and provide graceful degradation
    for missing fields in old checkpoint files.
    
    Args:
        data: Loaded checkpoint data (can be dict, list, or other types)
        stage: Pipeline stage name
        
    Returns:
        Validated and potentially migrated checkpoint data
    """
    # Handle different data types based on stage
    if stage == "step2a_clause_extraction" and isinstance(data, list):
        # Handle RawClause list - add missing clause_type field
        for clause_data in data:
            if isinstance(clause_data, dict) and "clause_type" not in clause_data:
                clause_data["clause_type"] = "rule"  # Default to rule type
                logger.debug("[checkpoint] %s: added default clause_type", stage)
        return data
    
    elif stage == "step2b_classification" and isinstance(data, list):
        # Handle ClassifiedClause list - add missing downgraded field
        for clause_data in data:
            if isinstance(clause_data, dict) and "downgraded" not in clause_data:
                clause_data["downgraded"] = False  # Default to not downgraded
                logger.debug("[checkpoint] %s: added default downgraded", stage)
        return data
    
    # For dict-based stages, check if it's actually a dict
    if not isinstance(data, dict):
        logger.warning("[checkpoint] %s: unexpected format, expected dict but got %s", stage, type(data).__name__)
        return data
    
    # Add default values for new fields that might be missing in old checkpoints
    if stage == "p1_reference_graph" and "graph" in data:
        graph_data = data["graph"]
        if isinstance(graph_data, dict):
            # Add missing fields with defaults for FileReferenceGraph
            if "local_scripts" not in graph_data:
                graph_data["local_scripts"] = []
                logger.debug("[checkpoint] %s: added default local_scripts", stage)
            if "referenced_libs" not in graph_data:
                graph_data["referenced_libs"] = []
                logger.debug("[checkpoint] %s: added default referenced_libs", stage)
    
    elif stage == "step3_interface_inference" and isinstance(data, dict):
        # Handle StructuredSpec - add missing fields to entities and workflow_steps
        if "entities" in data and isinstance(data["entities"], list):
            for entity_data in data["entities"]:
                if isinstance(entity_data, dict):
                    if "is_file" not in entity_data:
                        entity_data["is_file"] = False
                    if "file_path" not in entity_data:
                        entity_data["file_path"] = ""
                    if "from_omit_files" not in entity_data:
                        entity_data["from_omit_files"] = False
        
        if "workflow_steps" in data and isinstance(data["workflow_steps"], list):
            for step_data in data["workflow_steps"]:
                if isinstance(step_data, dict) and "execution_mode" not in step_data:
                    step_data["execution_mode"] = "LLM_PROMPT"  # Default execution mode
                    logger.debug("[checkpoint] %s: added default execution_mode", stage)
    
    return data


def _to_jsonable(obj: object) -> object:
    """
    Recursively convert dataclasses / enums to JSON-serializable objects.
    
    Handles backward compatibility by gracefully handling missing fields
    in older checkpoint files.
    """
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}  # type: ignore[arg-type]
    if isinstance(obj, list):
        return [_to_jsonable(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, Classification):
        return obj.value
    if hasattr(obj, "value"):  # other Enums
        return obj.value
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline runner
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """
    Execute the full skill-to-CNL-P pipeline.

    Args:
        config: PipelineConfig describing the skill to process and run options.

    Returns:
        PipelineResult containing all intermediate and final outputs.
    """
    session_usage = SessionUsage()
    client = LLMClient(config=config.llm_config, session_usage=session_usage)
    ckpt = _Checkpointer(config.output_dir, config.save_checkpoints)

    logger.info("=== skill-to-CNL-P pipeline start: %s ===", config.skill_root)

    # ── P1: Reference Graph Builder (code) ───────────────────────────────────
    logger.info("[P1] building reference graph...")
    graph = build_reference_graph(config.skill_root)
    ckpt.save("p1_graph", graph)
    logger.info("[P1] found %d files, %d doc edges", len(graph.nodes), len(graph.edges))

    # ── P2: File Role Resolver (LLM) ─────────────────────────────────────────
    logger.info("[P2] resolving file roles...")
    file_role_map = run_p2_file_role_resolver(graph=graph, client=client)
    ckpt.save("p2_file_role_map", file_role_map)

    # ── P3: Skill Package Assembler (code + optional LLM fallback) ──────────────
    logger.info("[P3] assembling skill package...")
    package = assemble_skill_package(
        graph=graph,
        file_role_map=file_role_map,
        summarize_fn=make_p3_summarize_fn(client),
    )
    ckpt.save("p3_package", {"skill_id": package.skill_id,
                             "merged_doc_chars": len(package.merged_doc_text)})

    # ── Step 1: Structure Extraction (LLM) ───────────────────────────────────
    logger.info("[Step 1] extracting structure...")
    bundle = run_step1_structure_extraction(package=package, client=client)
    ckpt.save("step1_bundle", bundle)

    # ── Step 2A: Clause Extraction + Scoring (LLM) ───────────────────────────
    logger.info("[Step 2A] extracting and scoring clauses...")
    raw_clauses = run_step2a_clause_extraction(bundle=bundle, client=client)
    ckpt.save("step2a_raw_clauses", raw_clauses)

    # ── Step 2B: Classification (code) ───────────────────────────────────────
    logger.info("[Step 2B] classifying clauses...")
    
    # Enhance capability profile with P1 data for environment-aware classification
    enhanced_capability_profile = config.capability_profile.copy() if config.capability_profile else {}
    enhanced_capability_profile["local_scripts"] = graph.local_scripts
    enhanced_capability_profile["referenced_libs"] = graph.referenced_libs
    
    classified = classify_all(
        raw_clauses=raw_clauses,
        capability_profile=enhanced_capability_profile,
    )
    ckpt.save("step2b_classified", classified)
    _log_classification_summary(classified)

    # ── Step 3: Entity & Interface Inference (LLM) ───────────────────────────
    logger.info("[Step 3] inferring interface spec...")
    interface_spec = run_step3_interface_inference(
        bundle=bundle,
        classified_clauses=classified,
        client=client,
    )
    ckpt.save("step3_interface_spec", interface_spec)

    # ── Step 4: SPL Emission (LLM) ───────────────────────────────────────────
    logger.info("[Step 4] emitting SPL spec...")
    spl_spec = run_step4_spl_emission(
        bundle=bundle,
        classified_clauses=classified,
        interface_spec=interface_spec,
        skill_id=graph.skill_id,
        client=client,
    )

    # ── Write final output ───────────────────────────────────────────────────
    _write_final_output(spl_spec, config.output_dir)

    # ── Diagnostics ──────────────────────────────────────────────────────────
    needs_review_count = sum(1 for c in classified if c.needs_review)
    low_confidence_count = sum(1 for c in classified if c.confidence < 0.6)
    _log_token_usage(session_usage)

    result = PipelineResult(
        skill_id=graph.skill_id,
        graph=graph,
        file_role_map=file_role_map,
        package=package,
        section_bundle=bundle,
        raw_clauses=raw_clauses,
        classified_clauses=classified,
        structured_spec=interface_spec,
        spl_spec=spl_spec,
        needs_review_count=needs_review_count,
        low_confidence_count=low_confidence_count,
    )

    logger.info(
        "=== pipeline complete: %d clauses, %d needs_review, %d low_confidence ===",
        len(classified), needs_review_count, low_confidence_count,
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Output writer
# ─────────────────────────────────────────────────────────────────────────────

def _write_final_output(spl_spec, output_dir: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    spl_path = out / f"{spl_spec.skill_id}.spl"
    spl_path.write_text(spl_spec.spl_text, encoding="utf-8")
    logger.info("[output] SPL spec written → %s", spl_path)

    if spl_spec.review_summary:
        review_path = out / f"{spl_spec.skill_id}_review.md"
        review_path.write_text(spl_spec.review_summary, encoding="utf-8")
        logger.info("[output] review summary written → %s", review_path)


# ─────────────────────────────────────────────────────────────────────────────
# Diagnostics helpers
# ─────────────────────────────────────────────────────────────────────────────

def _log_classification_summary(classified) -> None:
    from collections import Counter
    counts = Counter(c.classification.value for c in classified)
    logger.info(
        "[Step 2B] classification: HARD=%d MEDIUM=%d SOFT=%d NON=%d",
        counts.get("COMPILABLE_HARD", 0),
        counts.get("COMPILABLE_MEDIUM", 0),
        counts.get("COMPILABLE_SOFT", 0),
        counts.get("NON_COMPILABLE", 0),
    )


def _log_token_usage(session_usage: SessionUsage) -> None:
    for step, usage in session_usage.by_step.items():
        logger.info("[tokens] %s: in=%d out=%d", step, usage.input_tokens, usage.output_tokens)
    total = session_usage.total
    logger.info("[tokens] TOTAL: in=%d out=%d (%d)", total.input_tokens, total.output_tokens, total.total)
