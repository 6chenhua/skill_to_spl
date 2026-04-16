"""
Clarification module for ambiguity detection and question generation.

This module provides:
- AmbiguityMarker: Represents detected ambiguities in requirements
- ClarificationQuestion: Business-domain questions for users
- QuestionGenerator: Generates questions from ambiguity markers
- DetectionResult: Result of ambiguity detection
- SensitivityConfig: Configuration for detection sensitivity
- AmbiguityDetector: Hybrid detector combining rule-based and LLM detection
- ClarificationManager: Orchestrates the clarification workflow
- ClarificationContext: Complete clarification session state
- UserResponse: User's answer to a clarification question
"""

from .models import (
    AmbiguityMarker,
    AmbiguityType,
    AmbiguitySource,
    ClarificationQuestion,
    ClarificationContext,
    ClarificationStatus,
    QuestionPriority,
    QuestionGenerationResult,
    DetectionResult,
    SensitivityConfig,
    UserResponse,
    ResponseStatus,
)
from .detector import (
    AmbiguityDetector,
    RuleBasedDetector,
    LLMBasedDetector,
    calculate_defect_density,
    count_words,
    detect_ambiguities,
)

# Optional imports - only available if questions.py exists
try:
    from .questions import (
        QuestionGenerator,
        QUESTION_TEMPLATES,
        TRANSLATION_RULES,
        get_translation_for_term,
        is_spl_term,
        sanitize_question_text,
    )
    _HAS_QUESTIONS = True
except (ImportError, AttributeError):
    _HAS_QUESTIONS = False

# Optional imports - only available if manager.py exists
try:
    from .manager import (
        ClarificationManager,
        ClarificationCheckpoint,
        run_hitl_clarification,
        ClarificationPipelineStep,
    )
    _HAS_MANAGER = True
except (ImportError, AttributeError):
    _HAS_MANAGER = False

# Optional imports - only available if prompts.py exists
try:
    from .prompts import (
        QUESTION_GENERATION_SYSTEM,
        QUESTION_GENERATION_USER,
        render_question_generation_prompt,
        render_batch_question_generation_prompt,
        render_question_refinement_prompt,
        render_answer_processing_prompt,
    )
    _HAS_PROMPTS = True
except ImportError:
    _HAS_PROMPTS = False

__all__ = [
    # Models
    "AmbiguityMarker",
    "AmbiguityType",
    "AmbiguitySource",
    "ClarificationQuestion",
    "ClarificationContext",
    "ClarificationStatus",
    "QuestionPriority",
    "QuestionGenerationResult",
    "DetectionResult",
    "SensitivityConfig",
    "UserResponse",
    "ResponseStatus",
    # Detector
    "AmbiguityDetector",
    "RuleBasedDetector",
    "LLMBasedDetector",
    "calculate_defect_density",
    "count_words",
    "detect_ambiguities",
]

# Add optional exports if available
if _HAS_QUESTIONS:
    __all__.extend([
        "QuestionGenerator",
        "QUESTION_TEMPLATES",
        "TRANSLATION_RULES",
        "get_translation_for_term",
        "is_spl_term",
        "sanitize_question_text",
    ])

if _HAS_MANAGER:
    __all__.extend([
        "ClarificationManager",
        "ClarificationCheckpoint",
        "run_hitl_clarification",
        "ClarificationPipelineStep",
    ])

if _HAS_PROMPTS:
    __all__.extend([
        "QUESTION_GENERATION_SYSTEM",
        "QUESTION_GENERATION_USER",
        "render_question_generation_prompt",
        "render_batch_question_generation_prompt",
        "render_question_refinement_prompt",
        "render_answer_processing_prompt",
    ])
