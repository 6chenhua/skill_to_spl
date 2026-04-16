"""
Step 3-IO: Global I/O + Type Analysis
======================================

Analyze all workflow steps together to ensure type consistency.

Input:
- list[WorkflowStepRaw] from Step 3-W
- workflow_text: Original text for context
- artifacts_text: For file identification

Output:
- Step3IOOutput with per-step I/O specs and global registry
"""

import json
import logging
from typing import Any

from models.step3_types import (
    Step3IOOutput,
    StepIOSpec,
    VarSpec,
    GlobalVarRegistry,
    WorkflowStepRaw,
    TypeExpr
)
from pipeline.llm_client import LLMClient
from prompts.step3_io_system import S3IO_SYSTEM_V1, render_step3io_user

logger = logging.getLogger(__name__)


async def run_step3io_global_analysis(
    workflow_steps: list[WorkflowStepRaw],
    workflow_text: str,
    artifacts_text: str,
    client: LLMClient,
    model: str = "gpt-4o-mini"
) -> Step3IOOutput:
    """
    Run Step 3-IO: Global I/O + Type Analysis.
    
    Analyzes ALL steps together to ensure type consistency.
    
    Args:
        workflow_steps: Steps from Step 3-W
        workflow_text: Original workflow text
        artifacts_text: Artifacts section text
        client: LLM client
        model: Model name
        
    Returns:
        Step3IOOutput with step_io_specs and global_registry
    """
    logger.info(f"Starting Step 3-IO: Global analysis of {len(workflow_steps)} steps")
    
    # Format steps for prompt
    steps_formatted = _format_steps_for_prompt(workflow_steps)
    
    # Build prompt
    system_prompt = S3IO_SYSTEM_V1
    user_prompt = render_step3io_user(
        workflow_steps=steps_formatted,
        workflow_text=workflow_text,
        artifacts_text=artifacts_text
    )
    
    # Call LLM (async version)
    logger.debug("Calling LLM for Step 3-IO")
    response = await client.async_call_json(
        step_name="step3io",
        system=system_prompt,
        user=user_prompt,
        model=model,
    )
    
    # Parse response
    try:
        step_io_specs = _parse_step_io_specs(response.get("step_io_specs", {}))
        global_vars = _parse_global_vars(response.get("global_vars", []))
        
        # Build global registry
        global_registry = GlobalVarRegistry()
        for var_data in global_vars:
            var_spec = _create_var_spec(var_data)
            global_registry.register(var_spec)
        
        logger.info(
            f"Step 3-IO complete: {len(step_io_specs)} step specs, "
            f"{len(global_registry.variables)} vars, "
            f"{len(global_registry.files)} files"
        )
        
        return Step3IOOutput(
            step_io_specs=step_io_specs,
            global_registry=global_registry
        )
        
    except Exception as e:
        logger.error(f"Failed to parse Step 3-IO response: {e}")
        raise


def _format_steps_for_prompt(steps: list[WorkflowStepRaw]) -> str:
    """Format steps for LLM prompt."""
    lines = []
    for step in steps:
        lines.append(f"Step: {step.step_id}")
        lines.append(f"  Description: {step.description}")
        lines.append(f"  Action Type: {step.action_type}")
        lines.append(f"  Tool Hint: {step.tool_hint}")
        lines.append("")
    return "\n".join(lines)


def _parse_step_io_specs(specs_data: dict) -> dict[str, StepIOSpec]:
    """Parse step I/O specifications from LLM response."""
    specs = {}
    
    for step_id, step_data in specs_data.items():
        try:
            prerequisites = {}
            produces = {}
            
            for var_name, var_data in step_data.get("prerequisites", {}).items():
                prerequisites[var_name] = _create_var_spec({
                    "var_name": var_name,
                    **var_data
                })
            
            for var_name, var_data in step_data.get("produces", {}).items():
                produces[var_name] = _create_var_spec({
                    "var_name": var_name,
                    **var_data
                })
            
            specs[step_id] = StepIOSpec(
                step_id=step_id,
                prerequisites=prerequisites,
                produces=produces
            )
        except Exception as e:
            logger.warning(f"Failed to parse step spec for {step_id}: {e}")
            continue
    
    return specs


def _parse_global_vars(vars_data: list[dict]) -> list[dict]:
    """Parse global variables from LLM response."""
    return vars_data


def _create_var_spec(var_data: dict) -> VarSpec:
    """Create VarSpec from parsed data."""
    type_expr = _parse_type_expression(var_data.get("type", "text"))
    
    return VarSpec(
        var_name=var_data.get("var_name", "unknown"),
        type_expr=type_expr,
        is_file=var_data.get("is_file", False),
        description=var_data.get("description", "")
    )


def _parse_type_expression(type_str: str | dict | list) -> TypeExpr:
    """Parse type expression from various formats."""
    if isinstance(type_str, str):
        # Try to parse as JSON first
        try:
            parsed = json.loads(type_str)
            if isinstance(parsed, (list, dict)):
                return TypeExpr.from_dict(parsed)
        except:
            pass
        
        # Handle array shorthand
        if type_str.startswith("List[") and type_str.endswith("]"):
            inner = type_str[5:-1]
            return TypeExpr.array(_parse_type_expression(inner))
        
        # Simple types
        if type_str in ("text", "image", "audio", "number", "boolean"):
            return TypeExpr.simple(type_str)
        
        # Default to text
        return TypeExpr.simple("text")
    
    elif isinstance(type_str, list):
        return TypeExpr.enum(type_str)
    
    elif isinstance(type_str, dict):
        return TypeExpr.from_dict(type_str)
    
    return TypeExpr.simple("text")


def run_step3io_global_analysis_sync(
    workflow_steps: list[WorkflowStepRaw],
    workflow_text: str,
    artifacts_text: str,
    client: LLMClient,
    model: str = "gpt-4o-mini"
) -> Step3IOOutput:
    """Synchronous wrapper for run_step3io_global_analysis."""
    import asyncio
    return asyncio.run(run_step3io_global_analysis(
        workflow_steps=workflow_steps,
        workflow_text=workflow_text,
        artifacts_text=artifacts_text,
        client=client,
        model=model
    ))
