"""Sequential runner - executes steps one at a time."""
from __future__ import annotations

import logging
from typing import Any

from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.runners.base import Runner
from pipeline.orchestrator.step_executor import StepExecutor
from pipeline.orchestrator.step_registry import registry

logger = logging.getLogger(__name__)


class SequentialRunner(Runner):
    """Sequential runner - executes steps in order.

    Each step waits for all its dependencies to complete before executing.
    Simplest execution strategy with predictable behavior.

    Example:
        runner = SequentialRunner(executor)
        results = runner.run(execution_plan, context, inputs)
    """

    def __init__(self, executor: StepExecutor):
        """Initialize sequential runner.

        Args:
            executor: Step executor
        """
        super().__init__(executor)

    def run(
        self,
        execution_plan: list[str],
        context: ExecutionContext,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute steps sequentially.

        Args:
            execution_plan: Topologically sorted step names
            context: Execution context
            inputs: Initial inputs

        Returns:
            Dictionary of step outputs

        Raises:
            RuntimeError: If any step fails
        """
        results: dict[str, Any] = {}
        current_inputs = inputs.copy()

        logger.info("Starting sequential execution of %d steps", len(execution_plan))

        for step_name in execution_plan:
            step_class = registry.get(step_name)
            step = step_class()

            # Prepare inputs from dependencies
            step_inputs = self._prepare_step_inputs(
                step, results, current_inputs
            )

            # Execute
            result = self.executor.execute(step, context, step_inputs)

            if not result.success:
                raise RuntimeError(
                    f"Step '{step_name}' failed: {result.error}"
                )

            results[step_name] = result.output
            logger.debug("Step %s completed", step_name)

        logger.info("Sequential execution complete: %d steps", len(results))
        return results

    def _prepare_step_inputs(
        self,
        step: "PipelineStep",
        previous_results: dict[str, Any],
        initial_inputs: dict[str, Any],
    ) -> Any:
        """Prepare inputs for a step based on dependencies.

        Args:
            step: The step
            previous_results: Results from previous steps
            initial_inputs: Initial pipeline inputs

        Returns:
            Step inputs
        """
        # If no dependencies, use initial inputs
        if not step.dependencies:
            return initial_inputs

        # If single dependency, return that dependency's output directly
        if len(step.dependencies) == 1:
            dep_name = step.dependencies[0]
            return previous_results.get(dep_name)

        # Multiple dependencies - return dict of dependency outputs
        return {dep: previous_results.get(dep) for dep in step.dependencies}
