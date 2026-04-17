"""Pipeline result and configuration models.

This module contains the complete pipeline output and configuration.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from models.base import SourceRef
from models.core import SessionUsage, ReviewSummary

if TYPE_CHECKING:
    from models.pipeline_steps.step4 import SPLSpec


@dataclass(slots=True)
class PipelineResult:
    """The complete output of a full pipeline run.

    Contains all intermediate outputs for traceability and checkpoint resume,
    plus the final SPL output.

    Attributes:
        skill_id: Skill identifier
        graph: P1 reference graph output
        file_role_map: P2 file role map
        package: P3 skill package
        section_bundle: Step 1 section bundle
        structured_spec: Step 3 structured specification
        spl_spec: Step 4 SPL specification (final output)
        session_usage: Token usage tracking
        duration_seconds: Pipeline execution duration
        checkpoints_saved: List of saved checkpoint paths
        metadata: Additional metadata

    Examples:
        >>> result = PipelineResult(
        ...     skill_id="pdf",
        ...     graph=FileReferenceGraph(...),
        ...     file_role_map={},
        ...     package=SkillPackage(...),
        ...     section_bundle=SectionBundle(...),
        ...     structured_spec=StructuredSpec(...),
        ...     spl_spec=SPLSpec(...),
        ... )
    """

    skill_id: str
    graph: Any  # FileReferenceGraph
    file_role_map: dict[str, Any]
    package: Any  # SkillPackage
    section_bundle: Any  # SectionBundle
    structured_spec: Any  # StructuredSpec
    spl_spec: "SPLSpec"
    session_usage: SessionUsage = field(default_factory=SessionUsage)
    duration_seconds: float = 0.0
    checkpoints_saved: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_token_summary(self) -> str:
        """Generate token usage summary text.

        Returns:
            Formatted summary of token usage by step
        """
        total = self.session_usage.total
        lines = [
            f"Token Usage Summary for {self.skill_id}:",
            f"  Prompt: {total.prompt_tokens:,}",
            f"  Completion: {total.completion_tokens:,}",
            f"  Total: {total.total_tokens:,}",
            "",
            "By Step:",
        ]
        for step_name, usage in sorted(self.session_usage.steps.items()):
            lines.append(f"  {step_name}: {usage.total_tokens:,} tokens")
        return "\n".join(lines)

    def save_checkpoints(self, output_dir: Path) -> list[str]:
        """Save all intermediate results to checkpoint files.

        Args:
            output_dir: Directory to save checkpoints

        Returns:
            List of saved checkpoint paths
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        saved = []

        checkpoints = [
            ("graph", self.graph),
            ("file_role_map", self.file_role_map),
            ("package", self.package),
            ("section_bundle", self.section_bundle),
            ("structured_spec", self.structured_spec),
            ("spl_spec", self.spl_spec),
        ]

        for name, data in checkpoints:
            if data is not None:
                path = output_dir / f"{name}.json"
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        if hasattr(data, "__dataclass_fields__"):
                            json.dump(asdict(data), f, indent=2, default=str)
                        else:
                            json.dump(data, f, indent=2, default=str)
                    saved.append(str(path))
                except Exception as e:
                    # Log but don't fail if checkpoint saving fails
                    print(f"Warning: Failed to save checkpoint {name}: {e}")

        self.checkpoints_saved = saved
        return saved

    def get_final_output(self) -> str:
        """Get the final SPL output text.

        Returns:
            SPL specification text
        """
        return self.spl_spec.spl_text if self.spl_spec else ""

    def is_success(self) -> bool:
        """Check if pipeline completed successfully.

        Returns:
            True if successful
        """
        if self.spl_spec is None:
            return False
        if not self.spl_spec.spl_text:
            return False
        return len(self.spl_spec.spl_text) > 0

    def has_review_items(self) -> bool:
        """Check if there are review items needing attention.

        Returns:
            True if review items exist
        """
        if self.spl_spec is None:
            return False
        if not self.spl_spec.review_items:
            return False
        return len(self.spl_spec.review_items) > 0

    def summary(self) -> dict[str, Any]:
        """Return comprehensive summary.

        Returns:
            Dictionary with summary statistics
        """
        return {
            "skill_id": self.skill_id,
            "duration_seconds": self.duration_seconds,
            "success": self.is_success(),
            "token_usage": {
                "prompt": self.session_usage.total.prompt_tokens,
                "completion": self.session_usage.total.completion_tokens,
                "total": self.session_usage.total.total_tokens,
            },
            "checkpoints_saved": len(self.checkpoints_saved),
            "has_review_items": self.has_review_items(),
            "spl_length": len(self.spl_spec.spl_text) if self.spl_spec else 0,
        }


@dataclass(slots=True)
class PipelineConfig:
    """Configuration for a pipeline run.

    Attributes:
        skill_root: Path to skill package root
        output_dir: Directory for output files
        save_checkpoints: Whether to save intermediate results
        resume_from: Stage to resume from (e.g., "step3")
        step_configs: Per-step configuration overrides
        metadata: Additional configuration metadata

    Examples:
        >>> config = PipelineConfig(
        ...     skill_root="skills/pdf",
        ...     output_dir="output/pdf",
        ...     save_checkpoints=True,
        ... )
    """

    skill_root: str
    output_dir: str
    save_checkpoints: bool = True
    resume_from: Optional[str] = None
    step_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_step_config(self, step_name: str) -> dict[str, Any]:
        """Get configuration for a specific step.

        Args:
            step_name: Name of the step

        Returns:
            Step configuration dictionary
        """
        return self.step_configs.get(step_name, {})

    def set_step_config(self, step_name: str, config: dict[str, Any]) -> None:
        """Set configuration for a specific step.

        Args:
            step_name: Name of the step
            config: Configuration dictionary
        """
        self.step_configs[step_name] = config

    def should_resume(self) -> bool:
        """Check if should resume from checkpoint.

        Returns:
            True if resume_from is set
        """
        return self.resume_from is not None and len(self.resume_from) > 0

    def validate(self) -> list[str]:
        """Validate configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not self.skill_root:
            errors.append("skill_root is required")
        elif not Path(self.skill_root).exists():
            errors.append(f"skill_root does not exist: {self.skill_root}")

        if not self.output_dir:
            errors.append("output_dir is required")

        valid_resume_stages = [
            None, "", "p1", "p2", "p3", "step1", "step1_5", "step3", "step4"
        ]
        if self.resume_from not in valid_resume_stages:
            errors.append(
                f"Invalid resume_from: {self.resume_from}. "
                f"Must be one of: {valid_resume_stages}"
            )

        return errors

    def is_valid(self) -> bool:
        """Check if configuration is valid.

        Returns:
            True if valid
        """
        return len(self.validate()) == 0

    def summary(self) -> dict[str, Any]:
        """Return configuration summary.

        Returns:
            Dictionary with configuration info
        """
        return {
            "skill_root": self.skill_root,
            "output_dir": self.output_dir,
            "save_checkpoints": self.save_checkpoints,
            "resume_from": self.resume_from,
            "should_resume": self.should_resume(),
            "step_configs": list(self.step_configs.keys()),
            "is_valid": self.is_valid(),
        }
