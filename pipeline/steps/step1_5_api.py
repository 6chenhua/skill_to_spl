"""Step 1.5: API Definition Generation step."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from models import APISymbolTable, FunctionSpec, UnifiedAPISpec
from pipeline.llm_steps.step1_5_api_generation import generate_unified_api_definitions
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

        # Get unified_apis from P3 output (now includes both doc APIs and script APIs)
        unified_apis: list[UnifiedAPISpec] = []

        # Try to get from P3 output
        p3_data = inputs.get("p3_assembler", inputs)
        if isinstance(p3_data, dict) and "unified_apis" in p3_data:
            unified_apis_data = p3_data["unified_apis"]
            unified_apis = []
            for u in unified_apis_data:
                # Handle both dict (from checkpoint) and UnifiedAPISpec object (from memory)
                if isinstance(u, dict):
                    # Convert nested functions from dict to FunctionSpec
                    functions_data = u.get("functions", [])
                    functions = [
                        FunctionSpec(**f) if isinstance(f, dict) else f
                        for f in functions_data
                    ]
                    # Create UnifiedAPISpec with converted functions
                    unified_apis.append(UnifiedAPISpec(**{**u, "functions": functions}))
                elif hasattr(u, '__dataclass_fields__') and 'api_id' in u.__dataclass_fields__:
                    # Any UnifiedAPISpec-like dataclass (from models or pre_processing)
                    # Convert to models.UnifiedAPISpec
                    unified_apis.append(UnifiedAPISpec(**u.__dict__))
                else:
                    # Unexpected type, log and skip or convert
                    context.logger.warning(f"Unexpected unified_api type: {type(u)}")

        # Get model override if configured
        model = context.config.get_step_model("step1_5_api_generation")

        # Generate API definitions from unified_apis
        # (now includes both doc-based and script-based APIs)
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
            context.logger.warning(
                "[Step 1.5] No unified APIs found in P3 output"
            )
            api_table = APISymbolTable(apis={}, unified_apis={})

        context.logger.info(
            "[Step 1.5] Generated %d API definitions", len(api_table.apis)
        )

        # Convert to dictionary
        return {
            "apis": {
                name: asdict(spec) for name, spec in api_table.apis.items()
            },
        }
