"""Pipeline configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pipeline.llm_client import LLMConfig, StepLLMConfig


@dataclass
class PipelineConfig:
    """Configuration for the skill-to-CNL-P pipeline.

    This is the new configuration class used by the refactored pipeline.
    It maintains backward compatibility with the old PipelineConfig in
    models/pipeline_result.py while providing additional configuration options.

    Attributes:
        skill_root: Root directory of the skill package
        output_dir: Output directory for results and checkpoints
        llm_config: LLM configuration
        step_llm_config: Per-step LLM model overrides (optional)
        save_checkpoints: Whether to save intermediate results
        resume_from: Step name to resume from (optional)
        use_new_step3: Whether to use the new Step 3 architecture
        max_parallel_workers: Maximum number of parallel workers
        enable_detailed_logging: Whether to enable detailed logging
    """

    skill_root: str
    output_dir: str
    llm_config: LLMConfig
    step_llm_config: Optional[StepLLMConfig] = None
    save_checkpoints: bool = True
    resume_from: Optional[str] = None
    use_new_step3: bool = False

    # New configuration options (with defaults for backward compatibility)
    max_parallel_workers: int = field(default=4)
    enable_detailed_logging: bool = field(default=True)

    def get_step_model(self, step_name: str) -> Optional[str]:
        """Get the model override for a specific step.

        Args:
            step_name: Name of the step

        Returns:
            Model name if configured, None otherwise (use default)
        """
        if self.step_llm_config is not None:
            return self.step_llm_config.get_model(step_name, self.llm_config.model)
        return None

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.skill_root:
            raise ValueError("skill_root is required")
        if not self.output_dir:
            raise ValueError("output_dir is required")
        if self.max_parallel_workers < 1:
            raise ValueError("max_parallel_workers must be at least 1")
