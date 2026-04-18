"""Pipeline orchestrator base classes."""
from __future__ import annotations

import abc
from typing import Any, Generic, TypeVar

from pipeline.orchestrator.execution_context import ExecutionContext

T = TypeVar("T")
Output = TypeVar("Output")


class PipelineStep(abc.ABC, Generic[T, Output]):
    """Abstract base class for a single pipeline step.

    Each step has a clear input/output type contract.
    Steps are registered using the @registry.register decorator.

    Example:
        @registry.register
        class MyStep(PipelineStep[dict, Result]):
            @property
            def name(self) -> str:
                return "my_step"

            @property
            def dependencies(self) -> list[str]:
                return ["previous_step"]

            def execute(self, context: ExecutionContext, inputs: dict) -> Result:
                # Step logic here
                return Result(...)
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Step name, used for logging and checkpointing."""
        ...

    @property
    @abc.abstractmethod
    def dependencies(self) -> list[str]:
        """List of step names this step depends on."""
        ...

    @abc.abstractmethod
    def execute(self, context: ExecutionContext, inputs: T) -> Output:
        """Execute the step logic.

        Args:
            context: Execution context (contains client, logger, etc.)
            inputs: Step inputs (typically from dependency steps)

        Returns:
            Step output
        """
        ...

    def should_skip(self, context: ExecutionContext) -> bool:
        """Whether this step can be skipped (for resume_from functionality).

        Override to implement custom skip logic (e.g., based on config flags).

        Args:
            context: Execution context

        Returns:
            True if step should be skipped
        """
        return False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"


class PipelineOrchestrator(abc.ABC):
    """Abstract base class for pipeline orchestrators."""

    @abc.abstractmethod
    def run(self, initial_inputs: dict[str, Any]) -> dict[str, Any]:
        """Run the complete pipeline.

        Args:
            initial_inputs: Initial input data for the first steps

        Returns:
            Dictionary of all step outputs keyed by step name
        """
        ...
