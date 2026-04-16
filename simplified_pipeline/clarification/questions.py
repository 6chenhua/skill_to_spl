"""
Question Generation System for Ambiguity Clarification.

This module translates ambiguity detection results into business-domain
clarifying questions. Key principle: SPL must be hidden from users.

Based on research patterns:
- Rao & Daumé III: Generate questions whose answers most improve completeness
- CLAM Framework: Detect → Generate Question → Respond
- ClarifyGPT: Detect via consistency check → Prompt LLM for questions
- AmbiSQL: Multiple-choice questions with abstain and "other" options
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

from .models import (
    AmbiguityMarker,
    AmbiguityType,
    ClarificationQuestion,
    QuestionGenerationResult,
    QuestionPriority,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# QUESTION TEMPLATES
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class QuestionTemplate:
    """Template for generating clarification questions."""
    
    template_text: str  # Question template with {term} placeholder
    options_generator: Callable[[str], list[str]]  # Function to generate options
    context_hint: str  # Why this question matters
    priority: QuestionPriority = QuestionPriority.MEDIUM


# Template functions for generating options
def _lexical_options(term: str) -> list[str]:
    """Generate options for lexical ambiguities."""
    return [
        f"Common meaning of '{term}'",
        f"Alternative meaning of '{term}'",
        "Other: ____",
    ]


def _quantifier_options(term: str) -> list[str]:
    """Generate options for vague quantifiers."""
    quantifier_map = {
        "many": ["10-50", "50-500", "500+", "Other: ____"],
        "few": ["1-5", "5-10", "10-20", "Other: ____"],
        "some": ["Less than half", "About half", "More than half", "Other: ____"],
        "several": ["3-5", "5-10", "10-20", "Other: ____"],
        "most": ["51-75%", "75-90%", "90-99%", "Other: ____"],
        "all": ["Yes, all without exception", "No, there are exceptions", "Other: ____"],
    }
    return quantifier_map.get(term.lower(), ["Small amount", "Medium amount", "Large amount", "Other: ____"])


def _optionality_options(term: str) -> list[str]:
    """Generate options for optionality ambiguities."""
    return [
        "Required for all cases",
        "Optional - depends on specific conditions",
        "Recommended but not mandatory",
        "Other: ____",
    ]


def _weak_word_options(term: str) -> list[str]:
    """Generate options for weak/vague words."""
    weak_word_map = {
        "appropriate": ["Industry standard", "Company specific", "Context dependent", "Other: ____"],
        "sufficient": ["Minimum viable", "Above average", "Best practice", "Other: ____"],
        "reasonable": ["Within normal range", "As agreed with stakeholders", "Case-by-case basis", "Other: ____"],
        "suitable": ["Standard solution", "Custom solution", "Depends on requirements", "Other: ____"],
        "adequate": ["Basic level", "Standard level", "Premium level", "Other: ____"],
        "fast": ["Under 1 second", "1-5 seconds", "Under 1 minute", "Other: ____"],
        "quickly": ["Immediately", "Within hours", "Within days", "Other: ____"],
        "efficient": ["Optimized for speed", "Optimized for cost", "Balanced approach", "Other: ____"],
    }
    return weak_word_map.get(term.lower(), ["Minimum acceptable", "Standard", "Best effort", "Other: ____"])


def _temporal_options(term: str) -> list[str]:
    """Generate options for temporal ambiguities."""
    return [
        "Immediately when triggered",
        "After a delay (specify: ____)",
        "At a scheduled time",
        "Other: ____",
    ]


def _type_options(term: str) -> list[str]:
    """Generate options for type ambiguities."""
    return [
        "Text/String",
        "Number (integer)",
        "Number (decimal)",
        "Boolean (yes/no)",
        "List/Array",
        "Other: ____",
    ]


# Main template dictionary
QUESTION_TEMPLATES: dict[AmbiguityType, QuestionTemplate] = {
    AmbiguityType.LEXICAL: QuestionTemplate(
        template_text="The term '{term}' could have different meanings in this context. Which meaning applies here?",
        options_generator=_lexical_options,
        context_hint="Different interpretations may lead to different implementations.",
        priority=QuestionPriority.HIGH,
    ),
    AmbiguityType.QUANTIFIER: QuestionTemplate(
        template_text="'{term}' is a vague quantity. Please specify the approximate range:",
        options_generator=_quantifier_options,
        context_hint="Specific numbers help ensure the system handles the expected scale.",
        priority=QuestionPriority.HIGH,
    ),
    AmbiguityType.OPTIONALITY: QuestionTemplate(
        template_text="The requirement uses '{term}' which suggests optionality. Is this feature required or optional?",
        options_generator=_optionality_options,
        context_hint="Understanding whether this is mandatory affects the workflow design.",
        priority=QuestionPriority.CRITICAL,
    ),
    AmbiguityType.WEAK_WORD: QuestionTemplate(
        template_text="'{term}' is a subjective term. What would be considered '{term}' in this context?",
        options_generator=_weak_word_options,
        context_hint="Clear criteria help ensure consistent behavior.",
        priority=QuestionPriority.MEDIUM,
    ),
    AmbiguityType.PRAGMATIC: QuestionTemplate(
        template_text="'{term}' is vague. Please provide more specific criteria:",
        options_generator=lambda t: ["Specific value or range", "Reference to standard", "Depends on context", "Other: ____"],
        context_hint="Specific criteria ensure consistent implementation.",
        priority=QuestionPriority.MEDIUM,
    ),
    AmbiguityType.CONTEXT: QuestionTemplate(
        template_text="The context for '{term}' is unclear. What additional context is needed?",
        options_generator=lambda t: ["More background information", "Specific use case", "Related constraints", "Other: ____"],
        context_hint="Additional context ensures correct interpretation.",
        priority=QuestionPriority.HIGH,
    ),
    AmbiguityType.CONFLICT: QuestionTemplate(
        template_text="There appears to be a conflict involving '{term}'. Which interpretation should take precedence?",
        options_generator=lambda t: ["First interpretation", "Second interpretation", "Merge both (specify how)", "Other: ____"],
        context_hint="Resolving conflicts ensures consistent behavior.",
        priority=QuestionPriority.CRITICAL,
    ),
}


# ═════════════════════════════════════════════════════════════════════════════
# BUSINESS TRANSLATION RULES
# ═════════════════════════════════════════════════════════════════════════════

TRANSLATION_RULES: dict[str, str] = {
    # Weak words → Quantification questions
    "appropriate": "What would be considered appropriate in this context?",
    "sufficient": "How much/many would be sufficient?",
    "reasonable": "What timeframe/amount would be reasonable?",
    "suitable": "What criteria determine suitability?",
    "adequate": "What level would be adequate?",
    
    # Vague quantifiers → Specific numbers
    "many": "How many specifically?",
    "few": "How few? Please specify a range.",
    "some": "Which ones specifically?",
    "several": "How many exactly?",
    "most": "What percentage?",
    "all": "Are there any exceptions?",
    
    # Optionality → Business impact question
    "may": "Is this required for all cases, or optional in some scenarios?",
    "optionally": "When should this be included vs skipped?",
    "can": "Is this a capability or a permission?",
    "might": "How likely is this to occur?",
    "could": "Under what conditions would this happen?",
    
    # Temporal vagueness
    "soon": "What is the expected timeframe?",
    "quickly": "What response time is expected?",
    "immediately": "Is there any acceptable delay?",
    "eventually": "What is the maximum acceptable delay?",
    "periodically": "How frequently?",
    
    # Quality vagueness
    "good": "What quality criteria apply?",
    "better": "Better than what baseline?",
    "best": "What defines 'best' in this context?",
    "proper": "What constitutes proper execution?",
    "correct": "What makes it correct?",
}


# ═════════════════════════════════════════════════════════════════════════════
# QUESTION GENERATOR CLASS
# ═════════════════════════════════════════════════════════════════════════════

class QuestionGenerator:
    """
    Generates business-domain clarification questions from ambiguity markers.
    
    Key principle: Questions must be in business terms, NOT technical/SPL terms.
    Users should never see SPL, SQL, or programming jargon.
    
    Uses a hybrid approach:
    1. Template-based generation for common patterns (fast, deterministic)
    2. LLM-based generation for complex cases (flexible, context-aware)
    """
    
    def __init__(
        self,
        llm_client: Optional[object] = None,
        use_templates: bool = True,
        fallback_to_llm: bool = True,
    ):
        """
        Initialize the question generator.
        
        Args:
            llm_client: LLM client for complex question generation
            use_templates: Whether to use template-based generation first
            fallback_to_llm: Whether to fall back to LLM for unknown types
        """
        self.llm_client = llm_client
        self.use_templates = use_templates
        self.fallback_to_llm = fallback_to_llm
        self._question_counter = 0
    
    def generate_questions(
        self,
        markers: list[AmbiguityMarker],
    ) -> QuestionGenerationResult:
        """
        Generate clarification questions for detected ambiguities.
        
        Args:
            markers: List of detected ambiguity markers
            
        Returns:
            QuestionGenerationResult with generated questions
        """
        result = QuestionGenerationResult(total_markers_processed=len(markers))
        
        for marker in markers:
            try:
                question = self._generate_single_question(marker)
                if question:
                    result.questions.append(question)
                    result.questions_generated += 1
                    if self.use_templates and marker.ambiguity_type in QUESTION_TEMPLATES:
                        result.template_used_count += 1
                    else:
                        result.llm_used_count += 1
            except Exception as e:
                error_msg = f"Failed to generate question for marker {marker.source_text[:50]}: {e}"
                logger.warning(error_msg)
                result.errors.append(error_msg)
        
        # Sort by priority (CRITICAL first, then HIGH, MEDIUM, LOW)
        priority_order = {
            QuestionPriority.CRITICAL: 0,
            QuestionPriority.HIGH: 1,
            QuestionPriority.MEDIUM: 2,
            QuestionPriority.LOW: 3,
        }
        result.questions.sort(key=lambda q: priority_order.get(q.priority, 2))
        
        return result
    
    def _generate_single_question(
        self,
        marker: AmbiguityMarker,
    ) -> Optional[ClarificationQuestion]:
        """Generate a single clarification question from an ambiguity marker."""
        
        # Extract the ambiguous term
        term = self._extract_term(marker)
        
        # Try template-based generation first
        if self.use_templates and marker.ambiguity_type in QUESTION_TEMPLATES:
            return self._generate_from_template(marker, term)
        
        # Fall back to LLM-based generation
        if self.fallback_to_llm and self.llm_client:
            return self._generate_with_llm(marker, term)
        
        # Last resort: generic question
        return self._generate_generic_question(marker, term)
    
    def _extract_term(self, marker: AmbiguityMarker) -> str:
        """Extract the ambiguous term from the marker."""
        # Use suggestions if available
        if marker.suggestions:
            # Extract term from first suggestion if it looks like a term
            first_suggestion = marker.suggestions[0]
            if len(first_suggestion) < 50:
                return first_suggestion
        
        # Fall back to source text (truncated)
        text = marker.source_text
        if len(text) > 50:
            return text[:47] + "..."
        return text
    
    def _generate_from_template(
        self,
        marker: AmbiguityMarker,
        term: str,
    ) -> ClarificationQuestion:
        """Generate question using predefined template."""
        template = QUESTION_TEMPLATES.get(marker.ambiguity_type)
        if not template:
            raise ValueError(f"No template for ambiguity type: {marker.ambiguity_type}")

        # Generate question text
        question_text = template.template_text.format(term=term)

        # Generate options
        options = template.options_generator(term)

        # Determine priority from severity
        priority = self._severity_to_priority(marker.severity)

        # Create context display: show the source text with the term highlighted
        context_display = self._format_context_display(marker.source_text, term)

        # Combine question with context for better user understanding
        full_question_text = f"{context_display}\n\n{question_text}"

        # Create question
        self._question_counter += 1
        return ClarificationQuestion(
            question_id=f"q_{self._question_counter:04d}_{uuid.uuid4().hex[:8]}",
            ambiguity_marker_id=f"marker_{marker.section_name}_{marker.source_item_index}",
            question_text=full_question_text,
            options=options,
            allow_other=True,
            context_hint=template.context_hint,
            priority=priority,
            expected_answer_type="CHOICE",
            source_section=marker.section_name,
            source_text=marker.source_text,
        )

    def _format_context_display(self, source_text: str, term: str) -> str:
        """
        Format the source text to show context around the ambiguous term.
        
        This helps users understand where the ambiguity appears in the original text.
        
        Args:
            source_text: The full source text containing the ambiguity
            term: The ambiguous term to highlight
            
        Returns:
            Formatted string showing context with highlighted term
        """
        # Find the term position (case-insensitive)
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        match = pattern.search(source_text)
        
        if not match:
            # Term not found, show truncated source
            if len(source_text) <= 100:
                return f"原文片段：{source_text}"
            return f"原文片段：{source_text[:100]}..."
        
        # Calculate context window (50 chars before and after)
        start_pos = match.start()
        end_pos = match.end()
        
        context_before = max(0, start_pos - 50)
        context_after = min(len(source_text), end_pos + 50)
        
        # Extract context
        prefix = "..." if context_before > 0 else ""
        suffix = "..." if context_after < len(source_text) else ""
        
        before = source_text[context_before:start_pos]
        highlighted = source_text[start_pos:end_pos]
        after = source_text[end_pos:context_after]
        
        # Format with highlight markers
        context_snippet = f"{prefix}{before}【{highlighted}】{after}{suffix}"
        
        return f"原文片段：{context_snippet}"

    def _generate_with_llm(
        self,
        marker: AmbiguityMarker,
        term: str,
    ) -> ClarificationQuestion:
        """Generate question using LLM for complex cases."""
        # Import here to avoid circular dependency
        from .prompts import render_question_generation_prompt
        
        if not self.llm_client:
            raise ValueError("LLM client not available")
        
        # Prepare context for LLM
        prompt = render_question_generation_prompt(
            ambiguity_type=marker.ambiguity_type.value,
            source_text=marker.source_text,
            section=marker.section_name,
            description=marker.explanation,
            term=term,
        )
        
        # Call LLM
        try:
            response = self.llm_client.call_json(
                step_name="question_generation",
                system="You are a helpful assistant that generates clarification questions for business users. Never use technical jargon like SPL, SQL, or programming terms.",
                user=prompt,
            )
            
            # Parse response
            question_text = response.get("question_text", "")
            options = response.get("options", [])
            context_hint = response.get("context_hint", "")
            
            if not question_text:
                raise ValueError("LLM did not generate question text")
            
            # Ensure options include "Other"
            if options and not any("other" in opt.lower() for opt in options):
                options.append("Other: ____")
            
            self._question_counter += 1
            return ClarificationQuestion(
                question_id=f"q_{self._question_counter:04d}_{uuid.uuid4().hex[:8]}",
                ambiguity_marker_id=f"marker_{marker.section_name}_{marker.source_item_index}",
                question_text=question_text,
                options=options if options else ["Yes", "No", "Other: ____"],
                allow_other=True,
                context_hint=context_hint,
                priority=self._severity_to_priority(marker.severity),
                expected_answer_type="CHOICE",
                source_section=marker.section_name,
                source_text=marker.source_text,
            )
            
        except Exception as e:
            logger.error(f"LLM question generation failed: {e}")
            raise
    
    def _generate_generic_question(
        self,
        marker: AmbiguityMarker,
        term: str,
    ) -> ClarificationQuestion:
        """Generate a generic question as last resort."""
        self._question_counter += 1
        return ClarificationQuestion(
            question_id=f"q_{self._question_counter:04d}_{uuid.uuid4().hex[:8]}",
            ambiguity_marker_id=f"marker_{marker.section_name}_{marker.source_item_index}",
            question_text=f"Please clarify the following: '{term}'",
            options=["Provide specific details", "Needs more context", "Other: ____"],
            allow_other=True,
            context_hint="This requirement needs clarification to ensure correct implementation.",
            priority=self._severity_to_priority(marker.severity),
            expected_answer_type="TEXT",
            source_section=marker.section_name,
            source_text=marker.source_text,
        )
    
    def _severity_to_priority(self, severity: float) -> QuestionPriority:
        """Convert severity score to question priority."""
        if severity >= 0.8:
            return QuestionPriority.CRITICAL
        elif severity >= 0.6:
            return QuestionPriority.HIGH
        elif severity >= 0.4:
            return QuestionPriority.MEDIUM
        else:
            return QuestionPriority.LOW


# ═════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def get_translation_for_term(term: str) -> Optional[str]:
    """
    Get business translation for a vague term.
    
    Args:
        term: The vague term to translate
        
    Returns:
        Business-focused question or None if not found
    """
    return TRANSLATION_RULES.get(term.lower())


def is_spl_term(text: str) -> bool:
    """
    Check if text contains SPL/technical jargon that should be hidden.
    
    Args:
        text: Text to check
        
    Returns:
        True if text contains technical jargon
    """
    spl_patterns = [
        r'\bDEFINE_\w+\b',
        r'\bEND_\w+\b',
        r'\bMAIN_FLOW\b',
        r'\bALTERNATIVE_FLOW\b',
        r'\bEXCEPTION_FLOW\b',
        r'\bSEQUENTIAL_BLOCK\b',
        r'\bDECISION-\d+\b',
        r'\bCOMMAND-\d+\b',
        r'\[DEFINE_',
        r'\[END_',
        r'<REF>',
        r'</REF>',
        r'\bvar_id\b',
        r'\btype_name\b',
        r'\bschema_notes\b',
        r'\bprovenance\b',
        r'\bLLM_TASK\b',
        r'\bFILE_READ\b',
        r'\bFILE_WRITE\b',
        r'\bUSER_INTERACTION\b',
    ]
    
    for pattern in spl_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def sanitize_question_text(text: str) -> str:
    """
    Remove any SPL/technical jargon from question text.
    
    Args:
        text: Question text to sanitize
        
    Returns:
        Sanitized text with technical jargon removed
    """
    # Remove SPL block markers
    text = re.sub(r'\[DEFINE_\w+:\]', '', text)
    text = re.sub(r'\[END_\w+\]', '', text)
    
    # Remove REF tags
    text = re.sub(r'</?REF>', '', text)
    
    # Remove technical variable references
    text = re.sub(r'\bvar_id\b', 'variable', text, flags=re.IGNORECASE)
    text = re.sub(r'\btype_name\b', 'type', text, flags=re.IGNORECASE)
    text = re.sub(r'\bschema_notes\b', 'description', text, flags=re.IGNORECASE)
    
    # Remove action types
    text = re.sub(r'\bLLM_TASK\b', 'processing step', text, flags=re.IGNORECASE)
    text = re.sub(r'\bFILE_READ\b', 'file reading', text, flags=re.IGNORECASE)
    text = re.sub(r'\bFILE_WRITE\b', 'file writing', text, flags=re.IGNORECASE)
    text = re.sub(r'\bUSER_INTERACTION\b', 'user input', text, flags=re.IGNORECASE)
    
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text
