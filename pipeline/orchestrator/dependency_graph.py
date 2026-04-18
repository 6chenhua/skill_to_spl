"""Dependency graph for pipeline steps."""
from __future__ import annotations

from collections import deque
from typing import Optional, Type

from pipeline.orchestrator.base import PipelineStep


class DependencyGraph:
    """Step dependency graph - used to determine execution order.

    Builds a directed acyclic graph from step dependencies and provides:
    - Topological sort for sequential execution
    - Cycle detection
    - Execution plan generation with resume support
    - Parallel group identification

    Example:
        steps = [StepA, StepB, StepC]  # StepC depends on StepA and StepB
        graph = DependencyGraph(steps)
        order = graph.topological_sort()  # ['step_a', 'step_b', 'step_c']
    """

    def __init__(self, steps: list[Type[PipelineStep]]):
        """Initialize dependency graph from step classes.

        Args:
            steps: List of PipelineStep subclasses
        """
        self._steps: dict[str, Type[PipelineStep]] = {}
        for step_class in steps:
            step = step_class()
            self._steps[step.name] = step_class

        self._graph = self._build_graph()

    def _build_graph(self) -> dict[str, set[str]]:
        """Build the dependency graph adjacency list.

        Returns:
            Dictionary mapping step name to set of dependency names
        """
        graph: dict[str, set[str]] = {}
        for name, step_class in self._steps.items():
            step = step_class()
            # Only include dependencies that are in the graph
            deps = {dep for dep in step.dependencies if dep in self._steps}
            graph[name] = deps
        return graph

    def topological_sort(self) -> list[str]:
        """Return step names in topological order.

        Uses Kahn's algorithm. Raises error if cycle detected.

        Returns:
            List of step names in dependency order

        Raises:
            ValueError: If circular dependency detected
        """
        # Calculate in-degrees (number of incoming edges for each node)
        in_degree = {name: 0 for name in self._steps}
        for name, deps in self._graph.items():
            for dep in deps:
                # 'name' depends on 'dep', so increment in_degree of 'name'
                in_degree[name] += 1

        # Start with nodes having no dependencies (in_degree = 0)
        queue = deque([name for name, degree in in_degree.items() if degree == 0])
        result: list[str] = []

        while queue:
            current = queue.popleft()
            result.append(current)

            # Decrease in-degree of nodes that depend on current
            for name, deps in self._graph.items():
                if current in deps:
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        queue.append(name)

        if len(result) != len(self._steps):
            raise ValueError("Circular dependency detected in pipeline steps")

        return result

    def get_execution_plan(self, resume_from: Optional[str] = None) -> list[str]:
        """Get execution plan, optionally starting from a specific step.

        Args:
            resume_from: Step name to resume from (inclusive), or None for full pipeline

        Returns:
            List of step names to execute

        Raises:
            ValueError: If resume_from step not found
        """
        sorted_steps = self.topological_sort()

        if resume_from is None:
            return sorted_steps

        try:
            start_idx = sorted_steps.index(resume_from)
            return sorted_steps[start_idx:]
        except ValueError as e:
            raise ValueError(f"Resume step '{resume_from}' not found in pipeline") from e

    def get_parallel_groups(self) -> list[list[str]]:
        """Group steps into parallelizable batches.

        Each batch contains steps that can execute in parallel
        (no dependencies on each other within the batch).

        Returns:
            List of step name batches
        """
        sorted_steps = self.topological_sort()
        groups: list[list[str]] = []
        executed: set[str] = set()

        remaining = set(sorted_steps)

        while remaining:
            # Find steps whose dependencies are all executed
            ready = []
            for name in remaining:
                deps = self._graph.get(name, set())
                if deps <= executed:
                    ready.append(name)

            if not ready:
                # Should not happen if no cycles (checked in topological_sort)
                raise RuntimeError("Deadlock detected in dependency graph")

            groups.append(ready)
            executed.update(ready)
            remaining -= set(ready)

        return groups

    def get_dependencies(self, step_name: str) -> set[str]:
        """Get direct dependencies of a step.

        Args:
            step_name: Name of the step

        Returns:
            Set of dependency step names

        Raises:
            KeyError: If step not found
        """
        if step_name not in self._graph:
            raise KeyError(f"Step '{step_name}' not in graph")
        return self._graph[step_name].copy()

    def get_dependents(self, step_name: str) -> set[str]:
        """Get steps that depend on a given step.

        Args:
            step_name: Name of the step

        Returns:
            Set of dependent step names
        """
        dependents: set[str] = set()
        for name, deps in self._graph.items():
            if step_name in deps:
                dependents.add(name)
        return dependents

    def __len__(self) -> int:
        """Return number of steps in graph."""
        return len(self._steps)

    def __contains__(self, step_name: str) -> bool:
        """Check if a step is in the graph."""
        return step_name in self._steps
