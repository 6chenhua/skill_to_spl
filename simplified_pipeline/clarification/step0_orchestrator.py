"""
Step 0: Structural Clarification Orchestrator.

This module runs BEFORE Step 1 to clarify structural assignment ambiguities.

Flow:
    1. Detect structural ambiguities in raw text
    2. Generate indirect questions for top ambiguities
    3. Present questions to user one at a time
    4. Build SectionGuidance from answers
    5. Return guidance for Step 1 consumption

Key Design Principle:
    This step runs BEFORE Step 1, not after. The guidance directly influences
    Step 1's section assignment decisions.
"""

from __future__ import annotations

import logging
from typing import Optional, List

from .structural_models import (
    StructuralAmbiguity,
    SectionAssignmentQuestion,
    SectionGuidance,
    StructuralDetectionResult,
)
from .structural_detector import StructuralAmbiguityDetector
from .indirect_questions import IndirectQuestionGenerator
from .structural_ui import (
    StructuralClarificationUI,
    ConsoleStructuralClarificationUI,
    StructuralResponse,
)

logger = logging.getLogger(__name__)


def run_step0_structural_clarification(
    merged_doc_text: str,
    ui: Optional[ClarificationUI] = None,
    max_questions: int = 5,
    confidence_threshold: float = 0.6,
) -> SectionGuidance:
    """
    Step 0: Structural Clarification - runs BEFORE Step 1.
    
    Flow:
        1. Detect structural ambiguities in raw text
        2. Generate indirect questions for top ambiguities
        3. Present questions to user one at a time
        4. Build SectionGuidance from answers
        5. Return guidance for Step 1 consumption
    
    Args:
        merged_doc_text: Raw document text (before Step 1)
        ui: UI for user interaction (default: ConsoleClarificationUI)
        max_questions: Maximum number of clarification questions to ask
        confidence_threshold: Minimum confidence to trigger question
    
    Returns:
        SectionGuidance to pass to Step 1
    """
    import uuid
    
    session_id = f"guidance_{uuid.uuid4().hex[:8]}"
    
    # Import UI here to avoid circular dependency
    if ui is None:
        from .ui import ConsoleClarificationUI
        ui = ConsoleClarificationUI()
    
    logger.info(f"[{session_id}] Starting structural clarification...")
    
    # Step 1: Detect structural ambiguities
    logger.info(f"[{session_id}] Detecting structural ambiguities...")
    detector = StructuralAmbiguityDetector(confidence_threshold)
    detection_result = detector.detect(merged_doc_text)
    
    logger.info(
        f"[{session_id}] Analyzed {detection_result.total_statements} statements, "
        f"found {len(detection_result.ambiguities)} ambiguities"
    )
    
    if not detection_result.needs_clarification:
        logger.info(f"[{session_id}] No clarification needed")
        return SectionGuidance(
            session_id=session_id,
            clarification_applied=False,
            section_overrides={},
            section_hints={},
            questions=[],
        )
    
    # Filter by confidence threshold
    ambiguities = detection_result.get_high_confidence_ambiguities(confidence_threshold)
    
    if not ambiguities:
        logger.info(f"[{session_id}] No high-confidence ambiguities, skipping clarification")
        return SectionGuidance(
            session_id=session_id,
            clarification_applied=False,
            section_overrides={},
            section_hints={},
            questions=[],
        )
    
    # Limit to max_questions
    ambiguities = ambiguities[:max_questions]
    
    logger.info(f"[{session_id}] Will clarify {len(ambiguities)} ambiguities")
    
    # Step 2: Generate questions
    logger.info(f"[{session_id}] Generating clarification questions...")
    question_gen = IndirectQuestionGenerator()
    questions = question_gen.generate_questions(ambiguities)
    
    logger.info(f"[{session_id}] Generated {len(questions)} questions")
    
    # Step 3: Present questions and collect answers
    answered_questions: List[SectionAssignmentQuestion] = []
    
    for i, question in enumerate(questions, 1):
        logger.info(f"[{session_id}] Presenting question {i}/{len(questions)}")
        
        # Present question to user
        ui.present_question(question)
        
        # Collect response
        try:
            response = ui.collect_response(question)
            
            # Parse response to get selected section
            if response.selected_option:
                # Find which section this option corresponds to
                for section, desc in question.option_sections.items():
                    if response.selected_option == desc:
                        question.selected_section = section
                        break
            
            answered_questions.append(question)
            
            logger.info(
                f"[{session_id}] Question {i} answered: "
                f"{question.selected_section or 'unknown'}"
            )
            
        except Exception as e:
            logger.warning(f"[{session_id}] Failed to collect response: {e}")
            continue
    
    # Step 4: Build SectionGuidance
    section_overrides = {}
    section_hints = {}
    
    for question in answered_questions:
        if question.selected_section:
            # Map text to section
            section_overrides[question.source_text] = question.selected_section
            
            # Add hints for the selected section
            if question.selected_section not in section_hints:
                section_hints[question.selected_section] = []
            section_hints[question.selected_section].append(question.source_text)
    
    guidance = SectionGuidance(
        session_id=session_id,
        clarification_applied=len(answered_questions) > 0,
        section_overrides=section_overrides,
        section_hints=section_hints,
        questions=answered_questions,
    )
    
    logger.info(
        f"[{session_id}] Clarification complete: "
        f"{len(section_overrides)} overrides, "
        f"{len(section_hints)} sections with hints"
    )
    
    return guidance


def format_guidance_for_prompt(guidance: SectionGuidance) -> str:
    """
    Format SectionGuidance for inclusion in Step 1 LLM prompt.
    
    Returns a string that guides the LLM in section assignment.
    
    The guidance helps the LLM make better decisions about ambiguous statements
    based on user clarifications.
    
    Args:
        guidance: SectionGuidance from Step 0
    
    Returns:
        Formatted guidance string for LLM prompt
    """
    if not guidance.clarification_applied:
        return ""
    
    lines = [
        "## Section Assignment Guidance",
        "",
        "The following guidance comes from user clarification of ambiguous statements.",
        "Use these assignments when distributing content into sections:",
        "",
    ]
    
    # Add direct overrides
    if guidance.section_overrides:
        lines.append("### Direct Assignments")
        lines.append("(User clarified that these specific statements belong to particular sections)")
        lines.append("")
        
        for text, section in guidance.section_overrides.items():
            # Truncate long text for readability
            display_text = text[:80] + "..." if len(text) > 80 else text
            lines.append(f'- "{display_text}" → **{section}**')
        
        lines.append("")
    
    # Add section hints
    if guidance.section_hints:
        lines.append("### Section Hints")
        lines.append("(User indicated these types of content belong to specific sections)")
        lines.append("")
        
        for section, hints in guidance.section_hints.items():
            lines.append(f"**{section}** (user clarified content like these belongs here):")
            for hint in hints[:3]:  # Limit hints to avoid overwhelming
                display_hint = hint[:60] + "..." if len(hint) > 60 else hint
                lines.append(f'  - "{display_hint}"')
            if len(hints) > 3:
                lines.append(f"  - ... and {len(hints) - 3} more")
            lines.append("")
    
    lines.append("---")
    lines.append("When assigning ambiguous statements, prefer the section indicated above.")
    lines.append("If a statement matches multiple patterns, check the guidance first.")
    lines.append("")
    
    return "\n".join(lines)


def should_run_clarification(
    merged_doc_text: str,
    confidence_threshold: float = 0.6
) -> bool:
    """
    Quick check if clarification should run.
    
    Useful for deciding whether to enable HITL mode.
    
    Args:
        merged_doc_text: Document text to check
        confidence_threshold: Minimum confidence threshold
    
    Returns:
        True if clarification is needed
    """
    detector = StructuralAmbiguityDetector(confidence_threshold)
    result = detector.detect(merged_doc_text)
    
    # Check if there are high-confidence ambiguities
    high_conf = result.get_high_confidence_ambiguities(confidence_threshold)
    return len(high_conf) > 0


def get_clarification_summary(guidance: SectionGuidance) -> dict:
    """
    Get a summary of clarification results.
    
    Useful for logging and debugging.
    
    Args:
        guidance: SectionGuidance to summarize
    
    Returns:
        Summary dictionary
    """
    return {
        "session_id": guidance.session_id,
        "clarification_applied": guidance.clarification_applied,
        "section_overrides_count": len(guidance.section_overrides),
        "sections_with_hints": list(guidance.section_hints.keys()),
        "questions_answered": len([q for q in guidance.questions if q.selected_section]),
        "total_questions": len(guidance.questions),
    }


__all__ = [
    "run_step0_structural_clarification",
    "format_guidance_for_prompt",
    "should_run_clarification",
    "get_clarification_summary",
]
