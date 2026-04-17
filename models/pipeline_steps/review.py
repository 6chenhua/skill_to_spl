"""Review and validation models.

This module contains models for review items and validation results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from models.base import SourceRef


class ReviewSeverity(Enum):
    """Review item severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(slots=True)
class NeedsReviewItem:
    """Human review flag.

    Used to mark items that need human inspection during pipeline processing.

    Attributes:
        item: Description of what needs review
        reason: Why it needs review
        question: Question for the reviewer
        severity: Severity level
        source_ref: Source code reference

    Examples:
        >>> item = NeedsReviewItem(
        ...     item="Ambiguous workflow step",
        ...     reason="Multiple interpretations possible",
        ...     question="Which interpretation is correct?",
        ... )
    """

    item: str
    reason: str
    question: str
    severity: ReviewSeverity = field(default=ReviewSeverity.WARNING)
    source_ref: SourceRef | None = None

    def __post_init__(self) -> None:
        """Ensure severity is enum value."""
        if isinstance(self.severity, str):
            object.__setattr__(
                self, "severity", ReviewSeverity(self.severity.lower())
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "item": self.item,
            "reason": self.reason,
            "question": self.question,
            "severity": self.severity.value,
            "source_ref": str(self.source_ref) if self.source_ref else None,
        }


@dataclass(slots=True)
class ValidationResult:
    """Validation result for model instances.

    Attributes:
        is_valid: Whether validation passed
        errors: List of validation errors
        warnings: List of validation warnings

    Examples:
        >>> result = ValidationResult(is_valid=True)
        >>> result.add_warning("Consider adding description")
    """

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Add validation error."""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Add validation warning."""
        self.warnings.append(message)

    def merge(self, other: ValidationResult) -> ValidationResult:
        """Merge another validation result."""
        merged = ValidationResult(
            is_valid=self.is_valid and other.is_valid,
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
        )
        return merged

    def summary(self) -> dict[str, Any]:
        """Return summary statistics."""
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }
