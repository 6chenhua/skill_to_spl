"""
Step 3-W: Workflow Structure Analysis
======================================

Extract workflow steps from skill documentation WITHOUT inferring I/O.
This is the first step of the new Step 3 architecture.

Input:
- workflow_section: WORKFLOW text from skill
- tools_section: TOOLS text from skill
- evidence_section: EVIDENCE text from skill
- available_tools: List of tool specifications

Output:
- Step3WOutput with list[WorkflowStepRaw]
"""

import json
import logging
from typing import Any

from models.step3_types import WorkflowStepRaw, Step3WOutput
from pipeline.llm_client import LLMClient
from prompts.step3_w_system import S3W_SYSTEM_V1, render_step3w_user

logger = logging.getLogger(__name__)


async def run_step3w_workflow_analysis(
    workflow_section: str,
    tools_section: str,
    evidence_section: str,
    available_tools: list[dict[str, Any]],
    client: LLMClient,
    model: str = "gpt-4o-mini"
) -> Step3WOutput:
    """
    Run Step 3-W: Workflow Structure Analysis.
    
    Extracts workflow steps without I/O analysis.
    
    Args:
        workflow_section: WORKFLOW section text
        tools_section: TOOLS section text
        evidence_section: EVIDENCE section text
        available_tools: List of available tool specs
        client: LLM client instance
        model: Model name to use
        
    Returns:
        Step3WOutput with workflow_steps, alternative_flows, exception_flows
    """
    logger.info("Starting Step 3-W: Workflow Structure Analysis")
    
    # Format available tools for prompt
    tools_formatted = "\n".join(
        f"- {tool.get('name', 'unknown')}: {tool.get('api_type', 'SCRIPT')}"
        for tool in available_tools
    ) if available_tools else "(No tools available)"
    
    # Build prompt
    system_prompt = S3W_SYSTEM_V1
    user_prompt = render_step3w_user(
        workflow_section=workflow_section,
        available_tools=tools_formatted,
        evidence_section=evidence_section
    )
    
    # Call LLM
    logger.debug("Calling LLM for Step 3-W")
    response = await client.async_call_json(
        step_name="Step3-WorkflowStep-Analysis",
        system=system_prompt,
        user=user_prompt,
        model=model,
    )
    
    # Parse response
    try:
        workflow_steps = _parse_workflow_steps(response.get("workflow_steps", []))
        alternative_flows = _parse_flows(response.get("alternative_flows", []), "alternative")
        exception_flows = _parse_flows(response.get("exception_flows", []), "exception")

        logger.info(
            f"Step 3-W complete: {len(workflow_steps)} steps, "
            f"{len(alternative_flows)} alternatives, "
            f"{len(exception_flows)} exceptions"
        )

        return Step3WOutput(
            workflow_steps=workflow_steps,
            alternative_flows=alternative_flows,
            exception_flows=exception_flows
        )
        
    except Exception as e:
        logger.error(f"Failed to parse Step 3-W response: {e}")
        raise


def _parse_workflow_steps(steps_data: list[dict]) -> list[WorkflowStepRaw]:
    """
    Parse workflow steps from LLM response.
    
    Args:
        steps_data: Raw step data from LLM JSON
        
    Returns:
        List of WorkflowStepRaw objects
    """
    steps = []
    
    for step_data in steps_data:
        try:
            step = WorkflowStepRaw(
                step_id=step_data.get("step_id", ""),
                description=step_data.get("description", ""),
                action_type=step_data.get("action_type", "LLM_TASK"),
                tool_hint=step_data.get("tool_hint", ""),
                is_validation_gate=step_data.get("is_validation_gate", False),
                source_text=step_data.get("source_text", "")
            )
            steps.append(step)
        except Exception as e:
            logger.warning(f"Failed to parse step: {step_data}. Error: {e}")
            continue
    
    return steps


def _parse_flows(flows_data: list[dict], flow_type: str) -> list:
    """
    Parse alternative/exception flows from LLM response.
    
    Args:
        flows_data: Raw flow data from LLM JSON
        flow_type: "alternative" or "exception"
        
    Returns:
        List of AlternativeFlowSpec or ExceptionFlowSpec objects
    """
    from models.data_models import AlternativeFlowSpec, ExceptionFlowSpec
    from models.step3_types import WorkflowStepRaw
    
    flows = []
    
    for flow_data in flows_data:
        try:
            # Parse steps in the flow
            steps_data = flow_data.get("steps", [])
            steps = []
            for step_data in steps_data:
                steps.append(WorkflowStepRaw(
                    step_id=step_data.get("step_id", ""),
                    description=step_data.get("description", ""),
                    action_type=step_data.get("action_type", "LLM_TASK"),
                    tool_hint=step_data.get("tool_hint", ""),
                    is_validation_gate=step_data.get("is_validation_gate", False),
                    source_text=step_data.get("source_text", "")
                ))
            
            if flow_type == "alternative":
                flow = AlternativeFlowSpec(
                    flow_id=flow_data.get("flow_id", ""),
                    condition=flow_data.get("condition", ""),
                    description=flow_data.get("description", ""),
                    steps=steps,
                    source_text=flow_data.get("source_text", ""),
                    provenance=flow_data.get("provenance", "EXPLICIT")
                )
            else:  # exception
                flow = ExceptionFlowSpec(
                    flow_id=flow_data.get("flow_id", ""),
                    condition=flow_data.get("condition", ""),
                    log_ref=flow_data.get("log_ref", ""),
                    steps=steps,
                    source_text=flow_data.get("source_text", ""),
                    provenance=flow_data.get("provenance", "EXPLICIT")
                )
            
            flows.append(flow)
        except Exception as e:
            logger.warning(f"Failed to parse {flow_type} flow: {flow_data}. Error: {e}")
            continue
    
    return flows


def run_step3w_workflow_analysis_sync(
    workflow_section: str,
    tools_section: str,
    evidence_section: str,
    available_tools: list[dict[str, Any]],
    client: LLMClient,
    model: str = "gpt-4o-mini"
) -> Step3WOutput:
    """Synchronous wrapper for run_step3w_workflow_analysis."""
    import asyncio
    return asyncio.run(run_step3w_workflow_analysis(
        workflow_section=workflow_section,
        tools_section=tools_section,
        evidence_section=evidence_section,
        available_tools=available_tools,
        client=client,
        model=model
    ))
