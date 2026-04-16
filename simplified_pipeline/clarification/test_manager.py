"""
Unit tests for the ClarificationManager.

Tests cover:
- run_clarification() workflow
- Max iteration limit enforcement
- State persistence (save/load checkpoint)
- apply_clarifications() to merge answers into SectionBundle
- One question at a time logic
- Convenience functions
"""

from __future__ import annotations

import json
import pytest
import tempfile
from pathlib import Path
from typing import Union, cast
from unittest.mock import MagicMock, patch

from .manager import (
    ClarificationManager,
    ClarificationCheckpoint,
    run_hitl_clarification,
    ClarificationPipelineStep,
    CHECKPOINT_VERSION,
    CHECKPOINT_TYPE,
)
from .models import (
    AmbiguityMarker,
    AmbiguitySource,
    AmbiguityType,
    ClarificationContext,
    ClarificationQuestion,
    ClarificationStatus,
    DetectionResult,
    QuestionGenerationResult,
    QuestionPriority,
    ResponseStatus,
    SensitivityConfig,
    UserResponse,
)
from .detector import AmbiguityDetector
from .questions import QuestionGenerator
from .ui import MockClarificationUI


# ═════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_section_bundle():
    """Create a mock SectionBundle for testing."""
    bundle = MagicMock()

    # Create mock items
    intent_item = MagicMock()
    intent_item.text = "The system should provide appropriate responses."

    workflow_item = MagicMock()
    workflow_item.text = "Process many requests quickly."

    constraint_item = MagicMock()
    constraint_item.text = "The system must respond fast."

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
The system should provide appropriate responses.

## WORKFLOW
Process many requests quickly.

## CONSTRAINTS
The system must respond fast.
"""

    return bundle


@pytest.fixture
def sample_markers():
    """Create sample ambiguity markers."""
    return [
        AmbiguityMarker(
            source_text="appropriate",
            ambiguity_type=AmbiguityType.WEAK_WORD,
            severity=0.5,
            source=AmbiguitySource.RULE_BASED,
            section_name="INTENT",
            source_item_index=0,
            explanation="Vague term",
            suggestions=["Define specific criteria"],
        ),
        AmbiguityMarker(
            source_text="many",
            ambiguity_type=AmbiguityType.QUANTIFIER,
            severity=0.6,
            source=AmbiguitySource.RULE_BASED,
            section_name="WORKFLOW",
            source_item_index=0,
            explanation="Vague quantifier",
            suggestions=["Specify number"],
        ),
        AmbiguityMarker(
            source_text="fast",
            ambiguity_type=AmbiguityType.PRAGMATIC,
            severity=0.7,
            source=AmbiguitySource.RULE_BASED,
            section_name="CONSTRAINTS",
            source_item_index=0,
            explanation="No specific time threshold",
            suggestions=["Define response time"],
        ),
    ]


def _make_question(
    question_id: str,
    ambiguity_marker_id: str,
    question_text: str,
    options: list[str],
    context_hint: str,
    priority: QuestionPriority,
    source_section: str,
    source_text: str,
) -> ClarificationQuestion:
    """Helper to create ClarificationQuestion with all parameters."""
    return ClarificationQuestion(
        question_id=question_id,
        ambiguity_marker_id=ambiguity_marker_id,
        question_text=question_text,
        options=options,
        allow_other=True,
        context_hint=context_hint,
        priority=priority,
        expected_answer_type="CHOICE",
        validation_pattern="",
        source_section=source_section,
        source_text=source_text,
    )


@pytest.fixture
def sample_questions(sample_markers):
    """Create sample clarification questions."""
    return [
        _make_question(
            question_id="q_0001_test",
            ambiguity_marker_id="marker_INTENT_0",
            question_text="'appropriate' is a subjective term. What would be considered 'appropriate' in this context?",
            options=["Industry standard", "Company specific", "Context dependent", "Other: ____"],
            context_hint="Clear criteria help ensure consistent behavior.",
            priority=QuestionPriority.MEDIUM,
            source_section="INTENT",
            source_text="appropriate",
        ),
        _make_question(
            question_id="q_0002_test",
            ambiguity_marker_id="marker_WORKFLOW_0",
            question_text="'many' is a vague quantity. Please specify the approximate range:",
            options=["10-50", "50-500", "500+", "Other: ____"],
            context_hint="Specific numbers help ensure the system handles the expected scale.",
            priority=QuestionPriority.HIGH,
            source_section="WORKFLOW",
            source_text="many",
        ),
        _make_question(
            question_id="q_0003_test",
            ambiguity_marker_id="marker_CONSTRAINTS_0",
            question_text="'fast' is vague. Please provide more specific criteria:",
            options=["Under 1 second", "1-5 seconds", "Under 1 minute", "Other: ____"],
            context_hint="Specific criteria ensure consistent implementation.",
            priority=QuestionPriority.MEDIUM,
            source_section="CONSTRAINTS",
            source_text="fast",
        ),
    ]


@pytest.fixture
def mock_detector(sample_markers):
    """Create a mock AmbiguityDetector."""
    detector = MagicMock(spec=AmbiguityDetector)

    # Default: return detection result with markers
    detection_result = DetectionResult(
        markers=sample_markers,
        defect_density=0.20,
        total_words=100,
        affected_words=20,
        needs_clarification=True,
        confidence_score=0.75,
    )
    detector.detect.return_value = detection_result

    return detector


@pytest.fixture
def mock_question_generator(sample_questions):
    """Create a mock QuestionGenerator."""
    generator = MagicMock(spec=QuestionGenerator)

    # Default: return question generation result
    question_result = QuestionGenerationResult(
        questions=sample_questions,
        total_markers_processed=3,
        questions_generated=3,
        template_used_count=3,
        llm_used_count=0,
    )
    generator.generate_questions.return_value = question_result

    return generator


def make_mock_ui(predefined: dict[str, str]) -> MockClarificationUI:
    """Create a MockClarificationUI with proper typing."""
    # Cast to the expected type
    typed_predefined: dict[str, Union[str, dict[str, str]]] = cast(
        dict[str, Union[str, dict[str, str]]], predefined
    )
    return MockClarificationUI(typed_predefined)


@pytest.fixture
def mock_ui():
    """Create a mock UI with predefined responses."""
    predefined = {
        "q_0001_test": "Industry standard",
        "q_0002_test": "50-500",
        "q_0003_test": "Under 1 second",
    }
    return make_mock_ui(predefined)


@pytest.fixture
def manager(mock_detector, mock_question_generator, mock_ui):
    """Create a ClarificationManager with mocked dependencies."""
    return ClarificationManager(
        detector=mock_detector,
        question_generator=mock_question_generator,
        ui=mock_ui,
        max_iterations=5,
    )


# ═════════════════════════════════════════════════════════════════════════════
# CLARIFICATION MANAGER TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestClarificationManager:
    """Tests for ClarificationManager class."""

    def test_init_validates_max_iterations(self):
        """Test that max_iterations is validated."""
        # Valid range
        manager = ClarificationManager(
            detector=MagicMock(),
            question_generator=MagicMock(),
            ui=MagicMock(),
            max_iterations=5,
        )
        assert manager.max_iterations == 5

        # Invalid: too low
        with pytest.raises(ValueError):
            ClarificationManager(
                detector=MagicMock(),
                question_generator=MagicMock(),
                ui=MagicMock(),
                max_iterations=0,
            )

        # Invalid: too high
        with pytest.raises(ValueError):
            ClarificationManager(
                detector=MagicMock(),
                question_generator=MagicMock(),
                ui=MagicMock(),
                max_iterations=15,
            )

    def test_run_clarification_no_ambiguities(self, mock_section_bundle):
        """Test when no ambiguities are detected."""
        # Setup detector to return no clarification needed
        detector = MagicMock(spec=AmbiguityDetector)
        detector.detect.return_value = DetectionResult(
            markers=[],
            defect_density=0.0,
            total_words=100,
            affected_words=0,
            needs_clarification=False,
            confidence_score=1.0,
        )

        manager = ClarificationManager(
            detector=detector,
            question_generator=MagicMock(),
            ui=MagicMock(),
            max_iterations=5,
        )

        context = manager.run_clarification(mock_section_bundle)

        assert context.status == ClarificationStatus.COMPLETED
        assert len(context.questions) == 0
        assert len(context.responses) == 0

    def test_run_clarification_with_questions(
        self, manager, mock_section_bundle, mock_ui
    ):
        """Test full clarification workflow with questions."""
        context = manager.run_clarification(mock_section_bundle)

        # Check context was created
        assert context.session_id.startswith("clarification_")
        assert context.max_iterations == 5

        # Check questions were generated
        assert len(context.questions) == 3

        # Check responses were collected
        assert len(context.responses) == 3

        # Check status
        assert context.status == ClarificationStatus.COMPLETED

        # Check UI was called for each question
        assert len(mock_ui.questions_presented) == 3

    def test_run_clarification_max_iterations(
        self, mock_section_bundle, sample_markers, sample_questions
    ):
        """Test that max iteration limit is enforced."""
        # Create UI that will provide responses
        predefined = {f"q_{i:04d}_test": f"Answer {i}" for i in range(10)}
        ui = make_mock_ui(predefined)

        # Create manager with max_iterations=2
        detector = MagicMock(spec=AmbiguityDetector)
        detector.detect.return_value = DetectionResult(
            markers=sample_markers,
            defect_density=0.20,
            total_words=100,
            affected_words=20,
            needs_clarification=True,
            confidence_score=0.75,
        )

        generator = MagicMock(spec=QuestionGenerator)
        generator.generate_questions.return_value = QuestionGenerationResult(
            questions=sample_questions,
            total_markers_processed=3,
            questions_generated=3,
        )

        manager = ClarificationManager(
            detector=detector,
            question_generator=generator,
            ui=ui,
            max_iterations=2,
        )

        context = manager.run_clarification(mock_section_bundle)

        # Should stop at max iterations
        assert context.iteration == 2
        assert context.status == ClarificationStatus.MAX_ITERATIONS_REACHED
        # Should have only 2 responses (max_iterations)
        assert len(context.responses) == 2

    def test_run_clarification_custom_session_id(
        self, manager, mock_section_bundle
    ):
        """Test using a custom session ID."""
        custom_id = "custom_session_123"
        context = manager.run_clarification(
            mock_section_bundle, session_id=custom_id
        )

        assert context.session_id == custom_id

    def test_one_question_at_a_time(
        self, mock_section_bundle, sample_markers, sample_questions
    ):
        """Test that questions are presented one at a time."""
        # Track order of calls
        call_order = []

        class TrackingUI(MockClarificationUI):
            def present_question(self, question):
                call_order.append(("present", question.question_id))
                super().present_question(question)

            def collect_response(self, question):
                call_order.append(("collect", question.question_id))
                return super().collect_response(question)

        predefined = {
            "q_0001_test": "Answer 1",
            "q_0002_test": "Answer 2",
            "q_0003_test": "Answer 3",
        }
        typed_predefined: dict[str, Union[str, dict[str, str]]] = cast(
            dict[str, Union[str, dict[str, str]]], predefined
        )
        ui = TrackingUI(typed_predefined)

        detector = MagicMock(spec=AmbiguityDetector)
        detector.detect.return_value = DetectionResult(
            markers=sample_markers,
            defect_density=0.20,
            total_words=100,
            affected_words=20,
            needs_clarification=True,
            confidence_score=0.75,
        )

        generator = MagicMock(spec=QuestionGenerator)
        generator.generate_questions.return_value = QuestionGenerationResult(
            questions=sample_questions,
            total_markers_processed=3,
            questions_generated=3,
        )

        manager = ClarificationManager(
            detector=detector,
            question_generator=generator,
            ui=ui,
            max_iterations=5,
        )

        manager.run_clarification(mock_section_bundle)

        # Verify interleaved pattern: present, collect, present, collect...
        # Questions are sorted by priority, so order may differ from input
        # Just verify that present and collect are interleaved
        assert len(call_order) == 6  # 3 questions * 2 calls each
        for i in range(0, 6, 2):
            assert call_order[i][0] == "present"
            assert call_order[i + 1][0] == "collect"
            # Same question ID for each pair
            assert call_order[i][1] == call_order[i + 1][1]


# ═════════════════════════════════════════════════════════════════════════════
# APPLY CLARIFICATIONS TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestApplyClarifications:
    """Tests for apply_clarifications method."""

    def test_apply_clarifications_basic(
        self, manager, mock_section_bundle, sample_questions
    ):
        """Test basic application of clarifications."""
        # Create context with responses
        context = ClarificationContext(
            session_id="test_session",
            questions=sample_questions,
            responses=[
                UserResponse(question_id="q_0001_test", selected_option="Industry standard"),
                UserResponse(question_id="q_0002_test", selected_option="50-500"),
                UserResponse(question_id="q_0003_test", selected_option="Under 1 second"),
            ],
        )
        for resp in context.responses:
            resp.status = ResponseStatus.ANSWERED

        # Apply clarifications
        updated_bundle = manager.apply_clarifications(mock_section_bundle, context)

        # Verify bundle structure is preserved
        assert hasattr(updated_bundle, 'intent')
        assert hasattr(updated_bundle, 'workflow')
        assert hasattr(updated_bundle, 'constraints')

    def test_apply_clarifications_empty_context(self, manager, mock_section_bundle):
        """Test applying empty clarification context."""
        context = ClarificationContext(session_id="empty_session")

        updated_bundle = manager.apply_clarifications(mock_section_bundle, context)

        # Should return original bundle unchanged
        assert updated_bundle is not None

    def test_apply_clarifications_preserves_original(
        self, manager, sample_questions
    ):
        """Test that original SectionBundle is not modified."""
        # Create a real SectionBundle
        from simplified_pipeline.models import SectionBundle, SectionItem

        original_bundle = SectionBundle(
            intent=[SectionItem(text="Original intent text", source="test")],
            workflow=[SectionItem(text="Original workflow text", source="test")],
            constraints=[],
            examples=[],
            notes=[],
        )

        context = ClarificationContext(
            session_id="test",
            questions=[
                ClarificationQuestion(
                    question_id="q_001",
                    ambiguity_marker_id="m_001",
                    question_text="Test question",
                    source_section="INTENT",
                    source_text="intent",
                )
            ],
            responses=[
                UserResponse(question_id="q_001", selected_option="Answer"),
            ],
        )
        context.responses[0].status = ResponseStatus.ANSWERED

        # Store original text
        original_text = original_bundle.intent[0].text

        # Apply clarifications
        updated_bundle = manager.apply_clarifications(original_bundle, context)

        # Original should be unchanged
        assert original_bundle.intent[0].text == original_text

        # Updated should have annotation
        assert "[CLARIFIED:" in updated_bundle.intent[0].text


# ═════════════════════════════════════════════════════════════════════════════
# CHECKPOINT TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestCheckpoints:
    """Tests for checkpoint save/load functionality."""

    def test_save_checkpoint(self, manager, sample_questions):
        """Test saving clarification state to checkpoint."""
        context = ClarificationContext(
            session_id="test_checkpoint_session",
            questions=sample_questions,
            responses=[
                UserResponse(question_id="q_0001_test", selected_option="Answer 1"),
            ],
            iteration=1,
            max_iterations=5,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_path = Path(tmpdir) / "checkpoint.json"

            manager.save_checkpoint(context, str(checkpoint_path))

            # Verify file was created
            assert checkpoint_path.exists()

            # Verify content
            with open(checkpoint_path, 'r') as f:
                data = json.load(f)

            assert data["checkpoint_type"] == CHECKPOINT_TYPE
            assert data["version"] == CHECKPOINT_VERSION
            assert data["session_id"] == "test_checkpoint_session"

    def test_load_checkpoint(self, manager, sample_questions):
        """Test loading clarification state from checkpoint."""
        # First save a checkpoint
        context = ClarificationContext(
            session_id="load_test_session",
            questions=sample_questions,
            responses=[
                UserResponse(question_id="q_0001_test", selected_option="Answer"),
            ],
            iteration=2,
            max_iterations=5,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_path = Path(tmpdir) / "checkpoint.json"
            manager.save_checkpoint(context, str(checkpoint_path))

            # Load it back
            loaded_context = manager.load_checkpoint(str(checkpoint_path))

            assert loaded_context.session_id == "load_test_session"
            assert loaded_context.iteration == 2
            assert len(loaded_context.questions) == 3

    def test_load_checkpoint_invalid_type(self, manager):
        """Test loading checkpoint with invalid type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_path = Path(tmpdir) / "invalid.json"

            # Write invalid checkpoint
            with open(checkpoint_path, 'w') as f:
                json.dump({
                    "version": "1.0",
                    "checkpoint_type": "invalid_type",
                    "session_id": "test",
                    "data": {}
                }, f)

            with pytest.raises(ValueError, match="Invalid checkpoint type"):
                manager.load_checkpoint(str(checkpoint_path))

    def test_load_checkpoint_not_found(self, manager):
        """Test loading non-existent checkpoint."""
        with pytest.raises(FileNotFoundError):
            manager.load_checkpoint("/nonexistent/path/checkpoint.json")

    def test_checkpoint_roundtrip(self, manager, sample_questions):
        """Test complete save/load roundtrip preserves data."""
        original_context = ClarificationContext(
            session_id="roundtrip_test",
            questions=sample_questions,
            responses=[
                UserResponse(question_id="q_0001_test", selected_option="Option A"),
                UserResponse(question_id="q_0002_test", selected_option="Option B"),
            ],
            iteration=2,
            max_iterations=5,
            status=ClarificationStatus.IN_PROGRESS,
        )
        original_context.responses[0].status = ResponseStatus.ANSWERED
        original_context.responses[1].status = ResponseStatus.ANSWERED

        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_path = Path(tmpdir) / "roundtrip.json"

            # Save and load
            manager.save_checkpoint(original_context, str(checkpoint_path))
            loaded_context = manager.load_checkpoint(str(checkpoint_path))

            # Verify all fields match
            assert loaded_context.session_id == original_context.session_id
            assert loaded_context.iteration == original_context.iteration
            assert loaded_context.max_iterations == original_context.max_iterations
            assert loaded_context.status == original_context.status
            assert len(loaded_context.questions) == len(original_context.questions)
            assert len(loaded_context.responses) == len(original_context.responses)


class TestClarificationCheckpoint:
    """Tests for ClarificationCheckpoint dataclass."""

    def test_to_dict(self):
        """Test checkpoint serialization."""
        checkpoint = ClarificationCheckpoint(
            session_id="test_session",
            created_at="2024-01-01T00:00:00Z",
            data={"key": "value"},
        )

        data = checkpoint.to_dict()

        assert data["version"] == CHECKPOINT_VERSION
        assert data["checkpoint_type"] == CHECKPOINT_TYPE
        assert data["session_id"] == "test_session"
        assert data["data"] == {"key": "value"}

    def test_from_dict(self):
        """Test checkpoint deserialization."""
        data = {
            "version": "1.0",
            "checkpoint_type": "clarification_session",
            "session_id": "loaded_session",
            "created_at": "2024-01-01T00:00:00Z",
            "data": {"nested": "data"},
        }

        checkpoint = ClarificationCheckpoint.from_dict(data)

        assert checkpoint.version == "1.0"
        assert checkpoint.session_id == "loaded_session"
        assert checkpoint.data == {"nested": "data"}


# ═════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_run_hitl_clarification(self, mock_section_bundle):
        """Test the run_hitl_clarification convenience function."""
        # Mock LLM client
        llm_client = MagicMock()
        llm_client.call_json.return_value = {
            "ambiguities": [],
            "overall_confidence": 0.9,
        }

        # Mock UI
        predefined = {"q_0001_test": "Answer"}
        ui = make_mock_ui(predefined)

        # Patch the detector and generator using absolute path
        with patch('simplified_pipeline.clarification.manager.AmbiguityDetector') as mock_detector_cls, \
             patch('simplified_pipeline.clarification.manager.QuestionGenerator') as mock_gen_cls:

            # Setup mocks
            mock_detector = MagicMock()
            mock_detector.detect.return_value = DetectionResult(
                markers=[
                    AmbiguityMarker(
                        source_text="test",
                        ambiguity_type=AmbiguityType.WEAK_WORD,
                        severity=0.5,
                        source=AmbiguitySource.RULE_BASED,
                        section_name="INTENT",
                        source_item_index=0,
                    )
                ],
                defect_density=0.1,
                total_words=100,
                affected_words=10,
                needs_clarification=True,
                confidence_score=0.8,
            )
            mock_detector_cls.return_value = mock_detector

            mock_gen = MagicMock()
            mock_gen.generate_questions.return_value = QuestionGenerationResult(
                questions=[
                    ClarificationQuestion(
                        question_id="q_0001_test",
                        ambiguity_marker_id="m_001",
                        question_text="Test?",
                        source_section="INTENT",
                        source_text="test",
                    )
                ],
                total_markers_processed=1,
                questions_generated=1,
            )
            mock_gen_cls.return_value = mock_gen

            context, updated_bundle = run_hitl_clarification(
                section_bundle=mock_section_bundle,
                llm_client=llm_client,
                ui=ui,
                sensitivity="medium",
                max_iterations=5,
            )

            assert context is not None
            assert updated_bundle is not None


class TestClarificationPipelineStep:
    """Tests for ClarificationPipelineStep class."""

    def test_init(self):
        """Test initialization."""
        step = ClarificationPipelineStep(
            llm_client=MagicMock(),
            sensitivity="high",
            max_iterations=3,
        )

        assert step.sensitivity == "high"
        assert step.max_iterations == 3

    def test_should_run(self, mock_section_bundle):
        """Test should_run method."""
        llm_client = MagicMock()

        step = ClarificationPipelineStep(
            llm_client=llm_client,
            sensitivity="medium",
        )

        with patch('simplified_pipeline.clarification.manager.AmbiguityDetector') as mock_detector_cls:
            mock_detector = MagicMock()
            mock_detector.detect.return_value = DetectionResult(
                markers=[],
                defect_density=0.0,
                total_words=100,
                affected_words=0,
                needs_clarification=True,
                confidence_score=0.8,
            )
            mock_detector_cls.return_value = mock_detector

            result = step.should_run(mock_section_bundle)
            assert result is True

    def test_run_with_checkpoint(self, mock_section_bundle):
        """Test run method with checkpoint saving."""
        llm_client = MagicMock()
        llm_client.call_json.return_value = {
            "ambiguities": [],
            "overall_confidence": 0.9,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            step = ClarificationPipelineStep(
                llm_client=llm_client,
                sensitivity="medium",
                max_iterations=5,
                checkpoint_dir=tmpdir,
            )

            with patch('simplified_pipeline.clarification.manager.AmbiguityDetector') as mock_detector_cls, \
                 patch('simplified_pipeline.clarification.manager.QuestionGenerator') as mock_gen_cls:

                # Setup mocks
                mock_detector = MagicMock()
                mock_detector.detect.return_value = DetectionResult(
                    markers=[],
                    defect_density=0.0,
                    total_words=100,
                    affected_words=0,
                    needs_clarification=False,
                    confidence_score=1.0,
                )
                mock_detector_cls.return_value = mock_detector

                mock_gen = MagicMock()
                mock_gen_cls.return_value = mock_gen

                context, bundle = step.run(mock_section_bundle)

                assert context.status == ClarificationStatus.COMPLETED


# ═════════════════════════════════════════════════════════════════════════════
# RUN FROM CHECKPOINT TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestRunFromCheckpoint:
    """Tests for run_from_checkpoint method."""

    def test_run_from_checkpoint_completed(self, manager, mock_section_bundle):
        """Test resuming from a completed checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and save a completed context
            context = ClarificationContext(
                session_id="completed_session",
                status=ClarificationStatus.COMPLETED,
                max_iterations=5,
            )

            checkpoint_path = Path(tmpdir) / "completed.json"
            manager.save_checkpoint(context, str(checkpoint_path))

            # Resume
            resumed = manager.run_from_checkpoint(mock_section_bundle, str(checkpoint_path))

            assert resumed.status == ClarificationStatus.COMPLETED

    def test_run_from_checkpoint_in_progress(
        self, mock_section_bundle, sample_markers, sample_questions
    ):
        """Test resuming from an in-progress checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create an in-progress context with 1 question answered
            context = ClarificationContext(
                session_id="in_progress_session",
                questions=sample_questions,
                responses=[
                    UserResponse(question_id="q_0001_test", selected_option="Answer 1"),
                ],
                iteration=1,
                max_iterations=5,
                status=ClarificationStatus.IN_PROGRESS,
            )
            context.responses[0].status = ResponseStatus.ANSWERED

            # Setup manager
            predefined = {
                "q_0002_test": "Answer 2",
                "q_0003_test": "Answer 3",
            }
            ui = make_mock_ui(predefined)

            detector = MagicMock(spec=AmbiguityDetector)
            generator = MagicMock(spec=QuestionGenerator)

            manager = ClarificationManager(
                detector=detector,
                question_generator=generator,
                ui=ui,
                max_iterations=5,
            )

            checkpoint_path = Path(tmpdir) / "in_progress.json"
            manager.save_checkpoint(context, str(checkpoint_path))

            # Resume
            resumed = manager.run_from_checkpoint(mock_section_bundle, str(checkpoint_path))

            # Should have collected remaining questions
            assert len(resumed.responses) == 3
            assert resumed.status == ClarificationStatus.COMPLETED


# ═════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """Integration tests for the manager."""

    def test_full_workflow(self, mock_section_bundle, sample_markers, sample_questions):
        """Test the complete clarification workflow."""
        # Setup detector
        detector = MagicMock(spec=AmbiguityDetector)
        detector.detect.return_value = DetectionResult(
            markers=sample_markers,
            defect_density=0.20,
            total_words=100,
            affected_words=20,
            needs_clarification=True,
            confidence_score=0.75,
        )

        # Setup generator
        generator = MagicMock(spec=QuestionGenerator)
        generator.generate_questions.return_value = QuestionGenerationResult(
            questions=sample_questions,
            total_markers_processed=3,
            questions_generated=3,
        )

        # Setup UI
        predefined = {
            "q_0001_test": "Industry standard",
            "q_0002_test": "50-500",
            "q_0003_test": "Under 1 second",
        }
        ui = make_mock_ui(predefined)

        # Create manager
        manager = ClarificationManager(
            detector=detector,
            question_generator=generator,
            ui=ui,
            max_iterations=5,
        )

        # Run clarification
        context = manager.run_clarification(mock_section_bundle)

        # Verify complete workflow
        assert context.status == ClarificationStatus.COMPLETED
        assert len(context.questions) == 3
        assert len(context.responses) == 3
        assert context.iteration == 3

        # Apply clarifications
        updated_bundle = manager.apply_clarifications(mock_section_bundle, context)
        assert updated_bundle is not None

        # Save and load checkpoint
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_path = Path(tmpdir) / "final.json"
            manager.save_checkpoint(context, str(checkpoint_path))

            loaded = manager.load_checkpoint(str(checkpoint_path))
            assert loaded.session_id == context.session_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
