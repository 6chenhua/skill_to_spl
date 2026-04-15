"""
User interaction interfaces for HITL clarification module.

Provides abstract and concrete implementations for collecting user responses
to clarification questions during pipeline execution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from .models import (
    ClarificationQuestion,
    ClarificationContext,
    UserResponse,
    QuestionPriority,
    ClarificationStatus,
)


# ─────────────────────────────────────────────────────────────────────────────
# Abstract UI Interface
# ─────────────────────────────────────────────────────────────────────────────


class ClarificationUI(ABC):
    """
    Abstract interface for user interaction during clarification.

    This protocol can be implemented by different UI backends:
    - Console UI (for CLI usage)
    - Web UI (for browser-based interaction)
    - API endpoint (for remote/hybrid workflows)
    - Mock UI (for automated testing)
    """

    @abstractmethod
    def present_question(self, question: ClarificationQuestion) -> None:
        """
        Display a clarification question to the user.

        Args:
            question: The question to present
        """
        pass

    @abstractmethod
    def collect_response(self, question: ClarificationQuestion) -> UserResponse:
        """
        Collect and validate user response to a question.

        This method should block until the user provides a valid response.

        Args:
            question: The question to collect a response for

        Returns:
            UserResponse with the user's answer
        """
        pass

    @abstractmethod
    def present_summary(self, context: ClarificationContext) -> None:
        """
        Show a summary of all clarifications at the end.

        Args:
            context: The clarification context with all Q&A
        """
        pass

    @abstractmethod
    def confirm_proceed(self, message: str) -> bool:
        """
        Ask user to confirm before proceeding.

        Args:
            message: Confirmation message to display

        Returns:
            True if user confirms, False otherwise
        """
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Console Implementation
# ─────────────────────────────────────────────────────────────────────────────


class ConsoleClarificationUI(ClarificationUI):
    """
    Console-based implementation for CLI usage.

    Provides interactive command-line prompts for user clarification.

    Args:
        input_func: Injectable input function (for testing, default: built-in input)
        print_func: Injectable print function (for testing, default: built-in print)
    """

    def __init__(
        self,
        input_func: Callable[[str], str] | None = None,
        print_func: Callable[[str], None] | None = None,
    ) -> None:
        self._input = input_func if input_func is not None else input
        self._print = print_func if print_func is not None else print

    def present_question(self, question: ClarificationQuestion) -> None:
        """Display question with formatted options."""
        self._print(f"\n{'=' * 60}")
        self._print(f"[Question {question.priority.value.upper()}] {question.question_id}")
        self._print(f"\n{question.question_text}\n")

        for i, option in enumerate(question.options, 1):
            self._print(f"  {i}. {option}")

        if question.allow_other:
            self._print(f"  {len(question.options) + 1}. Other (specify your answer)")

        if question.context_hint:
            self._print(f"\n  Context: {question.context_hint}")

        self._print(f"{'=' * 60}\n")

    def collect_response(self, question: ClarificationQuestion) -> UserResponse:
        """Collect and validate user input."""
        max_option = len(question.options) + (1 if question.allow_other else 0)

        while True:
            try:
                user_input = self._input("Your answer (enter number): ").strip()
                if not user_input:
                    self._print("Please enter a number.")
                    continue

                selection = int(user_input)

                if 1 <= selection <= len(question.options):
                    response = UserResponse(
                        question_id=question.question_id,
                        selected_option=question.options[selection - 1],
                    )
                    response.mark_answered(question.options[selection - 1])
                    return response
                elif selection == max_option and question.allow_other:
                    custom = self._input("Please specify your answer: ").strip()
                    response = UserResponse(question_id=question.question_id)
                    response.mark_answered("CUSTOM", custom)
                    return response
                else:
                    self._print(f"Invalid selection. Please enter 1-{max_option}")
            except ValueError:
                self._print("Please enter a number.")

    def present_summary(self, context: ClarificationContext) -> None:
        """Show summary of all Q&A."""
        self._print(f"\n{'=' * 60}")
        self._print("Clarification Summary")
        self._print(f"{'=' * 60}\n")

        for question, response in zip(context.questions, context.responses):
            self._print(f"Q: {question.question_text}")
            answer = response.custom_answer if response.is_custom_answer() else response.selected_option
            self._print(f"A: {answer}\n")

        self._print(f"Total questions: {len(context.questions)}")
        self._print(f"Status: {context.status.value}")

    def confirm_proceed(self, message: str) -> bool:
        """Ask for confirmation."""
        while True:
            response = self._input(f"{message} (y/n): ").strip().lower()
            if response in ("y", "yes"):
                return True
            elif response in ("n", "no"):
                return False
            self._print("Please answer 'y' or 'n'.")


# ─────────────────────────────────────────────────────────────────────────────
# Mock Implementation for Testing
# ─────────────────────────────────────────────────────────────────────────────


class MockClarificationUI(ClarificationUI):
    """
    Mock implementation for automated testing.

    Provides predefined responses without actual user interaction.

    Args:
        predefined_responses: Dict mapping question_id to response value
            Value can be a string (selected option) or dict with keys:
            - 'selected_option': The option to select
            - 'custom_answer': Custom answer if option is 'CUSTOM'
    """

    def __init__(self, predefined_responses: dict[str, str | dict[str, str]]) -> None:
        self._predefined_responses = predefined_responses
        self._questions_presented: list[str] = []
        self._all_responses: list[UserResponse] = []

    @property
    def questions_presented(self) -> list[str]:
        """List of question IDs that have been presented."""
        return self._questions_presented

    @property
    def all_responses(self) -> list[UserResponse]:
        """All responses that have been collected."""
        return self._all_responses

    def present_question(self, question: ClarificationQuestion) -> None:
        """Record that question was presented."""
        self._questions_presented.append(question.question_id)

    def collect_response(self, question: ClarificationQuestion) -> UserResponse:
        """Return predefined response for the question."""
        response_value = self._predefined_responses.get(question.question_id)

        if response_value is None:
            # Default: select first option if available
            if question.options:
                response = UserResponse(question_id=question.question_id)
                response.mark_answered(question.options[0])
            else:
                response = UserResponse(question_id=question.question_id)
                response.mark_answered("CUSTOM", "default")
        elif isinstance(response_value, str):
            # Simple string - treat as option selection
            if response_value == "CUSTOM":
                response = UserResponse(question_id=question.question_id)
                response.mark_answered("CUSTOM", "custom answer")
            elif response_value in question.options:
                response = UserResponse(question_id=question.question_id)
                response.mark_answered(response_value)
            else:
                # Fallback to first option if invalid
                response = UserResponse(question_id=question.question_id)
                response.mark_answered(question.options[0] if question.options else "CUSTOM", "fallback")
        else:
            # Dict with selected_option and optional custom_answer
            selected = response_value.get("selected_option", "CUSTOM")
            custom = response_value.get("custom_answer", "")
            response = UserResponse(question_id=question.question_id)
            response.mark_answered(selected, custom)

        self._all_responses.append(response)
        return response

    def present_summary(self, context: ClarificationContext) -> None:
        """Mock summary - no-op for testing."""
        pass

    def confirm_proceed(self, message: str) -> bool:
        """Mock confirmation - always returns True."""
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Response Validation
# ─────────────────────────────────────────────────────────────────────────────


class ResponseValidator:
    """
    Validates user responses to clarification questions.

    Provides static methods for validating that responses match
    the expected format and constraints of the question.
    """

    @staticmethod
    def validate(
        response: UserResponse, question: ClarificationQuestion
    ) -> tuple[bool, str]:
        """
        Validate a user response against its question.

        Args:
            response: The user's response to validate
            question: The question being answered

        Returns:
            Tuple of (is_valid, error_message).
            error_message is empty string if valid.
        """
        if response.is_custom_answer():
            if not response.custom_answer or not response.custom_answer.strip():
                return False, "Custom answer cannot be empty"
            return True, ""

        # Validate selected option is in question's options
        if response.selected_option not in question.options:
            return False, f"Invalid option selected: {response.selected_option}"

        return True, ""

    @staticmethod
    def validate_context(context: ClarificationContext) -> tuple[bool, list[str]]:
        """
        Validate an entire clarification context.

        Checks that all questions have valid responses and that
        no required questions are missing.

        Args:
            context: The clarification context to validate

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors: list[str] = []

        # Check for missing responses
        if len(context.responses) < len(context.questions):
            errors.append(
                f"Missing responses: {len(context.questions) - len(context.responses)} "
                "questions unanswered"
            )

        # Validate each response
        for question in context.questions:
            response = context.get_answer_for_question(question.question_id)
            if response is None:
                errors.append(f"No response for question: {question.question_id}")
            else:
                is_valid, error_msg = ResponseValidator.validate(response, question)
                if not is_valid:
                    errors.append(f"Invalid response for {question.question_id}: {error_msg}")

        return len(errors) == 0, errors


# ─────────────────────────────────────────────────────────────────────────────
# Exports
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "ClarificationUI",
    "ConsoleClarificationUI",
    "MockClarificationUI",
    "ClarificationQuestion",
    "UserResponse",
    "ClarificationContext",
    "QuestionPriority",
    "ClarificationStatus",
    "ResponseValidator",
]