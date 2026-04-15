"""
Unit tests for the clarification UI module.

Tests cover:
- ClarificationUI abstract interface
- ConsoleClarificationUI implementation
- MockClarificationUI for testing
- ResponseValidator utility class
"""

import pytest
from datetime import datetime

from .ui import (
    ClarificationUI,
    ConsoleClarificationUI,
    MockClarificationUI,
    ClarificationQuestion,
    UserResponse,
    ClarificationContext,
    QuestionPriority,
    ClarificationStatus,
    ResponseValidator,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test Data Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_question() -> ClarificationQuestion:
    """Create a sample clarification question for testing."""
    return ClarificationQuestion(
        question_id="q1",
        question_text="What approach should be used for error handling?",
        options=["Retry with backoff", "Fail fast", "Log and continue"],
        has_custom_option=True,
        priority=QuestionPriority.HIGH,
        context_hint="Consider the criticality of the operation",
    )


@pytest.fixture
def sample_questions() -> list[ClarificationQuestion]:
    """Create multiple sample questions."""
    return [
        ClarificationQuestion(
            question_id="q1",
            question_text="What approach should be used for error handling?",
            options=["Retry with backoff", "Fail fast", "Log and continue"],
            has_custom_option=True,
            priority=QuestionPriority.HIGH,
        ),
        ClarificationQuestion(
            question_id="q2",
            question_text="Should we enable caching?",
            options=["Yes", "No"],
            has_custom_option=False,
            priority=QuestionPriority.MEDIUM,
        ),
        ClarificationQuestion(
            question_id="q3",
            question_text="Enter the maximum retry count:",
            options=[],
            has_custom_option=True,
            priority=QuestionPriority.CRITICAL,
            context_hint="Recommended: 3-5 attempts",
        ),
    ]


@pytest.fixture
def sample_response() -> UserResponse:
    """Create a sample user response."""
    return UserResponse(
        question_id="q1",
        selected_option="Retry with backoff",
        custom_answer="",
        timestamp=datetime.now().isoformat(),
        confidence=1.0,
    )


@pytest.fixture
def custom_response() -> UserResponse:
    """Create a sample custom user response."""
    return UserResponse(
        question_id="q3",
        selected_option="CUSTOM",
        custom_answer="5",
        timestamp=datetime.now().isoformat(),
        confidence=0.9,
    )


@pytest.fixture
def clarification_context(
    sample_questions: list[ClarificationQuestion],
) -> ClarificationContext:
    """Create a clarification context with questions."""
    return ClarificationContext(questions=sample_questions)


# ─────────────────────────────────────────────────────────────────────────────
# ResponseValidator Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestResponseValidator:
    """Tests for ResponseValidator class."""

    def test_validate_valid_option_selection(self, sample_question, sample_response):
        """Test validation passes for valid option selection."""
        is_valid, error_msg = ResponseValidator.validate(sample_response, sample_question)
        assert is_valid is True
        assert error_msg == ""

    def test_validate_valid_custom_answer(self, sample_question, custom_response):
        """Test validation passes for valid custom answer."""
        is_valid, error_msg = ResponseValidator.validate(custom_response, sample_question)
        assert is_valid is True
        assert error_msg == ""

    def test_validate_empty_custom_answer(self, sample_question):
        """Test validation fails for empty custom answer."""
        response = UserResponse(
            question_id="q1",
            selected_option="CUSTOM",
            custom_answer="",
            timestamp=datetime.now().isoformat(),
        )
        is_valid, error_msg = ResponseValidator.validate(response, sample_question)
        assert is_valid is False
        assert "cannot be empty" in error_msg

    def test_validate_whitespace_custom_answer(self, sample_question):
        """Test validation fails for whitespace-only custom answer."""
        response = UserResponse(
            question_id="q1",
            selected_option="CUSTOM",
            custom_answer="   ",
            timestamp=datetime.now().isoformat(),
        )
        is_valid, error_msg = ResponseValidator.validate(response, sample_question)
        assert is_valid is False
        assert "cannot be empty" in error_msg

    def test_validate_invalid_option(self, sample_question):
        """Test validation fails for option not in question's options."""
        response = UserResponse(
            question_id="q1",
            selected_option="Invalid Option",
            custom_answer="",
            timestamp=datetime.now().isoformat(),
        )
        is_valid, error_msg = ResponseValidator.validate(response, sample_question)
        assert is_valid is False
        assert "Invalid option" in error_msg

    def test_validate_context_complete(self, sample_questions):
        """Test context validation with all responses provided."""
        context = ClarificationContext(questions=sample_questions)
        context.add_response(
            UserResponse(question_id="q1", selected_option="Retry with backoff")
        )
        context.add_response(UserResponse(question_id="q2", selected_option="Yes"))
        context.add_response(
            UserResponse(question_id="q3", selected_option="CUSTOM", custom_answer="5")
        )

        is_valid, errors = ResponseValidator.validate_context(context)
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_context_missing_responses(self, sample_questions):
        """Test context validation fails when responses are missing."""
        context = ClarificationContext(questions=sample_questions)
        context.add_response(
            UserResponse(question_id="q1", selected_option="Retry with backoff")
        )
        # Missing q2 and q3

        is_valid, errors = ResponseValidator.validate_context(context)
        assert is_valid is False
        assert any("Missing responses" in e for e in errors)

    def test_validate_context_invalid_response(self, sample_questions):
        """Test context validation fails for invalid individual response."""
        context = ClarificationContext(questions=sample_questions)
        context.add_response(
            UserResponse(question_id="q1", selected_option="Invalid Option")
        )

        is_valid, errors = ResponseValidator.validate_context(context)
        assert is_valid is False
        assert any("Invalid response" in e for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# MockClarificationUI Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestMockClarificationUI:
    """Tests for MockClarificationUI class."""

    def test_predefined_string_response(self, sample_question):
        """Test predefined string response selects correct option."""
        ui = MockClarificationUI({"q1": "Fail fast"})
        ui.present_question(sample_question)
        response = ui.collect_response(sample_question)

        assert response.selected_option == "Fail fast"
        assert response.question_id == "q1"

    def test_predefined_custom_response(self, sample_question):
        """Test predefined CUSTOM response with custom answer."""
        ui = MockClarificationUI({"q1": "CUSTOM"})
        ui.present_question(sample_question)
        response = ui.collect_response(sample_question)

        assert response.selected_option == "CUSTOM"
        assert response.custom_answer == "custom answer"

    def test_predefined_dict_response(self, sample_question):
        """Test predefined dict response with explicit values."""
        ui = MockClarificationUI(
            {"q1": {"selected_option": "CUSTOM", "custom_answer": "10"}}
        )
        ui.present_question(sample_question)
        response = ui.collect_response(sample_question)

        assert response.selected_option == "CUSTOM"
        assert response.custom_answer == "10"

    def test_default_response_when_not_predefined(self, sample_question):
        """Test default response when question not in predefined responses."""
        ui = MockClarificationUI({})
        ui.present_question(sample_question)
        response = ui.collect_response(sample_question)

        # Should default to first option
        assert response.selected_option == "Retry with backoff"

    def test_questions_presented_tracking(self, sample_questions):
        """Test that presented questions are tracked."""
        ui = MockClarificationUI({"q1": "Retry with backoff"})

        for q in sample_questions:
            ui.present_question(q)

        assert ui.questions_presented == ["q1", "q2", "q3"]

    def test_all_responses_collected(self, sample_questions):
        """Test that all responses are collected."""
        ui = MockClarificationUI(
            {
                "q1": "Retry with backoff",
                "q2": "No",
                "q3": {"selected_option": "CUSTOM", "custom_answer": "3"},
            }
        )

        for q in sample_questions:
            ui.collect_response(q)

        assert len(ui.all_responses) == 3
        assert ui.all_responses[0].selected_option == "Retry with backoff"
        assert ui.all_responses[2].selected_option == "CUSTOM"

    def test_confirm_proceed_always_true(self):
        """Test that confirm_proceed always returns True."""
        ui = MockClarificationUI({})
        assert ui.confirm_proceed("Continue?") is True


# ─────────────────────────────────────────────────────────────────────────────
# ConsoleClarificationUI Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestConsoleClarificationUI:
    """Tests for ConsoleClarificationUI class."""

    def test_present_question_formats_output(self, sample_question):
        """Test that present_question formats output correctly."""
        output_lines: list[str] = []
        ui = ConsoleClarificationUI(
            input_func=lambda _: "1", print_func=lambda x: output_lines.append(x)
        )

        ui.present_question(sample_question)

        output = "\n".join(output_lines)
        assert "=" * 60 in output
        assert sample_question.question_text in output
        assert "Retry with backoff" in output
        assert "Fail fast" in output
        assert "Log and continue" in output
        assert "Other (specify your answer)" in output
        assert "Context:" in output

    def test_collect_response_valid_option(self, sample_question):
        """Test collecting a valid numeric option selection."""
        ui = ConsoleClarificationUI(
            input_func=lambda _: "2",  # Select "Fail fast"
            print_func=lambda _: None,
        )

        response = ui.collect_response(sample_question)

        assert response.selected_option == "Fail fast"
        assert response.question_id == "q1"

    def test_collect_response_custom_option(self, sample_question):
        """Test collecting a custom answer."""
        input_values = ["4", "Custom error handling strategy"]  # 4 = custom
        input_iter = iter(input_values)

        ui = ConsoleClarificationUI(
            input_func=lambda _: next(input_iter), print_func=lambda _: None
        )

        response = ui.collect_response(sample_question)

        assert response.selected_option == "CUSTOM"
        assert response.custom_answer == "Custom error handling strategy"

    def test_collect_response_invalid_number_retry(self, sample_question):
        """Test that invalid numeric input prompts retry."""
        input_values = ["99", "abc", "1"]  # Invalid, then valid
        input_iter = iter(input_values)

        ui = ConsoleClarificationUI(
            input_func=lambda _: next(input_iter), print_func=lambda _: None
        )

        response = ui.collect_response(sample_question)

        # Should have retried and finally accepted "1"
        assert response.selected_option == "Retry with backoff"

    def test_collect_response_empty_input_retry(self, sample_question):
        """Test that empty input prompts retry."""
        input_values = ["", "", "1"]  # Empty, then valid
        input_iter = iter(input_values)

        ui = ConsoleClarificationUI(
            input_func=lambda _: next(input_iter), print_func=lambda _: None
        )

        response = ui.collect_response(sample_question)

        assert response.selected_option == "Retry with backoff"

    def test_confirm_proceed_yes(self):
        """Test confirm_proceed accepts 'y'."""
        ui = ConsoleClarificationUI(
            input_func=lambda _: "y", print_func=lambda _: None
        )

        assert ui.confirm_proceed("Continue?") is True

    def test_confirm_proceed_yes_full_word(self):
        """Test confirm_proceed accepts 'yes'."""
        ui = ConsoleClarificationUI(
            input_func=lambda _: "yes", print_func=lambda _: None
        )

        assert ui.confirm_proceed("Continue?") is True

    def test_confirm_proceed_no(self):
        """Test confirm_proceed accepts 'n'."""
        ui = ConsoleClarificationUI(
            input_func=lambda _: "n", print_func=lambda _: None
        )

        assert ui.confirm_proceed("Continue?") is False

    def test_confirm_proceed_no_full_word(self):
        """Test confirm_proceed accepts 'no'."""
        ui = ConsoleClarificationUI(
            input_func=lambda _: "no", print_func=lambda _: None
        )

        assert ui.confirm_proceed("Continue?") is False

    def test_confirm_proceed_invalid_retry(self):
        """Test that invalid input prompts retry."""
        input_values = ["maybe", "invalid", "y"]
        input_iter = iter(input_values)

        ui = ConsoleClarificationUI(
            input_func=lambda _: next(input_iter), print_func=lambda _: None
        )

        result = ui.confirm_proceed("Continue?")
        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# ClarificationContext Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestClarificationContext:
    """Tests for ClarificationContext class."""

    def test_add_response_updates_status(self, sample_questions):
        """Test that adding response updates status."""
        context = ClarificationContext(questions=sample_questions)
        assert context.status == ClarificationStatus.PENDING

        context.add_response(UserResponse(question_id="q1", selected_option="Option1"))
        assert context.status == ClarificationStatus.IN_PROGRESS

    def test_add_response_completes_session(self, sample_questions):
        """Test that adding all responses completes the session."""
        context = ClarificationContext(questions=sample_questions)

        context.add_response(UserResponse(question_id="q1", selected_option="Option1"))
        context.add_response(UserResponse(question_id="q2", selected_option="Option1"))
        context.add_response(UserResponse(question_id="q3", selected_option="Option1"))

        assert context.status == ClarificationStatus.COMPLETED
        assert context.completed_at is not None
        assert context.is_complete() is True

    def test_get_response_finds_response(self, sample_questions):
        """Test get_response returns correct response."""
        context = ClarificationContext(questions=sample_questions)
        response = UserResponse(question_id="q1", selected_option="Option1")
        context.add_response(response)

        found = context.get_response("q1")
        assert found is not None
        assert found.selected_option == "Option1"

    def test_get_response_returns_none_for_missing(self, sample_questions):
        """Test get_response returns None for missing question ID."""
        context = ClarificationContext(questions=sample_questions)

        found = context.get_response("nonexistent")
        assert found is None


# ─────────────────────────────────────────────────────────────────────────────
# Data Model Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestClarificationQuestion:
    """Tests for ClarificationQuestion dataclass."""

    def test_default_priority(self):
        """Test default priority is MEDIUM."""
        q = ClarificationQuestion(
            question_id="test", question_text="Test question?"
        )
        assert q.priority == QuestionPriority.MEDIUM

    def test_has_custom_option_default_false(self):
        """Test default has_custom_option is False."""
        q = ClarificationQuestion(
            question_id="test", question_text="Test question?"
        )
        assert q.has_custom_option is False


class TestUserResponse:
    """Tests for UserResponse dataclass."""

    def test_timestamp_auto_generated(self):
        """Test that timestamp is auto-generated."""
        response = UserResponse(question_id="q1", selected_option="Option1")
        assert response.timestamp is not None
        assert response.timestamp != ""

    def test_default_confidence(self):
        """Test default confidence is 1.0."""
        response = UserResponse(question_id="q1", selected_option="Option1")
        assert response.confidence == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# ABC Interface Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestClarificationUIIsAbstract:
    """Tests to ensure ClarificationUI cannot be instantiated directly."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that ClarificationUI cannot be instantiated."""
        with pytest.raises (TypeError, match=r"abstract.*Cannot instantiate"):
            ClarificationUI()


class TestConsoleClarificationUIInheritsFromAbstract:
    """Tests to ensure ConsoleClarificationUI properly implements the interface."""

    def test_console_ui_is_instance_of_abstract(self):
        """Test ConsoleClarificationUI is a subclass."""
        ui = ConsoleClarificationUI()
        assert isinstance(ui, ClarificationUI)

    def test_mock_ui_is_instance_of_abstract(self):
        """Test MockClarificationUI is a subclass."""
        ui = MockClarificationUI({})
        assert isinstance(ui, ClarificationUI)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])