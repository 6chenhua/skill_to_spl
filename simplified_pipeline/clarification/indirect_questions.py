"""
Question Generation System for Structural Ambiguity Clarification.

Generates business-oriented, indirect questions that hide pipeline internals.

Key Principle: Questions must be in business terms, NOT technical/SPL terms.
Users should never see section names like "WORKFLOW", "CONSTRAINTS", etc.
"""

from __future__ import annotations

import uuid
import logging
from typing import Dict, List, Optional, Tuple

from .structural_models import (
    StructuralAmbiguity,
    SectionAssignmentQuestion,
)

logger = logging.getLogger(__name__)


class IndirectQuestionGenerator:
    """
    Generates indirect, business-oriented questions for structural ambiguities.
    
    Key Principle: Questions must be in business terms, NOT technical/SPL terms.
    Users should never see section names like "WORKFLOW" or "CONSTRAINTS".
    
    Instead of asking:
        "Should this go to WORKFLOW or CONSTRAINTS?"
    
    We ask:
        "这句话更强调系统的工作方式还是对系统的硬性限制？"
    """
    
    # ═════════════════════════════════════════════════════════════════════════════
    # QUESTION TEMPLATES BY AMBIGUITY TYPE
    # ═════════════════════════════════════════════════════════════════════════════
    
    # Templates for different section combinations
    # Keys are sorted tuples of section names
    QUESTION_TEMPLATES: Dict[Tuple[str, ...], Dict] = {
        # WORKFLOW vs CONSTRAINTS - Most common ambiguity
        ("CONSTRAINTS", "WORKFLOW"): {
            "question": "这句话更强调系统的工作方式，还是对系统的硬性限制？",
            "options": {
                "WORKFLOW": "描述系统如何工作（流程/行为/步骤）",
                "CONSTRAINTS": "描述硬性限制（必须/禁止/只能/不能）",
            },
            "context_hint": "工作方式描述系统做什么；硬性限制描述什么能做/不能做。",
        },
        
        # WORKFLOW vs EXAMPLES
        ("EXAMPLES", "WORKFLOW"): {
            "question": "这是在描述系统的一般工作流程，还是在举例说明？",
            "options": {
                "WORKFLOW": "系统的一般操作方式和工作流程",
                "EXAMPLES": "具体的使用示例或场景",
            },
            "context_hint": "一般流程描述系统通常如何工作；示例展示具体情形。",
        },
        
        # CONSTRAINTS vs INTENT
        ("CONSTRAINTS", "INTENT"): {
            "question": "这是在说明系统的核心职责，还是在规定必须遵守的规则？",
            "options": {
                "INTENT": "说明系统的目的和核心职责",
                "CONSTRAINTS": "规定必须/禁止的行为或限制",
            },
            "context_hint": "目的描述'做什么'；规则限制'怎么做'。",
        },
        
        # INTENT vs NOTES
        ("INTENT", "NOTES"): {
            "question": "这是系统的核心功能说明，还是补充的背景信息？",
            "options": {
                "INTENT": "核心功能和主要职责",
                "NOTES": "补充说明、背景信息或备注",
            },
            "context_hint": "核心功能是系统的主要职责；注释提供额外信息。",
        },
        
        # WORKFLOW vs NOTES
        ("NOTES", "WORKFLOW"): {
            "question": "这是操作步骤说明，还是相关的背景说明？",
            "options": {
                "WORKFLOW": "具体的操作步骤或流程",
                "NOTES": "背景信息、说明或注释",
            },
            "context_hint": "步骤是系统执行的动作；注释提供额外信息。",
        },
        
        # CONSTRAINTS vs EXAMPLES
        ("CONSTRAINTS", "EXAMPLES"): {
            "question": "这是在说明规则限制，还是在举例？",
            "options": {
                "CONSTRAINTS": "必须遵守的规则和限制",
                "EXAMPLES": "具体的示例场景",
            },
            "context_hint": "规则是硬性要求；示例展示如何应用。",
        },
        
        # INTENT vs EXAMPLES
        ("EXAMPLES", "INTENT"): {
            "question": "这是在说明系统的目的，还是在举例？",
            "options": {
                "INTENT": "系统的目的和职责",
                "EXAMPLES": "具体的示例场景",
            },
            "context_hint": "目的是系统要做什么；示例展示具体情形。",
        },
        
        # CONSTRAINTS vs NOTES
        ("CONSTRAINTS", "NOTES"): {
            "question": "这是硬性规则/限制，还是补充说明？",
            "options": {
                "CONSTRAINTS": "硬性规则和限制",
                "NOTES": "补充说明或背景信息",
            },
            "context_hint": "规则是硬性要求；注释是额外信息。",
        },
    }
    
    # Business-friendly section names (never shown to user, but useful for debugging)
    BUSINESS_NAMES: Dict[str, str] = {
        "INTENT": "系统的目的和职责",
        "WORKFLOW": "系统的工作流程和步骤",
        "CONSTRAINTS": "必须遵守的规则和限制",
        "EXAMPLES": "具体的使用示例",
        "NOTES": "补充说明和背景信息",
    }
    
    # ═════════════════════════════════════════════════════════════════════════════
    # QUESTION GENERATION METHODS
    # ═════════════════════════════════════════════════════════════════════════════
    
    def __init__(self):
        """Initialize the question generator."""
        pass
    
    def generate_question(self, ambiguity: StructuralAmbiguity) -> SectionAssignmentQuestion:
        """
        Generate appropriate indirect question for the ambiguity.
        
        Args:
            ambiguity: The detected structural ambiguity
        
        Returns:
            SectionAssignmentQuestion ready for user presentation
        """
        # Sort sections to create consistent key
        section_tuple = tuple(sorted(ambiguity.candidate_sections))
        
        # Look for template
        template = self.QUESTION_TEMPLATES.get(section_tuple)
        
        if template:
            return self._create_from_template(ambiguity, template)
        else:
            # Fallback: generic question
            return self._create_generic_question(ambiguity)
    
    def generate_questions(
        self,
        ambiguities: List[StructuralAmbiguity]
    ) -> List[SectionAssignmentQuestion]:
        """
        Generate questions for multiple ambiguities.
        
        Args:
            ambiguities: List of detected ambiguities
        
        Returns:
            List of questions, sorted by confidence (highest first)
        """
        questions = []
        
        for ambiguity in ambiguities:
            try:
                question = self.generate_question(ambiguity)
                questions.append(question)
            except Exception as e:
                logger.warning(f"Failed to generate question for ambiguity: {e}")
                continue
        
        # Sort by ambiguity confidence (highest first)
        questions.sort(key=lambda q: self._get_ambiguity_confidence(q), reverse=True)
        
        return questions
    
    def _create_from_template(
        self,
        ambiguity: StructuralAmbiguity,
        template: Dict
    ) -> SectionAssignmentQuestion:
        """Create question from predefined template."""
        
        # Format question text with context
        question_text = template["question"]
        
        # Add context display to help user understand
        context_display = self._format_context_display(ambiguity.source_text)
        full_question_text = f"{context_display}\n\n{question_text}"
        
        return SectionAssignmentQuestion(
            question_id=f"q_{uuid.uuid4().hex[:8]}",
            ambiguity_id=ambiguity.ambiguity_id,
            question_text=full_question_text,
            option_sections=template["options"],
            selected_section=None,
            source_text=ambiguity.source_text,
        )
    
    def _create_generic_question(
        self,
        ambiguity: StructuralAmbiguity
    ) -> SectionAssignmentQuestion:
        """Create generic question for unknown ambiguity types."""
        
        sections = ambiguity.candidate_sections
        
        # Build options using business names
        options = {
            section: self.BUSINESS_NAMES.get(section, section)
            for section in sections
        }
        
        # Build question
        section_descriptions = "、".join(
            self.BUSINESS_NAMES.get(s, s) for s in sections
        )
        question_text = f"这段话更适合描述以下哪个方面？\n\n原文片段：{ambiguity.source_text[:80]}..."
        
        return SectionAssignmentQuestion(
            question_id=f"q_{uuid.uuid4().hex[:8]}",
            ambiguity_id=ambiguity.ambiguity_id,
            question_text=question_text,
            option_sections=options,
            selected_section=None,
            source_text=ambiguity.source_text,
        )
    
    def _format_context_display(self, source_text: str, max_length: int = 100) -> str:
        """
        Format the source text to show context.
        
        Helps users understand which part of the document is being clarified.
        """
        text = source_text.strip()
        
        if len(text) <= max_length:
            return f"原文片段：「{text}」"
        else:
            return f"原文片段：「{text[:max_length]}...」"
    
    def _get_ambiguity_confidence(self, question: SectionAssignmentQuestion) -> float:
        """Get the confidence of the ambiguity this question is for."""
        # This is a simplified approach - in practice you'd look up the ambiguity
        # For now, return a default
        return 0.7
    
    # ═════════════════════════════════════════════════════════════════════════════
    # VALIDATION METHODS
    # ═════════════════════════════════════════════════════════════════════════════
    
    def validate_question(self, question: SectionAssignmentQuestion) -> Tuple[bool, List[str]]:
        """
        Validate that a question follows the design principles.
        
        Returns:
            (is_valid, list of violations)
        """
        violations = []
        
        # Check 1: No technical terms in question
        technical_terms = ["WORKFLOW", "CONSTRAINTS", "INTENT", "EXAMPLES", "NOTES"]
        for term in technical_terms:
            if term in question.question_text:
                violations.append(f"Question contains technical term: {term}")
        
        # Check 2: Options are in business language
        for section, desc in question.option_sections.items():
            if section == desc:
                violations.append(f"Option for {section} is not business-oriented")
        
        # Check 3: Has at least 2 options
        if len(question.option_sections) < 2:
            violations.append("Question must have at least 2 options")
        
        return len(violations) == 0, violations
    
    def get_template_coverage(self) -> Dict[str, any]:
        """
        Get information about template coverage.
        
        Useful for understanding which ambiguity types have good templates.
        """
        from itertools import combinations
        
        # All possible pairs of sections
        all_sections = ["INTENT", "WORKFLOW", "CONSTRAINTS", "EXAMPLES", "NOTES"]
        all_pairs = list(combinations(all_sections, 2))
        
        covered = set(self.QUESTION_TEMPLATES.keys())
        uncovered = []
        
        for pair in all_pairs:
            sorted_pair = tuple(sorted(pair))
            if sorted_pair not in covered:
                uncovered.append(pair)
        
        return {
            "total_pairs": len(all_pairs),
            "covered": len(covered),
            "uncovered": uncovered,
            "coverage_percentage": len(covered) / len(all_pairs) * 100,
        }


# ═════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def generate_indirect_question(
    ambiguity: StructuralAmbiguity
) -> SectionAssignmentQuestion:
    """
    Convenience function to generate a question for an ambiguity.
    
    Args:
        ambiguity: The detected structural ambiguity
    
    Returns:
        Business-oriented question ready for user presentation
    """
    generator = IndirectQuestionGenerator()
    return generator.generate_question(ambiguity)


def generate_questions_for_ambiguities(
    ambiguities: List[StructuralAmbiguity]
) -> List[SectionAssignmentQuestion]:
    """
    Generate questions for multiple ambiguities.
    
    Args:
        ambiguities: List of detected ambiguities
    
    Returns:
        List of questions sorted by confidence
    """
    generator = IndirectQuestionGenerator()
    return generator.generate_questions(ambiguities)


def check_template_coverage() -> Dict:
    """
    Check which section combinations have question templates.
    
    Returns:
        Coverage statistics
    """
    generator = IndirectQuestionGenerator()
    return generator.get_template_coverage()


__all__ = [
    "IndirectQuestionGenerator",
    "generate_indirect_question",
    "generate_questions_for_ambiguities",
    "check_template_coverage",
]
