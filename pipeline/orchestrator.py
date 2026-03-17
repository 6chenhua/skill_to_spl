"""
skill-to-CNL-P pipeline orchestrator.

Wires all stages together in the correct order and handles:
  - Checkpoint saving (save intermediate results to disk to enable rerun from any stage)
  - Capability profile injection (optional environment model for Step 2B)
  - Consolidated logging and token usage reporting
  - Maximum parallelism between Step 3 and Step 4

Pipeline stage order:
    P1 (code)   → FileReferenceGraph
    P2 (LLM)    → FileRoleMap
    P3 (code)   → SkillPackage
    Step 1 (LLM) → SectionBundle
    Step 3A (LLM) → entities
    Step 3B (LLM) + Step 4C/D (LLM) → workflow_steps + variables/files/apis (PARALLEL)
    Step 4A/B/E/F (LLM) → final SPL
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from pipeline.llm_client import LLMClient, LLMConfig, SessionUsage
from models.data_models import PipelineResult, StructuredSpec
from pipeline.llm_steps import (
    make_p3_summarize_fn,
    run_p2_file_role_resolver,
    run_step1_structure_extraction,
    run_step3a_entity_extraction,
    run_step3b_workflow_analysis,
    run_step4_spl_emission,
    run_step4_spl_emission_parallel,
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
        self.skill_root = skill_root
        self.output_dir = output_dir or str(Path(skill_root) / ".cnlp_output")
        self.llm_config = llm_config or LLMConfig()
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
    if hasattr(obj, "value"):  # Enums
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

    # ── Step 3 & 4: Parallel execution with dependency-driven scheduling ───
    # 
    # Dependency graph:
    #   Step 3A (entities) ──┬─→ S4C → symbol_table → (S4A || S4B)
    #                        │
    #                        └─→ Step 3B ──→ workflow/flows ──→ S4D
    #                                                          │
    #   S4E ←───────────────────────────────────────────────────┘
    #    ↓
    #   S4F
    #
    # Phase 1: Step 3A (must complete first)
    # Import Step 4 helper functions for parallel execution
    from pipeline.llm_steps.step4_spl_emission import (
        _call_4a, _call_4b, _call_4c, _call_4d, _call_4e, _call_4f,
        _extract_symbol_table, _format_symbol_table, _prepare_step4_inputs_parallel,
        _assemble_spl, _build_review_summary,
    )
    from models.data_models import SPLSpec
    
    logger.info("[Step 3A] extracting entities...")
    entities = run_step3a_entity_extraction(bundle=bundle, client=client)
    
    # Phase 2: Parallel lines
    #   Line 1: Step 3B (workflow analysis) + S4D (APIs)
    #   Line 2: S4C (variables/files) → S4A + S4B
    logger.info("[Parallel] launching Line 1 (3B→S4D) and Line 2 (S4C→S4A/B)...")
    
    with ThreadPoolExecutor(max_workers=2) as phase2_pool:
        # Line 1: Step 3B (needs entity_ids from 3A)
        entity_ids = [e.entity_id for e in entities]
        future_3b = phase2_pool.submit(
            run_step3b_workflow_analysis,
            bundle=bundle,
            entity_ids=entity_ids,
            client=client,
        )
        
        # Line 2: S4C (needs entities from 3A)
        # We'll handle S4A and S4B after S4C completes
        # Prepare inputs for Line 2 (we need workflow info for S4E later, prepare minimal)
        # We'll launch S4C now, then S4A/S4B when symbol_table is ready
        s4a_in, s4b_in, s4c_in, s4d_in, s4e_in, s4f_in = _prepare_step4_inputs_parallel(
            bundle, entities, [], [], []  # workflow/flows will be filled later
        )
        
        future_4c = phase2_pool.submit(_call_4c, client, s4c_in)
        
        # Wait for both lines to complete
        structured_spec_partial = future_3b.result()  # Has workflow_steps, flows, but empty entities
        block_4c = future_4c.result()
    
    # Build complete StructuredSpec
    structured_spec = StructuredSpec(
        entities=entities,
        workflow_steps=structured_spec_partial.workflow_steps,
        alternative_flows=structured_spec_partial.alternative_flows,
        exception_flows=structured_spec_partial.exception_flows,
    )
    ckpt.save("step3_structured_spec", structured_spec)
    
    # Phase 3: Complete Line 2 (S4A, S4B) and prepare S4D/S4E/S4F
    logger.info("[Step 4] Phase 3: completing S4A/S4B and running S4D/E/F...")
    
    # Extract symbol table from S4C output
    symbol_table = _extract_symbol_table(block_4c)
    symbol_table_text = _format_symbol_table(symbol_table)
    logger.info("[Step 4] Symbol table — variables: %d, files: %d",
                 len(symbol_table["variables"]), len(symbol_table["files"]))
    
    # Re-prepare inputs with complete workflow info
    s4a_inputs, s4b_inputs, _, s4d_inputs, s4e_inputs, s4f_inputs = _prepare_step4_inputs_parallel(
        bundle,
        entities,
        structured_spec.workflow_steps,
        structured_spec.alternative_flows,
        structured_spec.exception_flows,
    )
    
    with ThreadPoolExecutor(max_workers=3) as phase3_pool:
        # Line 2 continued: S4A and S4B (parallel, only need symbol_table)
        future_4a = phase3_pool.submit(_call_4a, client, s4a_inputs, symbol_table_text)
        future_4b = phase3_pool.submit(_call_4b, client, s4b_inputs, symbol_table_text)
        
        # Line 1 continued: S4D (needs workflow_steps with NETWORK effects)
        future_4d = phase3_pool.submit(_call_4d, client, s4d_inputs)
        
        # Collect S4A, S4B results
        block_4a = future_4a.result()
        block_4b = future_4b.result()
        
        # Wait for S4D
        block_4d = future_4d.result()
    
    # Phase 4: S4E (merge point - needs symbol_table from Line 2 and apis_spl from Line 1)
    logger.info("[Step 4] Phase 4: S4E (worker)...")
    block_4e = _call_4e(client, s4e_inputs, symbol_table_text, block_4d)
    
    # Phase 5: S4F (final)
    block_4f = ""
    if s4f_inputs["has_examples"]:
        logger.info("[Step 4] Phase 5: S4F (examples)...")
        block_4f = _call_4f(client, s4f_inputs, block_4e)
    
    # Assemble final SPL
    from pipeline.llm_steps.step4_spl_emission import _assemble_spl, _build_review_summary
    spl_text = _assemble_spl(
        graph.skill_id, block_4a, block_4b, block_4c, block_4d, block_4e, block_4f
    )
    review_summary = _build_review_summary()
    clause_counts = {}
    
    logger.info("[Step 4] SPL assembled (%d chars)", len(spl_text))
    
    from models.data_models import SPLSpec
    spl_spec = SPLSpec(
        skill_id=graph.skill_id,
        spl_text=spl_text,
        review_summary=review_summary,
        clause_counts=clause_counts,
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
