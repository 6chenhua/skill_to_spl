"""
Data models for structural assignment ambiguity detection.

These models represent ambiguities about which section (INTENT, WORKFLOW, 
CONSTRAINTS, EXAMPLES, NOTES) a statement should be assigned to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


class SectionCategory(str, Enum):
    """The 5 section categories in Step 1."""
    INTENT = "INTENT"
    WORKFLOW = "WORKFLOW"
    CONSTRAINTS = "CONSTRAINTS"
    EXAMPLES = "EXAMPLES"
    NOTES = "NOTES"


@dataclass
class StructuralAmbiguity:
    """
    Ambiguity about which section a statement belongs to.
    
    Example:
        source_text: "你不直接回复用户，只负责输出一个数字"
        candidate_sections: ["WORKFLOW", "CONSTRAINTS"]
        ambiguity_reason: "Could describe behavior (workflow) or limitation (constraint)"
    
    Attributes:
        ambiguity_id: Unique identifier
        source_text: The ambiguous statement
        candidate_sections: List of possible sections this could belong to
        ambiguity_reason: Explanation of why it's ambiguous
        confidence: 0.0-1.0, higher means more confident this is ambiguous
        pattern_matched: Which pattern detected this ambiguity
    """
    ambiguity_id: str
    source_text: str
    candidate_sections: List[str]
    ambiguity_reason: str
    confidence: float
    pattern_matched: Optional[str] = None
    
    def __post_init__(self):
        """Validate confidence range."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")


@dataclass
class SectionAssignmentQuestion:
    """
    Indirect question about section assignment.
    
    Business-oriented, never exposes pipeline internals.
    
    Attributes:
        question_id: Unique identifier
        ambiguity_id: Links to StructuralAmbiguity
        question_text: Business-oriented question (no technical jargon)
        option_sections: Dict mapping section name to business description
        selected_section: User's selected section (None until answered)
        source_text: Original ambiguous text
    """
    question_id: str
    ambiguity_id: str
    question_text: str
    option_sections: Dict[str, str]
    selected_section: Optional[str] = None
    source_text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "question_id": self.question_id,
            "ambiguity_id": self.ambiguity_id,
            "question_text": self.question_text,
            "option_sections": self.option_sections,
            "selected_section": self.selected_section,
            "source_text": self.source_text,
        }


@dataclass
class SectionGuidance:
    """
    Guidance passed to Step 1 to influence section assignment.
    
    This is the key integration point between Step 0 (clarification) and Step 1.
    
    Attributes:
        session_id: Unique session identifier
        clarification_applied: Whether clarification was performed
        section_overrides: Direct assignments: text -> section_name
        section_hints: Hints for sections: section_name -> list of hint texts
        questions: All questions and answers for audit trail
    """
    session_id: str
    clarification_applied: bool
    section_overrides: Dict[str, str] = field(default_factory=dict)
    section_hints: Dict[str, List[str]] = field(default_factory=dict)
    questions: List[SectionAssignmentQuestion] = field(default_factory=list)
    
    def get_section_for_text(self, text: str) -> Optional[str]:
        """Get override section for specific text (exact match)."""
        return self.section_overrides.get(text)
    
    def get_hints_for_section(self, section: str) -> List[str]:
        """Get hint texts for a section."""
        return self.section_hints.get(section, [])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "clarification_applied": self.clarification_applied,
            "section_overrides": self.section_overrides,
            "section_hints": self.section_hints,
            "questions": [q.to_dict() for q in self.questions],
        }


@dataclass
class StructuralDetectionResult:
    """
    Result of structural ambiguity detection.
    
    Attributes:
        ambiguities: List of detected structural ambiguities
        total_statements: Total statements analyzed
        ambiguous_statements: Number of statements with ambiguity
        needs_clarification: Whether clarification is needed
    """
    ambiguities: List[StructuralAmbiguity] = field(default_factory=list)
    total_statements: int = 0
    ambiguous_statements: int = 0
    
    @property
    def needs_clarification(self) -> bool:
        """Check if clarification is needed."""
        return len(self.ambiguities) > 0
    
    def get_ambiguities_by_sections(self, sections: List[str]) -> List[StructuralAmbiguity]:
        """Get ambiguities for specific section combination."""
        section_set = set(sections)
        return [a for a in self.ambiguities if set(a.candidate_sections) == section_set]
    
    def get_high_confidence_ambiguities(self, threshold: float = 0.6) -> List[StructuralAmbiguity]:
        """Get ambiguities above confidence threshold."""
        return [a for a in self.ambiguities if a.confidence >= threshold]


# Export all models
__all__ = [
    "SectionCategory",
    "StructuralAmbiguity",
    "SectionAssignmentQuestion",
    "SectionGuidance",
    "StructuralDetectionResult",
]
