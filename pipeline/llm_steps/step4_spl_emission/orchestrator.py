"""Step 4: SPL Emission orchestrator (dependency-driven parallel execution)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from models.data_models import (
    AlternativeFlowSpec,
    EntitySpec,
    ExceptionFlowSpec,
    SectionBundle,
    SPLSpec,
    StructuredSpec,
    WorkflowStepSpec,
)
from pipeline.llm_client import LLMClient
from pipeline.llm_steps.step4_spl_emission.assembly import _assemble_spl
from pipeline.llm_steps.step4_spl_emission.inputs import (
    _prepare_step4_inputs_parallel,
    _prepare_step4_inputs_v2,
)
from pipeline.llm_steps.step4_spl_emission.substep_calls import (
    _call_4a,
    _call_4b,
    _call_4c,
    _call_4d,
    _call_4e,
    _call_4f,
)
from pipeline.llm_steps.step4_spl_emission.symbol_table import (
    _extract_symbol_table,
    _format_symbol_table,
)
from pipeline.llm_steps.step4_spl_emission.utils import _build_review_summary

logger = logging.getLogger(__name__)


def run_step4_spl_emission(
    bundle: SectionBundle,
    interface_spec: StructuredSpec,
    tools: list,  # list[ToolSpec]
    skill_id: str,
    client: LLMClient,
    model: str | None = None,
) -> SPLSpec:
    """
    Step 4: Emit the final normalized SPL specification.

    Dependency-driven parallel execution:
    1. S4C (variables/files) and S4D (apis) start immediately in parallel
    - S4C depends on interface_spec.entities (Step 3A output)
    - S4D depends on interface_spec.workflow_steps (Step 3B output)

    2. When S4C completes -> extract symbol_table -> immediately start S4A + S4B
    - S4A depends on symbol_table + bundle[INTENT/NOTES]
    - S4B depends on symbol_table + bundle[CONSTRAINTS]
    - S4A/S4B do NOT wait for S4D to complete (optimization!)

    3. S4E starts only when BOTH symbol_table (from S4C) AND apis_spl (from S4D) are ready
    - S4E depends on: symbol_table + apis_spl + workflow/flows (from Step 3B)

    4. S4F starts when S4E completes
    - S4F depends on: worker_spl (from S4E) + bundle[EXAMPLES]

    This design maximizes parallelism: S4A and S4B can complete while S4D is still running.
    """
    # Prepare all inputs upfront (lightweight, no LLM calls)
    s4a_inputs, s4b_inputs, s4c_inputs, s4d_inputs, s4e_inputs, s4f_inputs = _prepare_step4_inputs_v2(
        bundle, interface_spec, tools
    )

    with ThreadPoolExecutor(max_workers=4) as pool:
        # -- Phase 1: Launch S4C and S4D immediately (they are independent) ------
        # S4D now launches one LLM call per tool for individual API generation
        logger.info("[Step 4] Phase 1: Launching S4C (variables/files) and S4D (apis per tool) in parallel")

        future_4c = pool.submit(_call_4c, client, s4c_inputs, model=model)

        # Launch S4D: one LLM call per tool
        tools_list = s4d_inputs.get("tools_list", [])
        if s4d_inputs["has_tools"] and tools_list:
            logger.info("[Step 4] Phase 1: Launching S4D with %d tools (individual LLM calls)", len(tools_list))
            futures_4d = [pool.submit(_call_4d, client, tool, model=model) for tool in tools_list]
        else:
            logger.info("[Step 4] Phase 1: No tools found, S4D skipped")
            futures_4d = []

        # -- Phase 2: When S4C completes, extract symbol table and launch S4A + S4B --
        # Note: We don't wait for S4D here - this is the key optimization!
        logger.info("[Step 4] Phase 2: Waiting for S4C to extract symbol table...")
        block_4c = future_4c.result()

        symbol_table = _extract_symbol_table(block_4c)
        symbol_table_text = _format_symbol_table(symbol_table)
        logger.info("[Step 4] Symbol table extracted - variables: %d, files: %d",
                    len(symbol_table["variables"]), len(symbol_table["files"]))

        # Launch S4A and S4B immediately (they only need symbol_table, not apis_spl)
        logger.info("[Step 4] Phase 2: Launching S4A (persona) and S4B (constraints) in parallel")
        future_4a = pool.submit(_call_4a, client, s4a_inputs, symbol_table_text, model=model)
        future_4b = pool.submit(_call_4b, client, s4b_inputs, symbol_table_text, model=model)

        # -- Phase 3: Wait for all S4D calls to complete, then launch S4E ----------------
        # S4E needs both symbol_table (ready) and apis_spl (from S4D - now multiple results)
        logger.info("[Step 4] Phase 3: Waiting for S4D to complete...")
        block_4d_parts = [f.result() for f in futures_4d] if futures_4d else []
        block_4d = "\n\n".join(block_4d_parts) if block_4d_parts else ""
        logger.info("[Step 4] Phase 3: S4D completed - %d API definitions generated", len(block_4d_parts))

        logger.info("[Step 4] Phase 3: Launching S4E (worker)")
        future_4e = pool.submit(_call_4e, client, s4e_inputs, symbol_table_text, block_4d, model=model)

        # -- Phase 4: Collect S4A and S4B results ------------------------------
        # These may have already completed while we were waiting for S4D
        block_4a = future_4a.result()
        block_4b = future_4b.result()

        # -- Phase 5: Wait for S4E, then launch S4F ----------------------------
        logger.info("[Step 4] Phase 4: Waiting for S4E to complete...")
        block_4e = future_4e.result()

        block_4f = ""
        if s4f_inputs["has_examples"]:
            logger.info("[Step 4] Phase 5: Generating S4F (examples)")
            block_4f = _call_4f(client, s4f_inputs, block_4e, model=model)

        # -- Assemble final SPL -----------------------------------------------
        spl_text = _assemble_spl(
            skill_id, "", block_4a, block_4b, block_4c, block_4d, block_4e, block_4f
        )
        review_summary = _build_review_summary()
        clause_counts = {}

        logger.info("[Step 4] SPL assembled (%d chars)", len(spl_text))
        return SPLSpec(
            skill_id=skill_id,
            spl_text=spl_text,
            review_summary=review_summary,
            clause_counts=clause_counts,
        )


def run_step4_spl_emission_parallel(
    bundle: SectionBundle,
    entities: list[EntitySpec],
    workflow_steps: list[WorkflowStepSpec],
    alternative_flows: list[AlternativeFlowSpec],
    exception_flows: list[ExceptionFlowSpec],
    skill_id: str,
    client: LLMClient,
    model: str | None = None,
) -> SPLSpec:
    """
    Step 4: SPL Emission with maximum parallelism between 3A/3B and Step 4.

    Parallel execution lines:
    Line 1: S4C (needs entities) -> symbol_table -> (S4A || S4B)
    Line 2: S4D (needs workflow_steps with NETWORK effects)

    Merge point: S4E needs both symbol_table (from Line 1) and apis_spl (from Line 2)
    Final: S4F needs S4E output

    Args:
        bundle: SectionBundle with all sections (INTENT, NOTES, CONSTRAINTS, EXAMPLES, etc.)
        entities: From Step 3A entity extraction
        workflow_steps: From Step 3B workflow analysis
        alternative_flows: From Step 3B workflow analysis
        exception_flows: From Step 3B workflow analysis
        skill_id: The skill identifier
        client: LLM client for making calls

    Returns:
        SPLSpec with the complete SPL specification
    """
    # Prepare inputs for each sub-step
    s4a_inputs, s4b_inputs, s4c_inputs, s4d_inputs, s4e_inputs, s4f_inputs = _prepare_step4_inputs_parallel(
        bundle, entities, workflow_steps, alternative_flows, exception_flows
    )

    with ThreadPoolExecutor(max_workers=4) as pool:
        # -- Line 1: S4C (needs entities) --------------------------------------
        logger.info("[Step 4] Line 1: Launching S4C (variables/files)")
        future_4c = pool.submit(_call_4c, client, s4c_inputs, model=model)

        # -- Line 2: S4D (needs workflow_steps with NETWORK effects) ---------
        # S4D now launches one LLM call per tool for individual API generation
        tools_list = s4d_inputs.get("tools_list", [])
        if s4d_inputs["has_tools"] and tools_list:
            logger.info("[Step 4] Line 2: Launching S4D with %d tools (individual LLM calls)", len(tools_list))
            futures_4d = [pool.submit(_call_4d, client, tool, model=model) for tool in tools_list]
        else:
            logger.info("[Step 4] Line 2: No tools found, S4D skipped")
            futures_4d = []

        # -- Line 1 continued: When S4C completes, extract symbol_table ------
        logger.info("[Step 4] Line 1: Waiting for S4C to extract symbol table...")
        block_4c = future_4c.result()

        symbol_table = _extract_symbol_table(block_4c)
        symbol_table_text = _format_symbol_table(symbol_table)
        logger.info("[Step 4] Symbol table extracted - variables: %d, files: %d",
                    len(symbol_table["variables"]), len(symbol_table["files"]))

        # Launch S4A and S4B (they only need symbol_table, not apis_spl)
        logger.info("[Step 4] Line 1: Launching S4A (persona) and S4B (constraints)")
        future_4a = pool.submit(_call_4a, client, s4a_inputs, symbol_table_text, model=model)
        future_4b = pool.submit(_call_4b, client, s4b_inputs, symbol_table_text, model=model)

        # -- Merge Point: Wait for all Line 2 (S4D) calls to complete ----------------
        logger.info("[Step 4] Merge point: Waiting for Line 2 (S4D) to complete...")
        block_4d_parts = [f.result() for f in futures_4d] if futures_4d else []
        block_4d = "\n\n".join(block_4d_parts) if block_4d_parts else ""
        logger.info("[Step 4] Merge point: S4D completed - %d API definitions generated", len(block_4d_parts))

        # -- S4E: Needs both symbol_table (Line 1) and apis_spl (Line 2) -----
        logger.info("[Step 4] Launching S4E (worker) - merge of Line 1 and Line 2")
        future_4e = pool.submit(_call_4e, client, s4e_inputs, symbol_table_text, block_4d, model=model)

        # Collect S4A and S4B results (may already be done)
        block_4a = future_4a.result()
        block_4b = future_4b.result()

        # -- S4F: Final step, needs S4E output --------------------------------
        logger.info("[Step 4] Final: Waiting for S4E to complete...")
        block_4e = future_4e.result()

        block_4f = ""
        if s4f_inputs["has_examples"]:
            logger.info("[Step 4] Final: Generating S4F (examples)")
            block_4f = _call_4f(client, s4f_inputs, block_4e, model=model)

        # -- Assemble final SPL -----------------------------------------------
        spl_text = _assemble_spl(
            skill_id, "", block_4a, block_4b, block_4c, block_4d, block_4e, block_4f
        )
        review_summary = _build_review_summary()
        clause_counts = {}

        logger.info("[Step 4] SPL assembled (%d chars)", len(spl_text))
        return SPLSpec(
            skill_id=skill_id,
            spl_text=spl_text,
            review_summary=review_summary,
            clause_counts=clause_counts,
        )
