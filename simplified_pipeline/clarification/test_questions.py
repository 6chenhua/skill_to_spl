"""
Unit tests for the question generation system.

Tests cover:
- QuestionGenerator class
- Template-based question generation
- LLM-based question generation
- Business translation rules
- SPL term sanitization
- Priority ordering
"""

import pytest
from unittest.mock import Mock, MagicMock

from .models import (
    AmbiguityMarker,
    AmbiguityType,
    AmbiguitySource,
    QuestionPriority,
)
from .questions import (
    QuestionGenerator,
    QUESTION_TEMPLATES,
    TRANSLATION_RULES,
    get_translation_for_term,
    is_spl_term,
    sanitize_question_text,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test Data Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_lexical_marker() -> AmbiguityMarker:
    """Create a sample lexical ambiguity marker."""
    return AmbiguityMarker(
        source_text="The system should process bank transactions",
        ambiguity_type=AmbiguityType.LEXICAL,
        severity=0.7,
        source=AmbiguitySource.RULE_BASED,
        section_name="WORKFLOW",
        source_item_index=0,
        explanation="'bank' could mean financial institution or river edge",
        suggestions=["financial institution", "river edge"],
        confidence=0.9,
        detected_by="lexical_detector",
    )


@pytest.fixture
def sample_quantifier_marker() -> AmbiguityMarker:
    """Create a sample quantifier ambiguity marker."""
    return AmbiguityMarker(
        source_text="The system should handle many users",
        ambiguity_type=AmbiguityType.QUANTIFIER,
        severity=0.8,
        source=AmbiguitySource.RULE_BASED,
        section_name="CONSTRAINTS",
        source_item_index=1,
        explanation="'many' is a vague quantifier",
        suggestions=["10-50", "50-500", "500+"],
        confidence=0.95,
        detected_by="quantifier_detector",
    )


@pytest.fixture
def sample_optionality_marker() -> AmbiguityMarker:
    """Create a sample optionality ambiguity marker."""
    return AmbiguityMarker(
        source_text="Users may optionally enable notifications",
        ambiguity_type=AmbiguityType.OPTIONALITY,
        severity=0.9,
        source=AmbiguitySource.RULE_BASED,
        section_name="WORKFLOW",
        source_item_index=2,
        explanation="'may optionally' creates uncertainty about requirement strength",
        suggestions=["required", "optional", "recommended"],
        confidence=0.85,
        detected_by="optionality_detector",
    )


@pytest.fixture
def sample_weak_word_marker() -> AmbiguityMarker:
    """Create a sample weak word ambiguity marker."""
    return AmbiguityMarker(
        source_text="Response time should be fast",
        ambiguity_type=AmbiguityType.WEAK_WORD,
        severity=0.6,
        source=AmbiguitySource.RULE_BASED,
        section_name="CONSTRAINTS",
        source_item_index=3,
        explanation="'fast' is subjective and needs quantification",
        suggestions=["under 1 second", "1-5 seconds", "under 1 minute"],
        confidence=0.8,
        detected_by="weak_word_detector",
    )


@pytest.fixture
def sample_markers(
    sample_lexical_marker,
    sample_quantifier_marker,
    sample_optionality_marker,
    sample_weak_word_marker,
) -> list[AmbiguityMarker]:
    """Create a list of sample markers."""
    return [
        sample_lexical_marker,
        sample_quantifier_marker,
        sample_optionality_marker,
        sample_weak_word_marker,
    ]


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = Mock()
    client.call_json = Mock(return_value={
        "question_text": "What response time do users typically expect?",
        "options": ["Under 1 second", "1-5 seconds", "Under 1 minute", "Other: ____"],
        "context_hint": "Response time affects user experience and system design.",
    })
    return client


# ─────────────────────────────────────────────────────────────────────────────
# QuestionGenerator Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestQuestionGenerator:
    """Tests for QuestionGenerator class."""

    def test_init_default_settings(self):
        """Test default initialization."""
        generator = QuestionGenerator()
        assert generator.use_templates is True
        assert generator.fallback_to_llm is True
        assert generator.llm_client is None

    def test_init_with_llm_client(self, mock_llm_client):
        """Test initialization with LLM client."""
        generator = QuestionGenerator(llm_client=mock_llm_client)
        assert generator.llm_client is mock_llm_client

    def test_generate_questions_empty_list(self):
        """Test generating questions from empty marker list."""
        generator = QuestionGenerator()
        result = generator.generate_questions([])
        
        assert result.success is False
        assert result.total_markers_processed == 0
        assert result.questions_generated == 0

    def test_generate_questions_single_marker(self, sample_lexical_marker):
        """Test generating question from single marker."""
        generator = QuestionGenerator()
        result = generator.generate_questions([sample_lexical_marker])
        
        assert result.total_markers_processed == 1
        assert result.questions_generated == 1
        assert len(result.questions) == 1

    def test_generate_questions_multiple_markers(self, sample_markers):
        """Test generating questions from multiple markers."""
        generator = QuestionGenerator()
        result = generator.generate_questions(sample_markers)
        
        assert result.total_markers_processed == 4
        assert result.questions_generated == 4
        assert len(result.questions) == 4

    def test_template_based_generation_lexical(self, sample_lexical_marker):
        """Test template-based generation for lexical ambiguity."""
        generator = QuestionGenerator(use_templates=True, fallback_to_llm=False)
        result = generator.generate_questions([sample_lexical_marker])
        
        assert result.template_used_count == 1
        assert result.llm_used_count == 0
        
        question = result.questions[0]
        assert "bank" in question.question_text.lower()
        assert len(question.options) >= 3
        assert question.allow_other is True

    def test_template_based_generation_quantifier(self, sample_quantifier_marker):
        """Test template-based generation for quantifier ambiguity."""
        generator = QuestionGenerator(use_templates=True, fallback_to_llm=False)
        result = generator.generate_questions([sample_quantifier_marker])
        
        question = result.questions[0]
        assert "many" in question.question_text.lower() or "quantity" in question.question_text.lower()
        # Should have numeric range options
        assert any("-" in opt or "+" in opt for opt in question.options)

    def test_template_based_generation_optionality(self, sample_optionality_marker):
        """Test template-based generation for optionality ambiguity."""
        generator = QuestionGenerator(use_templates=True, fallback_to_llm=False)
        result = generator.generate_questions([sample_optionality_marker])
        
        question = result.questions[0]
        assert "required" in question.question_text.lower() or "optional" in question.question_text.lower()
        assert question.priority == QuestionPriority.CRITICAL

    def test_priority_ordering(self, sample_markers):
        """Test that questions are ordered by priority."""
        generator = QuestionGenerator()
        result = generator.generate_questions(sample_markers)
        
        priorities = [q.priority for q in result.questions]
        # Should be sorted: CRITICAL < HIGH < MEDIUM < LOW
        priority_order = {
            QuestionPriority.CRITICAL: 0,
            QuestionPriority.HIGH: 1,
            QuestionPriority.MEDIUM: 2,
            QuestionPriority.LOW: 3,
        }
        sorted_priorities = sorted(priorities, key=lambda p: priority_order[p])
        assert priorities == sorted_priorities

    def test_llm_fallback_for_unknown_type(self):
        """Test LLM fallback for unknown ambiguity type."""
        # Create marker with a type not in templates
        marker = AmbiguityMarker(
            source_text="Some ambiguous text",
            ambiguity_type=AmbiguityType.CONTEXT,  # May not have template
            severity=0.5,
            source=AmbiguitySource.RULE_BASED,
            section_name="INTENT",
            source_item_index=0,
            explanation="Context is unclear",
            confidence=0.7,
            detected_by="context_detector",
        )
        
        mock_client = Mock()
        mock_client.call_json = Mock(return_value={
            "question_text": "Please provide more context for this requirement.",
            "options": ["Option A", "Option B", "Other: ____"],
            "context_hint": "More context helps ensure correct implementation.",
        })
        
        generator = QuestionGenerator(
            llm_client=mock_client,
            use_templates=True,
            fallback_to_llm=True,
        )
        result = generator.generate_questions([marker])
        
        assert result.llm_used_count >= 1
        mock_client.call_json.assert_called()

    def test_generic_question_when_no_template_no_llm(self):
        """Test generic question generation when no template and no LLM."""
        marker = AmbiguityMarker(
            source_text="Some ambiguous text",
            ambiguity_type=AmbiguityType.CONTEXT,
            severity=0.5,
            source=AmbiguitySource.RULE_BASED,
            section_name="INTENT",
            source_item_index=0,
            explanation="Context is unclear",
            confidence=0.7,
            detected_by="context_detector",
        )
        
        generator = QuestionGenerator(
            use_templates=False,
            fallback_to_llm=False,
        )
        result = generator.generate_questions([marker])
        
        assert result.questions_generated == 1
        question = result.questions[0]
        assert "clarify" in question.question_text.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Template Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestQuestionTemplates:
    """Tests for question templates."""

    def test_all_ambiguity_types_have_templates(self):
        """Test that common ambiguity types have templates."""
        common_types = [
            AmbiguityType.LEXICAL,
            AmbiguityType.QUANTIFIER,
            AmbiguityType.OPTIONALITY,
            AmbiguityType.WEAK_WORD,
            AmbiguityType.PRAGMATIC,
        ]
        
        for amb_type in common_types:
            assert amb_type in QUESTION_TEMPLATES, f"Missing template for {amb_type}"

    def test_templates_have_required_fields(self):
        """Test that all templates have required fields."""
        for amb_type, template in QUESTION_TEMPLATES.items():
            assert template.template_text, f"Missing template_text for {amb_type}"
            assert template.options_generator, f"Missing options_generator for {amb_type}"
            assert template.context_hint, f"Missing context_hint for {amb_type}"

    def test_template_options_include_other(self):
        """Test that template options include 'Other' option."""
        for amb_type, template in QUESTION_TEMPLATES.items():
            options = template.options_generator("test")
            assert any("other" in opt.lower() for opt in options), \
                f"Template for {amb_type} missing 'Other' option"

    def test_quantifier_options_are_numeric_ranges(self):
        """Test that quantifier options provide numeric ranges."""
        template = QUESTION_TEMPLATES.get(AmbiguityType.QUANTIFIER)
        if template:
            options = template.options_generator("many")
            # Should have at least one option with a number
            assert any(any(c.isdigit() for c in opt) for opt in options)


# ─────────────────────────────────────────────────────────────────────────────
# Translation Rules Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTranslationRules:
    """Tests for business translation rules."""

    def test_translation_rules_exist(self):
        """Test that translation rules are defined."""
        assert len(TRANSLATION_RULES) > 0

    def test_get_translation_for_common_terms(self):
        """Test translation for common vague terms."""
        # Test weak words
        assert get_translation_for_term("appropriate") is not None
        assert get_translation_for_term("sufficient") is not None
        assert get_translation_for_term("reasonable") is not None
        
        # Test quantifiers
        assert get_translation_for_term("many") is not None
        assert get_translation_for_term("few") is not None
        
        # Test optionality
        assert get_translation_for_term("may") is not None
        assert get_translation_for_term("optionally") is not None

    def test_translation_is_business_focused(self):
        """Test that translations use business language."""
        for term, translation in TRANSLATION_RULES.items():
            # Should not contain SPL terms
            assert not is_spl_term(translation), \
                f"Translation for '{term}' contains SPL terms: {translation}"
            # Should be a question
            assert "?" in translation or "specify" in translation.lower(), \
                f"Translation for '{term}' is not a question: {translation}"

    def test_translation_case_insensitive(self):
        """Test that translation lookup is case insensitive."""
        assert get_translation_for_term("MANY") is not None
        assert get_translation_for_term("Many") is not None
        assert get_translation_for_term("many") is not None


# ─────────────────────────────────────────────────────────────────────────────
# SPL Sanitization Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSPLSanitization:
    """Tests for SPL term detection and sanitization."""

    def test_is_spl_term_detects_spl_blocks(self):
        """Test detection of SPL block markers."""
        assert is_spl_term("[DEFINE_VARIABLES:]")
        assert is_spl_term("[END_VARIABLES]")
        assert is_spl_term("[MAIN_FLOW]")
        assert is_spl_term("[DEFINE_PERSONA:]")

    def test_is_spl_term_detects_ref_tags(self):
        """Test detection of REF tags."""
        assert is_spl_term("<REF>variable</REF>")
        assert is_spl_term("Use <REF>input</REF> here")

    def test_is_spl_term_detects_action_types(self):
        """Test detection of action types."""
        assert is_spl_term("LLM_TASK")
        assert is_spl_term("FILE_READ")
        assert is_spl_term("USER_INTERACTION")

    def test_is_spl_term_allows_business_text(self):
        """Test that business text is not flagged."""
        assert not is_spl_term("What response time do users expect?")
        assert not is_spl_term("How many users should this support?")
        assert not is_spl_term("Is this feature required?")

    def test_sanitize_removes_spl_blocks(self):
        """Test that sanitization removes SPL block markers."""
        text = "The [DEFINE_VARIABLES:] block defines variables [END_VARIABLES]"
        sanitized = sanitize_question_text(text)
        assert "[DEFINE_VARIABLES:]" not in sanitized
        assert "[END_VARIABLES]" not in sanitized

    def test_sanitize_removes_ref_tags(self):
        """Test that sanitization removes REF tags."""
        text = "Use <REF>input_data</REF> for processing"
        sanitized = sanitize_question_text(text)
        assert "<REF>" not in sanitized
        assert "</REF>" not in sanitized

    def test_sanitize_replaces_technical_terms(self):
        """Test that sanitization replaces technical terms."""
        text = "The var_id specifies the type_name"
        sanitized = sanitize_question_text(text)
        assert "var_id" not in sanitized
        assert "type_name" not in sanitized

    def test_sanitize_preserves_business_content(self):
        """Test that sanitization preserves business content."""
        text = "What is the expected response time for users?"
        sanitized = sanitize_question_text(text)
        assert "response time" in sanitized
        assert "users" in sanitized


# ─────────────────────────────────────────────────────────────────────────────
# Severity to Priority Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSeverityToPriority:
    """Tests for severity to priority conversion."""

    def test_critical_severity(self):
        """Test that severity >= 0.8 maps to CRITICAL."""
        generator = QuestionGenerator()
        assert generator._severity_to_priority(0.8) == QuestionPriority.CRITICAL
        assert generator._severity_to_priority(0.9) == QuestionPriority.CRITICAL
        assert generator._severity_to_priority(1.0) == QuestionPriority.CRITICAL

    def test_high_severity(self):
        """Test that severity 0.6-0.79 maps to HIGH."""
        generator = QuestionGenerator()
        assert generator._severity_to_priority(0.6) == QuestionPriority.HIGH
        assert generator._severity_to_priority(0.7) == QuestionPriority.HIGH
        assert generator._severity_to_priority(0.79) == QuestionPriority.HIGH

    def test_medium_severity(self):
        """Test that severity 0.4-0.59 maps to MEDIUM."""
        generator = QuestionGenerator()
        assert generator._severity_to_priority(0.4) == QuestionPriority.MEDIUM
        assert generator._severity_to_priority(0.5) == QuestionPriority.MEDIUM
        assert generator._severity_to_priority(0.59) == QuestionPriority.MEDIUM

    def test_low_severity(self):
        """Test that severity < 0.4 maps to LOW."""
        generator = QuestionGenerator()
        assert generator._severity_to_priority(0.0) == QuestionPriority.LOW
        assert generator._severity_to_priority(0.1) == QuestionPriority.LOW
        assert generator._severity_to_priority(0.39) == QuestionPriority.LOW


# ─────────────────────────────────────────────────────────────────────────────
# Question Quality Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestQuestionQuality:
    """Tests for question quality assurance."""

    def test_question_has_no_spl_terms(self, sample_markers):
        """Test that generated questions contain no SPL terms."""
        generator = QuestionGenerator()
        result = generator.generate_questions(sample_markers)
        
        for question in result.questions:
            assert not is_spl_term(question.question_text), \
                f"Question contains SPL terms: {question.question_text}"
            for option in question.options:
                assert not is_spl_term(option), \
                    f"Option contains SPL terms: {option}"

    def test_question_has_context_hint(self, sample_markers):
        """Test that generated questions have context hints."""
        generator = QuestionGenerator()
        result = generator.generate_questions(sample_markers)
        
        for question in result.questions:
            assert question.context_hint, \
                f"Question missing context hint: {question.question_text}"
            assert len(question.context_hint) > 10, \
                f"Context hint too short: {question.context_hint}"

    def test_question_has_multiple_options(self, sample_markers):
        """Test that generated questions have multiple options."""
        generator = QuestionGenerator()
        result = generator.generate_questions(sample_markers)
        
        for question in result.questions:
            assert len(question.options) >= 2, \
                f"Question has fewer than 2 options: {question.question_text}"

    def test_question_allows_other_option(self, sample_markers):
        """Test that questions allow 'Other' option."""
        generator = QuestionGenerator()
        result = generator.generate_questions(sample_markers)
        
        for question in result.questions:
            assert question.allow_other is True, \
                f"Question does not allow 'Other': {question.question_text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
