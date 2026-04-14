"""
step4_spl_emission.py
─────────────────────
Step 4: SPL Emission (dependency-driven parallel execution).

Changes from prior version:
  - Implemented dependency-driven task scheduling for optimal parallelism:
    * S4C generates symbol_table, which immediately triggers S4A and S4B
    * S4D runs in parallel with S4C (no mutual dependency)
    * S4E waits for both S4C (symbol_table) and S4D (apis_spl)
  - Previous round-based blocking approach removed in favor of async futures

Task dependency graph:
  Step 3A (entities) ──┬─→ S4C ──→ symbol_table ──┬─→ S4A (persona)
                       │                          ├─→ S4B (constraints)
                       │                          └─→ S4E ←──┬── apis_spl (from S4D)
                       │                                     │
                       └─→ Step 3B ──→ workflow/flows ────────┘
                                                       │
                                                       ↓
                                                      S4F
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
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
from pipeline.spl_formatter import format_spl_indentation
from prompts import templates

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_step4_spl_emission(
    bundle: SectionBundle,
    interface_spec: StructuredSpec,
    tools: list,  # list[ToolSpec]
    skill_id: str,
    client: LLMClient,
) -> SPLSpec:
    """
    Step 4: Emit the final normalized SPL specification.

    Dependency-driven parallel execution:
      1. S4C (variables/files) and S4D (apis) start immediately in parallel
         - S4C depends on interface_spec.entities (Step 3A output)
         - S4D depends on interface_spec.workflow_steps (Step 3B output)
      
      2. When S4C completes → extract symbol_table → immediately start S4A + S4B
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
        # ── Phase 1: Launch S4C and S4D immediately (they are independent) ─────
        # S4D now launches one LLM call per tool for individual API generation
        logger.info("[Step 4] Phase 1: Launching S4C (variables/files) and S4D (apis per tool) in parallel")

        future_4c = pool.submit(_call_4c, client, s4c_inputs)

        # Launch S4D: one LLM call per tool
        tools_list = s4d_inputs.get("tools_list", [])
        if s4d_inputs["has_tools"] and tools_list:
            logger.info("[Step 4] Phase 1: Launching S4D with %d tools (individual LLM calls)", len(tools_list))
            futures_4d = [pool.submit(_call_4d, client, tool) for tool in tools_list]
        else:
            logger.info("[Step 4] Phase 1: No tools found, S4D skipped")
            futures_4d = []

        # ── Phase 2: When S4C completes, extract symbol table and launch S4A + S4B ──
        # Note: We don't wait for S4D here - this is the key optimization!
        logger.info("[Step 4] Phase 2: Waiting for S4C to extract symbol table...")
        block_4c = future_4c.result()

        symbol_table = _extract_symbol_table(block_4c)
        symbol_table_text = _format_symbol_table(symbol_table)
        logger.info("[Step 4] Symbol table extracted — variables: %d, files: %d",
            len(symbol_table["variables"]), len(symbol_table["files"]))

        # Launch S4A and S4B immediately (they only need symbol_table, not apis_spl)
        logger.info("[Step 4] Phase 2: Launching S4A (persona) and S4B (constraints) in parallel")
        future_4a = pool.submit(_call_4a, client, s4a_inputs, symbol_table_text)
        future_4b = pool.submit(_call_4b, client, s4b_inputs, symbol_table_text)

        # ── Phase 3: Wait for all S4D calls to complete, then launch S4E ─────────────────
        # S4E needs both symbol_table (ready) and apis_spl (from S4D - now multiple results)
        logger.info("[Step 4] Phase 3: Waiting for S4D to complete...")
        block_4d_parts = [f.result() for f in futures_4d] if futures_4d else []
        block_4d = "\n\n".join(block_4d_parts) if block_4d_parts else ""
        logger.info("[Step 4] Phase 3: S4D completed — %d API definitions generated", len(block_4d_parts))

        logger.info("[Step 4] Phase 3: Launching S4E (worker)")
        future_4e = pool.submit(_call_4e, client, s4e_inputs, symbol_table_text, block_4d)

        # ── Phase 4: Collect S4A and S4B results ───────────────────────────────
        # These may have already completed while we were waiting for S4D
        block_4a = future_4a.result()
        block_4b = future_4b.result()

        # ── Phase 5: Wait for S4E, then launch S4F ─────────────────────────────
        logger.info("[Step 4] Phase 4: Waiting for S4E to complete...")
        block_4e = future_4e.result()

        block_4f = ""
    if s4f_inputs["has_examples"]:
        logger.info("[Step 4] Phase 5: Generating S4F (examples)")
        block_4f = _call_4f(client, s4f_inputs, block_4e)

    # ── Assemble final SPL ────────────────────────────────────────────────────
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
) -> SPLSpec:
    """
    Step 4: SPL Emission with maximum parallelism between 3A/3B and Step 4.
    
    Parallel execution lines:
      Line 1: S4C (needs entities) → symbol_table → (S4A || S4B)
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
        # ── Line 1: S4C (needs entities) ─────────────────────────────────────
        logger.info("[Step 4] Line 1: Launching S4C (variables/files)")
        future_4c = pool.submit(_call_4c, client, s4c_inputs)

        # ── Line 2: S4D (needs workflow_steps with NETWORK effects) ──────────
        # S4D now launches one LLM call per tool for individual API generation
        tools_list = s4d_inputs.get("tools_list", [])
        if s4d_inputs["has_tools"] and tools_list:
            logger.info("[Step 4] Line 2: Launching S4D with %d tools (individual LLM calls)", len(tools_list))
            futures_4d = [pool.submit(_call_4d, client, tool) for tool in tools_list]
        else:
            logger.info("[Step 4] Line 2: No tools found, S4D skipped")
            futures_4d = []

        # ── Line 1 continued: When S4C completes, extract symbol_table ───────
        logger.info("[Step 4] Line 1: Waiting for S4C to extract symbol table...")
        block_4c = future_4c.result()

        symbol_table = _extract_symbol_table(block_4c)
        symbol_table_text = _format_symbol_table(symbol_table)
        logger.info("[Step 4] Symbol table extracted — variables: %d, files: %d",
            len(symbol_table["variables"]), len(symbol_table["files"]))

        # Launch S4A and S4B (they only need symbol_table, not apis_spl)
        logger.info("[Step 4] Line 1: Launching S4A (persona) and S4B (constraints)")
        future_4a = pool.submit(_call_4a, client, s4a_inputs, symbol_table_text)
        future_4b = pool.submit(_call_4b, client, s4b_inputs, symbol_table_text)

        # ── Merge Point: Wait for all Line 2 (S4D) calls to complete ───────────────────
        logger.info("[Step 4] Merge point: Waiting for Line 2 (S4D) to complete...")
        block_4d_parts = [f.result() for f in futures_4d] if futures_4d else []
        block_4d = "\n\n".join(block_4d_parts) if block_4d_parts else ""
        logger.info("[Step 4] Merge point: S4D completed — %d API definitions generated", len(block_4d_parts))

        # ── S4E: Needs both symbol_table (Line 1) and apis_spl (Line 2) ──────
        logger.info("[Step 4] Launching S4E (worker) - merge of Line 1 and Line 2")
        future_4e = pool.submit(_call_4e, client, s4e_inputs, symbol_table_text, block_4d)

        # Collect S4A and S4B results (may already be done)
        block_4a = future_4a.result()
        block_4b = future_4b.result()

        # ── S4F: Final step, needs S4E output ────────────────────────────────
        logger.info("[Step 4] Final: Waiting for S4E to complete...")
        block_4e = future_4e.result()

        block_4f = ""
        if s4f_inputs["has_examples"]:
            logger.info("[Step 4] Final: Generating S4F (examples)")
            block_4f = _call_4f(client, s4f_inputs, block_4e)

    # ── Assemble final SPL ────────────────────────────────────────────────────
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


# ── Individual step call functions ────────────────────────────────────────────
# Note: Both sync and async versions are provided for backward compatibility.
# New code should use the async versions.

async def _call_4c_async(client: LLMClient, inputs: dict) -> str:
    """Generate DEFINE_VARIABLES + DEFINE_FILES block."""
    if not inputs["has_entities"]:
        return ""
    return await client.async_call(
        "step4c_variables_files",
        templates.S4C_SYSTEM,
        templates.render_s4c_user(inputs["entities_text"], inputs["omit_files_text"]),
    )


async def _call_4a_async(client: LLMClient, inputs: dict, symbol_table_text: str) -> str:
    """Generate PERSONA / AUDIENCE / CONCEPTS block."""
    return await client.async_call(
        "step4a_persona",
        templates.S4A_SYSTEM,
        templates.render_s4a_user(
            intent_text=inputs["intent_text"],
            notes_text=inputs["notes_text"],
            symbol_table=symbol_table_text,
        ),
    )


async def _call_4b_async(client: LLMClient, inputs: dict, symbol_table_text: str) -> str:
    """Generate DEFINE_CONSTRAINTS block."""
    if not inputs["has_constraints"]:
        return ""
    return await client.async_call(
        "step4b_constraints",
        templates.S4B_SYSTEM,
        templates.render_s4b_user(
            constraints_text=inputs["constraints_text"],
            symbol_table=symbol_table_text,
        ),
    )


async def _call_4e_async(client: LLMClient, inputs: dict, symbol_table_text: str, apis_spl: str) -> str:
    """Generate WORKER block (MAIN_FLOW + ALTERNATIVE_FLOW + EXCEPTION_FLOW)."""
    # Convert tools_list to JSON string for S4E
    tools_list = inputs.get("tools_list", [])
    tools_json_str = json.dumps(tools_list, indent=2, ensure_ascii=False) if tools_list else "[]"
    s4e_system, s4e_user = templates.render_s4e_user(
        workflow_steps_json=inputs["workflow_steps_json"],
        workflow_prose=inputs["workflow_prose"],
        alternative_flows_json=inputs["alternative_flows_json"],
        exception_flows_json=inputs["exception_flows_json"],
        symbol_table=symbol_table_text,
        apis_spl=apis_spl,
        tools_json=tools_json_str,
    )
    return await client.async_call(step_name="step4e_worker", system=s4e_system, user=s4e_user)


async def _call_4e1_async(client: LLMClient, worker_spl: str) -> dict:
    """Detect illegal nested BLOCK structures in WORKER SPL.

    Returns a dict with:
    - has_violations: bool
    - violations: list of violation dicts
    """
    s4e1_user = templates.render_s4e1_user(worker_spl=worker_spl)
    response = await client.async_call(
        step_name="step4e1_nesting_detection",
        system=templates.S4E1_SYSTEM,
        user=s4e1_user,
    )

    # Parse JSON response (handle markdown code blocks)
    try:
        # Strip markdown fences if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Remove opening fence
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        result = json.loads(cleaned)
        return result
    except json.JSONDecodeError as e:
        logger.warning("[Step 4E1] Failed to parse JSON response: %s", e)
        logger.debug("[Step 4E1] Raw response:\n%s", response[:500])
        return {"has_violations": False, "violations": []}


async def _call_4e2_async(client: LLMClient, worker_spl: str, violations: list) -> str:
    """Fix illegal nested BLOCK structures by flattening.

    Returns the corrected WORKER SPL text.
    """
    violations_json = json.dumps(violations, indent=2, ensure_ascii=False)
    s4e2_user = templates.render_s4e2_user(
        worker_spl=worker_spl,
        violations_json=violations_json,
    )
    return await client.async_call(
        step_name="step4e2_nesting_fix",
        system=templates.S4E2_SYSTEM,
        user=s4e2_user,
    )


async def validate_and_fix_worker_nesting_async(client: LLMClient, worker_spl: str) -> tuple[str, dict]:
    """Validate and fix nested BLOCK structures in WORKER SPL.

    Args:
        client: LLM client for making calls
        worker_spl: The generated WORKER SPL text

    Returns:
        Tuple of (corrected_worker_spl, detection_result)
        - corrected_worker_spl: The fixed SPL (or original if no violations)
        - detection_result: The full S4E1 detection result dict
    """
    logger.info("[Step 4E.1] Checking for illegal BLOCK nesting...")
    detection_result = await _call_4e1_async(client, worker_spl)

    if detection_result.get("has_violations", False):
        violations = detection_result.get("violations", [])
        logger.warning(
            "[Step 4E.1] Found %d nested BLOCK violations, fixing...",
            len(violations)
        )
        for v in violations:
            logger.debug(
                " - %s inside %s: %s",
                v.get("inner_block", "?"),
                v.get("outer_block", "?"),
                v.get("snippet", "")[:50]
            )

        logger.info("[Step 4E.2] Fixing nested BLOCK structures...")
        fixed_spl = await _call_4e2_async(client, worker_spl, violations)
        return fixed_spl, detection_result
    else:
        logger.info("[Step 4E.1] No nested BLOCK violations found")
        return worker_spl, detection_result


async def _call_4f_async(client: LLMClient, inputs: dict, worker_spl: str) -> str:
    """Generate [EXAMPLES] block."""
    return await client.async_call(
        "step4f_examples",
        templates.S4F_SYSTEM,
        templates.render_s4f_user(
            worker_spl=worker_spl,
            examples_text=inputs["examples_text"],
        ),
    )


async def _call_s0_async(client: LLMClient, skill_id: str, intent_text: str, notes_text: str) -> str:
    """Generate DEFINE_AGENT header block.

    Args:
        client: LLM client for making calls
        skill_id: The skill identifier
        intent_text: The INTENT section text
        notes_text: The NOTES section text

    Returns:
        The DEFINE_AGENT header line (e.g., "[DEFINE_AGENT: AgentName \"description\"]")
    """
    return await client.async_call(
        "step0_define_agent",
        templates.S0_SYSTEM,
        templates.render_s0_user(skill_id, intent_text, notes_text),
    )


# Legacy sync functions (kept for backward compatibility)
def _call_4d(client: LLMClient, tool: dict) -> str:
    """Generate DEFINE_APIS block for a single tool.

    DEPRECATED: API generation moved to Step 1.5.
    This function is kept for backward compatibility.
    """
    return ""


def _call_4c(client: LLMClient, inputs: dict) -> str:
    """Generate DEFINE_VARIABLES + DEFINE_FILES block."""
    if not inputs["has_entities"]:
        return ""
    return client.call(
        "step4c_variables_files",
        templates.S4C_SYSTEM,
        templates.render_s4c_user(inputs["entities_text"], inputs["omit_files_text"]),
    )


def _call_4a(client: LLMClient, inputs: dict, symbol_table_text: str) -> str:
    """Generate PERSONA / AUDIENCE / CONCEPTS block."""
    return client.call(
        "step4a_persona",
        templates.S4A_SYSTEM,
        templates.render_s4a_user(
            intent_text=inputs["intent_text"],
            notes_text=inputs["notes_text"],
            symbol_table=symbol_table_text,
        ),
    )


def _call_4b(client: LLMClient, inputs: dict, symbol_table_text: str) -> str:
    """Generate DEFINE_CONSTRAINTS block."""
    if not inputs["has_constraints"]:
        return ""
    return client.call(
        "step4b_constraints",
        templates.S4B_SYSTEM,
        templates.render_s4b_user(
            constraints_text=inputs["constraints_text"],
            symbol_table=symbol_table_text,
        ),
    )


def _call_4e(client: LLMClient, inputs: dict, symbol_table_text: str, apis_spl: str) -> str:
    """Generate WORKER block (MAIN_FLOW + ALTERNATIVE_FLOW + EXCEPTION_FLOW)."""
    tools_list = inputs.get("tools_list", [])
    tools_json_str = json.dumps(tools_list, indent=2, ensure_ascii=False) if tools_list else "[]"
    s4e_system, s4e_user = templates.render_s4e_user(
        workflow_steps_json=inputs["workflow_steps_json"],
        workflow_prose=inputs["workflow_prose"],
        alternative_flows_json=inputs["alternative_flows_json"],
        exception_flows_json=inputs["exception_flows_json"],
        symbol_table=symbol_table_text,
        apis_spl=apis_spl,
        tools_json=tools_json_str,
    )
    return client.call(step_name="step4e_worker", system=s4e_system, user=s4e_user)


def _call_4f(client: LLMClient, inputs: dict, worker_spl: str) -> str:
    """Generate [EXAMPLES] block."""
    return client.call(
        "step4f_examples",
        templates.S4F_SYSTEM,
        templates.render_s4f_user(
            worker_spl=worker_spl,
            examples_text=inputs["examples_text"],
        ),
    )


def validate_and_fix_worker_nesting(client: LLMClient, worker_spl: str) -> tuple[str, dict]:
    """Validate and fix nested BLOCK structures in WORKER SPL (sync version).

    Args:
        client: LLM client for making calls
        worker_spl: The generated WORKER SPL text

    Returns:
        Tuple of (corrected_worker_spl, detection_result)
        - corrected_worker_spl: The fixed SPL (or original if no violations)
        - detection_result: The full S4E1 detection result dict
    """
    logger.info("[Step 4E.1] Checking for illegal BLOCK nesting...")
    
    s4e1_user = templates.render_s4e1_user(worker_spl=worker_spl)
    response = client.call(
        step_name="step4e1_nesting_detection",
        system=templates.S4E1_SYSTEM,
        user=s4e1_user,
    )

    # Parse JSON response (handle markdown code blocks)
    try:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        detection_result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("[Step 4E1] Failed to parse JSON response: %s", e)
        logger.debug("[Step 4E1] Raw response:\n%s", response[:500])
        detection_result = {"has_violations": False, "violations": []}

    if detection_result.get("has_violations", False):
        violations = detection_result.get("violations", [])
        logger.warning(
            "[Step 4E.1] Found %d nested BLOCK violations, fixing...",
            len(violations)
        )
        for v in violations:
            logger.debug(
                " - %s inside %s: %s",
                v.get("inner_block", "?"),
                v.get("outer_block", "?"),
                v.get("snippet", "")[:50]
            )

        logger.info("[Step 4E.2] Fixing nested BLOCK structures...")
        
        violations_json = json.dumps(violations, indent=2, ensure_ascii=False)
        s4e2_user = templates.render_s4e2_user(
            worker_spl=worker_spl,
            violations_json=violations_json,
        )
        fixed_spl = client.call(
            step_name="step4e2_nesting_fix",
            system=templates.S4E2_SYSTEM,
            user=s4e2_user,
        )
        return fixed_spl, detection_result
    else:
        logger.info("[Step 4E.1] No nested BLOCK violations found")
        return worker_spl, detection_result


def _call_s0(client: LLMClient, skill_id: str, intent_text: str, notes_text: str) -> str:
    """Generate DEFINE_AGENT header block.

    Args:
        client: LLM client for making calls
        skill_id: The skill identifier
        intent_text: The INTENT section text
        notes_text: The NOTES section text

    Returns:
        The DEFINE_AGENT header line (e.g., "[DEFINE_AGENT: AgentName \"description\"]")
    """
    return client.call(
        "step0_define_agent",
        templates.S0_SYSTEM,
        templates.render_s0_user(skill_id, intent_text, notes_text),
    )


# ── Input preparation ─────────────────────────────────────────────────────────

def _prepare_step4_inputs_parallel(
    bundle: SectionBundle,
    entities: list[EntitySpec],
    workflow_steps: list[WorkflowStepSpec],
    alternative_flows: list[AlternativeFlowSpec],
    exception_flows: list[ExceptionFlowSpec],
) -> tuple[dict, dict, dict, dict, dict, dict]:
    """
    Pre-compute all inputs for Step 4 calls with parallel execution support.
    
    Accepts decomposed inputs from Step 3A (entities) and Step 3B (workflow/flows)
    to enable maximum parallelism between Step 3 and Step 4.
    
    Returns 6 dictionaries for each S4x call.
    
    Parallel lines:
      Line 1: S4C (entities) -> symbol_table -> S4A + S4B
      Line 2: S4D (workflow_steps with NETWORK effects)
      Merge: S4E (needs symbol_table + apis_spl)
      Final: S4F (needs S4E output)
    """
    # S4A inputs - from bundle
    intent_text = bundle.to_text(["INTENT"])
    notes_text = bundle.to_text(["NOTES"])
    s4a_inputs = {
        "intent_text": intent_text,
        "notes_text": notes_text,
    }
    
    # S4B inputs - from bundle
    constraints_text = bundle.to_text(["CONSTRAINTS"])
    s4b_inputs = {
        "constraints_text": constraints_text,
        "has_constraints": bool(constraints_text.strip()),
    }
    
    # S4C inputs - from entities (Step 3A)
    entities_text = _format_entities_for_s4c(entities)
    omit_files = [e for e in entities if getattr(e, "from_omit_files", False)]
    omit_files_text = _format_omit_files_for_s4c(omit_files)
    s4c_inputs = {
        "entities_text": entities_text,
        "omit_files_text": omit_files_text,
        "has_entities": bool(entities),
    }
    
    # S4D inputs - from workflow_steps with API action types (Step 3B)
    api_steps = [s for s in workflow_steps if s.action_type in ["EXTERNAL_API", "EXEC_SCRIPT", "LOCAL_CODE_SNIPPET"]]
    # Prepare list of individual step dicts for parallel processing
    api_steps_list = [_step_to_dict(s) for s in api_steps]
    s4d_inputs = {
        "tools_list": api_steps_list,
        "has_tools": bool(api_steps),
    }

    # S4E inputs - from workflow_steps, flows (Step 3B)
    workflow_steps_json = json.dumps(
        [_step_to_dict(s) for s in workflow_steps],
        indent=2, ensure_ascii=False,
    )
    workflow_prose = bundle.to_text(["WORKFLOW"])
    alternative_flows_json = json.dumps(
        [dataclasses.asdict(f) for f in alternative_flows],
        indent=2, ensure_ascii=False,
    )
    exception_flows_json = json.dumps(
        [dataclasses.asdict(f) for f in exception_flows],
        indent=2, ensure_ascii=False,
    )
    s4e_inputs = {
        "workflow_steps_json": workflow_steps_json,
        "workflow_prose": workflow_prose,
        "alternative_flows_json": alternative_flows_json,
        "exception_flows_json": exception_flows_json,
        "tools_list": api_steps_list,
    }

    # S4F inputs - from bundle
    examples_text = bundle.to_text(["EXAMPLES"])
    s4f_inputs = {
        "examples_text": examples_text,
        "has_examples": bool(examples_text.strip()),
    }

    return s4a_inputs, s4b_inputs, s4c_inputs, s4d_inputs, s4e_inputs, s4f_inputs


def _prepare_step4_inputs_v2(
    bundle: SectionBundle,
    structured_spec: StructuredSpec,
    tools: list,  # list[ToolSpec]
) -> tuple[dict, dict, dict, dict, dict, dict]:
    """
    Pre-compute all inputs for the Step 4 calls.

    Returns 6 dictionaries, one for each S4x call, to avoid passing unnecessary
    data to each function.

    Dependencies:
    S4A: bundle[INTENT + NOTES]
    S4B: bundle[CONSTRAINTS]
    S4C: structured_spec.entities + omit_files
    S4D: tools list for API generation
    S4E: ALL workflow_steps + flows + symbol_table + apis_spl + tools
    S4F: bundle[EXAMPLES] + worker_spl
    """
    # S4A inputs
    intent_text = bundle.to_text(["INTENT"])
    notes_text = bundle.to_text(["NOTES"])
    s4a_inputs = {
        "intent_text": intent_text,
        "notes_text": notes_text,
    }
    
    # S4B inputs
    constraints_text = bundle.to_text(["CONSTRAINTS"])
    s4b_inputs = {
        "constraints_text": constraints_text,
        "has_constraints": bool(constraints_text.strip()),
    }
    
    # S4C inputs
    entities_text = _format_entities_for_s4c(structured_spec.entities)
    omit_files = [e for e in structured_spec.entities if getattr(e, "from_omit_files", False)]
    omit_files_text = _format_omit_files_for_s4c(omit_files)
    s4c_inputs = {
        "entities_text": entities_text,
        "omit_files_text": omit_files_text,
        "has_entities": bool(structured_spec.entities),
    }
    
    # S4D inputs - prepare list of individual tool dicts for parallel processing
    tools_list = [
        {"name": t.name, "api_type": t.api_type, "url": t.url,
         "authentication": t.authentication, "input_schema": t.input_schema,
         "output_schema": t.output_schema, "description": t.description,
         "source_text": t.source_text[:500] if len(t.source_text) > 500 else t.source_text}
        for t in tools
    ]
    s4d_inputs = {
        "tools_list": tools_list,
        "has_tools": bool(tools),
    }

    # S4E inputs
    workflow_steps_json = json.dumps(
        [_step_to_dict(s) for s in structured_spec.workflow_steps],
        indent=2, ensure_ascii=False,
    )
    workflow_prose = bundle.to_text(["WORKFLOW"])
    alternative_flows_json = json.dumps(
        [dataclasses.asdict(f) for f in structured_spec.alternative_flows],
        indent=2, ensure_ascii=False,
    )
    exception_flows_json = json.dumps(
        [dataclasses.asdict(f) for f in structured_spec.exception_flows],
        indent=2, ensure_ascii=False,
    )
    # For S4E, pass the tools_list directly (will be converted to JSON when needed)
    s4e_inputs = {
        "workflow_steps_json": workflow_steps_json,
        "workflow_prose": workflow_prose,
        "alternative_flows_json": alternative_flows_json,
        "exception_flows_json": exception_flows_json,
        "tools_list": tools_list,
    }

    # S4F inputs
    examples_text = bundle.to_text(["EXAMPLES"])
    s4f_inputs = {
        "examples_text": examples_text,
        "has_examples": bool(examples_text.strip()),
    }

    return s4a_inputs, s4b_inputs, s4c_inputs, s4d_inputs, s4e_inputs, s4f_inputs


# Legacy function kept for backward compatibility
def _prepare_step4_inputs(
    bundle: SectionBundle,
    structured_spec: StructuredSpec,
    tools: list | None = None,
) -> dict:
    """
    Legacy input preparation function.
    Use _prepare_step4_inputs_v2 for the new dependency-driven scheduler.
    """
    tools = tools if tools is not None else []
    s4a, s4b, s4c, s4d, s4e, s4f = _prepare_step4_inputs_v2(bundle, structured_spec, tools)
    return {
        **s4a,
        **s4b,
        **s4c,
        **s4d,
        **s4e,
        **s4f,
    }


def _format_entities_for_s4c(entities: list[EntitySpec]) -> str:
    if not entities:
        return "(No entities found)"

    variables = [e for e in entities if e.kind != "Artifact"]
    files     = [e for e in entities if e.kind == "Artifact"]
    lines = []

    if variables:
        lines.append("VARIABLES (in-memory data structures → DEFINE_VARIABLES):")
        lines.append("")
        for e in variables:
            readonly = "[READONLY] " if e.provenance_required else ""
            lines.append(f"Variable: {readonly}{e.entity_id}")
            lines.append(f"Type:     {e.type_name}")
            lines.append(f"Kind:     {e.kind}")
            if e.schema_notes:
                lines.append(f"Schema:   {e.schema_notes}")
            lines.append(f"Provenance: {e.provenance}")
            if e.source_text:
                lines.append(f"Source:   {e.source_text[:120]}")
            lines.append("")

    if files:
        lines.append("FILES (disk artifacts → DEFINE_FILES):")
        lines.append("")
        for e in files:
            path_display = getattr(e, "file_path", "") or "< >"
            lines.append(f"File: {e.entity_id}")
            lines.append(f"Path: {path_display}")
            lines.append(f"Type: {e.type_name}")
            if e.schema_notes:
                lines.append(f"Description: {e.schema_notes}")
            lines.append(f"Provenance: {e.provenance}")
            if getattr(e, "from_omit_files", False):
                lines.append("Note: Sourced from P1 omit-files (priority=3)")
            lines.append("")

    return "\n".join(lines)


def _format_omit_files_for_s4c(omit_files: list[EntitySpec]) -> str:
    if not omit_files:
        return "(No omit files found)"
    lines = ["Additional files from skill package (P1 priority=3, not merged into main doc):"]
    lines.append("")
    for e in omit_files:
        path_display = getattr(e, "file_path", "") or "< >"
        lines.append(f"- {e.entity_id}: {path_display}")
        lines.append(f"  Type: {e.type_name}")
        lines.append(f"  Kind: {e.kind}")
        lines.append("")
    return "\n".join(lines)


def _step_to_dict(s: WorkflowStepSpec) -> dict:
    return {
        "step_id": s.step_id,
        "description": s.description,
        "prerequisites": s.prerequisites,
        "produces": s.produces,
        "is_validation_gate": s.is_validation_gate,
        "action_type": s.action_type,
        "tool_hint": s.tool_hint,
        "source_text": s.source_text,
    }


# ── Symbol table ──────────────────────────────────────────────────────────────

# Regex to match file declarations in DEFINE_FILES
# Files are defined in two-line format:
#   "description"
#   variable_name path : type
# Where path can be a filename or placeholders like "< >" (with spaces)
_FILE_NAME_RE = re.compile(
    r'^\s*"[^"]*"\s*\n\s+([a-z][a-z0-9_]+)\s+[^\n:]*?:',
    re.MULTILINE | re.IGNORECASE
)


def _extract_symbol_table(block_4c: str) -> dict[str, list[str]]:
    """
    Extract FILES and VARIABLES declared in the DEFINE_VARIABLES/DEFINE_FILES
    block (4c). APIS are NOT included — they are passed separately to S4E.
    
    Handles both formats:
    - [DEFINE_VARIABLES:] ... [END_VARIABLES] [DEFINE_FILES:] ... [END_FILES]
    - [DEFINE_FILES:] ... [END_FILES] (no variables section)
    - [DEFINE_VARIABLES:] ... [END_VARIABLES] (no files section)
    
    Files are defined in two-line format:
      "description"
      variable_name path : type
    
    Variables can be in single-line or two-line format:
      "description" [READONLY] variable_name : type
      "description"
      [READONLY] variable_name : type
    """
    table: dict[str, list[str]] = {
        "variables": [],
        "files": [],
    }
    if not block_4c:
        return table
    
    # Extract VARIABLES block if present
    var_start = block_4c.find("[DEFINE_VARIABLES:]")
    var_end = block_4c.find("[END_VARIABLES]")
    
    if var_start >= 0 and var_end > var_start:
        var_block = block_4c[var_start:var_end]
        # Find all variable declarations
        # Pattern: "description" followed by optional READONLY and variable_name :
        # Handles both single-line and two-line formats
        var_matches = re.findall(
            r'(?:^\s*"[^"]*"(?:\s+READONLY)?\s+([a-z][a-z0-9_]+)\s*:)|'
            r'(?:^\s*"[^"]*"\s*\n\s*(?:READONLY\s+)?([a-z][a-z0-9_]+)\s*:)',
            var_block,
            re.MULTILINE | re.IGNORECASE
        )
        # Flatten matches (each match is a tuple from alternation)
        table["variables"] = [v for match in var_matches for v in match if v]
    
    # Extract FILES block if present  
    file_start = block_4c.find("[DEFINE_FILES:]")
    file_end = block_4c.find("[END_FILES]")
    
    if file_start >= 0 and file_end > file_start:
        file_block = block_4c[file_start:file_end]
        # Files are always in two-line format:
        # "description"
        # variable_name path : type
        # Where path can contain spaces (e.g., "< >")
        file_matches = re.findall(
            r'^\s*"[^"]*"\s*\n\s+([a-z][a-z0-9_]+)\s+[^\n:]*?:',
            file_block,
            re.MULTILINE | re.IGNORECASE
        )
        table["files"] = file_matches
    
    return table


def _format_symbol_table(symbol_table: dict[str, list[str]]) -> str:
    """
    Render FILES + VARIABLES as a reference block for S4A, S4B, and S4E.
    These are the names that may appear in DESCRIPTION_WITH_REFERENCES across
    all three blocks.  APIS are injected separately into S4E.
    """
    mapping = {
        "variables": "VARIABLES (reference as <REF> var_name </REF>)",
        "files":     "FILES     (reference as <REF> file_name </REF>)",
    }
    lines = []
    for key, label in mapping.items():
        names = symbol_table.get(key, [])
        if names:
            lines.append(f"{label}:\n  {', '.join(names)}")
    return "\n\n".join(lines) if lines else "(no variables or files declared)"


# ── Assembly ──────────────────────────────────────────────────────────────────

def _assemble_spl(
    skill_id: str,
    define_agent_header: str,
    block_4a: str,
    block_4b: str,
    block_4c: str,
    block_4d: str,
    block_4e: str,
    block_4f: str,
) -> str:
    """
    Concatenate all blocks in canonical SPL order, wrapping with DEFINE_AGENT.

    Final structure:
    [DEFINE_AGENT: AGENT_NAME "description"]
    # SPL_PROMPT content (blocks 4a-4f)
    [END_AGENT]

    block_4f ([EXAMPLES] block) is inserted INSIDE the WORKER, before
    [END_WORKER]. If [END_WORKER] is not found, 4f is appended separately.
    """
    # Insert S4F [EXAMPLES] block into the WORKER before [END_WORKER]
    worker_block = _strip_fences(block_4e.strip())
    if block_4f:
        examples_block = _strip_fences(block_4f.strip())
        if "[END_WORKER]" in worker_block:
            worker_block = worker_block.replace(
                "[END_WORKER]",
                examples_block + "\n[END_WORKER]",
                1,
            )
        else:
            worker_block = worker_block + "\n\n" + examples_block

    # Assemble SPL_PROMPT content (everything inside DEFINE_AGENT)
    spl_prompt_blocks = []
    for raw_block in (block_4a, block_4b, block_4c, block_4d):
        cleaned = _strip_fences(raw_block.strip())
        if cleaned:
            spl_prompt_blocks.append(cleaned)
    if worker_block:
        spl_prompt_blocks.append(worker_block)

    spl_prompt_content = "\n\n".join(spl_prompt_blocks)

    # Wrap with DEFINE_AGENT header and footer
    header = f"# SPL specification — {skill_id}\n# Generated by skill-to-cnlp pipeline\n\n"

    # Use the generated DEFINE_AGENT header (or create a default one)
    if define_agent_header and define_agent_header.strip():
        define_agent_line = _strip_fences(define_agent_header.strip())
    else:
        # Fallback: generate a simple DEFINE_AGENT header
        agent_name = _to_pascal_case(skill_id)
        define_agent_line = f"[DEFINE_AGENT: {agent_name}]"

    final_spl = header + define_agent_line + "\n\n" + spl_prompt_content + "\n\n[END_AGENT]"

    # 格式化SPL缩进，确保使用标准4空格缩进
    final_spl = format_spl_indentation(final_spl)

    return final_spl


def _to_pascal_case(text: str) -> str:
    """Convert a skill_id to PascalCase agent name."""
    import re
    # Remove non-alphanumeric characters and split into words
    words = re.split(r'[^a-zA-Z0-9]+', text)
    # Capitalize each word and join
    return ''.join(word.capitalize() for word in words if word)


def _strip_fences(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


# ── Review summary ────────────────────────────────────────────────────────────

def _build_review_summary() -> str:
    return "## Review Summary\n"




# Legacy helper — kept for compatibility
def _split_spl_output(raw_text: str) -> tuple[str, str]:
    marker = "## Review Summary"
    idx = raw_text.find(marker)
    if idx >= 0:
        return raw_text[:idx].strip(), raw_text[idx:].strip()
    return raw_text.strip(), ""