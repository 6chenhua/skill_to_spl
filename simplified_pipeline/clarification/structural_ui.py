"""
UI interfaces for structural clarification (Step 0).

This is a separate UI module specifically for structural clarification,
working with SectionAssignmentQuestion instead of the legacy ClarificationQuestion.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional, Dict

from .structural_models import SectionAssignmentQuestion


class StructuralResponse:
    """Response from user for a structural clarification question."""
    
    def __init__(
        self,
        question_id: str,
        selected_option: Optional[str] = None,
    ):
        self.question_id = question_id
        self.selected_option = selected_option


class StructuralClarificationUI(ABC):
    """
    Abstract interface for structural clarification user interaction.
    
    This is separate from the legacy ClarificationUI to avoid type conflicts.
    """
    
    @abstractmethod
    def present_question(self, question: SectionAssignmentQuestion) -> None:
        """Display a structural clarification question."""
        pass
    
    @abstractmethod
    def collect_response(self, question: SectionAssignmentQuestion) -> StructuralResponse:
        """Collect user response to a question."""
        pass


class ConsoleStructuralClarificationUI(StructuralClarificationUI):
    """
    Console-based UI for structural clarification.
    
    Provides interactive command-line prompts for user clarification.
    """
    
    def __init__(
        self,
        input_func: Callable[[str], str] | None = None,
        print_func: Callable[[str], None] | None = None,
    ) -> None:
        self._input = input_func if input_func is not None else input
        self._print = print_func if print_func is not None else print
    
    def present_question(self, question: SectionAssignmentQuestion) -> None:
        """Display structural clarification question."""
        self._print(f"\n{'=' * 70}")
        self._print(f"[结构澄清问题] {question.question_id}")
        self._print(f"{'=' * 70}")
        self._print(f"\n{question.question_text}\n")
        
        # Display options
        options = list(question.option_sections.values())
        for i, option in enumerate(options, 1):
            self._print(f"  {i}. {option}")
        
        self._print(f"\n{'=' * 70}\n")
    
    def collect_response(self, question: SectionAssignmentQuestion) -> StructuralResponse:
        """Collect user selection."""
        options = list(question.option_sections.values())
        max_option = len(options)
        
        while True:
            try:
                user_input = self._input("请选择 (输入数字): ").strip()
                if not user_input:
                    self._print("请输入一个数字。")
                    continue
                
                selection = int(user_input)
                
                if 1 <= selection <= max_option:
                    selected_option = options[selection - 1]
                    return StructuralResponse(
                        question_id=question.question_id,
                        selected_option=selected_option,
                    )
                else:
                    self._print(f"无效选择。请输入 1-{max_option}")
            except ValueError:
                self._print("请输入数字。")


class MockStructuralClarificationUI(StructuralClarificationUI):
    """
    Mock UI for automated testing.
    
    Provides predefined responses without actual user interaction.
    """
    
    def __init__(
        self,
        predefined_responses: Dict[str, str],
    ) -> None:
        """
        Initialize with predefined responses.
        
        Args:
            predefined_responses: Dict mapping question_id to selected option
        """
        self._predefined_responses = predefined_responses
        self._questions_presented: list[str] = []
    
    @property
    def questions_presented(self) -> list[str]:
        """List of question IDs that have been presented."""
        return self._questions_presented
    
    def present_question(self, question: SectionAssignmentQuestion) -> None:
        """Record that question was presented."""
        self._questions_presented.append(question.question_id)
    
    def collect_response(self, question: SectionAssignmentQuestion) -> StructuralResponse:
        """Return predefined response for the question."""
        selected = self._predefined_responses.get(question.question_id)
        
        if selected is None:
            # Default: first option
            options = list(question.option_sections.values())
            selected = options[0] if options else None
        
        return StructuralResponse(
            question_id=question.question_id,
            selected_option=selected,
        )


__all__ = [
    "StructuralResponse",
    "StructuralClarificationUI",
    "ConsoleStructuralClarificationUI",
    "MockStructuralClarificationUI",
]
