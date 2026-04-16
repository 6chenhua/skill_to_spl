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

from pipeline.llm_client import LLMClient, LLMConfig, SessionUsage, StepLLMConfig
from models.data_models import PipelineResult, StructuredSpec
from pipeline.llm_steps import (
    run_step1_structure_extraction,
    run_step3a_entity_extraction,
    run_step3b_workflow_analysis,
    run_step4_spl_emission,
    run_step4_spl_emission_parallel,
    run_step3_full,  # NEW: W→IO→T orchestrator
)
from pipeline.llm_steps.step1_5_api_generation import (
    generate_api_definitions,
    merge_api_spl_blocks,
)
from pre_processing.p1_reference_graph import build_reference_graph
from pre_processing.p2_file_roles import assign_file_priorities
from pre_processing.p3_assembler import assemble_skill_package
from pipeline.llm_steps.step4_spl_emission import (
    _call_4a, _call_4b, _call_4c, _call_4d, _call_4e, _call_4f, _call_s0,
    _extract_symbol_table, _format_symbol_table, _prepare_step4_inputs_parallel,
    _assemble_spl, _build_review_summary,
    validate_and_fix_worker_nesting,
)

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
            Defaults to <skill_root>/.cnlp_output/
        llm_config: LLM model and retry settings (used for steps without overrides).
        step_llm_config: Optional per-step model overrides. Allows different
            steps to use different models.
        save_checkpoints: If True, save each stage output as JSON to output_dir.
        resume_from: If set, load checkpoints up to (but not including) this
            stage and resume from there. Useful for reruns after
            prompt changes.
            Values: "p2" | "step1" | "step3" | "step4"
    """

    def __init__(
        self,
        skill_root: str,
        output_dir: Optional[str] = None,
        llm_config: Optional[LLMConfig] = None,
        step_llm_config: Optional[StepLLMConfig] = None,
        save_checkpoints: bool = True,
        resume_from: Optional[str] = None,
        use_new_step3: bool = True,  # NEW: Enable new Step 3 (W→IO→T)
    ):
        self.skill_root = skill_root
        self.output_dir = output_dir or str(Path(skill_root) / ".cnlp_output")
        self.llm_config = llm_config or LLMConfig()
        self.step_llm_config = step_llm_config
        self.save_checkpoints = save_checkpoints
        self.resume_from = resume_from
        self.use_new_step3 = use_new_step3  # NEW


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
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()} # type: ignore[arg-type]
    if isinstance(obj, list):
        return [_to_jsonable(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if hasattr(obj, "value"): # Enums
        return obj.value
    return obj


def _step_model(config: PipelineConfig, step_name: str) -> str | None:
    """Look up the model for a given step name, or None to use the default."""
    if config.step_llm_config is not None:
        return config.step_llm_config.get_model(step_name, config.llm_config.model)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline runner
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

    # ── P2: File Role Resolver (rule-based, no LLM) ───────────────────────────────
    logger.info("[P2] assigning file priorities (rule-based)...")
    file_role_map = assign_file_priorities(graph=graph)
    ckpt.save("p2_file_role_map", file_role_map)

    # ── P3: Skill Package Assembler (code + P2.5 API analysis merged) ──────────────
    logger.info("[P3] assembling skill package with P2.5 API analysis...")
    package = assemble_skill_package(
        graph=graph,
        file_role_map=file_role_map,
        client=client,  # P2.5 uses this for script and code snippet analysis
    )
    ckpt.save("p3_package", {"skill_id": package.skill_id, "merged_doc_chars": len(package.merged_doc_text), "tools_count": len(package.tools)})
    logger.info("[P3] assembled with %d pre-extracted tools (scripts + code snippets)", len(package.tools))

    # ── Step 1: Structure Extraction (LLM) ───────────────────────────────────
    logger.info("[Step 1] extracting structure...")
    bundle, step1_network_apis = run_step1_structure_extraction(package=package, client=client, model=_step_model(config, "step1_structure_extraction"))
    ckpt.save("step1_bundle", bundle)

    # Merge network APIs from Step 1 into package.tools
    package.tools.extend(step1_network_apis)
    logger.info("[Tools] total merged tools: %d", len(package.tools))

    # ── Step 1.5: API Definition Generation ──────────────────────────────────
    # Generate API definitions for all tools (moved from Step 4D for earlier availability)
    logger.info("[Step 1.5] generating API definitions...")
    api_table = generate_api_definitions(
        tools=package.tools,
        client=client,
        max_workers=4,
        model=_step_model(config, "step1_5_api_generation"),
    )
    ckpt.save("step1_5_api_table", {
        "api_count": len(api_table.apis),
        "api_names": list(api_table.apis.keys()),
    })
    logger.info("[Step 1.5] generated %d API definitions", len(api_table.apis))

# ── Step 3 & 4: Parallel execution with dependency-driven scheduling ───
    #
    # NEW: Step 3 (W→IO→T) replaces old Step 3A + Step 3B
    # Dependency graph:
    # Step 3 (W→IO→T) ──┬─→ TYPES + Global Registry
    #                   │     ↓
    #                   ├─→ S4C (variables/files with types)
    #                   │     ↓
    #                   │   symbol_table → (S4A || S4B)
    #                   │
    #                   └─→ workflow/flows ──→ S4D
    #                                          │
    # S4E ←────────────────────────────────────┘
    #   ↓
    # S4F
    #
    # Phase 1: NEW Step 3 (W→IO→T) - unified entity, workflow, and type extraction

    if config.use_new_step3:
        # NEW: Use unified Step 3 (W→IO→T)
        logger.info("[Step 3] running unified W→IO→T extraction (NEW)...")
        
        import asyncio
        step3_result = asyncio.run(run_step3_full(
            workflow_section=bundle.to_text(["WORKFLOW"]),
            tools_section=bundle.to_text(["TOOLS"]),
            evidence_section=bundle.to_text(["EVIDENCE"]),
            artifacts_section=bundle.to_text(["ARTIFACTS"]),
            available_tools=[{"name": t.name, "api_type": t.api_type} for t in package.tools],
            client=client,
            model=_step_model(config, "step3")
        ))
        
        # Convert new Step 3 output to old StructuredSpec format
        from models.data_models import EntitySpec, WorkflowStepSpec, AlternativeFlowSpec, ExceptionFlowSpec
        
        # Build entities from global registry
        entities = []
        for var_name, var_spec in step3_result["global_registry"].variables.items():
            entities.append(EntitySpec(
                entity_id=var_name,
                type_name=var_spec.type_expr.to_spl(),
                kind="Variable",
                is_file=var_spec.is_file,
                schema_notes=var_spec.description,
                provenance_required=True,
                provenance="EXPLICIT",
                source_text=f"Variable from global registry: {var_name}",
            ))
        for var_name, var_spec in step3_result["global_registry"].files.items():
            entities.append(EntitySpec(
                entity_id=var_name,
                type_name=var_spec.type_expr.to_spl(),
                kind="Artifact",
                is_file=True,
                schema_notes=var_spec.description,
                provenance_required=True,
                provenance="EXPLICIT",
                source_text=f"File artifact from global registry: {var_name}",
            ))

        # Build workflow steps from Step 3-W output + I/O specs
        workflow_steps = []
        for step_raw in step3_result["workflow_steps"]:
            io_spec = step3_result["step_io_specs"].get(step_raw.step_id)
            if io_spec:
                prerequisites = list(io_spec.prerequisites.keys())
                produces = list(io_spec.produces.keys())
            else:
                prerequisites = []
                produces = []
            workflow_steps.append(WorkflowStepSpec(
                step_id=step_raw.step_id,
                description=step_raw.description,
                action_type=step_raw.action_type,
                tool_hint=step_raw.tool_hint,
                is_validation_gate=step_raw.is_validation_gate,
                prerequisites=prerequisites,
                produces=produces,
                source_text=step_raw.source_text,
            ))

        structured_spec = StructuredSpec(
            entities=entities,
            workflow_steps=workflow_steps,
            alternative_flows=step3_result.get("alternative_flows", []),
            exception_flows=step3_result.get("exception_flows", []),
        )
        
        # Save TYPES block separately for Step 4
        types_spl = step3_result.get("types_spl", "")
        type_registry = step3_result.get("type_registry", {})
        
        ckpt.save("step3_new_output", step3_result)
        logger.info("[Step 3] extracted %d entities, %d workflow steps", len(entities), len(workflow_steps))
        logger.info("[Step 3] generated %d type declarations", len(type_registry))
        
        # NEW: Generate [DEFINE_VARIABLES:] and [DEFINE_FILES:] from Step 3 registry
        logger.info("[Step 4C] generating variables and files from Step 3 registry...")
        
        from pipeline.llm_steps.step4_spl_emission.s4c_from_registry import generate_variables_files_from_registry
        
        # Generate blocks directly from registry
        block_4c = generate_variables_files_from_registry(
            registry=step3_result["global_registry"],
            types_spl=types_spl if types_spl else None
        )
        
        # Save S4C output
        ckpt.save("step4c_variables_files", {"variables_files_spl": block_4c, "types_spl": types_spl})
        logger.info("[Step 4C] generated variables/files block (%d chars)", len(block_4c))

    else:
        # LEGACY: Use old Step 3A + Step 3B
        logger.info("[Step 3A] extracting entities...")
        entities = run_step3a_entity_extraction(bundle=bundle, client=client, model=_step_model(config, "step3a_entity_extraction"))
        
        # Initialize types_spl for legacy mode
        types_spl = ""
        type_registry = {}

        # Phase 2: Parallel lines
        # Line 1: Step 3B (workflow analysis) + S4D (APIs)
        # Line 2: S4C (variables/files) → S4A + S4B
        logger.info("[Parallel] launching Line 1 (3B→S4D) and Line 2 (S4C→S4A/B)...")

        with ThreadPoolExecutor(max_workers=2) as phase2_pool:
            # Line 1: Step 3B (needs entity_ids from 3A and tools from P2.5/Step 1)
            entity_ids = [e.entity_id for e in entities]
            future_3b = phase2_pool.submit(
                run_step3b_workflow_analysis,
                bundle=bundle,
                entity_ids=entity_ids,
                tools=package.tools,
                client=client,
                model=_step_model(config, "step3b_workflow_analysis"),
            )

            # Line 2: S4C (needs entities from 3A)
            # We'll handle S4A and S4B after S4C completes
            # Prepare inputs for Line 2 (we need workflow info for S4E later, prepare minimal)
            # We'll launch S4C now, then S4A/S4B when symbol_table is ready
            s4a_in, s4b_in, s4c_in, s4d_in, s4e_in, s4f_in = _prepare_step4_inputs_parallel(
                bundle, entities, [], [], [] # workflow/flows will be filled later
            )

            future_4c = phase2_pool.submit(_call_4c, client, s4c_in, model=_step_model(config, "step4c_variables_files"))

            # Wait for both lines to complete
            structured_spec_partial = future_3b.result() # Has workflow_steps, flows, but empty entities
            block_4c = future_4c.result()

            # Save S4C output (variables and files)
            ckpt.save("step4c_variables_files", {"variables_files_spl": block_4c})

            # Build complete StructuredSpec
            structured_spec = StructuredSpec(
                entities=entities,
                workflow_steps=structured_spec_partial.workflow_steps,
                alternative_flows=structured_spec_partial.alternative_flows,
                exception_flows=structured_spec_partial.exception_flows,
            )
            
            types_spl = ""  # No TYPES in legacy mode
            type_registry = {}
        
    ckpt.save("step3_structured_spec", structured_spec)

    # Phase 3: Complete Line 2 (S4A, S4B) and prepare S4D/S4E/S4F
    logger.info("[Step 4] Phase 3: completing S4A/S4B and running S4D/E/F...")

    # block_4c is already set in both paths:
    # - New path: generated from registry in Step 3
    # - Legacy path: from S4C future result
    # DO NOT reset it here!

    # Extract symbol table from S4C output (or generate from new Step 3 registry)
    if config.use_new_step3:
        # Generate symbol table from block_4c (which was generated from Step 3 registry)
        symbol_table = _extract_symbol_table(
            block_4c,  # Use the generated block
            types_spl=types_spl
        )
        # Add types to symbol table
        if types_spl:
            import re
            type_matches = re.findall(
                r'^\s*(?:"[^"]*"\s*)?([A-Z][a-zA-Z0-9]*)\s*=',
                types_spl,
                re.MULTILINE
            )
            symbol_table["types"] = type_matches
    else:
        # Legacy: extract from S4C block
        symbol_table = _extract_symbol_table(block_4c)
    
    symbol_table_text = _format_symbol_table(symbol_table)
    logger.info("[Step 4] Symbol table — types: %d, variables: %d, files: %d",
    len(symbol_table.get("types", [])),
    len(symbol_table.get("variables", [])),
    len(symbol_table.get("files", [])))
    
    # Re-prepare inputs with complete workflow info
    s4a_inputs, s4b_inputs, _, s4d_inputs, s4e_inputs, s4f_inputs = _prepare_step4_inputs_parallel(
        bundle,
        entities,
        structured_spec.workflow_steps,
        structured_spec.alternative_flows,
        structured_spec.exception_flows,
    )
    
    # Prepare API SPL block from pre-generated API table (Step 1.5)
    block_4d = merge_api_spl_blocks(api_table)

    with ThreadPoolExecutor(max_workers=3) as phase3_pool:
        # Line 2 continued: S4A and S4B (parallel, only need symbol_table)
        future_4a = phase3_pool.submit(_call_4a, client, s4a_inputs, symbol_table_text, model=_step_model(config, "step4a_persona"))
        future_4b = phase3_pool.submit(_call_4b, client, s4b_inputs, symbol_table_text, model=_step_model(config, "step4b_constraints"))

        # S0: Generate DEFINE_AGENT header (parallel, only needs bundle)
        intent_text = bundle.to_text(["INTENT"])
        notes_text = bundle.to_text(["NOTES"])
        future_s0 = phase3_pool.submit(_call_s0, client, graph.skill_id, intent_text, notes_text, model=_step_model(config, "step0_define_agent"))

        # Collect S4A, S4B results
        block_4a = future_4a.result()
        block_4b = future_4b.result()

        # Wait for S0
        block_s0 = future_s0.result()

        # Save S4A, S4B outputs
        ckpt.save("step4a_persona", {"persona_spl": block_4a})
        ckpt.save("step4b_constraints", {"constraints_spl": block_4b})

        # Save S4D output
        ckpt.save("step4d_apis", {"apis_spl": block_4d})

        # Save S0 output
        ckpt.save("step0_define_agent", {"define_agent_header": block_s0})
    
        # Phase 4: S4E (merge point - needs symbol_table from Line 2 and apis_spl from Line 1)
        logger.info("[Step 4] Phase 4: S4E (worker)...")
        block_4e_original = _call_4e(client, s4e_inputs, symbol_table_text, block_4d, model=_step_model(config, "step4e_worker"))
        ckpt.save("step4e_worker_original", {"worker_spl": block_4e_original})

        # Phase 4.5: S4E1/S4E2 - Validate and fix nested BLOCK structures
        block_4e, nesting_result = validate_and_fix_worker_nesting(client, block_4e_original, model=_step_model(config, "step4e1_nesting_fix"))
        
        # Save S4E1 detection result
        ckpt.save("step4e1_nesting_detection", nesting_result)
        
        # Save S4E2 result if violations were found and fixed
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

        # Phase 5: S4F (final)
        block_4f = ""
        if s4f_inputs["has_examples"]:
            logger.info("[Step 4] Phase 5: S4F (examples)...")
            block_4f = _call_4f(client, s4f_inputs, block_4e, model=_step_model(config, "step4f_examples"))
            # Save S4F output (examples)
            ckpt.save("step4f_examples", {"examples_spl": block_4f})
    
    # Assemble final SPL
    from pipeline.llm_steps.step4_spl_emission import _assemble_spl, _build_review_summary
    
    # Ensure block_4c is defined (for new Step 3 path)
    if config.use_new_step3:
        # block_4c should already be generated in new Step 3 path
        pass  # block_4c is already set
    
    spl_text = _assemble_spl(
        graph.skill_id, block_s0, block_4a, block_4b, block_4c, block_4d, block_4e, block_4f
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

    # ── Cleanup HTTP clients to prevent Windows asyncio warnings ─────────────
    client.close()

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
