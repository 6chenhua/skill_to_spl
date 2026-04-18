"""Runner base class."""
from __future__ import annotations

import abc
from typing import Any

from pipeline.orchestrator.base import PipelineStep
from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.step_executor import StepExecutor


class Runner(abc.ABC):
    """Abstract base class for pipeline runners.

    Runners implement different execution strategies:
    - SequentialRunner: Execute steps one at a time
    - ParallelRunner: Execute independent steps in parallel

    Example:
        runner = SequentialRunner(executor)
        results = runner.run(execution_plan, context, inputs)
    """

    def __init__(self, executor: StepExecutor):
        """Initialize runner.

        Args:
            executor: Step executor for running individual steps
        """
        self.executor = executor

    @abc.abstractmethod
    def run(
        self,
        execution_plan: list[str],
        context: ExecutionContext,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the pipeline.

        Args:
            execution_plan: Topologically sorted list of step names
            context: Execution context
            inputs: Initial input data

        Returns:
            Dictionary of all step outputs keyed by step name
        """
        ...

    def _prepare_step_inputs(
        self,
        step: "PipelineStep",
        previous_results: dict[str, Any],
        initial_inputs: dict[str, Any],
    ) -> Any:
        """Prepare inputs for a step based on its dependencies.

        Args:
            step: The step instance
            previous_results: Results from previous steps
            initial_inputs: Initial pipeline inputs

        Returns:
            Prepared inputs for the step
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
