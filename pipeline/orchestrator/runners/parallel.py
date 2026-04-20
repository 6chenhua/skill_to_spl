"""Parallel runner - executes independent steps in parallel."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.runners.base import Runner
from pipeline.orchestrator.step_executor import StepExecutor
from pipeline.orchestrator.step_registry import registry

logger = logging.getLogger(__name__)


class ParallelRunner(Runner):
    """Parallel runner - executes independent steps concurrently.

    Uses ThreadPoolExecutor to run steps that don't depend on each other
    in parallel. Respects dependency ordering.

    Example:
        runner = ParallelRunner(executor, max_workers=4)
        results = runner.run(execution_plan, context, inputs)
    """

    def __init__(self, executor: StepExecutor, max_workers: int = 4):
        """Initialize parallel runner.

        Args:
            executor: Step executor
            max_workers: Maximum number of parallel workers
        """
        super().__init__(executor)
        self.max_workers = max_workers

    def run(
        self,
        execution_plan: list[str],
        context: ExecutionContext,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute pipeline with parallelization where possible.

        Args:
            execution_plan: Topologically sorted step names
            context: Execution context
            inputs: Initial inputs

        Returns:
            Dictionary of step outputs

        Raises:
            RuntimeError: If deadlock detected or step fails
        """
        results: dict[str, Any] = {}
        remaining = execution_plan.copy()

        logger.info(
            "Starting parallel execution of %d steps with %d workers",
            len(execution_plan),
            self.max_workers,
        )

        failed_error: Exception | None = None

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            while remaining and failed_error is None:
                # Find steps ready to execute (all dependencies complete)
                ready = self._get_ready_steps(remaining, results)

                if not ready:
                    raise RuntimeError(
                        "Deadlock detected in pipeline execution. "
                        "Remaining steps: " + ", ".join(remaining)
                    )

                logger.debug("Executing batch: %s", ready)

                # Submit ready steps for execution
                futures = {
                    pool.submit(
                        self._execute_step, name, context, results, inputs
                    ): name
                    for name in ready
                }

                # Collect results — capture first error, don't raise inside
                # the with-block to avoid "cannot schedule new futures after
                # shutdown" when the pool's __exit__ is triggered mid-loop.
                batch_failed = False
                for future in as_completed(futures):
                    step_name = futures[future]
                    try:
                        output = future.result()
                        results[step_name] = output
                        logger.debug("Step %s completed", step_name)
                    except Exception as e:
                        logger.error("Step %s failed: %s", step_name, e)
                        failed_error = e
                        batch_failed = True
                        break  # exit as_completed loop, then while loop exits too

                # Only mark steps as done if the entire batch succeeded
                if not batch_failed:
                    for name in ready:
                        remaining.remove(name)

        # Re-raise outside the with-block so the pool is already shut down
        # cleanly before we propagate the error.
        if failed_error is not None:
            raise failed_error

        logger.info("Parallel execution complete: %d steps", len(results))
        return results

    def _get_ready_steps(
        self,
        remaining: list[str],
        completed: dict[str, Any],
    ) -> list[str]:
        """Find steps whose dependencies are all complete.

        Args:
            remaining: Steps not yet executed
            completed: Steps that have completed

        Returns:
            List of step names ready to execute
        """
        ready = []
        for step_name in remaining:
            step_class = registry.get(step_name)
            step = step_class()

            # Check if all dependencies are complete
            if all(dep in completed for dep in step.dependencies):
                ready.append(step_name)

        return ready

    def _execute_step(
        self,
        step_name: str,
        context: ExecutionContext,
        completed: dict[str, Any],
        initial_inputs: dict[str, Any],
    ) -> Any:
        """Execute a single step (for thread pool).

        Args:
            step_name: Name of step to execute
            context: Execution context
            completed: Results from completed steps
            initial_inputs: Initial pipeline inputs

        Returns:
            Step output

        Raises:
            RuntimeError: If step execution fails
        """
        step_class = registry.get(step_name)
        step = step_class()

        # Prepare inputs from dependencies
        step_inputs = self._prepare_step_inputs(step, completed, initial_inputs)

        # Execute
        result = self.executor.execute(step, context, step_inputs)

        if not result.success:
            raise RuntimeError(f"Step '{step_name}' failed: {result.error}")

        return result.output

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
