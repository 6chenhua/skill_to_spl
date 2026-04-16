"""Input preparation functions for Step 4 (v2 with GlobalVarRegistry)."""

from __future__ import annotations

import json
import logging

from models.step3_types import (
    GlobalVarRegistry,
    VarSpec,
    TypeExpr,
    StepIOSpec,
    WorkflowStepRaw
)
from models.data_models import (
    AlternativeFlowSpec,
    ExceptionFlowSpec,
    SectionBundle,
    ToolSpec,
)

logger = logging.getLogger(__name__)


def _prepare_step4_inputs_new(
    bundle: SectionBundle,
    global_registry: GlobalVarRegistry,
    step_io_specs: dict[str, StepIOSpec],
    workflow_steps: list[WorkflowStepRaw],
    alternative_flows: list[AlternativeFlowSpec],
    exception_flows: list[ExceptionFlowSpec],
    types_spl: str,
    type_registry: dict[str, str],
    tools: list[ToolSpec],
) -> tuple[dict, dict, dict, dict, dict, dict, dict]:
    """
    Pre-compute all inputs for Step 4 calls with new type system.

    Args:
        bundle: SectionBundle with source text
        global_registry: GlobalVarRegistry from Step 3-IO
        step_io_specs: Per-step I/O specs from Step 3-IO
        workflow_steps: Raw workflow steps from Step 3-W
        alternative_flows: Alternative flow specs
        exception_flows: Exception flow specs
        types_spl: SPL TYPES block from Step 3-T
        type_registry: Mapping of signatures to type names
        tools: Tool specifications

    Returns:
        7 dictionaries for each S4x call + types
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

    # S4C inputs - use new registry-based format
    variables_text = _format_variables_for_s4c(global_registry.variables, type_registry)
    files_text = _format_files_for_s4c(global_registry.files, type_registry)
    s4c_inputs = {
        "variables_text": variables_text,
        "files_text": files_text,
        "types_spl": types_spl,
        "has_variables": bool(global_registry.variables),
        "has_files": bool(global_registry.files),
        "has_types": bool(types_spl),
    }

    # S4D inputs
    tools_list = [
        {
            "name": t.name,
            "api_type": t.api_type,
            "url": t.url,
            "authentication": t.authentication,
            "input_schema": t.input_schema,
            "output_schema": t.output_schema,
            "description": t.description,
            "source_text": t.source_text[:500] if len(t.source_text) > 500 else t.source_text
        }
        for t in tools
    ]
    s4d_inputs = {
        "tools_list": tools_list,
        "has_tools": bool(tools),
    }

    # S4E inputs - include typed I/O specs
    workflow_steps_json = json.dumps(
        [_workflow_raw_to_dict(s, step_io_specs.get(s.step_id)) for s in workflow_steps],
        indent=2, ensure_ascii=False,
    )
    workflow_prose = bundle.to_text(["WORKFLOW"])
    alternative_flows_json = json.dumps(
        [_flow_to_dict(f) for f in alternative_flows],
        indent=2, ensure_ascii=False,
    )
    exception_flows_json = json.dumps(
        [_flow_to_dict(f) for f in exception_flows],
        indent=2, ensure_ascii=False,
    )
    s4e_inputs = {
        "workflow_steps_json": workflow_steps_json,
        "workflow_prose": workflow_prose,
        "alternative_flows_json": alternative_flows_json,
        "exception_flows_json": exception_flows_json,
        "tools_list": tools_list,
        "type_registry": type_registry,  # Pass type names for typed I/O
    }

    # S4F inputs
    examples_text = bundle.to_text(["EXAMPLES"])
    s4f_inputs = {
        "examples_text": examples_text,
        "has_examples": bool(examples_text.strip()),
    }

    # Types input (for symbol table)
    types_inputs = {
        "types_spl": types_spl,
        "has_types": bool(types_spl),
    }

    return s4a_inputs, s4b_inputs, s4c_inputs, s4d_inputs, s4e_inputs, s4f_inputs, types_inputs


def _format_variables_for_s4c(
    variables: dict[str, VarSpec],
    type_registry: dict[str, str]
) -> str:
    """Format variables for S4C prompt with types."""
    if not variables:
        return "(No variables found)"

    lines = ["VARIABLES (in-memory data structures -> DEFINE_VARIABLES):"]
    lines.append("")

    for var_name, var_spec in sorted(variables.items()):
        # Get type name from registry or use inline SPL
        type_name = _get_type_display(var_spec.type_expr, type_registry)

        lines.append(f"Variable: {var_name}")
        lines.append(f"Type: {type_name}")
        if var_spec.description:
            lines.append(f"Description: {var_spec.description}")
        lines.append("")

    return "\n".join(lines)


def _format_files_for_s4c(
    files: dict[str, VarSpec],
    type_registry: dict[str, str]
) -> str:
    """Format files for S4C prompt with types."""
    if not files:
        return "(No files found)"

    lines = ["FILES (disk artifacts -> DEFINE_FILES):"]
    lines.append("")

    for var_name, var_spec in sorted(files.items()):
        # Get type name from registry or use inline SPL
        type_name = _get_type_display(var_spec.type_expr, type_registry)

        lines.append(f"File: {var_name}")
        lines.append(f"Type: {type_name}")
        if var_spec.description:
            lines.append(f"Description: {var_spec.description}")
        lines.append("")

    return "\n".join(lines)


def _get_type_display(type_expr: TypeExpr, type_registry: dict[str, str]) -> str:
    """Get display string for type (declared name or inline SPL)."""
    signature = type_expr.to_signature()
    if signature in type_registry:
        return type_registry[signature]  # Use declared name
    return type_expr.to_spl()  # Use inline SPL


def _workflow_raw_to_dict(
    step: WorkflowStepRaw,
    io_spec: StepIOSpec | None
) -> dict:
    """Convert WorkflowStepRaw + StepIOSpec to dict for S4E."""
    result = {
        "step_id": step.step_id,
        "description": step.description,
        "action_type": step.action_type,
        "tool_hint": step.tool_hint,
        "is_validation_gate": step.is_validation_gate,
        "source_text": step.source_text,
    }

    # Add typed I/O if available
    if io_spec:
        result["prerequisites"] = {
            name: {
                "type": spec.type_expr.to_spl(),
                "is_file": spec.is_file
            }
            for name, spec in io_spec.prerequisites.items()
        }
        result["produces"] = {
            name: {
                "type": spec.type_expr.to_spl(),
                "is_file": spec.is_file
            }
            for name, spec in io_spec.produces.items()
        }
    else:
        result["prerequisites"] = {}
        result["produces"] = {}

    return result


def _flow_to_dict(flow) -> dict:
    """Convert flow spec to dict."""
    return {
        "flow_id": flow.flow_id,
        "condition": flow.condition,
        "description": getattr(flow, "description", ""),
        "steps": [
            {
                "description": step.description,
                "action_type": step.action_type,
                "tool_hint": step.tool_hint,
                "source_text": step.source_text,
            }
            for step in flow.steps
        ] if hasattr(flow, "steps") else [],
        "source_text": flow.source_text,
    }
