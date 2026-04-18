"""Pipeline builder."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional, Type

from pipeline.llm_client import LLMClient, SessionUsage
from pipeline.orchestrator.base import PipelineOrchestrator, PipelineStep
from pipeline.orchestrator.checkpoint import CheckpointManager
from pipeline.orchestrator.config import PipelineConfig
from pipeline.orchestrator.dependency_graph import DependencyGraph
from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.runners.base import Runner
from pipeline.orchestrator.runners.parallel import ParallelRunner
from pipeline.orchestrator.runners.sequential import SequentialRunner
from pipeline.orchestrator.step_executor import StepExecutor

logger = logging.getLogger(__name__)


class PipelineBuilder:
    """Builder for constructing pipeline orchestrators.

    Provides a fluent API for configuring and building pipelines:
    - Add steps
    - Configure runner (sequential/parallel)
    - Set checkpoint options
    - Build orchestrator

    Example:
        builder = PipelineBuilder()
        orchestrator = (
            builder
            .with_config(config)
            .with_steps(StepA, StepB, StepC)
            .with_runner("parallel", max_workers=4)
            .with_checkpointing(True)
            .build()
        )
        results = orchestrator.run(initial_inputs={})
    """

    def __init__(self):
        """Initialize builder with empty configuration."""
        self._steps: list[Type[PipelineStep]] = []
        self._config: Optional[PipelineConfig] = None
        self._runner_type: str = "sequential"
        self._max_workers: int = 4
        self._enable_checkpoints: bool = True

    def with_config(self, config: PipelineConfig) -> "PipelineBuilder":
        """Set pipeline configuration.

        Args:
            config: Pipeline configuration

        Returns:
            Self for chaining
        """
        self._config = config
        return self

    def with_runner(self, runner_type: str, max_workers: int = 4) -> "PipelineBuilder":
        """Set runner type and configuration.

        Args:
            runner_type: "sequential" or "parallel"
            max_workers: Maximum parallel workers (for parallel runner)

        Returns:
            Self for chaining

        Raises:
            ValueError: If invalid runner type
        """
        if runner_type not in ("sequential", "parallel"):
            raise ValueError(f"Invalid runner type: {runner_type}")
        self._runner_type = runner_type
        self._max_workers = max_workers
        return self

    def with_steps(self, *steps: Type[PipelineStep]) -> "PipelineBuilder":
        """Add steps to the pipeline.

        Args:
            *steps: Pipeline step classes

        Returns:
            Self for chaining
        """
        self._steps.extend(steps)
        return self

    def with_checkpointing(self, enabled: bool = True) -> "PipelineBuilder":
        """Enable or disable checkpointing.

        Args:
            enabled: Whether to enable checkpoints

        Returns:
            Self for chaining
        """
        self._enable_checkpoints = enabled
        return self

    def build(self) -> PipelineOrchestrator:
        """Build and return the configured pipeline orchestrator.

        Returns:
            Configured PipelineOrchestrator

        Raises:
            ValueError: If configuration is invalid
        """
        if self._config is None:
            raise ValueError("Config is required. Call with_config() first.")

        if not self._steps:
            raise ValueError("At least one step is required. Call with_steps() first.")

        logger.info(
            "Building pipeline with %d steps, %s runner",
            len(self._steps),
            self._runner_type,
        )

        # Create execution context
        session_usage = SessionUsage()
        client = LLMClient(
            config=self._config.llm_config,
            session_usage=session_usage,
        )

        context = ExecutionContext(
            client=client,
            session_usage=session_usage,
            config=self._config,
            output_dir=Path(self._config.output_dir),
            logger=logger,
            checkpoint_enabled=self._enable_checkpoints,
        )

        # Create step executor
        executor = StepExecutor(
            checkpoint_manager=CheckpointManager() if self._enable_checkpoints else None
        )

        # Create runner
        runner: Runner
        if self._runner_type == "parallel":
            runner = ParallelRunner(executor, max_workers=self._max_workers)
        else:
            runner = SequentialRunner(executor)

        # Build dependency graph
        dependency_graph = DependencyGraph(self._steps)

        # Create orchestrator
        return ConcretePipelineOrchestrator(
            context=context,
            runner=runner,
            dependency_graph=dependency_graph,
            resume_from=self._config.resume_from,
        )


class ConcretePipelineOrchestrator(PipelineOrchestrator):
    """Concrete pipeline orchestrator implementation."""

    def __init__(
        self,
        context: ExecutionContext,
        runner: Runner,
        dependency_graph: DependencyGraph,
        resume_from: Optional[str] = None,
    ):
        """Initialize orchestrator.

        Args:
            context: Execution context
            runner: Step runner
            dependency_graph: Step dependency graph
            resume_from: Step to resume from (optional)
        """
        self.context = context
        self.runner = runner
        self.dependency_graph = dependency_graph
        self.resume_from = resume_from

    def run(self, initial_inputs: dict[str, Any]) -> dict[str, Any]:
        """Run the pipeline.

        Args:
            initial_inputs: Initial input data

        Returns:
            Dictionary of all step outputs
        """
        # Get execution plan
        execution_plan = self.dependency_graph.get_execution_plan(self.resume_from)
        logger.info("Pipeline execution plan: %s", execution_plan)

        # Execute
        return self.runner.run(
            execution_plan=execution_plan,
            context=self.context,
            inputs=initial_inputs,
        )

    def __repr__(self) -> str:
        return (
            f"ConcretePipelineOrchestrator("
            f"steps={len(self.dependency_graph)}, "
            f"resume_from={self.resume_from!r}"
            f")"
        )
