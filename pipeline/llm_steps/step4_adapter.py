"""
Step 4 Adapter for New Step 3 Output
=====================================

Bridges new Step 3 output (Step3WOutput, Step3IOOutput, Step3TOutput)
with existing Step 4 infrastructure.

This allows gradual migration while maintaining backward compatibility.
"""

from __future__ import annotations

import logging
from typing import Any

from models.data_models import (
    AlternativeFlowSpec,
    ExceptionFlowSpec,
    SectionBundle,
    SPLSpec,
    ToolSpec,
)
from models.step3_types import (
    GlobalVarRegistry,
    StepIOSpec,
    Step3IOOutput,
    Step3TOutput,
    Step3WOutput,
    WorkflowStepRaw,
)
from pipeline.llm_client import LLMClient
from pipeline.llm_steps.step4_spl_emission.orchestrator import run_step4_spl_emission
from pipeline.llm_steps.step4_spl_emission.inputs_v2 import _prepare_step4_inputs_new
from pipeline.llm_steps.step4_spl_emission.symbol_table import _extract_symbol_table, _format_symbol_table
from pipeline.llm_steps.step4_spl_emission.assembly import _assemble_spl
from pipeline.llm_steps.step4_spl_emission.utils import _build_review_summary

logger = logging.getLogger(__name__)


def run_step4_with_new_step3(
    bundle: SectionBundle,
    step3w_output: Step3WOutput,
    step3io_output: Step3IOOutput,
    step3t_output: Step3TOutput,
    tools: list[ToolSpec],
    skill_id: str,
    client: LLMClient,
    model: str | None = None,
) -> SPLSpec:
    """
    Run Step 4 with new Step 3 output format.
    
    Args:
        bundle: SectionBundle with source sections
        step3w_output: Step3-W output (workflow steps)
        step3io_output: Step3-IO output (I/O specs + registry)
        step3t_output: Step3-T output (TYPES block)
        tools: Tool specifications
        skill_id: Skill identifier
        client: LLM client
        model: Model name
        
    Returns:
        SPLSpec with generated SPL
    """
    logger.info("[Step 4 Adapter] Running with new Step 3 output")
    
    # For now, convert new format to old format that Step 4 expects
    # This allows gradual migration
    
    # Prepare inputs with new format
    s4a_inputs, s4b_inputs, s4c_inputs, s4d_inputs, s4e_inputs, s4f_inputs, types_inputs = (
        _prepare_step4_inputs_new(
            bundle=bundle,
            global_registry=step3io_output.global_registry,
            step_io_specs=step3io_output.step_io_specs,
            workflow_steps=step3w_output.workflow_steps,
            alternative_flows=step3w_output.alternative_flows,
            exception_flows=step3w_output.exception_flows,
            types_spl=step3t_output.types_spl,
            type_registry=step3t_output.type_registry,
            tools=tools,
        )
    )
    
    # Import and call Step 4 sub-steps directly with new inputs
    from pipeline.llm_steps.step4_spl_emission.substep_calls import (
        _call_4a, _call_4b, _call_4c, _call_4d, _call_4e, _call_4f
    )
    from concurrent.futures import ThreadPoolExecutor
    
    with ThreadPoolExecutor(max_workers=4) as pool:
        # Phase 1: S4C and S4D in parallel
        logger.info("[Step 4] Phase 1: Launching S4C and S4D")
        
        future_4c = pool.submit(_call_4c, client, s4c_inputs, model=model)
        
        # S4D for tools
        tools_list = s4d_inputs.get("tools_list", [])
        if s4d_inputs.get("has_tools") and tools_list:
            logger.info(f"[Step 4] Launching S4D with {len(tools_list)} tools")
            futures_4d = [
                pool.submit(_call_4d, client, tool, model=model) 
                for tool in tools_list
            ]
        else:
            logger.info("[Step 4] No tools found, S4D skipped")
            futures_4d = []
        
        # Phase 2: When S4C completes, extract symbol table
        logger.info("[Step 4] Phase 2: Waiting for S4C")
        block_4c = future_4c.result()
        
        # Extract symbol table WITH types
        symbol_table = _extract_symbol_table(
            block_4c, 
            types_spl=types_inputs.get("types_spl", "")
        )
        symbol_table_text = _format_symbol_table(symbol_table)
        
        logger.info(
            f"[Step 4] Symbol table: {len(symbol_table.get('types', []))} types, "
            f"{len(symbol_table.get('variables', []))} vars, "
            f"{len(symbol_table.get('files', []))} files"
        )
        
        # Phase 2b: Launch S4A and S4B
        logger.info("[Step 4] Launching S4A and S4B")
        s4a_inputs["symbol_table"] = symbol_table_text
        s4b_inputs["symbol_table"] = symbol_table_text
        
        future_4a = pool.submit(_call_4a, client, s4a_inputs, model=model)
        future_4b = pool.submit(_call_4b, client, s4b_inputs, model=model)
        
        # Phase 3: Wait for S4D and build API block
        logger.info("[Step 4] Phase 3: Collecting S4D results")
        apis_spl = ""
        if futures_4d:
            api_results = [f.result() for f in futures_4d]
            apis_spl = "\n\n".join(api_results)
            logger.info(f"[Step 4] Collected {len(api_results)} API declarations")
        
        # Phase 4: Launch S4E (needs symbol_table + apis_spl)
        logger.info("[Step 4] Phase 4: Launching S4E")
        s4e_inputs["symbol_table"] = symbol_table_text
        s4e_inputs["apis_spl"] = apis_spl
        
        block_4e = _call_4e(client, s4e_inputs, model=model)
        
        # Phase 5: Launch S4F (needs worker_spl)
        logger.info("[Step 4] Phase 5: Launching S4F")
        s4f_inputs["worker_spl"] = block_4e
        
        block_4f = _call_4f(client, s4f_inputs, model=model)
    
    # Phase 6: Assemble final SPL
    logger.info("[Step 4] Phase 6: Assembling final SPL")
    
    spl_blocks = {
        "persona_audience_concepts": block_4a,
        "constraints": block_4b,
        "variables_files_types": block_4c,  # Now includes TYPES
        "apis": apis_spl,
        "worker": block_4e,
        "examples": block_4f,
    }
    
    spl_text = _assemble_spl(spl_blocks)
    review_summary = _build_review_summary(spl_blocks)
    
    logger.info("[Step 4] Complete - SPL generated")
    
    return SPLSpec(
        skill_id=skill_id,
        spl_text=spl_text,
        review_summary=review_summary,
        clause_counts={}  # TODO: Calculate from output
    )


def convert_step3_old_to_new(
    workflow_steps: list,
    entities: list,
    alternative_flows: list,
    exception_flows: list,
) -> tuple[Step3WOutput, Step3IOOutput, Step3TOutput]:
    """
    Convert old Step 3 output to new format.
    
    Useful for backward compatibility during migration.
    """
    # Convert workflow steps
    raw_steps = []
    step_io_specs = {}
    
    for step in workflow_steps:
        raw_step = WorkflowStepRaw(
            step_id=step.step_id,
            description=step.description,
            action_type=step.action_type,
            tool_hint=step.tool_hint,
            is_validation_gate=step.is_validation_gate,
            source_text=step.source_text,
        )
        raw_steps.append(raw_step)
        
        # Create I/O spec from old prerequisites/produces (list of strings)
        # For now, treat as text type
        from models.step3_types import TEXT_TYPE
        
        prereqs = {}
        for prereq_id in getattr(step, "prerequisites", []):
            prereqs[prereq_id] = step_io_specs.get(prereq_id, {}) if prereq_id in step_io_specs else {}
        
        step_io_specs[step.step_id] = StepIOSpec(
            step_id=step.step_id,
            prerequisites={},  # Will be filled by Step3-IO
            produces={},
        )
    
    # Convert entities to registry
    registry = GlobalVarRegistry()
    for entity in entities:
        from models.step3_types import VarSpec, TypeExpr
        
        var = VarSpec(
            var_name=entity.entity_id,
            type_expr=TEXT_TYPE,  # Default for migration
            is_file=entity.is_file,
            description=entity.schema_notes,
        )
        registry.register(var)
    
    step3w = Step3WOutput(
        workflow_steps=raw_steps,
        alternative_flows=alternative_flows,
        exception_flows=exception_flows,
    )
    
    step3io = Step3IOOutput(
        step_io_specs=step_io_specs,
        global_registry=registry,
    )
    
    step3t = Step3TOutput(
        types_spl="",
        type_registry={},
        declared_names=set(),
    )
    
    return step3w, step3io, step3t
