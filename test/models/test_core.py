"""Tests for models.core module."""

import pytest
from models.core import (
    CheckResult,
    ReviewItem,
    ReviewSeverity,
    SessionUsage,
    TokenUsage,
)


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_token_usage_creation(self) -> None:
        """Test creating TokenUsage."""
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_token_usage_addition(self) -> None:
        """Test adding two TokenUsage objects."""
        usage1 = TokenUsage(prompt_tokens=100, completion_tokens=50)
        usage2 = TokenUsage(prompt_tokens=200, completion_tokens=100)
        total = usage1 + usage2
        assert total.prompt_tokens == 300
        assert total.completion_tokens == 150
        assert total.total_tokens == 450

    def test_token_usage_repr(self) -> None:
        """Test repr format."""
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        repr_str = repr(usage)
        assert "p=100" in repr_str
        assert "c=50" in repr_str
        assert "t=150" in repr_str


class TestSessionUsage:
    """Tests for SessionUsage class."""

    def test_session_usage_creation(self) -> None:
        """Test creating SessionUsage."""
        usage = SessionUsage()
        assert usage.steps == {}
        assert usage.total.total_tokens == 0

    def test_session_usage_add(self) -> None:
        """Test adding step usage."""
        usage = SessionUsage()
        usage.add("step1", TokenUsage(prompt_tokens=100, completion_tokens=50))
        assert "step1" in usage.steps
        assert usage.steps["step1"].total_tokens == 150

    def test_session_usage_total(self) -> None:
        """Test calculating total usage."""
        usage = SessionUsage()
        usage.add("step1", TokenUsage(100, 50))
        usage.add("step2", TokenUsage(200, 100))
        total = usage.total
        assert total.prompt_tokens == 300
        assert total.completion_tokens == 150

    def test_session_usage_get_step(self) -> None:
        """Test getting step usage."""
        usage = SessionUsage()
        usage.add("step1", TokenUsage(100, 50))
        step_usage = usage.get_step_usage("step1")
        assert step_usage is not None
        assert step_usage.total_tokens == 150
        assert usage.get_step_usage("nonexistent") is None

    def test_session_usage_summary(self) -> None:
        """Test summary generation."""
        usage = SessionUsage()
        usage.add("step1", TokenUsage(100, 50))
        summary = usage.summary()
        assert "Token Usage Summary" in summary
        assert "step1" in summary


class TestReviewSeverity:
    """Tests for ReviewSeverity enum."""

    def test_severity_values(self) -> None:
        """Test severity enum values."""
        assert ReviewSeverity.ERROR.value == "error"
        assert ReviewSeverity.WARNING.value == "warning"
        assert ReviewSeverity.INFO.value == "info"


class TestReviewItem:
    """Tests for ReviewItem dataclass."""

    def test_review_item_creation(self) -> None:
        """Test creating ReviewItem."""
        item = ReviewItem(
            item="Test issue",
            reason="For testing",
            question="What should we do?",
            severity=ReviewSeverity.WARNING,
        )
        assert item.item == "Test issue"
        assert item.severity == ReviewSeverity.WARNING

    def test_review_item_with_string_severity(self) -> None:
        """Test creating ReviewItem with string severity."""
        item = ReviewItem(
            item="Test issue",
            reason="For testing",
            question="What?",
            severity="error",  # String instead of enum
        )
        assert item.severity == ReviewSeverity.ERROR

    def test_review_item_format_for_display(self) -> None:
        """Test formatting for display."""
        item = ReviewItem(
            item="Test issue",
            reason="For testing",
            question="What should we do?",
            severity=ReviewSeverity.ERROR,
        )
        formatted = item.format_for_display()
        assert "[ERROR]" in formatted
        assert "Test issue" in formatted


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_check_result_success(self) -> None:
        """Test creating successful result."""
        result = CheckResult.success("All good")
        assert result.passed is True
        assert result.message == "All good"

    def test_check_result_failure(self) -> None:
        """Test creating failed result."""
        result = CheckResult.failure("Something wrong")
        assert result.passed is False
        assert result.message == "Something wrong"

    def test_check_result_bool(self) -> None:
        """Test boolean conversion."""
        success = CheckResult.success("OK")
        failure = CheckResult.failure("Not OK")
        assert bool(success) is True
        assert bool(failure) is False
