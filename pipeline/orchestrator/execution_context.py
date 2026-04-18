"""Execution context for pipeline steps."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pipeline.llm_client import LLMClient, SessionUsage
from pipeline.orchestrator.config import PipelineConfig


@dataclass(frozen=True)
class ExecutionContext:
    """Execution context - passed to each step via dependency injection.

    This immutable context provides all dependencies needed by pipeline steps:
    - LLM client for API calls
    - Token usage tracking
    - Pipeline configuration
    - Output directory
    - Logger
    - Checkpoint configuration

    Attributes:
        client: LLM client wrapper
        session_usage: Token usage tracking across the session
        config: Pipeline configuration
        output_dir: Output directory for results
        logger: Logger instance
        checkpoint_enabled: Whether checkpointing is enabled
    """

    client: LLMClient
    session_usage: SessionUsage
    config: PipelineConfig
    output_dir: Path
    logger: logging.Logger
    checkpoint_enabled: bool = True

    def get_step_logger(self, step_name: str) -> logging.Logger:
        """Get a logger for a specific step.

        Args:
            step_name: Name of the step

        Returns:
            Logger with step name as child
        """
        return self.logger.getChild(step_name)

    def get_step_output_dir(self, step_name: str) -> Path:
        """Get the output directory for a specific step.

        Args:
            step_name: Name of the step

        Returns:
            Path to step output directory
        """
        return self.output_dir / step_name

    def __repr__(self) -> str:
        return (
            f"ExecutionContext("
            f"config={self.config.skill_root!r}, "
            f"output_dir={self.output_dir!r}, "
            f"checkpoint_enabled={self.checkpoint_enabled}"
            f")"
        )
