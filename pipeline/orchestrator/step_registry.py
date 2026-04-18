"""Step registry - manages all available pipeline steps."""
from __future__ import annotations

import logging
from typing import Optional, Type

from pipeline.orchestrator.base import PipelineStep

logger = logging.getLogger(__name__)


class StepRegistry:
    """Pipeline step registry - singleton pattern.

    Manages registration and lookup of pipeline steps.
    Steps are registered using the @registry.register decorator.

    Example:
        from pipeline.orchestrator.step_registry import registry

        @registry.register
        class MyStep(PipelineStep[Input, Output]):
            @property
            def name(self) -> str:
                return "my_step"
            ...

        # Later, retrieve the step
        step_class = registry.get("my_step")
    """

    _instance: Optional["StepRegistry"] = None
    _steps: dict[str, Type[PipelineStep]] = {}

    def __new__(cls) -> "StepRegistry":
        """Create or return the singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._steps = {}
        return cls._instance

    def register(self, step_class: Type[PipelineStep]) -> Type[PipelineStep]:
        """Register a step class (can be used as decorator).

        Args:
            step_class: The PipelineStep subclass to register

        Returns:
            The same class (for use as decorator)

        Raises:
            ValueError: If a step with the same name is already registered
        """
        name = step_class().name
        if name in self._steps:
            logger.warning("Overwriting registered step: %s", name)
        self._steps[name] = step_class
        logger.debug("Registered step: %s", name)
        return step_class

    def get(self, name: str) -> Type[PipelineStep]:
        """Get a registered step class by name.

        Args:
            name: Name of the step

        Returns:
            The registered step class

        Raises:
            KeyError: If step is not registered
        """
        if name not in self._steps:
            raise KeyError(f"Step '{name}' not registered")
        return self._steps[name]

    def list_steps(self) -> list[str]:
        """Return list of all registered step names.

        Returns:
            Sorted list of step names
        """
        return sorted(self._steps.keys())

    def clear(self) -> None:
        """Clear the registry (mainly for testing).

        Warning: This removes all registered steps. Use with caution.
        """
        self._steps.clear()
        logger.debug("Registry cleared")

    def __contains__(self, name: str) -> bool:
        """Check if a step is registered.

        Args:
            name: Step name to check

        Returns:
            True if step is registered
        """
        return name in self._steps

    def __len__(self) -> int:
        """Return number of registered steps."""
        return len(self._steps)


# Global singleton instance
registry = StepRegistry()
