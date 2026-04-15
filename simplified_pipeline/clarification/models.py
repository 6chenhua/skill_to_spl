"""
Data models for the HITL clarification module.

Defines the core data structures for ambiguity detection and clarification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class AmbiguityType(str, Enum):
    """Classification of ambiguity types."""

    LEXICAL = "lexical"  # Word has multiple meanings (e.g., "bank", "green")
    SYNTACTIC = "syntactic"  # Multiple parse interpretations
    SEMANTIC = "semantic"  # Scope/quantifier ambiguity
    PRAGMATIC = "pragmatic"  # Vague terms (e.g., "fast", "sufficient")
    REFERENCE = "reference"  # Unclear pronoun antecedent
    NEGATION = "negation"  # Double negatives, unclear negation scope
    OPTIONALITY = "optionality"  # Uncertain requirement strength
    QUANTIFIER = "quantifier"  # Vague quantifiers (many, few, some)
    WEAK_WORD = "weak_word"  # Weak requirement words (appropriate, suitable)
    CONTEXT = "context"  # Insufficient context for interpretation
    CONFLICT = "conflict"  # Contradictory statements


class AmbiguitySource(str, Enum):
    """Source of ambiguity detection."""

    RULE_BASED = "rule_based"  # Detected by pattern matching
    LLM_BASED = "llm_based"  # Detected by LLM analysis
    HYBRID = "hybrid"  # Detected by both methods


@dataclass
class AmbiguityMarker:
    """
    Represents a detected ambiguity in the text.

    Attributes:
        source_text: The exact text causing ambiguity
        ambiguity_type: Classification of the ambiguity
        severity: Score from 0.0 (minor) to 1.0 (critical)
        source: How this ambiguity was detected
        section_name: Which section contains this ambiguity (INTENT, WORKFLOW, etc.)
        source_item_index: Index of the SectionItem in the section
        explanation: Why this text is ambiguous
        suggestions: Possible interpretations or clarifications
        confidence: Confidence in this detection (0.0-1.0)
        detected_by: Which detector found this (rule name or LLM)
    """

    source_text: str
    ambiguity_type: AmbiguityType
    severity: float
    source: AmbiguitySource
    section_name: str
    source_item_index: int
    explanation: str = ""
    suggestions: list[str] = field(default_factory=list)
    confidence: float = 0.8
    detected_by: str = ""

    def __post_init__(self):
        """Validate severity and confidence ranges."""
        if not 0.0 <= self.severity <= 1.0:
            raise ValueError(f"Severity must be between 0.0 and 1.0, got {self.severity}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")


@dataclass
class DetectionResult:
    """
    Result of ambiguity detection on a SectionBundle.

    Attributes:
        markers: List of detected ambiguity markers
        defect_density: Calculated defect density (affected_words / total_words)
        total_words: Total word count in the analyzed text
        affected_words: Number of words affected by ambiguities
        needs_clarification: Whether clarification is needed based on threshold
        confidence_score: Overall confidence score for the extraction
    """

    markers: list[AmbiguityMarker]
    defect_density: float
    total_words: int
    affected_words: int
    needs_clarification: bool
    confidence_score: float

    def get_markers_by_type(self, ambiguity_type: AmbiguityType) -> list[AmbiguityMarker]:
        """Filter markers by ambiguity type."""
        return [m for m in self.markers if m.ambiguity_type == ambiguity_type]

    def get_markers_by_section(self, section_name: str) -> list[AmbiguityMarker]:
        """Filter markers by section name."""
        return [m for m in self.markers if m.section_name == section_name]

    def get_high_severity_markers(self, threshold: float = 0.7) -> list[AmbiguityMarker]:
        """Get markers with severity above threshold."""
        return [m for m in self.markers if m.severity >= threshold]


@dataclass
class SensitivityConfig:
    """
    Configuration for ambiguity detection sensitivity.

    Attributes:
        defect_density_threshold: Trigger clarification if above this value
        confidence_threshold: Trigger clarification if below this value
        severity_threshold: Minimum severity to include in results
        enable_rule_based: Enable rule-based detection
        enable_llm_based: Enable LLM-based detection
        merge_overlapping: Merge overlapping markers from different sources
    """

    defect_density_threshold: float = 0.15
    confidence_threshold: float = 0.7
    severity_threshold: float = 0.3
    enable_rule_based: bool = True
    enable_llm_based: bool = True
    merge_overlapping: bool = True

    @classmethod
    def low(cls) -> "SensitivityConfig":
        """Low sensitivity - fewer clarifications triggered."""
        return cls(
            defect_density_threshold=0.25,
            confidence_threshold=0.5,
            severity_threshold=0.5,
        )

    @classmethod
    def medium(cls) -> "SensitivityConfig":
        """Medium sensitivity - balanced detection."""
        return cls(
            defect_density_threshold=0.15,
            confidence_threshold=0.7,
            severity_threshold=0.3,
        )

    @classmethod
    def high(cls) -> "SensitivityConfig":
        """High sensitivity - more clarifications triggered."""
        return cls(
            defect_density_threshold=0.10,
            confidence_threshold=0.8,
            severity_threshold=0.2,
        )


class QuestionPriority(str, Enum):
    """Priority levels for clarification questions."""

    CRITICAL = "critical"  # Must be answered before proceeding
    HIGH = "high"  # Important for correctness
    MEDIUM = "medium"  # Improves quality but not blocking
    LOW = "low"  # Nice to have, optional clarification


@dataclass
class ClarificationQuestion:
    """
    A business-domain clarification question for users.

    Key principle: Questions must be in business terms, NOT technical/SPL terms.
    Users should never see SPL, SQL, or programming jargon.

    Attributes:
        question_id: Unique identifier for this question
        ambiguity_marker_id: ID of the AmbiguityMarker this addresses
        question_text: The actual question (no technical jargon)
        options: Multiple choice options for the user
        allow_other: Whether to allow "Other: ____" free text response
        context_hint: Why this question matters (business context)
        priority: Priority level for ordering questions
        expected_answer_type: Type of answer expected (CHOICE, TEXT, NUMBER, BOOLEAN)
        validation_pattern: Optional regex pattern for answer validation
        source_section: Which section this relates to
        source_text: Original ambiguous text
        answered: Whether this question has been answered
        answer: The user's answer (if provided)
        answer_timestamp: When the answer was provided
    """

    question_id: str
    ambiguity_marker_id: str
    question_text: str
    options: list[str] = field(default_factory=list)
    allow_other: bool = True
    context_hint: str = ""
    priority: QuestionPriority = QuestionPriority.MEDIUM
    expected_answer_type: str = "CHOICE"  # CHOICE, TEXT, NUMBER, BOOLEAN
    validation_pattern: str = ""
    source_section: str = ""
    source_text: str = ""
    answered: bool = False
    answer: Optional[str] = None
    answer_timestamp: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "question_id": self.question_id,
            "ambiguity_marker_id": self.ambiguity_marker_id,
            "question_text": self.question_text,
            "options": self.options,
            "allow_other": self.allow_other,
            "context_hint": self.context_hint,
            "priority": self.priority.value,
            "expected_answer_type": self.expected_answer_type,
            "source_section": self.source_section,
            "source_text": self.source_text,
            "answered": self.answered,
            "answer": self.answer,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClarificationQuestion":
        """Create instance from dictionary."""
        priority = data.get("priority", "medium")
        if isinstance(priority, str):
            priority = QuestionPriority(priority)
        return cls(
            question_id=data["question_id"],
            ambiguity_marker_id=data["ambiguity_marker_id"],
            question_text=data["question_text"],
            options=data.get("options", []),
            allow_other=data.get("allow_other", True),
            context_hint=data.get("context_hint", ""),
            priority=priority,
            expected_answer_type=data.get("expected_answer_type", "CHOICE"),
            validation_pattern=data.get("validation_pattern", ""),
            source_section=data.get("source_section", ""),
            source_text=data.get("source_text", ""),
            answered=data.get("answered", False),
            answer=data.get("answer"),
        )


@dataclass
class QuestionGenerationResult:
    """
    Result of generating clarification questions.

    Attributes:
        questions: List of generated clarification questions
        total_markers_processed: Number of ambiguity markers processed
        questions_generated: Number of questions generated
        template_used_count: Number of questions from templates
        llm_used_count: Number of questions from LLM
        errors: Any errors encountered during generation
    """

    questions: list[ClarificationQuestion] = field(default_factory=list)
    total_markers_processed: int = 0
    questions_generated: int = 0
    template_used_count: int = 0
    llm_used_count: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Whether question generation was successful."""
        return len(self.errors) == 0 and len(self.questions) > 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "questions": [q.to_dict() for q in self.questions],
            "total_markers_processed": self.total_markers_processed,
            "questions_generated": self.questions_generated,
            "template_used_count": self.template_used_count,
            "llm_used_count": self.llm_used_count,
            "errors": self.errors,
            "success": self.success,
        }


# ─────────────────────────────────────────────────────────────────────────────
# User Response & Clarification Context
# ─────────────────────────────────────────────────────────────────────────────


class ResponseStatus(str, Enum):
    """Status of a user response."""

    PENDING = "pending"
    ANSWERED = "answered"
    SKIPPED = "skipped"
    CLARIFIED = "clarified"  # Answered via iteration


@dataclass
class UserResponse:
    """
    User's answer to a clarification question.

    Attributes:
        question_id: Links to ClarificationQuestion
        selected_option: Selected option value or "CUSTOM"
        custom_answer: Filled if selected_option == "CUSTOM"
        timestamp: ISO format timestamp
        confidence: User's confidence in their answer (optional, 0.0-1.0)
        status: PENDING | ANSWERED | SKIPPED | CLARIFIED
    """

    question_id: str
    selected_option: str = ""
    custom_answer: str = ""
    timestamp: str = ""
    confidence: Optional[float] = None
    status: ResponseStatus = ResponseStatus.PENDING

    def __post_init__(self) -> None:
        """Set default timestamp and validate."""
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be 0.0-1.0, got {self.confidence}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "question_id": self.question_id,
            "selected_option": self.selected_option,
            "custom_answer": self.custom_answer,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserResponse":
        """Create instance from dictionary."""
        return cls(
            question_id=data["question_id"],
            selected_option=data.get("selected_option", ""),
            custom_answer=data.get("custom_answer", ""),
            timestamp=data.get("timestamp", ""),
            confidence=data.get("confidence"),
            status=ResponseStatus(data.get("status", "pending")),
        )

    def is_valid(self) -> bool:
        """Check if response has a valid answer."""
        if not self.question_id:
            return False
        if not self.selected_option:
            return False
        if self.selected_option == "CUSTOM" and not self.custom_answer:
            return False
        return True

    def is_custom_answer(self) -> bool:
        """Check if user provided a custom answer."""
        return self.selected_option == "CUSTOM"

    def get_answer_text(self) -> str:
        """Get the answered text (custom or selected)."""
        if self.is_custom_answer():
            return self.custom_answer
        return self.selected_option

    def mark_answered(self, option: str, custom: str = "", conf: Optional[float] = None) -> None:
        """Mark this response as answered."""
        self.selected_option = option
        self.custom_answer = custom
        self.confidence = conf
        self.status = ResponseStatus.ANSWERED
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def mark_skipped(self) -> None:
        """Mark this response as skipped."""
        self.status = ResponseStatus.SKIPPED
        self.timestamp = datetime.now(timezone.utc).isoformat()


class ClarificationStatus(str, Enum):
    """Status of a clarification session."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"


@dataclass
class ClarificationContext:
    """
    Complete clarification session state.

    Attributes:
        session_id: Unique session identifier
        markers: All detected ambiguities
        questions: Generated questions
        responses: User answers
        iteration: Current clarification round
        max_iterations: Max allowed (default 5)
        status: PENDING | IN_PROGRESS | COMPLETED | ABANDONED
        created_at: ISO timestamp
        updated_at: ISO timestamp
    """

    session_id: str
    markers: list[AmbiguityMarker] = field(default_factory=list)
    questions: list[ClarificationQuestion] = field(default_factory=list)
    responses: list[UserResponse] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 5
    status: ClarificationStatus = ClarificationStatus.PENDING
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        """Set default timestamps and validate."""
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if not 1 <= self.max_iterations <= 10:
            raise ValueError(f"max_iterations must be 1-10, got {self.max_iterations}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "markers": [m.__dict__ for m in self.markers],  # AmbiguityMarker uses __dict__
            "questions": [q.to_dict() for q in self.questions],
            "responses": [r.to_dict() for r in self.responses],
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClarificationContext":
        """Create instance from dictionary."""
        markers = []
        for m in data.get("markers", []):
            # Reconstruct AmbiguityMarker from dict
            markers.append(AmbiguityMarker(
                source_text=m["source_text"],
                ambiguity_type=AmbiguityType(m["ambiguity_type"]),
                severity=m["severity"],
                source=AmbiguitySource(m["source"]),
                section_name=m["section_name"],
                source_item_index=m["source_item_index"],
                explanation=m.get("explanation", ""),
                suggestions=m.get("suggestions", []),
                confidence=m.get("confidence", 0.8),
                detected_by=m.get("detected_by", ""),
            ))

        questions = [ClarificationQuestion.from_dict(q) for q in data.get("questions", [])]
        responses = [UserResponse.from_dict(r) for r in data.get("responses", [])]

        return cls(
            session_id=data["session_id"],
            markers=markers,
            questions=questions,
            responses=responses,
            iteration=data.get("iteration", 0),
            max_iterations=data.get("max_iterations", 5),
            status=ClarificationStatus(data.get("status", "pending")),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_marker(self, marker: AmbiguityMarker) -> None:
        """Add an ambiguity marker."""
        self.markers.append(marker)
        self.update_timestamp()

    def add_question(self, question: ClarificationQuestion) -> None:
        """Add a clarification question."""
        self.questions.append(question)
        self.update_timestamp()

    def add_response(self, response: UserResponse) -> None:
        """Add a user response."""
        self.responses.append(response)
        self.update_timestamp()

    def get_unanswered_questions(self) -> list[ClarificationQuestion]:
        """Get questions that haven't been answered."""
        answered_ids = {r.question_id for r in self.responses if r.status == ResponseStatus.ANSWERED}
        return [q for q in self.questions if q.question_id not in answered_ids]

    def get_pending_markers(self) -> list[AmbiguityMarker]:
        """Get markers that don't have corresponding answers."""
        answered_marker_ids = set()
        for r in self.responses:
            if r.status == ResponseStatus.ANSWERED:
                # Find the question to get its marker_id
                for q in self.questions:
                    if q.question_id == r.question_id:
                        answered_marker_ids.add(q.ambiguity_marker_id)
                        break
        return [m for m in self.markers if m.source_item_index not in answered_marker_ids]

    def is_complete(self) -> bool:
        """Check if all questions have been answered."""
        return len(self.get_unanswered_questions()) == 0

    def can_continue(self) -> bool:
        """Check if clarification can continue (not maxed out)."""
        return self.iteration < self.max_iterations and not self.is_complete()

    def advance_iteration(self) -> None:
        """Advance to next iteration round."""
        self.iteration += 1
        self.status = ClarificationStatus.IN_PROGRESS
        self.update_timestamp()

    def mark_completed(self) -> None:
        """Mark the session as completed."""
        self.status = ClarificationStatus.COMPLETED
        self.update_timestamp()

    def mark_abandoned(self) -> None:
        """Mark the session as abandoned."""
        self.status = ClarificationStatus.ABANDONED
        self.update_timestamp()

    def sort_questions_by_priority(self) -> list[ClarificationQuestion]:
        """Return questions sorted by priority (highest first)."""
        priority_order = {
            QuestionPriority.CRITICAL: 0,
            QuestionPriority.HIGH: 1,
            QuestionPriority.MEDIUM: 2,
            QuestionPriority.LOW: 3,
        }
        return sorted(self.questions, key=lambda q: priority_order.get(q.priority, 2))

    def get_high_severity_markers(self, threshold: float = 0.7) -> list[AmbiguityMarker]:
        """Get markers exceeding severity threshold."""
        return [m for m in self.markers if m.severity >= threshold]

    def get_answer_for_question(self, question_id: str) -> Optional[UserResponse]:
        """Get the response for a specific question_id."""
        for r in self.responses:
            if r.question_id == question_id:
                return r
        return None

    def get_answers_summary(self) -> dict[str, str]:
        """Get a summary of all answers as question_id -> answer_text."""
        summary = {}
        for q in self.questions:
            resp = self.get_answer_for_question(q.question_id)
            if resp and resp.is_valid():
                summary[q.question_id] = resp.get_answer_text()
        return summary