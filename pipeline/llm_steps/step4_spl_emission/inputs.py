"""Input preparation functions for Step 4."""

from __future__ import annotations

import dataclasses
import json
import logging

from models.data_models import (
    AlternativeFlowSpec,
    EntitySpec,
    ExceptionFlowSpec,
    SectionBundle,
    StructuredSpec,
    WorkflowStepSpec,
)

logger = logging.getLogger(__name__)


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
    files = [e for e in entities if e.kind == "Artifact"]
    lines = []

    if variables:
        lines.append("VARIABLES (in-memory data structures -> DEFINE_VARIABLES):")
        lines.append("")
        for e in variables:
            readonly = "[READONLY] " if e.provenance_required else ""
            lines.append(f"Variable: {readonly}{e.entity_id}")
            lines.append(f"Type: {e.type_name}")
            lines.append(f"Kind: {e.kind}")
            if e.schema_notes:
                lines.append(f"Schema: {e.schema_notes}")
            lines.append(f"Provenance: {e.provenance}")
            if e.source_text:
                lines.append(f"Source: {e.source_text[:120]}")
            lines.append("")

    if files:
        lines.append("FILES (disk artifacts -> DEFINE_FILES):")
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
        lines.append(f" Type: {e.type_name}")
        lines.append(f" Kind: {e.kind}")
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
