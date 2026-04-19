"""skill-to-CNL-P pipeline orchestrator.

Wires all stages together in the correct order and handles:
- Checkpoint saving (save intermediate results to disk to enable rerun from any stage)
- Capability profile injection (optional environment model for Step 2B)
- Consolidated logging and token usage reporting
- Maximum parallelism between Step 3 and Step 4

Pipeline stage order:
P1 (code) → FileReferenceGraph
P2 (code) → FileRoleMap
P3 (code+LLM) → SkillPackage
Step 1 (LLM) → SectionBundle
Step 1.5 (LLM) → API definitions
Step 3-W (LLM) → Workflow steps (structure only)
Step 3-IO (LLM) → Global I/O analysis + type registry
Step 3-T (code) → TYPES declarations
Step 4 (LLM parallel) → S4A/B/C/D/E/F → final SPL
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from pipeline.llm_client import LLMClient, LLMConfig, SessionUsage, StepLLMConfig
from models.data_models import PipelineResult, StructuredSpec
from pipeline.llm_steps import (
    run_step1_structure_extraction,
    run_step4_spl_emission,
    run_step4_spl_emission_parallel,
)
from pipeline.llm_steps.step3 import (
    run_step3_full_sync,  # Step 3-W → Step 3-IO → Step 3-T (sequential)
)
from pipeline.llm_steps.step1_5_api_generation import (
    generate_api_definitions,
    generate_unified_api_definitions,  # NEW: Unified API generation
)
from pipeline.llm_steps.step4_spl_emission.substep_calls import (
    _call_4a,
    _call_4b,
    _call_4c,
    _call_4e,
    _call_4f,
    _call_s0,
)
from pipeline.llm_steps.step4_spl_emission.symbol_table import (
    _extract_symbol_table,
    _format_symbol_table,
)
from pipeline.llm_steps.step4_spl_emission.inputs import _prepare_step4_inputs_parallel
from pipeline.llm_steps.step4_spl_emission.assembly import _assemble_spl
from pipeline.llm_steps.step4_spl_emission.utils import _build_review_summary
from pipeline.llm_steps.step4_spl_emission.s4c_from_registry import (
    generate_variables_files_from_registry,
)
from pre_processing.p1_reference_graph import build_reference_graph  # type: ignore
from pre_processing.p2_file_roles import assign_file_priorities  # type: ignore
from pre_processing.p3_assembler import assemble_skill_package
from pipeline.spl_formatter import format_spl_indentation
from pipeline.llm_steps.step4_spl_emission.nesting_validation import (
    validate_and_fix_worker_nesting,
)
from models.data_models import EntitySpec
from models.step3_types import GlobalVarRegistry, VarSpec

logger = logging.getLogger(__name__)


class PipelineConfig:
    """Configuration for a pipeline run."""

    def __init__(
        self,
        skill_root: str,
        output_dir: str,
        llm_config: LLMConfig,
        step_llm_config: Optional[StepLLMConfig] = None,
        save_checkpoints: bool = True,
        resume_from: Optional[str] = None,
        use_new_step3: bool = False,
    ):
        self.skill_root = skill_root
        self.output_dir = output_dir
        self.llm_config = llm_config
        self.step_llm_config = step_llm_config
        self.save_checkpoints = save_checkpoints
        self.resume_from = resume_from
        self.use_new_step3 = use_new_step3


def _to_jsonable(obj: object) -> object:
    """Recursively convert dataclasses / enums to JSON-serializable objects."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}  # type: ignore[arg-type]
    if isinstance(obj, list):
        return [_to_jsonable(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def _convert_registry_to_entities(registry: GlobalVarRegistry) -> list[EntitySpec]:
    """
    Convert GlobalVarRegistry to list of EntitySpec for S4C compatibility.

    This bridges the gap between the new Step 3 architecture (W→IO→T)
    and the old S4C input format that expects EntitySpec objects.
    """
    entities: list[EntitySpec] = []

    # Convert variables (non-file) to EntitySpec
    for var_name, var_spec in registry.variables.items():
        entity = EntitySpec(
            entity_id=var_name,
            kind="Run",  # Default kind for variables
            type_name=var_spec.type_expr.to_spl(),
            schema_notes=var_spec.description,
            provenance_required=False,
            provenance="EXPLICIT",
            source_text=f"Extracted from Step 3-IO analysis",
            is_file=False,
            file_path="",
            from_omit_files=False,
        )
        entities.append(entity)

    # Convert files to EntitySpec
    for var_name, var_spec in registry.files.items():
        entity = EntitySpec(
            entity_id=var_name,
            kind="Artifact",
            type_name=var_spec.type_expr.to_spl(),
            schema_notes=var_spec.description,
            provenance_required=False,
            provenance="EXPLICIT",
            source_text=f"Extracted from Step 3-IO analysis",
            is_file=True,
            file_path=var_name,  # Use var_name as file path
            from_omit_files=False,
        )
        entities.append(entity)

    return entities


def _step_model(config: PipelineConfig, step_name: str) -> str | None:
    """Look up the model for a given step name, or None to use the default."""
    if config.step_llm_config is not None:
        return config.step_llm_config.get_model(step_name, config.llm_config.model)
    return None


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

    logger.info("=== skill-to-CNL-P pipeline start: %s ===", config.skill_root)

    # ── P1: Reference Graph Builder (code) ───────────────────────────────────
    logger.info("[P1] building reference graph...")
    graph = build_reference_graph(config.skill_root)
    logger.info("[P1] found %d files, %d doc edges", len(graph.nodes), len(graph.edges))

    # ── P2: File Role Resolver (rule-based, no LLM) ───────────────────────────────
    logger.info("[P2] assigning file priorities (rule-based)...")
    file_role_map = assign_file_priorities(graph=graph)

    # ── P3: Skill Package Assembler (code + P2.5 API analysis merged) ──────────────
    logger.info("[P3] assembling skill package with P2.5 API analysis...")
    package = assemble_skill_package(
        graph=graph,
        file_role_map=file_role_map,
        client=client,  # P2.5 uses this for script and code snippet analysis
    )
    logger.info("[P3] assembled with %d pre-extracted tools", len(package.tools))
    if getattr(package, 'unified_apis', None):
        logger.info("[P3] extracted %d unified APIs", len(package.unified_apis))

    # ── Step 1: Structure Extraction (LLM) ───────────────────────────────────
    logger.info("[Step 1] extracting structure...")
    bundle, step1_network_apis = run_step1_structure_extraction(
        package=package, client=client, model=_step_model(config, "step1_structure_extraction")
    )

    # Merge network APIs from Step 1 into package.tools
    package.tools.extend(step1_network_apis)
    logger.info("[Tools] total merged tools: %d", len(package.tools))

    # ── Step 1.5: API Definition Generation ──────────────────────────────────
    # Generate API definitions for all tools (moved from Step 4D for earlier availability)
    logger.info("[Step 1.5] generating API definitions...")

    # Check if we have unified APIs from P3 (new unified API extraction)
    if getattr(package, 'unified_apis', None):
        logger.info("[Step 1.5] using unified API extraction (%d unified APIs)", len(package.unified_apis))
        api_table = generate_unified_api_definitions(
            unified_apis=package.unified_apis,
            client=client,
            max_workers=4,
            model=_step_model(config, "step1_5_api_generation"),
        )
    else:
        # Fall back to legacy tool-based API generation
        logger.info("[Step 1.5] using legacy tool-based API generation (%d tools)", len(package.tools))
        api_table = generate_api_definitions(
            tools=package.tools,
            client=client,
            max_workers=4,
            model=_step_model(config, "step1_5_api_generation"),
        )

    logger.info("[Step 1.5] generated %d API definitions", len(api_table.apis))

    # ── Step 3: New Architecture (W → IO → T, sequential) ──────────────────
    logger.info("[Step 3] Running new Step 3 architecture (W → IO → T)...")

    # Run Step 3-W → Step 3-IO → Step 3-T sequentially
    step3_result = run_step3_full_sync(
        workflow_section=bundle.to_text(["WORKFLOW"]),
        tools_section=bundle.to_text(["TOOLS"]),
        evidence_section=bundle.to_text(["EVIDENCE"]),
        artifacts_section=bundle.to_text(["ARTIFACTS"]),
        available_tools=[{"name": t.name, "api_type": t.api_type} for t in package.tools],
        client=client,
        model=_step_model(config, "step3") or config.llm_config.model,
    )

    # Convert WorkflowStepRaw to WorkflowStepSpec for Step 4 compatibility
    from models.data_models import WorkflowStepSpec, AlternativeFlowSpec, ExceptionFlowSpec, FlowStep
    from models.step3_types import WorkflowStepRaw

    workflow_steps = [
        WorkflowStepSpec(
            step_id=s.step_id,
            description=s.description,
            prerequisites=[],  # Will be populated from step_io_specs
            produces=[],  # Will be populated from step_io_specs
            action_type=s.action_type,
            tool_hint=s.tool_hint,
            is_validation_gate=s.is_validation_gate,
            source_text=s.source_text,
        )
        for s in step3_result["workflow_steps"]
    ]
    alternative_flows = step3_result.get("alternative_flows", [])
    exception_flows = step3_result.get("exception_flows", [])

    logger.info("[Step 3-W] extracted %d workflow steps", len(workflow_steps))
    logger.info("[Step 3-IO] analyzed %d step I/O specs, %d variables, %d files",
        len(step3_result["step_io_specs"]),
        len(step3_result["global_registry"].variables),
        len(step3_result["global_registry"].files))
    logger.info("[Step 3-T] generated %d type declarations", len(step3_result.get("declared_names", [])))

    # Get type_registry and types_spl for S4C and final SPL
    type_registry = step3_result.get("type_registry", {})
    types_spl = step3_result.get("types_spl", "")
    global_registry = step3_result["global_registry"]

    # Convert GlobalVarRegistry to EntitySpec list for S4C compatibility
    # This bridges the gap between new Step 3 architecture and old S4C input format
    entities = _convert_registry_to_entities(global_registry)
    logger.info("[Step 3→4] Converted registry to %d entities (%d vars, %d files)",
        len(entities), len(global_registry.variables), len(global_registry.files))

    # ── Step 4: Parallel execution with dependency-driven scheduling ─────────
    logger.info("[Step 4] launching parallel sub-steps...")

    # Prepare inputs for Step 4 (using new Step 3 outputs)
    s4a_in, s4b_in, s4c_in, s4d_in, s4e_in, s4f_in = _prepare_step4_inputs_parallel(
        bundle, entities, workflow_steps, alternative_flows, exception_flows, type_registry
    )

    # Phase 1: Launch S4C (needs type_registry from Step 3-T)
    with ThreadPoolExecutor(max_workers=2) as phase2_pool:
        future_4c = phase2_pool.submit(_call_4c, client, s4c_in, model=_step_model(config, "step4c_variables_files"))

        # Wait for S4C
        block_4c = future_4c.result()

        # Extract symbol table from S4C output
        symbol_table = _extract_symbol_table(block_4c)
        symbol_table_text = _format_symbol_table(symbol_table)
        logger.info("[Step 4] Symbol table - types: %d, variables: %d, files: %d",
            len(symbol_table.get("types", [])),
            len(symbol_table["variables"]),
            len(symbol_table["files"]))

        # Re-prepare inputs with complete workflow info
        s4a_inputs, s4b_inputs, _, s4d_inputs, s4e_inputs, s4f_inputs = _prepare_step4_inputs_parallel(
            bundle,
            entities,
            workflow_steps,
            alternative_flows,
            exception_flows,
            type_registry,
        )

    # Prepare API SPL block from pre-generated API table (Step 1.5)
    from pipeline.llm_steps.step1_5_api_generation import merge_api_spl_blocks
    block_4d = merge_api_spl_blocks(api_table)
    logger.info("[Step 4D] prepared APIs block (%d chars)", len(block_4d))

    # Phase 3: Complete Line 2 (S4A, S4B) and prepare S4E/S4F
    with ThreadPoolExecutor(max_workers=3) as phase3_pool:
        # Line 2 continued: S4A and S4B
        future_4a = phase3_pool.submit(_call_4a, client, s4a_inputs, symbol_table_text, model=_step_model(config, "step4a_persona"))
        future_4b = phase3_pool.submit(_call_4b, client, s4b_inputs, symbol_table_text, model=_step_model(config, "step4b_constraints"))
        
        # S0: Generate DEFINE_AGENT header
        # FIX: Use package.skill_name if available, otherwise fall back to graph.skill_id
        # This ensures skill_id is never "unknown" or empty
        effective_skill_id = getattr(package, 'skill_name', None) or getattr(graph, 'skill_id', None) or Path(config.skill_root).name
        logger.info("[S0] Using skill_id: %s", effective_skill_id)
        
        intent_text = bundle.to_text(["INTENT"])
        notes_text = bundle.to_text(["NOTES"])
        future_s0 = phase3_pool.submit(_call_s0, client, effective_skill_id, intent_text, notes_text, model=_step_model(config, "step0_define_agent"))
        
    # Collect S4A, S4B results
    block_4a = future_4a.result()
    block_4b = future_4b.result()
    block_s0 = future_s0.result()

    # Phase 4: S4E (merge point)
    logger.info("[Step 4] Phase 4: S4E (worker)...")
    block_4e_original = _call_4e(client, s4e_inputs, symbol_table_text, block_4d, model=_step_model(config, "step4e_worker"))

    # Phase 4.5: S4E1/S4E2 - Validate and fix nested BLOCK structures
    block_4e, nesting_result = validate_and_fix_worker_nesting(client, block_4e_original, model=_step_model(config, "step4e1_nesting_fix"))

    if nesting_result.get("has_violations", False):
        logger.info("[Step 4] Phase 4.5: S4E1 detected %d violations, S4E2 fixed them",
                    len(nesting_result.get("violations", [])))
    else:
        logger.info("[Step 4] Phase 4.5: S4E1 - no nested BLOCK violations found")

    # Phase 5: S4F (final)
    block_4f = ""
    if s4f_inputs["has_examples"]:
        logger.info("[Step 4] Phase 5: S4F (examples)...")
        block_4f = _call_4f(client, s4f_inputs, block_4e, model=_step_model(config, "step4f_examples"))

    # Assemble final SPL (with types_spl from Step 3-T)
    spl_text = _assemble_spl(
        graph.skill_id, block_s0, block_4a, block_4b, block_4c, block_4d, block_4e, block_4f, types_spl
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

    # Write final output
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    spl_path = output_dir / f"{graph.skill_id}.spl"
    spl_path.write_text(spl_text, encoding="utf-8")
    logger.info("[Output] SPL written to %s", spl_path)

    # Build StructuredSpec for backward compatibility with PipelineResult
    from models.data_models import StructuredSpec, EntitySpec
    structured_spec = StructuredSpec(
        entities=[],  # New architecture doesn't produce EntitySpec
        workflow_steps=workflow_steps,
        alternative_flows=alternative_flows,
        exception_flows=exception_flows,
    )

    # Return final result
    result = PipelineResult(
        skill_id=graph.skill_id,
        graph=graph,
        file_role_map=file_role_map,
        package=package,
        section_bundle=bundle,
        structured_spec=structured_spec,
        spl_spec=spl_spec,
    )

    # Log token usage
    total = session_usage.total
    logger.info("=== skill-to-CNL-P pipeline complete: %s ===", config.skill_root)
    logger.info("[Tokens] total: %d (input: %d, output: %d)", total.total, total.input_tokens, total.output_tokens)

    return result
