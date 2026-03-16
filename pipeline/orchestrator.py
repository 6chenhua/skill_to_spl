"""
skill-to-CNL-P pipeline orchestrator.

Wires all stages together in the correct order and handles:
  - Checkpoint saving (save intermediate results to disk to enable rerun from any stage)
  - Capability profile injection (optional environment model for Step 2B)
  - Consolidated logging and token usage reporting

Pipeline stage order:
    P1 (code)   → FileReferenceGraph
    P2 (LLM)    → FileRoleMap
    P3 (code)   → SkillPackage
    Step 1 (LLM) → SectionBundle
    Step 3 (LLM) → StructuredSpec   (3A: entities, 3B: workflow)
    Step 4 (LLM) → SPLSpec
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional


from pipeline.llm_client import LLMClient, LLMConfig, SessionUsage
from models.data_models import PipelineResult
from pipeline.llm_steps import (
    make_p3_summarize_fn,
    run_p2_file_role_resolver,
    run_step1_structure_extraction,
    run_step3_structured_extraction,
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
        save_checkpoints:    If True, save each stage output as JSON to output_dir.
        resume_from:         If set, load checkpoints up to (but not including) this
                             stage and resume from there. Useful for reruns after
                             prompt changes.
                             Values: "p2" | "step1" | "step3" | "step4"
    """

    def __init__(
        self,
        skill_root: str,
        output_dir: Optional[str] = None,
        llm_config: Optional[LLMConfig] = None,
        save_checkpoints: bool = True,
        resume_from: Optional[str] = None,
    ):
        self.skill_root      = skill_root
        self.output_dir      = output_dir or str(Path(skill_root) / ".cnlp_output")
        self.llm_config      = llm_config or LLMConfig()
        self.save_checkpoints = save_checkpoints
        self.resume_from     = resume_from


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint helpers
# ─────────────────────────────────────────────────────────────────────────────

class _Checkpointer:
    def __init__(self, output_dir: str, enabled: bool):
        self._dir     = Path(output_dir)
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
                return json.load(fh)
        except Exception as exc:
            logger.warning("[checkpoint] could not load %s: %s", stage, exc)
            return None


def _to_jsonable(obj: object) -> object:
    """Recursively convert dataclasses / enums to JSON-serializable objects."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}  # type: ignore[arg-type]
    if isinstance(obj, list):
        return [_to_jsonable(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if hasattr(obj, "value"):   # Enums
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
    client        = LLMClient(config=config.llm_config, session_usage=session_usage)
    ckpt          = _Checkpointer(config.output_dir, config.save_checkpoints)

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

    # ── Step 3: Structured Entity & Workflow Extraction (LLM) ──────────────
    logger.info("[Step 3] extracting entities and workflow structure...")
    structured_spec = run_step3_structured_extraction(
        bundle=bundle,
        client=client,
    )
    ckpt.save("step3_structured_spec", structured_spec)

    # ── Step 4: SPL Emission (LLM) ───────────────────────────────────────────
    logger.info("[Step 4] emitting SPL spec...")
    spl_spec = run_step4_spl_emission(
        bundle=bundle,
        interface_spec=structured_spec,
        skill_id=graph.skill_id,
        client=client,
    )

    # ── Write final output ───────────────────────────────────────────────────
    _write_final_output(spl_spec, config.output_dir)

    # ── Diagnostics ──────────────────────────────────────────────────────────
    _log_token_usage(session_usage)

    result = PipelineResult(
        skill_id=graph.skill_id,
        graph=graph,
        file_role_map=file_role_map,
        package=package,
        section_bundle=bundle,
        structured_spec=structured_spec,
        spl_spec=spl_spec,
    )

    logger.info("=== pipeline complete: %s ===", graph.skill_id)
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


def _log_token_usage(session_usage: SessionUsage) -> None:
    for step, usage in session_usage.by_step.items():
        logger.info("[tokens] %s: in=%d out=%d", step, usage.input_tokens, usage.output_tokens)
    total = session_usage.total
    logger.info("[tokens] TOTAL: in=%d out=%d (%d)", total.input_tokens, total.output_tokens, total.total)

