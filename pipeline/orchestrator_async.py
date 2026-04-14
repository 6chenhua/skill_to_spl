"""
orchestrator_async.py
─────────────────────
Async version of the skill-to-CNL-P pipeline orchestrator.

Key changes from sync version:
- All pipeline steps are async
- Uses asyncio.gather() instead of ThreadPoolExecutor
- Clear dependency control via await
- API generation moved to Step 1.5 (after Step 1)

Pipeline flow:
Step 1 → Step 1.5 (API Generation) → Step 3A
                                    ↓
Step 3B (async parallel) ←→ S4C (async parallel)
       ↓                         ↓
       └────────→ S4E ←─────────┘
                     ↓
                    S4F
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from pipeline.llm_client import LLMClient, LLMConfig, SessionUsage
from models.data_models import (
    APISymbolTable,
    PipelineResult,
    SPLSpec,
    StructuredSpec,
)
from pipeline.llm_steps import (
    run_step1_structure_extraction,
    run_step3a_entity_extraction,
    run_step3b_workflow_analysis,
)
from pipeline.llm_steps.step1_5_api_generation import (
    merge_api_spl_blocks,
    _generate_single_api_async,
    build_api_symbol_table,
)
from pipeline.llm_steps.step4_spl_emission import (
    _call_4a_async,
    _call_4b_async,
    _call_4c_async,
    _call_4e_async,
    _call_4f_async,
    _call_s0_async,
    _assemble_spl,
    _build_review_summary,
    _extract_symbol_table,
    _format_symbol_table,
    _prepare_step4_inputs_parallel,
    validate_and_fix_worker_nesting_async,
)
from pre_processing.p1_reference_graph import build_reference_graph
from pre_processing.p2_file_roles import assign_file_priorities
from pre_processing.p3_assembler import assemble_skill_package

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline configuration
# ─────────────────────────────────────────────────────────────────────────────

class PipelineConfig:
    """
    Configuration for a single pipeline run.

    Args:
        skill_root: Path to the skill directory (must contain SKILL.md).
        output_dir: Where to write intermediate and final outputs.
        llm_config: LLM model and retry settings.
        save_checkpoints: If True, save each stage output as JSON.
    """

    def __init__(
        self,
        skill_root: str,
        output_dir: Optional[str] = None,
        llm_config: Optional[LLMConfig] = None,
        save_checkpoints: bool = True,
    ):
        self.skill_root = skill_root
        self.output_dir = output_dir or str(Path(skill_root) / ".cnlp_output")
        self.llm_config = llm_config or LLMConfig()
        self.save_checkpoints = save_checkpoints


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
        # type: ignore[arg-type] - we know obj has __dataclass_fields__
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}  # type: ignore[arg-type]
    if isinstance(obj, list):
        return [_to_jsonable(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if hasattr(obj, "value"):
        return obj.value
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# Async Pipeline Runner
# ─────────────────────────────────────────────────────────────────────────────

async def run_pipeline_async(config: PipelineConfig) -> PipelineResult:
    """
    Execute the full skill-to-CNL-P pipeline using async/await.

    Args:
        config: PipelineConfig describing the skill to process.

    Returns:
        PipelineResult containing all intermediate and final outputs.
    """
    session_usage = SessionUsage()
    client = LLMClient(config=config.llm_config, session_usage=session_usage)
    ckpt = _Checkpointer(config.output_dir, config.save_checkpoints)

    logger.info("=== skill-to-CNL-P pipeline (async) start: %s ===", config.skill_root)

    # ── P1: Reference Graph Builder (code) ───────────────────────────────────
    logger.info("[P1] building reference graph...")
    graph = build_reference_graph(config.skill_root)
    ckpt.save("p1_graph", graph)
    logger.info("[P1] found %d files, %d doc edges", len(graph.nodes), len(graph.edges))

    # ── P2: File Role Resolver (rule-based, no LLM) ───────────────────────────────
    logger.info("[P2] assigning file priorities (rule-based)...")
    file_role_map = assign_file_priorities(graph=graph)
    ckpt.save("p2_file_role_map", file_role_map)

    # ── P3: Skill Package Assembler (code + P2.5 API analysis merged) ──────────────
    logger.info("[P3] assembling skill package with P2.5 API analysis...")
    package = assemble_skill_package(
        graph=graph,
        file_role_map=file_role_map,
        client=client,
    )
    ckpt.save("p3_package", {
        "skill_id": package.skill_id,
        "merged_doc_chars": len(package.merged_doc_text),
        "tools_count": len(package.tools),
    })
    logger.info("[P3] assembled with %d pre-extracted tools", len(package.tools))

    # ── Step 1: Structure Extraction (LLM) ───────────────────────────────────
    logger.info("[Step 1] extracting structure...")
    # Note: Step 1 is still sync - consider making it async if needed
    bundle, step1_network_apis = run_step1_structure_extraction(package=package, client=client)
    ckpt.save("step1_bundle", bundle)

    # Merge network APIs from Step 1 into package.tools
    package.tools.extend(step1_network_apis)
    logger.info("[Tools] total merged tools: %d", len(package.tools))

    # ── Step 1.5: API Definition Generation ──────────────────────────────────
    # Generate API definitions for all tools (moved from Step 4D)
    logger.info("[Step 1.5] generating API definitions...")
    api_table = await _generate_api_definitions_async(
        tools=package.tools,
        client=client,
    )
    ckpt.save("step1_5_api_table", {
        "api_count": len(api_table.apis),
        "api_names": list(api_table.apis.keys()),
    })
    logger.info("[Step 1.5] generated %d API definitions", len(api_table.apis))

    # ── Step 3A: Entity Extraction (LLM) ─────────────────────────────────────
    logger.info("[Step 3A] extracting entities...")
    # Note: Step 3A is still sync - consider making it async if needed
    entities = run_step3a_entity_extraction(bundle=bundle, client=client)

    # ── Phase 2: Step 3B + S4C (parallel async) ───────────────────────────────
    logger.info("[Phase 2] launching Step 3B and S4C in parallel...")

    # Launch both in parallel
    step3b_task = asyncio.create_task(_run_step3b_async(
        bundle=bundle,
        entities=entities,
        tools=package.tools,
        client=client,
    ))

    # Prepare S4C inputs
    s4a_inputs, s4b_inputs, s4c_inputs, _, s4e_inputs, s4f_inputs = _prepare_step4_inputs_parallel(
        bundle, entities, [], [], []
    )

    s4c_task = asyncio.create_task(_call_4c_async(client, s4c_inputs))

    # Wait for both to complete
    structured_spec_partial, block_4c = await asyncio.gather(step3b_task, s4c_task)

    # Save S4C output
    ckpt.save("step4c_variables_files", {"variables_files_spl": block_4c})

    # Build complete StructuredSpec
    structured_spec = StructuredSpec(
        entities=entities,
        workflow_steps=structured_spec_partial.workflow_steps,
        alternative_flows=structured_spec_partial.alternative_flows,
        exception_flows=structured_spec_partial.exception_flows,
    )
    ckpt.save("step3_structured_spec", structured_spec)

    # ── Phase 3: S4A, S4B (parallel async) + S0 ──────────────────────────────
    logger.info("[Phase 3] launching S4A, S4B, and S0 in parallel...")

    # Extract symbol table from S4C output
    symbol_table = _extract_symbol_table(block_4c)
    symbol_table_text = _format_symbol_table(symbol_table)
    logger.info("[Step 4] Symbol table — variables: %d, files: %d",
                len(symbol_table["variables"]), len(symbol_table["files"]))

    # Re-prepare inputs with complete workflow info
    s4a_inputs, s4b_inputs, _, _, s4e_inputs, s4f_inputs = _prepare_step4_inputs_parallel(
        bundle,
        entities,
        structured_spec.workflow_steps,
        structured_spec.alternative_flows,
        structured_spec.exception_flows,
    )

    # Launch S4A, S4B, and S0 in parallel
    s4a_task = asyncio.create_task(_call_4a_async(client, s4a_inputs, symbol_table_text))
    s4b_task = asyncio.create_task(_call_4b_async(client, s4b_inputs, symbol_table_text))

    intent_text = bundle.to_text(["INTENT"])
    notes_text = bundle.to_text(["NOTES"])
    s0_task = asyncio.create_task(_call_s0_async(client, graph.skill_id, intent_text, notes_text))

    # Collect results
    block_4a, block_4b, block_s0 = await asyncio.gather(s4a_task, s4b_task, s0_task)

    # Prepare API block from pre-generated API table
    block_4d = merge_api_spl_blocks(api_table)

    # Save outputs
    ckpt.save("step4a_persona", {"persona_spl": block_4a})
    ckpt.save("step4b_constraints", {"constraints_spl": block_4b})
    ckpt.save("step4d_apis", {"apis_spl": block_4d})
    ckpt.save("step0_define_agent", {"define_agent_header": block_s0})

    # ── Phase 4: S4E (depends on everything above) ────────────────────────────
    logger.info("[Phase 4] S4E (worker)...")
    block_4e_original = await _call_4e_async(client, s4e_inputs, symbol_table_text, block_4d)
    ckpt.save("step4e_worker_original", {"worker_spl": block_4e_original})

    # ── Phase 4.5: S4E1/S4E2 - Validate and fix nested BLOCK structures ──────
    block_4e, nesting_result = await validate_and_fix_worker_nesting_async(client, block_4e_original)
    ckpt.save("step4e1_nesting_detection", nesting_result)

    if nesting_result.get("has_violations", False):
        ckpt.save("step4e2_nesting_fix", {
            "original": block_4e_original,
            "fixed": block_4e,
            "violations_count": len(nesting_result.get("violations", [])),
        })
        logger.info("[Step 4] Phase 4.5: S4E1 detected %d violations, S4E2 fixed them",
                    len(nesting_result.get("violations", [])))
    else:
        logger.info("[Step 4] Phase 4.5: S4E1 - no nested BLOCK violations found")

    # ── Phase 5: S4F (final) ─────────────────────────────────────────────────
    block_4f = ""
    if s4f_inputs["has_examples"]:
        logger.info("[Phase 5] S4F (examples)...")
        block_4f = await _call_4f_async(client, s4f_inputs, block_4e)
        ckpt.save("step4f_examples", {"examples_spl": block_4f})

    # ── Assemble final SPL ───────────────────────────────────────────────────
    spl_text = _assemble_spl(
        graph.skill_id, block_s0, block_4a, block_4b, block_4c, block_4d, block_4e, block_4f
    )
    review_summary = _build_review_summary()
    clause_counts = {}

    logger.info("[Step 4] SPL assembled (%d chars)", len(spl_text))

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

    # ── Cleanup ───────────────────────────────────────────────────────────────
    client.close()

    logger.info("=== pipeline complete: %s ===", graph.skill_id)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Async helper functions
# ─────────────────────────────────────────────────────────────────────────────

async def _generate_api_definitions_async(
    tools: list,
    client: LLMClient,
) -> APISymbolTable:
    """
    Async version of API generation.
    Generates API definitions for all tools in parallel.
    """
    from pipeline.llm_steps.step1_5_api_generation import (
        _generate_single_api_async,
        build_api_symbol_table,
    )

    if not tools:
        logger.info("[Step 1.5] No tools to generate APIs for")
        return APISymbolTable(apis={})

    logger.info("[Step 1.5] Generating API definitions for %d tools (async)...", len(tools))

    # Launch all API generation tasks in parallel
    tasks = [
        asyncio.create_task(_generate_single_api_async(client, tool))
        for tool in tools
    ]

    # Collect results
    api_specs = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and build table
    apis = {}
    for tool, spec in zip(tools, api_specs):
        if isinstance(spec, Exception):
            logger.error("[Step 1.5] Failed to generate API for %s: %s", tool.name, spec)
        elif spec:
            apis[tool.name] = spec

    logger.info("[Step 1.5] Generated %d/%d API definitions", len(apis), len(tools))
    return build_api_symbol_table(apis)


async def _run_step3b_async(
    bundle,
    entities,
    tools,
    client: LLMClient,
):
    """Async wrapper for Step 3B."""
    # Step 3B is currently sync, run in executor to not block
    entity_ids = [e.entity_id for e in entities]
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: run_step3b_workflow_analysis(
            bundle=bundle,
            entity_ids=entity_ids,
            tools=tools,
            client=client,
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# Output writer
# ─────────────────────────────────────────────────────────────────────────────

def _write_final_output(spl_spec: SPLSpec, output_dir: str) -> None:
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
