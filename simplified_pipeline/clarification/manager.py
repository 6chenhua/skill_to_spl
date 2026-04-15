"""
Clarification State Manager for HITL Clarification Module.

Orchestrates the entire clarification workflow:
1. Detect ambiguities using AmbiguityDetector
2. Generate questions using QuestionGenerator
3. Present questions to user via UI
4. Collect responses
5. Update context and check for completion
6. Return clarified data for pipeline continuation

Features:
- Bounded iterations (max 5 by default)
- State persistence (checkpoint support)
- One question at a time logic
- Integration with existing checkpoint system
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from .models import (
    AmbiguityMarker,
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
from .ui import ClarificationUI, ConsoleClarificationUI, MockClarificationUI

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# CHECKPOINT FORMAT
# ═════════════════════════════════════════════════════════════════════════════

CHECKPOINT_VERSION = "1.0"
CHECKPOINT_TYPE = "clarification_session"


@dataclass
class ClarificationCheckpoint:
    """
    Checkpoint format for clarification state persistence.

    Compatible with the pipeline's checkpoint system.
    """

    version: str = CHECKPOINT_VERSION
    checkpoint_type: str = CHECKPOINT_TYPE
    session_id: str = ""
    created_at: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "checkpoint_type": self.checkpoint_type,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClarificationCheckpoint":
        """Create instance from dictionary."""
        return cls(
            version=data.get("version", CHECKPOINT_VERSION),
            checkpoint_type=data.get("checkpoint_type", CHECKPOINT_TYPE),
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", ""),
            data=data.get("data", {}),
        )


# ═════════════════════════════════════════════════════════════════════════════
# CLARIFICATION MANAGER
# ═════════════════════════════════════════════════════════════════════════════


class ClarificationManager:
    """
    Orchestrates the clarification workflow.

    Flow:
    1. Detect ambiguities using AmbiguityDetector
    2. Generate questions using QuestionGenerator
    3. Present questions to user via UI
    4. Collect responses
    5. Update context and check for completion
    6. Return clarified data for pipeline continuation

    Features:
    - Bounded iterations (max 5 by default)
    - State persistence (checkpoint support)
    - One question at a time logic
    - Integration with existing checkpoint system
    """

    def __init__(
        self,
        detector: AmbiguityDetector,
        question_generator: QuestionGenerator,
        ui: ClarificationUI,
        max_iterations: int = 5,
    ):
        """
        Initialize the clarification manager.

        Args:
            detector: AmbiguityDetector for detecting ambiguities
            question_generator: QuestionGenerator for generating questions
            ui: ClarificationUI for user interaction
            max_iterations: Maximum clarification iterations (default: 5)
        """
        if not 1 <= max_iterations <= 10:
            raise ValueError(f"max_iterations must be 1-10, got {max_iterations}")

        self.detector = detector
        self.question_generator = question_generator
        self.ui = ui
        self.max_iterations = max_iterations

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        return f"clarification_{timestamp}_{unique_id}"

    def run_clarification(
        self,
        section_bundle: Any,
        session_id: Optional[str] = None,
    ) -> ClarificationContext:
        """
        Run the complete clarification workflow.

        Args:
            section_bundle: The SectionBundle from Step 1
            session_id: Optional session ID (auto-generated if None)

        Returns:
            ClarificationContext with all questions and answers
        """
        # Create or restore context
        context = ClarificationContext(
            session_id=session_id or self._generate_session_id(),
            max_iterations=self.max_iterations,
        )

        # Step 1: Detect ambiguities
        logger.info(f"[{context.session_id}] Starting ambiguity detection...")
        detection_result = self.detector.detect(section_bundle)

        if not detection_result.needs_clarification:
            logger.info(f"[{context.session_id}] No clarification needed")
            context.status = ClarificationStatus.COMPLETED
            return context

        logger.info(
            f"[{context.session_id}] Detected {len(detection_result.markers)} ambiguities, "
            f"defect_density={detection_result.defect_density:.3f}"
        )

        # Step 2: Generate questions
        logger.info(f"[{context.session_id}] Generating clarification questions...")
        question_result = self.question_generator.generate_questions(
            detection_result.markers
        )

        context.markers = detection_result.markers
        context.questions = question_result.questions

        logger.info(
            f"[{context.session_id}] Generated {len(context.questions)} questions"
        )

        # Step 3: Present questions and collect answers (one at a time)
        for question in context.sort_questions_by_priority():
            # Check iteration limit
            if context.iteration >= self.max_iterations:
                logger.warning(
                    f"[{context.session_id}] Max iterations ({self.max_iterations}) reached"
                )
                context.status = ClarificationStatus.MAX_ITERATIONS_REACHED
                break

            # Present question to user
            self.ui.present_question(question)

            # Collect response
            response = self.ui.collect_response(question)

            # Add response to context
            context.add_response(response)
            context.advance_iteration()

            logger.debug(
                f"[{context.session_id}] Collected response for {question.question_id}: "
                f"{response.get_answer_text()[:50]}..."
            )

        # Step 4: Finalize
        if context.is_complete():
            context.mark_completed()
            logger.info(f"[{context.session_id}] Clarification completed successfully")
        else:
            unanswered = len(context.get_unanswered_questions())
            logger.warning(
                f"[{context.session_id}] Clarification ended with {unanswered} unanswered questions"
            )

        # Present summary
        self.ui.present_summary(context)

        return context

    def apply_clarifications(
        self,
        section_bundle: Any,
        context: ClarificationContext,
    ) -> Any:
        """
        Apply clarifications to create an updated SectionBundle.

        Uses the answers to annotate/modify the original sections.
        The clarified information is added as metadata/annotations to
        SectionItems, preserving the original text.

        Args:
            section_bundle: Original SectionBundle from Step 1
            context: ClarificationContext with Q&A

        Returns:
            Updated SectionBundle with clarification annotations
        """
        # Import here to avoid circular dependency
        from ..models import SectionBundle, SectionItem

        # Get answers summary
        answers = context.get_answers_summary()

        if not answers:
            logger.info("No clarifications to apply")
            return section_bundle

        # Create a mapping of question_id -> answer for quick lookup
        question_answer_map: dict[str, tuple[ClarificationQuestion, str]] = {}
        for question in context.questions:
            answer_text = answers.get(question.question_id)
            if answer_text:
                question_answer_map[question.question_id] = (question, answer_text)

        # Create updated sections with clarification annotations
        # We add clarification info as a suffix to the text (preserving original)
        def annotate_item(item: SectionItem, section_name: str) -> SectionItem:
            """Annotate a SectionItem with relevant clarifications."""
            relevant_clarifications = []

            for question_id, (question, answer) in question_answer_map.items():
                # Check if this question relates to this section/item
                if question.source_section == section_name:
                    # Create annotation
                    annotation = f"[CLARIFIED: {question.source_text} → {answer}]"
                    relevant_clarifications.append(annotation)

            if relevant_clarifications:
                # Append clarifications to text
                annotated_text = f"{item.text}\n" + "\n".join(relevant_clarifications)
                return SectionItem(
                    text=annotated_text,
                    source=item.source,
                    multi=item.multi,
                )

            return item

        # Build updated bundle
        updated_bundle = SectionBundle(
            intent=[annotate_item(item, "INTENT") for item in section_bundle.intent],
            workflow=[annotate_item(item, "WORKFLOW") for item in section_bundle.workflow],
            constraints=[annotate_item(item, "CONSTRAINTS") for item in section_bundle.constraints],
            examples=[annotate_item(item, "EXAMPLES") for item in section_bundle.examples],
            notes=[annotate_item(item, "NOTES") for item in section_bundle.notes],
        )

        logger.info(f"Applied {len(answers)} clarifications to SectionBundle")
        return updated_bundle

    def save_checkpoint(
        self,
        context: ClarificationContext,
        path: str,
    ) -> None:
        """
        Save clarification state to checkpoint file.

        Args:
            context: ClarificationContext to save
            path: File path for the checkpoint
        """
        checkpoint = ClarificationCheckpoint(
            session_id=context.session_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            data=context.to_dict(),
        )

        checkpoint_path = Path(path)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint.to_dict(), f, indent=2, ensure_ascii=False)

        logger.info(f"Saved clarification checkpoint to {path}")

    def load_checkpoint(self, path: str) -> ClarificationContext:
        """
        Load clarification state from checkpoint file.

        Args:
            path: File path for the checkpoint

        Returns:
            ClarificationContext restored from checkpoint

        Raises:
            FileNotFoundError: If checkpoint file doesn't exist
            ValueError: If checkpoint is invalid
        """
        checkpoint_path = Path(path)

        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {path}")

        with open(checkpoint_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        checkpoint = ClarificationCheckpoint.from_dict(data)

        if checkpoint.checkpoint_type != CHECKPOINT_TYPE:
            raise ValueError(
                f"Invalid checkpoint type: {checkpoint.checkpoint_type}, "
                f"expected {CHECKPOINT_TYPE}"
            )

        context = ClarificationContext.from_dict(checkpoint.data)
        logger.info(f"Loaded clarification checkpoint from {path}")

        return context

    def run_from_checkpoint(
        self,
        section_bundle: Any,
        checkpoint_path: str,
    ) -> ClarificationContext:
        """
        Resume clarification from a saved checkpoint.

        Args:
            section_bundle: The SectionBundle from Step 1
            checkpoint_path: Path to saved checkpoint

        Returns:
            ClarificationContext with all questions and answers
        """
        # Load existing context
        context = self.load_checkpoint(checkpoint_path)

        logger.info(
            f"[{context.session_id}] Resuming from checkpoint, "
            f"iteration={context.iteration}, status={context.status.value}"
        )

        # If already completed, just return
        if context.status == ClarificationStatus.COMPLETED:
            logger.info(f"[{context.session_id}] Already completed")
            return context

        # Continue with remaining questions
        unanswered = context.get_unanswered_questions()

        for question in unanswered:
            # Check iteration limit
            if context.iteration >= self.max_iterations:
                context.status = ClarificationStatus.MAX_ITERATIONS_REACHED
                break

            # Present question
            self.ui.present_question(question)

            # Collect response
            response = self.ui.collect_response(question)

            # Add response
            context.add_response(response)
            context.advance_iteration()

        # Finalize
        if context.is_complete():
            context.mark_completed()

        self.ui.present_summary(context)

        return context


# ═════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ═════════════════════════════════════════════════════════════════════════════


def run_hitl_clarification(
    section_bundle: Any,
    llm_client: Any,
    ui: Optional[ClarificationUI] = None,
    sensitivity: str = "medium",
    max_iterations: int = 5,
) -> tuple[ClarificationContext, Any]:
    """
    Convenience function for running HITL clarification.

    Args:
        section_bundle: SectionBundle from Step 1
        llm_client: LLM client for detection and question generation
        ui: UI implementation (default: ConsoleClarificationUI)
        sensitivity: Detection sensitivity ("low", "medium", "high")
        max_iterations: Max clarification iterations

    Returns:
        Tuple of (ClarificationContext, updated SectionBundle)
    """
    # Create sensitivity config
    config_map = {
        "low": SensitivityConfig.low,
        "medium": SensitivityConfig.medium,
        "high": SensitivityConfig.high,
    }
    config = config_map.get(sensitivity, SensitivityConfig.medium)()

    # Create components
    detector = AmbiguityDetector(llm_client=llm_client, config=config)
    question_gen = QuestionGenerator(llm_client=llm_client)
    ui = ui or ConsoleClarificationUI()

    # Run manager
    manager = ClarificationManager(
        detector=detector,
        question_generator=question_gen,
        ui=ui,
        max_iterations=max_iterations,
    )

    context = manager.run_clarification(section_bundle)

    # Apply clarifications
    updated_bundle = manager.apply_clarifications(section_bundle, context)

    return context, updated_bundle


# ═════════════════════════════════════════════════════════════════════════════
# PIPELINE INTEGRATION HELPER
# ═════════════════════════════════════════════════════════════════════════════


class ClarificationPipelineStep:
    """
    Helper class for integrating clarification into the pipeline.

    This class provides a clean interface for inserting clarification
    as a step in the pipeline after Step 1 (Structure Extraction).
    """

    def __init__(
        self,
        llm_client: Any,
        sensitivity: str = "medium",
        max_iterations: int = 5,
        ui: Optional[ClarificationUI] = None,
        checkpoint_dir: Optional[str] = None,
    ):
        """
        Initialize the clarification pipeline step.

        Args:
            llm_client: LLM client for detection and question generation
            sensitivity: Detection sensitivity ("low", "medium", "high")
            max_iterations: Max clarification iterations
            ui: UI implementation (default: ConsoleClarificationUI)
            checkpoint_dir: Directory for saving checkpoints (optional)
        """
        self.llm_client = llm_client
        self.sensitivity = sensitivity
        self.max_iterations = max_iterations
        self.ui = ui
        self.checkpoint_dir = checkpoint_dir

        # Create config
        config_map = {
            "low": SensitivityConfig.low,
            "medium": SensitivityConfig.medium,
            "high": SensitivityConfig.high,
        }
        self.config = config_map.get(sensitivity, SensitivityConfig.medium)()

    def run(
        self,
        section_bundle: Any,
        session_id: Optional[str] = None,
    ) -> tuple[ClarificationContext, Any]:
        """
        Run clarification on a SectionBundle.

        Args:
            section_bundle: SectionBundle from Step 1
            session_id: Optional session ID

        Returns:
            Tuple of (ClarificationContext, updated SectionBundle)
        """
        # Create components
        detector = AmbiguityDetector(llm_client=self.llm_client, config=self.config)
        question_gen = QuestionGenerator(llm_client=self.llm_client)
        ui = self.ui or ConsoleClarificationUI()

        # Create manager
        manager = ClarificationManager(
            detector=detector,
            question_generator=question_gen,
            ui=ui,
            max_iterations=self.max_iterations,
        )

        # Run clarification
        context = manager.run_clarification(section_bundle, session_id)

        # Save checkpoint if directory specified
        if self.checkpoint_dir and context.status == ClarificationStatus.COMPLETED:
            checkpoint_path = Path(self.checkpoint_dir) / f"{context.session_id}.json"
            manager.save_checkpoint(context, str(checkpoint_path))

        # Apply clarifications
        updated_bundle = manager.apply_clarifications(section_bundle, context)

        return context, updated_bundle

    def should_run(self, section_bundle: Any) -> bool:
        """
        Check if clarification should run for this SectionBundle.

        Performs a quick detection to determine if clarification is needed.

        Args:
            section_bundle: SectionBundle to check

        Returns:
            True if clarification is needed
        """
        detector = AmbiguityDetector(llm_client=self.llm_client, config=self.config)
        result = detector.detect(section_bundle)
        return result.needs_clarification


# ═════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═════════════════════════════════════════════════════════════════════════════

__all__ = [
    "ClarificationManager",
    "ClarificationCheckpoint",
    "run_hitl_clarification",
    "ClarificationPipelineStep",
]
