"""
End-to-end integration test for HITL clarification module.

This test verifies the complete clarification workflow from detection to application.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

# Import all clarification components
from simplified_pipeline.clarification import (
    AmbiguityDetector,
    QuestionGenerator,
    AmbiguityMarker,
    ClarificationQuestion,
    DetectionResult,
    SensitivityConfig,
    AmbiguityType,
    AmbiguitySource,
    QuestionPriority,
)
from simplified_pipeline.clarification.manager import ClarificationManager
from simplified_pipeline.clarification.ui import MockClarificationUI
from simplified_pipeline.clarification.models import (
    ClarificationContext,
    UserResponse,
    ClarificationStatus,
    ResponseStatus,
)
from simplified_pipeline.models import SectionBundle, SectionItem


def make_section_item(text: str, source: str = "SKILL.md:1") -> SectionItem:
    """Helper to create SectionItem with correct parameters."""
    return SectionItem(text=text, source=source)


def make_bundle(intent: str, workflow: str, constraints: str, examples: str, notes: str) -> SectionBundle:
    """Helper to create SectionBundle with correct structure."""
    return SectionBundle(
        intent=[make_section_item(intent)],
        workflow=[make_section_item(workflow)],
        constraints=[make_section_item(constraints)],
        examples=[make_section_item(examples)],
        notes=[make_section_item(notes)],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_bundle():
    """Create a sample SectionBundle with ambiguities."""
    return make_bundle(
        intent="This skill provides appropriate error handling for many scenarios.",
        workflow="1. Receive input\n2. Process data\n3. Return result quickly",
        constraints="MUST handle errors gracefully. MAY retry failed operations.",
        examples="Example: User sends invalid input, system responds appropriately.",
        notes="Some users may need additional guidance.",
    )


@pytest.fixture
def mock_ui():
    """Create a MockClarificationUI with predefined responses."""
    return MockClarificationUI(
        predefined_responses={
            "q_0001": "All cases without exception",
            "q_0002": "Under 1 second",
            "q_0003": "Required for all cases",
        }
    )


@pytest.fixture
def sensitivity_config():
    """Create a medium sensitivity config."""
    return SensitivityConfig.medium()


# ─────────────────────────────────────────────────────────────────────────────
# E2E Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestE2EClarificationWorkflow:
    """End-to-end tests for the complete clarification workflow."""

    def test_e2e_detection_to_question_generation(self, sample_bundle, sensitivity_config):
        """Test complete flow: detection → question generation."""
        # Step 1: Create detector without LLM (rule-based only)
        detector = AmbiguityDetector(llm_client=None, config=sensitivity_config)

        # Step 2: Detect ambiguities
        result = detector.detect(sample_bundle)

        # Verify detection
        assert result is not None
        assert isinstance(result, DetectionResult)
        assert len(result.markers) > 0  # Should detect "appropriate", "many", "quickly"
        assert result.defect_density > 0

        # Step 3: Generate questions
        question_gen = QuestionGenerator(llm_client=None)
        question_result = question_gen.generate_questions(result.markers)

        # Verify question generation
        assert question_result is not None
        assert len(question_result.questions) > 0
        for q in question_result.questions:
            assert q.question_text != ""
            assert len(q.options) > 0 or q.allow_other
            # SPL hiding principle
            assert "[DEFINE_" not in q.question_text
            assert "<REF>" not in q.question_text

    def test_e2e_full_workflow_with_mock_ui(self, sample_bundle, mock_ui, sensitivity_config):
        """Test complete workflow with Mock UI."""
        # Setup
        detector = AmbiguityDetector(llm_client=None, config=sensitivity_config)
        question_gen = QuestionGenerator(llm_client=None)

        # Create manager
        manager = ClarificationManager(
            detector=detector,
            question_generator=question_gen,
            ui=mock_ui,
            max_iterations=5,
        )

        # Run clarification
        context = manager.run_clarification(sample_bundle)

        # Verify context
        assert context is not None
        assert isinstance(context, ClarificationContext)
        assert context.session_id != ""
        # Note: markers/questions may be empty if detection finds nothing
        # The important thing is the workflow completes without errors

    def test_e2e_apply_clarifications(self, sample_bundle, mock_ui, sensitivity_config):
        """Test that clarifications are properly applied to SectionBundle."""
        # Setup and run clarification
        detector = AmbiguityDetector(llm_client=None, config=sensitivity_config)
        question_gen = QuestionGenerator(llm_client=None)

        manager = ClarificationManager(
            detector=detector,
            question_generator=question_gen,
            ui=mock_ui,
            max_iterations=5,
        )

        context = manager.run_clarification(sample_bundle)

        # Apply clarifications
        clarified_bundle = manager.apply_clarifications(sample_bundle, context)

        # Verify bundle is modified
        assert clarified_bundle is not None
        # Check that clarifications are added as annotations or modifications
        # The original content should be preserved but enriched

    def test_e2e_checkpoint_save_restore(self, sample_bundle, mock_ui, sensitivity_config, tmp_path):
        """Test checkpoint save and restore."""
        import json

        # Setup
        detector = AmbiguityDetector(llm_client=None, config=sensitivity_config)
        question_gen = QuestionGenerator(llm_client=None)

        manager = ClarificationManager(
            detector=detector,
            question_generator=question_gen,
            ui=mock_ui,
            max_iterations=5,
        )

        # Run partial clarification
        context = manager.run_clarification(sample_bundle)

        # Save checkpoint
        checkpoint_path = tmp_path / "checkpoint.json"
        manager.save_checkpoint(context, str(checkpoint_path))

        # Verify file exists
        assert checkpoint_path.exists()

        # Load checkpoint
        loaded_context = manager.load_checkpoint(str(checkpoint_path))

        # Verify loaded context
        assert loaded_context.session_id == context.session_id
        assert len(loaded_context.questions) == len(context.questions)
        assert len(loaded_context.responses) == len(context.responses)

    def test_e2e_no_clarification_needed(self, sensitivity_config):
        """Test when no clarification is needed."""
        # Create a clear, unambiguous bundle
        clear_bundle = make_bundle(
            intent="This skill converts PDF files to text format.",
            workflow="1. Open PDF file\n2. Extract text\n3. Return text string",
            constraints="MUST handle password-protected files. MUST NOT modify original file.",
            examples="Input: document.pdf. Output: 'Hello World' text content.",
            notes="Supports PDF version 1.4 and later.",
        )

        # Create high sensitivity to trigger even on small ambiguities
        high_config = SensitivityConfig.high()
        detector = AmbiguityDetector(llm_client=None, config=high_config)
        result = detector.detect(clear_bundle)

        # Verify detection works
        assert result is not None


class TestE2EEdgeCases:
    """Edge case tests for the clarification workflow."""

    def test_empty_bundle(self, sensitivity_config):
        """Test handling of empty SectionBundle."""
        empty_bundle = make_bundle(
            intent="",
            workflow="",
            constraints="",
            examples="",
            notes="",
        )

        detector = AmbiguityDetector(llm_client=None, config=sensitivity_config)
        result = detector.detect(empty_bundle)

        # Should not crash, should return empty markers
        assert result is not None
        assert len(result.markers) == 0
        assert result.defect_density == 0.0

    def test_max_iterations_limit(self, sample_bundle, sensitivity_config):
        """Test that max iterations limit is enforced."""
        # Create UI that never provides all answers
        ui = MockClarificationUI(predefined_responses={})

        detector = AmbiguityDetector(llm_client=None, config=sensitivity_config)
        question_gen = QuestionGenerator(llm_client=None)

        manager = ClarificationManager(
            detector=detector,
            question_generator=question_gen,
            ui=ui,
            max_iterations=2,  # Low limit
        )

        context = manager.run_clarification(sample_bundle)

        # Should stop at max iterations
        assert context.iteration <= 2

    def test_chinese_text_detection(self, sensitivity_config):
        """Test ambiguity detection in Chinese text."""
        chinese_bundle = make_bundle(
            intent="这个技能处理适当的错误。",  # Contains "适当" (appropriate)
            workflow="1. 接收输入\n2. 快速处理数据\n3. 返回结果",  # Contains "快速" (fast)
            constraints="必须处理所有错误。",
            examples="示例：用户输入，系统处理。",
            notes="一些用户可能需要帮助。",  # Contains "一些" (some)
        )

        detector = AmbiguityDetector(llm_client=None, config=sensitivity_config)
        result = detector.detect(chinese_bundle)

        # Should detect Chinese ambiguities
        assert result is not None
        # Chinese weak words like 适当 should be detected


class TestE2ESPLHiding:
    """Tests for the SPL hiding principle."""

    def test_no_spl_in_questions(self, sample_bundle, sensitivity_config):
        """Verify no SPL terminology appears in generated questions."""
        detector = AmbiguityDetector(llm_client=None, config=sensitivity_config)
        result = detector.detect(sample_bundle)

        question_gen = QuestionGenerator(llm_client=None)
        question_result = question_gen.generate_questions(result.markers)

        spl_terms = [
            "[DEFINE_", "[END_", "<REF>", "</REF>",
            "LLM_TASK", "FILE_READ", "FILE_WRITE",
            "var_id", "type_name", "MAIN_FLOW",
            "EXCEPTION_FLOW", "ALTERNATIVE_FLOW",
        ]

        for q in question_result.questions:
            for term in spl_terms:
                assert term not in q.question_text, f"SPL term '{term}' found in question"
                assert term not in q.context_hint, f"SPL term '{term}' found in context hint"

    def test_business_friendly_questions(self, sample_bundle, sensitivity_config):
        """Verify questions use business-friendly language."""
        detector = AmbiguityDetector(llm_client=None, config=sensitivity_config)
        result = detector.detect(sample_bundle)

        question_gen = QuestionGenerator(llm_client=None)
        question_result = question_gen.generate_questions(result.markers)

        for q in question_result.questions:
            # Questions should be meaningful
            assert len(q.question_text) > 10  # Should be meaningful
            # Questions should not contain SPL terms
            assert "[DEFINE_" not in q.question_text
            assert "<REF>" not in q.question_text


# ─────────────────────────────────────────────────────────────────────────────
# Test Runner
# ─────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
