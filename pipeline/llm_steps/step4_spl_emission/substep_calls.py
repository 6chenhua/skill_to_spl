"""Sub-step call functions for Step 4 (sync and async versions)."""

from __future__ import annotations

import json
import logging

from pipeline.llm_client import LLMClient
from prompts import templates

logger = logging.getLogger(__name__)


# ── Async versions (new code should use these) ─────────────────────────────────

async def _call_4c_async(client: LLMClient, inputs: dict, model: str | None = None) -> str:
    """Generate DEFINE_VARIABLES + DEFINE_FILES block."""
    if not inputs["has_entities"]:
        return ""
    return await client.async_call(
        "step4c_variables_files",
        templates.S4C_SYSTEM,
        templates.render_s4c_user(inputs["entities_text"], inputs["omit_files_text"], inputs.get("types_text", "")),
        model=model,
    )


async def _call_4a_async(client: LLMClient, inputs: dict, symbol_table_text: str, model: str | None = None) -> str:
    """Generate PERSONA / AUDIENCE / CONCEPTS block."""
    return await client.async_call(
        "step4a_persona",
        templates.S4A_SYSTEM,
        templates.render_s4a_user(
            intent_text=inputs["intent_text"],
            notes_text=inputs["notes_text"],
            symbol_table=symbol_table_text,
        ),
        model=model,
    )


async def _call_4b_async(client: LLMClient, inputs: dict, symbol_table_text: str, model: str | None = None) -> str:
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
        model=model,
    )


async def _call_4e_async(client: LLMClient, inputs: dict, symbol_table_text: str, apis_spl: str, model: str | None = None) -> str:
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
    return await client.async_call(step_name="step4e_worker", system=s4e_system, user=s4e_user, model=model)


async def _call_4e1_async(client: LLMClient, worker_spl: str, model: str | None = None) -> dict:
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
        model=model,
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


async def _call_4e2_async(client: LLMClient, worker_spl: str, violations: list, model: str | None = None) -> str:
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
        model=model,
    )


async def _call_4f_async(client: LLMClient, inputs: dict, worker_spl: str, model: str | None = None) -> str:
    """Generate [EXAMPLES] block."""
    return await client.async_call(
        "step4f_examples",
        templates.S4F_SYSTEM,
        templates.render_s4f_user(
            worker_spl=worker_spl,
            examples_text=inputs["examples_text"],
        ),
        model=model,
    )


async def _call_s0_async(client: LLMClient, skill_id: str, intent_text: str, notes_text: str, model: str | None = None) -> str:
    """Generate DEFINE_AGENT header block.

    Args:
        client: LLM client for making calls
        skill_id: The skill identifier
        intent_text: The INTENT section text
        notes_text: The NOTES section text
        model: Optional model override

    Returns:
        The DEFINE_AGENT header line (e.g., "[DEFINE_AGENT: AgentName "description"]")
    """
    return await client.async_call(
        "step0_define_agent",
        templates.S0_SYSTEM,
        templates.render_s0_user(skill_id, intent_text, notes_text),
        model=model,
    )


# ── Sync versions (legacy, kept for backward compatibility) ──────────────────────

def _call_4d(client: LLMClient, tool: dict, model: str | None = None) -> str:
    """Generate DEFINE_APIS block for a single tool.

    DEPRECATED: API generation moved to Step 1.5.
    This function is kept for backward compatibility.
    """
    return ""


def _call_4c(client: LLMClient, inputs: dict, model: str | None = None) -> str:
    """Generate DEFINE_VARIABLES + DEFINE_FILES block."""
    if not inputs["has_entities"]:
        return ""
    return client.call(
        "step4c_variables_files",
        templates.S4C_SYSTEM,
        templates.render_s4c_user(inputs["entities_text"], inputs["omit_files_text"], inputs.get("types_text", "")),
        model=model,
    )


def _call_4a(client: LLMClient, inputs: dict, symbol_table_text: str, model: str | None = None) -> str:
    """Generate PERSONA / AUDIENCE / CONCEPTS block."""
    return client.call(
        "step4a_persona",
        templates.S4A_SYSTEM,
        templates.render_s4a_user(
            intent_text=inputs["intent_text"],
            notes_text=inputs["notes_text"],
            symbol_table=symbol_table_text,
        ),
        model=model,
    )


def _call_4b(client: LLMClient, inputs: dict, symbol_table_text: str, model: str | None = None) -> str:
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
        model=model,
    )


def _call_4e(client: LLMClient, inputs: dict, symbol_table_text: str, apis_spl: str, model: str | None = None) -> str:
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
    return client.call(step_name="step4e_worker", system=s4e_system, user=s4e_user, model=model)


def _call_4f(client: LLMClient, inputs: dict, worker_spl: str, model: str | None = None) -> str:
    """Generate [EXAMPLES] block."""
    return client.call(
        "step4f_examples",
        templates.S4F_SYSTEM,
        templates.render_s4f_user(
            worker_spl=worker_spl,
            examples_text=inputs["examples_text"],
        ),
        model=model,
    )


def _call_s0(client: LLMClient, skill_id: str, intent_text: str, notes_text: str, model: str | None = None) -> str:
    """Generate DEFINE_AGENT header block.

    Args:
        client: LLM client for making calls
        skill_id: The skill identifier
        intent_text: The INTENT section text
        notes_text: The NOTES section text
        model: Optional model override

    Returns:
        The DEFINE_AGENT header line (e.g., "[DEFINE_AGENT: AgentName "description"]")
    """
    return client.call(
        "step0_define_agent",
        templates.S0_SYSTEM,
        templates.render_s0_user(skill_id, intent_text, notes_text),
        model=model,
    )
