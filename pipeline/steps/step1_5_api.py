"""Step 1.5: API Definition Generation step."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from models import APISymbolTable, FunctionSpec, ToolSpec, UnifiedAPISpec
from pipeline.llm_steps.step1_5_api_generation import (
    generate_api_definitions,
    generate_unified_api_definitions,
)
from pipeline.orchestrator.base import PipelineStep
from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.step_registry import registry


@registry.register
class Step1_5APIGenStep(PipelineStep[dict, dict]):
    """Step 1.5: Generate API definitions for all tools.

    Runs in parallel: one LLM call per tool.
    Generates DEFINE_API blocks and builds APISymbolTable.

    Input:
    Dictionary with:
    - step1_output: Step 1 output dict
    - p3_output: P3 output dict (for tools)

    Output:
    Dictionary containing APISymbolTable as dict:
    - apis: Dict mapping API name to APISpec dict
    """

    @property
    def name(self) -> str:
        """Step name for logging and checkpointing."""
        return "step1_5_api"

    @property
    def dependencies(self) -> list[str]:
        """Step 1.5 depends on Step 1 output."""
        return ["step1_structure", "p3_assembler"]

    def execute(self, context: ExecutionContext, inputs: dict) -> dict:
        """Generate API definitions.

        Args:
        context: Execution context with LLM client
        inputs: Dictionary with step outputs

        Returns:
        Dictionary with API symbol table
        """
        context.logger.info("[Step 1.5] Generating API definitions...")

        # Get tools from inputs - try different sources
        tools: list[ToolSpec] = []
        unified_apis: list[UnifiedAPISpec] = []

        # Try to get from P3 output
        p3_data = inputs.get("p3_assembler", inputs)
        if isinstance(p3_data, dict) and "tools" in p3_data:
            tools = [ToolSpec(**t) for t in p3_data["tools"]]
        if "unified_apis" in p3_data:
            unified_apis_data = p3_data["unified_apis"]
            unified_apis = []
            for u in unified_apis_data:
                # Convert nested functions from dict to FunctionSpec
                functions_data = u.get("functions", [])
                functions = [
                    FunctionSpec(**f) if isinstance(f, dict) else f
                    for f in functions_data
                ]
                # Create UnifiedAPISpec with converted functions
                unified_apis.append(UnifiedAPISpec(**{**u, "functions": functions}))

        # Try to get network APIs from Step 1
        step1_data = inputs.get("step1_structure", {})
        if isinstance(step1_data, dict) and "network_apis" in step1_data:
            network_apis = [ToolSpec(**t) for t in step1_data["network_apis"]]
            tools.extend(network_apis)

        # Get model override if configured
        model = context.config.get_step_model("step1_5_api_generation")

        # Generate API definitions
        if unified_apis:
            context.logger.info(
                "[Step 1.5] Using unified API extraction (%d unified APIs)",
                len(unified_apis),
            )
            api_table = generate_unified_api_definitions(
                unified_apis=unified_apis,
                client=context.client,
                max_workers=context.config.max_parallel_workers,
                model=model,
            )
        else:
            context.logger.info(
                "[Step 1.5] Using legacy tool-based API generation (%d tools)",
                len(tools),
            )
            api_table = generate_api_definitions(
                tools=tools,
                client=context.client,
                max_workers=context.config.max_parallel_workers,
                model=model,
            )

        context.logger.info(
            "[Step 1.5] Generated %d API definitions", len(api_table.apis)
        )

        # Convert to dictionary
        return {
            "apis": {
                name: asdict(spec) for name, spec in api_table.apis.items()
            },
        }
