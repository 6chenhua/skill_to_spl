"""
Step 3 New Orchestrator
=======================

Orchestrates the new Step 3 architecture:
Step3-W -> Step3-IO -> Step3-T

Input:
- workflow_section
- tools_section
- evidence_section
- artifacts_section
- available_tools

Output:
- Combined output with workflow, I/O specs, types, and registry
"""

import logging
from typing import Any

from models.step3_types import (
    Step3WOutput,
    Step3IOOutput,
    Step3TOutput,
    WorkflowStepRaw
)
from pipeline.llm_client import LLMClient
from .w import run_step3w_workflow_analysis
from .io import run_step3io_global_analysis
from .t import run_step3t_types_declaration

logger = logging.getLogger(__name__)


async def run_step3_full(
    workflow_section: str,
    tools_section: str,
    evidence_section: str,
    artifacts_section: str,
    available_tools: list[dict[str, Any]],
    client: LLMClient,
    model: str = "gpt-4o-mini"
) -> dict[str, Any]:
    """
    Run complete Step 3: W -> IO -> T.
    
    Args:
        workflow_section: WORKFLOW text
        tools_section: TOOLS text
        evidence_section: EVIDENCE text
        artifacts_section: ARTIFACTS text
        available_tools: List of tool specs
        client: LLM client
        model: Model name
        
    Returns:
        Combined output dict with all Step 3 results
    """
    logger.info("=" * 60)
    logger.info("Starting Step 3 Full (W -> IO -> T)")
    logger.info("=" * 60)
    
    # Step 3-W: Workflow Structure Analysis
    logger.info("[Step 3-W] Workflow Structure Analysis")
    step3w_output = await run_step3w_workflow_analysis(
        workflow_section=workflow_section,
        tools_section=tools_section,
        evidence_section=evidence_section,
        available_tools=available_tools,
        client=client,
        model=model
    )
    logger.info(f"[Step 3-W] Extracted {len(step3w_output.workflow_steps)} steps")
    
    # Step 3-IO: Global I/O + Type Analysis
    logger.info("[Step 3-IO] Global I/O + Type Analysis")
    step3io_output = await run_step3io_global_analysis(
        workflow_steps=step3w_output.workflow_steps,
        workflow_text=workflow_section,
        artifacts_text=artifacts_section,
        client=client,
        model=model
    )
    logger.info(
        f"[Step 3-IO] Analyzed {len(step3io_output.step_io_specs)} steps, "
        f"{len(step3io_output.global_registry.variables)} vars, "
        f"{len(step3io_output.global_registry.files)} files"
    )
    
    # Step 3-T: TYPES Declaration
    logger.info("[Step 3-T] TYPES Declaration")
    step3t_output = await run_step3t_types_declaration(
        registry=step3io_output.global_registry
    )
    if step3t_output.types_spl:
        logger.info(f"[Step 3-T] Generated {len(step3t_output.declared_names)} type declarations")
    else:
        logger.info("[Step 3-T] No complex types to declare")
    
    logger.info("=" * 60)
    logger.info("Step 3 Complete")
    logger.info("=" * 60)
    
    return {
        # From Step 3-W
        "workflow_steps": step3w_output.workflow_steps,
        "alternative_flows": step3w_output.alternative_flows,
        "exception_flows": step3w_output.exception_flows,
        
        # From Step 3-IO
        "step_io_specs": step3io_output.step_io_specs,
        "global_registry": step3io_output.global_registry,
        
        # From Step 3-T
        "types_spl": step3t_output.types_spl,
        "type_registry": step3t_output.type_registry,
        "declared_names": step3t_output.declared_names
    }


def run_step3_full_sync(
    workflow_section: str,
    tools_section: str,
    evidence_section: str,
    artifacts_section: str,
    available_tools: list[dict[str, Any]],
    client: LLMClient,
    model: str = "gpt-4o-mini"
) -> dict[str, Any]:
    """Synchronous wrapper for run_step3_full."""
    import asyncio
    return asyncio.run(run_step3_full(
        workflow_section=workflow_section,
        tools_section=tools_section,
        evidence_section=evidence_section,
        artifacts_section=artifacts_section,
        available_tools=available_tools,
        client=client,
        model=model
    ))
