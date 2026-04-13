"""
Simplified pipeline steps implementation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .models import (
    AlternativeFlowSpec,
    ExceptionFlowSpec,
    FlowStep,
    SectionBundle,
    SectionItem,
    SPLSpec,
    StructuredSpec,
    VariableSpec,
    WorkflowStepSpec,
)
from .llm_client import LLMClient
from . import prompts

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# STEP 1: Structure Extraction (5 sections only)
# ═════════════════════════════════════════════════════════════════════════════

def run_step1_structure_extraction(
    merged_doc_text: str,
    client: LLMClient
) -> SectionBundle:
    """
    Step 1: Parse merged document into 5 canonical sections.
    
    Extracts: INTENT, WORKFLOW, CONSTRAINTS, EXAMPLES, NOTES
    """
    user_prompt = prompts.render_step1_user(merged_doc_text)
    
    raw = client.call_json(
        step_name="step1_structure_extraction",
        system=prompts.STEP1_SYSTEM,
        user=user_prompt,
    )
    
    bundle = _parse_section_bundle(raw)
    total = sum(len(getattr(bundle, s.lower())) for s in [
        "INTENT", "WORKFLOW", "CONSTRAINTS", "EXAMPLES", "NOTES"
    ])
    logger.info(f"[Step 1] Extracted {total} items across 5 sections")
    return bundle


def _parse_section_bundle(raw: dict) -> SectionBundle:
    """Convert the LLM JSON response into a SectionBundle."""
    def parse_items(key: str) -> list[SectionItem]:
        items = raw.get(key, raw.get(key.lower(), []))
        result = []
        for item in items:
            if isinstance(item, dict):
                result.append(SectionItem(
                    text=item.get("text", ""),
                    source=item.get("source", "unknown"),
                    multi=item.get("multi", False),
                ))
            elif isinstance(item, str):
                result.append(SectionItem(text=item, source="unknown"))
        return result
    
    return SectionBundle(
        intent=parse_items("INTENT"),
        workflow=parse_items("WORKFLOW"),
        constraints=parse_items("CONSTRAINTS"),
        examples=parse_items("EXAMPLES"),
        notes=parse_items("NOTES"),
    )


# ═════════════════════════════════════════════════════════════════════════════
# STEP 3A: Variable Extraction (No files)
# ═════════════════════════════════════════════════════════════════════════════

def run_step3a_variable_extraction(
    bundle: SectionBundle,
    client: LLMClient
) -> list[VariableSpec]:
    """
    Step 3A: Extract variables (in-memory data only, no files).
    """
    user_prompt = prompts.render_step3a_user(
        workflow_section=bundle.to_text(["WORKFLOW"]),
        examples_section=bundle.to_text(["EXAMPLES"]),
    )
    
    raw = client.call_json(
        step_name="step3a_variable_extraction",
        system=prompts.STEP3A_SYSTEM,
        user=user_prompt,
    )
    
    variables = _parse_variables(raw.get("variables", []))
    logger.info(f"[Step 3A] Extracted {len(variables)} variables")
    return variables


def _parse_variables(items: list) -> list[VariableSpec]:
    """Parse variable specifications from JSON."""
    parsed = []
    for item in items:
        parsed.append(VariableSpec(
            var_id=item.get("var_id", ""),
            type_name=item.get("type_name", ""),
            schema_notes=item.get("schema_notes", ""),
            provenance_required=bool(item.get("provenance_required", False)),
            provenance=item.get("provenance", "LOW_CONFIDENCE"),
            source_text=item.get("source_text", ""),
        ))
    return parsed


# ═════════════════════════════════════════════════════════════════════════════
# STEP 3B: Workflow Analysis (Simplified action types)
# ═════════════════════════════════════════════════════════════════════════════

def run_step3b_workflow_analysis(
    bundle: SectionBundle,
    var_ids: list[str],
    client: LLMClient
) -> StructuredSpec:
    """
    Step 3B: Extract workflow steps, flows with simplified action types.
    
    Action types: LLM_TASK | FILE_READ | FILE_WRITE | USER_INTERACTION
    No EXTERNAL_API, EXEC_SCRIPT, LOCAL_CODE_SNIPPET.
    """
    user_prompt = prompts.render_step3b_user(
        var_ids_json=json.dumps(var_ids, indent=2),
        workflow_section=bundle.to_text(["WORKFLOW"]),
        constraints_section=bundle.to_text(["CONSTRAINTS"]),
    )
    
    raw = client.call_json(
        step_name="step3b_workflow_analysis",
        system=prompts.STEP3B_SYSTEM,
        user=user_prompt,
    )
    
    spec = StructuredSpec(
        variables=[],  # Filled by caller
        workflow_steps=_parse_workflow_steps(raw.get("workflow_steps", [])),
        alternative_flows=_parse_alternative_flows(raw.get("alternative_flows", [])),
        exception_flows=_parse_exception_flows(raw.get("exception_flows", [])),
    )
    
    val_gates = sum(1 for s in spec.workflow_steps if s.is_validation_gate)
    logger.info(
        f"[Step 3B] {len(spec.workflow_steps)} steps ({val_gates} validation gates), "
        f"{len(spec.alternative_flows)} alt-flows, {len(spec.exception_flows)} exc-flows"
    )
    return spec


def _parse_workflow_steps(items: list) -> list[WorkflowStepSpec]:
    """Parse workflow step specifications."""
    return [
        WorkflowStepSpec(
            step_id=item.get("step_id", ""),
            description=item.get("description", ""),
            prerequisites=item.get("prerequisites", []),
            produces=item.get("produces", []),
            is_validation_gate=bool(item.get("is_validation_gate", False)),
            action_type=item.get("action_type", "LLM_TASK"),
            source_text=item.get("source_text", ""),
        )
        for item in items
    ]


def _parse_flow_step(item: dict) -> FlowStep:
    """Parse a flow step."""
    return FlowStep(
        description=item.get("description", ""),
        action_type=item.get("action_type", "LLM_TASK"),
        source_text=item.get("source_text", ""),
    )


def _parse_alternative_flows(items: list) -> list[AlternativeFlowSpec]:
    """Parse alternative flow specifications."""
    return [
        AlternativeFlowSpec(
            flow_id=item.get("flow_id", f"alt-{i:03d}"),
            condition=item.get("condition", ""),
            description=item.get("description", ""),
            steps=[_parse_flow_step(s) for s in item.get("steps", [])],
            source_text=item.get("source_text", ""),
            provenance=item.get("provenance", "EXPLICIT"),
        )
        for i, item in enumerate(items)
    ]


def _parse_exception_flows(items: list) -> list[ExceptionFlowSpec]:
    """Parse exception flow specifications."""
    return [
        ExceptionFlowSpec(
            flow_id=item.get("flow_id", f"exc-{i:03d}"),
            condition=item.get("condition", ""),
            log_ref=item.get("log_ref", ""),
            steps=[_parse_flow_step(s) for s in item.get("steps", [])],
            source_text=item.get("source_text", ""),
            provenance=item.get("provenance", "EXPLICIT"),
        )
        for i, item in enumerate(items)
    ]


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4: SPL Emission (Simplified - no APIs, no files)
# ═════════════════════════════════════════════════════════════════════════════

def run_step4_spl_emission(
    skill_id: str,
    bundle: SectionBundle,
    spec: StructuredSpec,
    client: LLMClient
) -> SPLSpec:
    """
    Step 4: Emit simplified SPL specification.
    
    Generates:
    - 4a: PERSONA / AUDIENCE / CONCEPTS
    - 4b: CONSTRAINTS
    - 4c: VARIABLES only (no FILES)
    - 4e: WORKER (no API calls, no file declarations)
    
    Skips: 4d (APIS) - no external APIs in simplified pipeline
    """
    # Prepare inputs
    variables_list = ", ".join(v.var_id for v in spec.variables) if spec.variables else "(none)"
    
    # Generate blocks
    block_4a = _call_4a(client, bundle, variables_list)
    block_4b = _call_4b(client, bundle, variables_list)
    block_4c = _call_4c(client, spec.variables)
    block_4e = _call_4e(client, spec, variables_list)
    
    # Assemble final SPL
    spl_text = _assemble_spl(skill_id, block_4a, block_4b, block_4c, block_4e)
    
    logger.info(f"[Step 4] SPL assembled ({len(spl_text)} chars)")
    return SPLSpec(skill_id=skill_id, spl_text=spl_text)


def _call_4a(client: LLMClient, bundle: SectionBundle, variables_list: str) -> str:
    """Generate PERSONA / AUDIENCE / CONCEPTS block."""
    user = prompts.render_step4a_user(
        intent_text=bundle.to_text(["INTENT"]),
        notes_text=bundle.to_text(["NOTES"]),
        variables_list=variables_list,
    )
    return client.call("step4a_persona", prompts.STEP4A_SYSTEM, user)


def _call_4b(client: LLMClient, bundle: SectionBundle, variables_list: str) -> str:
    """Generate CONSTRAINTS block."""
    constraints_text = bundle.to_text(["CONSTRAINTS"])
    if not constraints_text.strip():
        return "[DEFINE_CONSTRAINTS:]\n[END_CONSTRAINTS]"
    
    user = prompts.render_step4b_user(
        constraints_text=constraints_text,
        variables_list=variables_list,
    )
    return client.call("step4b_constraints", prompts.STEP4B_SYSTEM, user)


def _call_4c(client: LLMClient, variables: list[VariableSpec]) -> str:
    """Generate VARIABLES block (no files)."""
    if not variables:
        return ""
    
    variables_json = json.dumps([
        {
            "var_id": v.var_id,
            "type_name": v.type_name,
            "schema_notes": v.schema_notes,
            "provenance_required": v.provenance_required,
            "provenance": v.provenance,
        }
        for v in variables
    ], indent=2)
    
    user = prompts.render_step4c_user(variables_json)
    return client.call("step4c_variables", prompts.STEP4C_SYSTEM, user)


def _call_4e(
    client: LLMClient,
    spec: StructuredSpec,
    variables_list: str
) -> str:
    """Generate WORKER block."""
    workflow_steps_json = json.dumps([
        {
            "step_id": s.step_id,
            "description": s.description,
            "prerequisites": s.prerequisites,
            "produces": s.produces,
            "is_validation_gate": s.is_validation_gate,
            "action_type": s.action_type,
        }
        for s in spec.workflow_steps
    ], indent=2)
    
    alternative_flows_json = json.dumps([
        {
            "flow_id": f.flow_id,
            "condition": f.condition,
            "description": f.description,
            "steps": [
                {"description": s.description, "action_type": s.action_type}
                for s in f.steps
            ],
        }
        for f in spec.alternative_flows
    ], indent=2) if spec.alternative_flows else "[]"
    
    exception_flows_json = json.dumps([
        {
            "flow_id": f.flow_id,
            "condition": f.condition,
            "log_ref": f.log_ref,
            "steps": [
                {"description": s.description, "action_type": s.action_type}
                for s in f.steps
            ],
        }
        for f in spec.exception_flows
    ], indent=2) if spec.exception_flows else "[]"
    
    user = prompts.render_step4e_user(
        workflow_steps_json=workflow_steps_json,
        alternative_flows_json=alternative_flows_json,
        exception_flows_json=exception_flows_json,
        variables_list=variables_list,
    )
    
    # S4E_SYSTEM needs variables list injected
    system = prompts.STEP4E_SYSTEM.replace("{{variables_list}}", variables_list)
    return client.call("step4e_worker", system, user)


def _assemble_spl(
    skill_id: str,
    block_4a: str,
    block_4b: str,
    block_4c: str,
    block_4e: str,
) -> str:
    """Concatenate all blocks in canonical SPL order."""
    header = f"# SPL specification — {skill_id}\n# Generated by simplified pipeline\n"
    
    blocks = [header]
    
    for block in (block_4a, block_4b, block_4c):
        cleaned = _strip_fences(block.strip())
        if cleaned:
            blocks.append(cleaned)
    
    # Add WORKER block
    worker_cleaned = _strip_fences(block_4e.strip())
    if worker_cleaned:
        blocks.append(worker_cleaned)
    
    return "\n\n".join(blocks)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences."""
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
