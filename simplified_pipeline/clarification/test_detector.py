"""
Unit tests for the ambiguity detection engine.
"""

import pytest
from unittest.mock import MagicMock, patch

from .detector import (
    AmbiguityDetector,
    RuleBasedDetector,
    LLMBasedDetector,
    calculate_defect_density,
    count_words,
    detect_ambiguities,
    WEAK_WORDS,
    VAGUE_QUANTIFIERS,
    OPTIONALITY_MARKERS,
    PRONOUNS,
)
from .models import (
    AmbiguityMarker,
    AmbiguitySource,
    AmbiguityType,
    DetectionResult,
    SensitivityConfig,
)


# ═════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_section_bundle():
    """Create a mock SectionBundle for testing."""
    bundle = MagicMock()
    
    # Create mock items
    intent_item = MagicMock()
    intent_item.text = "The system should provide appropriate responses in a timely manner."
    
    workflow_item = MagicMock()
    workflow_item.text = "Process many requests and handle some errors appropriately."
    
    constraint_item = MagicMock()
    constraint_item.text = "The system must respond quickly. It may optionally cache results."
    
    # Setup all_sections
    bundle.all_sections.return_value = {
        "INTENT": [intent_item],
        "WORKFLOW": [workflow_item],
        "CONSTRAINTS": [constraint_item],
        "EXAMPLES": [],
        "NOTES": [],
    }
    
    # Setup to_text
    bundle.to_text.return_value = """
## INTENT
The system should provide appropriate responses in a timely manner.

## WORKFLOW
Process many requests and handle some errors appropriately.

## CONSTRAINTS
The system must respond quickly. It may optionally cache results.
"""
    
    return bundle


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock()
    client.call_json.return_value = {
        "ambiguities": [
            {
                "source_text": "appropriate",
                "ambiguity_type": "weak_word",
                "severity": 0.6,
                "section_name": "INTENT",
                "explanation": "Vague term without specific criteria",
                "suggestions": ["Define specific response quality criteria"],
            }
        ],
        "overall_confidence": 0.75,
    }
    return client


# ═════════════════════════════════════════════════════════════════════════════
# RULE-BASED DETECTOR TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestRuleBasedDetector:
    """Tests for RuleBasedDetector class."""

    def test_detect_weak_words_english(self):
        """Test detection of English weak words."""
        detector = RuleBasedDetector()
        text = "The system should provide appropriate and suitable responses."
        markers = detector.scan_text(text, "INTENT", 0)

        # Should detect 'appropriate' and 'suitable'
        weak_word_markers = [m for m in markers if m.ambiguity_type == AmbiguityType.WEAK_WORD]
        assert len(weak_word_markers) >= 2

        # Check that detected words are in our list
        detected_texts = {m.source_text.lower() for m in weak_word_markers}
        assert "appropriate" in detected_texts
        assert "suitable" in detected_texts

    def test_detect_weak_words_chinese(self):
        """Test detection of Chinese weak words."""
        detector = RuleBasedDetector()
        text = "系统应提供适当的响应，并合理处理请求。"
        markers = detector.scan_text(text, "INTENT", 0)

        weak_word_markers = [m for m in markers if m.ambiguity_type == AmbiguityType.WEAK_WORD]
        assert len(weak_word_markers) >= 1

    def test_detect_vague_quantifiers(self):
        """Test detection of vague quantifiers."""
        detector = RuleBasedDetector()
        text = "Many users will access the system, but few will use advanced features."
        markers = detector.scan_text(text, "WORKFLOW", 0)

        quantifier_markers = [m for m in markers if m.ambiguity_type == AmbiguityType.QUANTIFIER]
        assert len(quantifier_markers) >= 2

        detected_texts = {m.source_text.lower() for m in quantifier_markers}
        assert "many" in detected_texts
        assert "few" in detected_texts

    def test_detect_optionality_markers(self):
        """Test detection of optionality markers."""
        detector = RuleBasedDetector()
        text = "The system may cache results if needed. Users can optionally enable notifications."
        markers = detector.scan_text(text, "CONSTRAINTS", 0)

        optionality_markers = [m for m in markers if m.ambiguity_type == AmbiguityType.OPTIONALITY]
        assert len(optionality_markers) >= 2

    def test_detect_pronouns(self):
        """Test detection of pronouns."""
        detector = RuleBasedDetector()
        text = "The system processes it and returns them to the user. This is important."
        markers = detector.scan_text(text, "WORKFLOW", 0)

        reference_markers = [m for m in markers if m.ambiguity_type == AmbiguityType.REFERENCE]
        assert len(reference_markers) >= 2

        detected_texts = {m.source_text.lower() for m in reference_markers}
        assert "it" in detected_texts or "them" in detected_texts or "this" in detected_texts

    def test_detect_negation_patterns(self):
        """Test detection of negation patterns."""
        detector = RuleBasedDetector()
        text = "The result is not uncommon. This is not impossible."
        markers = detector.scan_text(text, "CONSTRAINTS", 0)

        negation_markers = [m for m in markers if m.ambiguity_type == AmbiguityType.NEGATION]
        assert len(negation_markers) >= 1

    def test_word_boundary_detection(self):
        """Test that word boundaries are respected."""
        detector = RuleBasedDetector()
        # 'many' should not match in 'manyfold' or 'howmany'
        text = "The system has manyfold capabilities. Howmany users?"
        markers = detector.scan_text(text, "INTENT", 0)

        # Should not detect 'many' in 'manyfold' or 'howmany'
        quantifier_markers = [m for m in markers if m.ambiguity_type == AmbiguityType.QUANTIFIER]
        assert len(quantifier_markers) == 0

    def test_case_insensitive_detection(self):
        """Test case-insensitive pattern matching."""
        detector = RuleBasedDetector()
        text = "APPROPRIATE and Suitable and ADEQUATE responses."
        markers = detector.scan_text(text, "INTENT", 0)

        weak_word_markers = [m for m in markers if m.ambiguity_type == AmbiguityType.WEAK_WORD]
        assert len(weak_word_markers) >= 3

    def test_marker_attributes(self):
        """Test that markers have correct attributes."""
        detector = RuleBasedDetector()
        text = "The system should provide appropriate responses."
        markers = detector.scan_text(text, "INTENT", 0)

        assert len(markers) >= 1
        marker = markers[0]

        assert marker.source_text == "appropriate"
        assert marker.ambiguity_type == AmbiguityType.WEAK_WORD
        assert marker.section_name == "INTENT"
        assert marker.source_item_index == 0
        assert marker.source == AmbiguitySource.RULE_BASED
        assert 0.0 <= marker.severity <= 1.0
        assert 0.0 <= marker.confidence <= 1.0
        assert marker.detected_by.startswith("rule:")


# ═════════════════════════════════════════════════════════════════════════════
# LLM-BASED DETECTOR TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMBasedDetector:
    """Tests for LLMBasedDetector class."""

    def test_llm_detection_basic(self, mock_section_bundle, mock_llm_client):
        """Test basic LLM detection."""
        detector = LLMBasedDetector(mock_llm_client)
        markers, confidence = detector.scan_bundle(mock_section_bundle)

        assert isinstance(markers, list)
        assert isinstance(confidence, float)
        assert 0.0 <= confidence <= 1.0

    def test_llm_parsing_response(self, mock_llm_client):
        """Test parsing of LLM response."""
        detector = LLMBasedDetector(mock_llm_client)
        
        response = {
            "ambiguities": [
                {
                    "source_text": "fast",
                    "ambiguity_type": "pragmatic",
                    "severity": 0.7,
                    "section_name": "CONSTRAINTS",
                    "explanation": "No specific time threshold defined",
                    "suggestions": ["Define maximum response time in seconds"],
                }
            ],
            "overall_confidence": 0.8,
        }

        markers, confidence = detector._parse_llm_response(response, "CONSTRAINTS", 0)

        assert len(markers) == 1
        assert confidence == 0.8
        assert markers[0].source_text == "fast"
        assert markers[0].ambiguity_type == AmbiguityType.PRAGMATIC

    def test_llm_empty_response(self, mock_llm_client):
        """Test handling of empty LLM response."""
        mock_llm_client.call_json.return_value = {"ambiguities": [], "overall_confidence": 1.0}
        
        detector = LLMBasedDetector(mock_llm_client)
        markers, confidence = detector.scan_bundle(MagicMock())

        assert markers == []
        assert confidence == 1.0

    def test_llm_type_mapping(self, mock_llm_client):
        """Test ambiguity type string mapping."""
        detector = LLMBasedDetector(mock_llm_client)

        assert detector._map_ambiguity_type("lexical") == AmbiguityType.LEXICAL
        assert detector._map_ambiguity_type("SYNTACTIC") == AmbiguityType.SYNTACTIC
        assert detector._map_ambiguity_type("unknown") == AmbiguityType.PRAGMATIC


# ═════════════════════════════════════════════════════════════════════════════
# DEFECT DENSITY TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestDefectDensity:
    """Tests for defect density calculation."""

    def test_empty_markers(self):
        """Test defect density with no markers."""
        density = calculate_defect_density([], 100)
        assert density == 0.0

    def test_zero_total_words(self):
        """Test defect density with zero total words."""
        marker = AmbiguityMarker(
            source_text="ambiguous",
            ambiguity_type=AmbiguityType.WEAK_WORD,
            severity=0.5,
            source=AmbiguitySource.RULE_BASED,
            section_name="INTENT",
            source_item_index=0,
        )
        density = calculate_defect_density([marker], 0)
        assert density == 0.0

    def test_normal_calculation(self):
        """Test normal defect density calculation."""
        markers = [
            AmbiguityMarker(
                source_text="appropriate response",
                ambiguity_type=AmbiguityType.WEAK_WORD,
                severity=0.5,
                source=AmbiguitySource.RULE_BASED,
                section_name="INTENT",
                source_item_index=0,
            ),
            AmbiguityMarker(
                source_text="many users",
                ambiguity_type=AmbiguityType.QUANTIFIER,
                severity=0.4,
                source=AmbiguitySource.RULE_BASED,
                section_name="WORKFLOW",
                source_item_index=0,
            ),
        ]
        
        # 2 words + 2 words = 4 affected words
        # Total 100 words
        density = calculate_defect_density(markers, 100)
        assert 0.0 <= density <= 1.0

    def test_density_capped_at_one(self):
        """Test that density is capped at 1.0."""
        markers = [
            AmbiguityMarker(
                source_text="word " * 50,  # 50 words
                ambiguity_type=AmbiguityType.WEAK_WORD,
                severity=0.5,
                source=AmbiguitySource.RULE_BASED,
                section_name="INTENT",
                source_item_index=0,
            ),
        ]
        
        density = calculate_defect_density(markers, 10)  # Only 10 total words
        assert density == 1.0


class TestCountWords:
    """Tests for word counting."""

    def test_english_text(self):
        """Test counting English words."""
        text = "The quick brown fox jumps over the lazy dog."
        count = count_words(text)
        assert count == 9

    def test_chinese_text(self):
        """Test counting Chinese characters."""
        text = "系统应提供适当的响应"
        count = count_words(text)
        assert count >= 5  # At least 5 Chinese characters

    def test_mixed_text(self):
        """Test counting mixed text."""
        text = "The 系统 should 提供 responses"
        count = count_words(text)
        assert count > 0

    def test_empty_text(self):
        """Test counting empty text."""
        assert count_words("") == 0
        assert count_words(None) == 0


# ═════════════════════════════════════════════════════════════════════════════
# HYBRID DETECTOR TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestAmbiguityDetector:
    """Tests for the hybrid AmbiguityDetector class."""

    def test_detect_rule_based_only(self, mock_section_bundle):
        """Test detection with rule-based only."""
        config = SensitivityConfig(
            enable_rule_based=True,
            enable_llm_based=False,
        )
        detector = AmbiguityDetector(config=config)
        result = detector.detect(mock_section_bundle)

        assert isinstance(result, DetectionResult)
        assert isinstance(result.markers, list)
        assert result.defect_density >= 0.0
        assert result.total_words > 0

    def test_detect_with_llm(self, mock_section_bundle, mock_llm_client):
        """Test detection with LLM enabled."""
        config = SensitivityConfig(
            enable_rule_based=True,
            enable_llm_based=True,
        )
        detector = AmbiguityDetector(llm_client=mock_llm_client, config=config)
        result = detector.detect(mock_section_bundle)

        assert isinstance(result, DetectionResult)
        assert isinstance(result.confidence_score, float)

    def test_severity_filtering(self, mock_section_bundle):
        """Test that markers are filtered by severity threshold."""
        config = SensitivityConfig(
            severity_threshold=0.8,  # High threshold
            enable_rule_based=True,
            enable_llm_based=False,
        )
        detector = AmbiguityDetector(config=config)
        result = detector.detect(mock_section_bundle)

        # All markers should have severity >= 0.8
        for marker in result.markers:
            assert marker.severity >= 0.8

    def test_needs_clarification_trigger(self, mock_section_bundle):
        """Test needs_clarification flag based on thresholds."""
        config = SensitivityConfig(
            defect_density_threshold=0.01,  # Very low threshold
            confidence_threshold=0.99,  # Very high threshold
            enable_rule_based=True,
            enable_llm_based=False,
        )
        detector = AmbiguityDetector(config=config)
        result = detector.detect(mock_section_bundle)

        # Should trigger due to low defect_density_threshold
        assert result.needs_clarification is True

    def test_merge_overlapping_markers(self, mock_section_bundle, mock_llm_client):
        """Test merging of overlapping markers."""
        # Setup LLM to return same ambiguity as rule-based
        mock_llm_client.call_json.return_value = {
            "ambiguities": [
                {
                    "source_text": "appropriate",
                    "ambiguity_type": "weak_word",
                    "severity": 0.6,
                    "section_name": "INTENT",
                    "explanation": "LLM detected",
                    "suggestions": [],
                }
            ],
            "overall_confidence": 0.8,
        }

        config = SensitivityConfig(
            merge_overlapping=True,
            enable_rule_based=True,
            enable_llm_based=True,
        )
        detector = AmbiguityDetector(llm_client=mock_llm_client, config=config)
        result = detector.detect(mock_section_bundle)

        # Check that overlapping markers are merged
        appropriate_markers = [
            m for m in result.markers 
            if m.source_text.lower() == "appropriate"
        ]
        
        # Should have at most one marker for "appropriate"
        assert len(appropriate_markers) <= 1

    def test_convenience_function(self, mock_section_bundle):
        """Test the detect_ambiguities convenience function."""
        result = detect_ambiguities(
            mock_section_bundle,
            sensitivity="medium",
        )

        assert isinstance(result, DetectionResult)


# ═════════════════════════════════════════════════════════════════════════════
# SENSITIVITY CONFIG TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestSensitivityConfig:
    """Tests for SensitivityConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SensitivityConfig()

        assert config.defect_density_threshold == 0.15
        assert config.confidence_threshold == 0.7
        assert config.severity_threshold == 0.3
        assert config.enable_rule_based is True
        assert config.enable_llm_based is True

    def test_low_sensitivity(self):
        """Test low sensitivity preset."""
        config = SensitivityConfig.low()

        assert config.defect_density_threshold == 0.25
        assert config.confidence_threshold == 0.5
        assert config.severity_threshold == 0.5

    def test_medium_sensitivity(self):
        """Test medium sensitivity preset."""
        config = SensitivityConfig.medium()

        assert config.defect_density_threshold == 0.15
        assert config.confidence_threshold == 0.7
        assert config.severity_threshold == 0.3

    def test_high_sensitivity(self):
        """Test high sensitivity preset."""
        config = SensitivityConfig.high()

        assert config.defect_density_threshold == 0.10
        assert config.confidence_threshold == 0.8
        assert config.severity_threshold == 0.2


# ═════════════════════════════════════════════════════════════════════════════
# DETECTION RESULT TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestDetectionResult:
    """Tests for DetectionResult class."""

    @pytest.fixture
    def sample_result(self):
        """Create a sample DetectionResult."""
        markers = [
            AmbiguityMarker(
                source_text="appropriate",
                ambiguity_type=AmbiguityType.WEAK_WORD,
                severity=0.5,
                source=AmbiguitySource.RULE_BASED,
                section_name="INTENT",
                source_item_index=0,
            ),
            AmbiguityMarker(
                source_text="many",
                ambiguity_type=AmbiguityType.QUANTIFIER,
                severity=0.4,
                source=AmbiguitySource.RULE_BASED,
                section_name="WORKFLOW",
                source_item_index=0,
            ),
            AmbiguityMarker(
                source_text="critical issue",
                ambiguity_type=AmbiguityType.CONFLICT,
                severity=0.9,
                source=AmbiguitySource.LLM_BASED,
                section_name="CONSTRAINTS",
                source_item_index=0,
            ),
        ]
        
        return DetectionResult(
            markers=markers,
            defect_density=0.15,
            total_words=100,
            affected_words=15,
            needs_clarification=True,
            confidence_score=0.75,
        )

    def test_get_markers_by_type(self, sample_result):
        """Test filtering markers by type."""
        weak_words = sample_result.get_markers_by_type(AmbiguityType.WEAK_WORD)
        assert len(weak_words) == 1
        assert weak_words[0].source_text == "appropriate"

    def test_get_markers_by_section(self, sample_result):
        """Test filtering markers by section."""
        intent_markers = sample_result.get_markers_by_section("INTENT")
        assert len(intent_markers) == 1

    def test_get_high_severity_markers(self, sample_result):
        """Test getting high severity markers."""
        high_severity = sample_result.get_high_severity_markers(threshold=0.7)
        assert len(high_severity) == 1
        assert high_severity[0].severity == 0.9


# ═════════════════════════════════════════════════════════════════════════════
# AMBIGUITY MARKER VALIDATION TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestAmbiguityMarkerValidation:
    """Tests for AmbiguityMarker validation."""

    def test_valid_marker(self):
        """Test creating a valid marker."""
        marker = AmbiguityMarker(
            source_text="test",
            ambiguity_type=AmbiguityType.WEAK_WORD,
            severity=0.5,
            source=AmbiguitySource.RULE_BASED,
            section_name="INTENT",
            source_item_index=0,
        )
        
        assert marker.severity == 0.5
        assert marker.confidence == 0.8  # Default

    def test_invalid_severity(self):
        """Test that invalid severity raises error."""
        with pytest.raises(ValueError):
            AmbiguityMarker(
                source_text="test",
                ambiguity_type=AmbiguityType.WEAK_WORD,
                severity=1.5,  # Invalid
                source=AmbiguitySource.RULE_BASED,
                section_name="INTENT",
                source_item_index=0,
            )

    def test_invalid_confidence(self):
        """Test that invalid confidence raises error."""
        with pytest.raises(ValueError):
            AmbiguityMarker(
                source_text="test",
                ambiguity_type=AmbiguityType.WEAK_WORD,
                severity=0.5,
                source=AmbiguitySource.RULE_BASED,
                section_name="INTENT",
                source_item_index=0,
                confidence=-0.1,  # Invalid
            )


# ═════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """Integration tests for the detection engine."""

    def test_full_detection_pipeline(self, mock_section_bundle):
        """Test the full detection pipeline."""
        result = detect_ambiguities(
            mock_section_bundle,
            sensitivity="medium",
        )

        # Verify result structure
        assert isinstance(result, DetectionResult)
        assert isinstance(result.markers, list)
        assert isinstance(result.defect_density, float)
        assert isinstance(result.total_words, int)
        assert isinstance(result.affected_words, int)
        assert isinstance(result.needs_clarification, bool)
        assert isinstance(result.confidence_score, float)

        # Verify all markers are valid
        for marker in result.markers:
            assert isinstance(marker, AmbiguityMarker)
            assert 0.0 <= marker.severity <= 1.0
            assert 0.0 <= marker.confidence <= 1.0
            assert marker.section_name in ["INTENT", "WORKFLOW", "CONSTRAINTS", "EXAMPLES", "NOTES"]

    def test_chinese_text_detection(self):
        """Test detection on Chinese text."""
        bundle = MagicMock()
        
        item = MagicMock()
        item.text = "系统应提供适当的响应，并合理处理许多请求。"
        
        bundle.all_sections.return_value = {
            "INTENT": [item],
            "WORKFLOW": [],
            "CONSTRAINTS": [],
            "EXAMPLES": [],
            "NOTES": [],
        }
        bundle.to_text.return_value = item.text

        result = detect_ambiguities(bundle, sensitivity="medium")

        # Should detect Chinese weak words and quantifiers
        assert len(result.markers) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
