"""Step execution wrapper."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from pipeline.orchestrator.base import PipelineStep
from pipeline.orchestrator.checkpoint import CheckpointManager
from pipeline.orchestrator.execution_context import ExecutionContext

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Result of executing a pipeline step.

    Attributes:
        step_name: Name of the step
        success: Whether execution succeeded
        output: Step output data (None if failed)
        duration_ms: Execution duration in milliseconds
        token_usage: Token usage for this step
        error: Error message if failed (None if succeeded)
    """

    step_name: str
    success: bool
    output: Any
    duration_ms: int
    token_usage: int
    error: Optional[str] = None

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"StepResult({self.step_name}: {status}, {self.duration_ms}ms)"


class StepExecutor:
    """Executor for individual pipeline steps.

    Handles:
    - Step execution
    - Checkpoint save/load
    - Timing and token tracking
    - Error handling
    - Skip logic

    Example:
        executor = StepExecutor(checkpoint_manager=CheckpointManager())
        result = executor.execute(step, context, inputs)
    """

    def __init__(
        self,
        checkpoint_manager: Optional[CheckpointManager] = None,
    ):
        """Initialize step executor.

        Args:
            checkpoint_manager: Checkpoint manager for persistence
        """
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()

    def execute(
        self,
        step: PipelineStep,
        context: ExecutionContext,
        inputs: Any,
    ) -> StepResult:
        """Execute a single step.

        Args:
            step: The step to execute
            context: Execution context
            inputs: Step inputs

        Returns:
            StepResult with execution outcome
        """
        step_logger = context.get_step_logger(step.name)
        step_logger.info("Starting execution")

        start_time = time.time()
        start_tokens = context.session_usage.total.total

        try:
            # Check if should skip
            if step.should_skip(context):
                step_logger.info("Step skipped")
                return StepResult(
                    step_name=step.name,
                    success=True,
                    output=None,
                    duration_ms=0,
                    token_usage=0,
                )

            # Check checkpoint
            if context.checkpoint_enabled:
                cached = self.checkpoint_manager.load(step.name, context.output_dir)
                if cached is not None:
                    step_logger.info("Restored from checkpoint")
                    return StepResult(
                        step_name=step.name,
                        success=True,
                        output=cached,
                        duration_ms=0,
                        token_usage=0,
                    )

            # Execute step
            output = step.execute(context, inputs)

            # Save checkpoint
            if context.checkpoint_enabled:
                self.checkpoint_manager.save(step.name, output, context.output_dir)

            duration_ms = int((time.time() - start_time) * 1000)
            token_usage = context.session_usage.total.total - start_tokens

            step_logger.info("Completed in %dms, tokens: %d", duration_ms, token_usage)

            return StepResult(
                step_name=step.name,
                success=True,
                output=output,
                duration_ms=duration_ms,
                token_usage=token_usage,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            step_logger.error("Failed after %dms: %s", duration_ms, error_msg)

            return StepResult(
                step_name=step.name,
                success=False,
                output=None,
                duration_ms=duration_ms,
                token_usage=0,
                error=error_msg,
            )

    def clear_checkpoint(self, step_name: str, context: ExecutionContext) -> bool:
        """Clear checkpoint for a step.

        Args:
            step_name: Name of the step
            context: Execution context

        Returns:
            True if checkpoint was cleared, False if not found
        """
        return self.checkpoint_manager.delete(step_name, context.output_dir)
