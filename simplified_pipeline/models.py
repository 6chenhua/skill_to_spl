"""
Simplified data models for the minimal pipeline.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .clarification.structural_models import SectionGuidance


# ─────────────────────────────────────────────────────────────────────────────
# Input/Output Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SectionItem:
    """A single item within a section. Text is always verbatim."""
    text: str
    source: str
    multi: bool = False


@dataclass
class SectionBundle:
    """
    Simplified Step 1 output with 5 sections only.
    """
    intent: list[SectionItem] = field(default_factory=list)
    workflow: list[SectionItem] = field(default_factory=list)
    constraints: list[SectionItem] = field(default_factory=list)
    examples: list[SectionItem] = field(default_factory=list)
    notes: list[SectionItem] = field(default_factory=list)

    def all_sections(self) -> dict[str, list[SectionItem]]:
        return {
            "INTENT": self.intent,
            "WORKFLOW": self.workflow,
            "CONSTRAINTS": self.constraints,
            "EXAMPLES": self.examples,
            "NOTES": self.notes,
        }

    def to_text(self, sections: Optional[list[str]] = None) -> str:
        """Render selected (or all) sections as labelled text blocks."""
        target = self.all_sections()
        if sections:
            target = {k: v for k, v in target.items() if k in sections}
        parts = []
        for name, items in target.items():
            if items:
                block = "\n".join(
                    f" [{item.source}] {item.text}" + (" [MULTI]" if item.multi else "")
                    for item in items
                )
                parts.append(f"## {name}\n{block}")
        return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Step 3A: Entity Extraction (Variables only, no files)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VariableSpec:
    """
    A variable entity (simplified - no files, only in-memory variables).
    """
    var_id: str  # snake_case identifier
    type_name: str  # PascalCase type label
    schema_notes: str  # description of structure
    provenance_required: bool  # must be validated/produced
    provenance: str  # EXPLICIT | ASSUMED | LOW_CONFIDENCE
    source_text: str  # verbatim quote from source


# ─────────────────────────────────────────────────────────────────────────────
# Step 3B: Workflow Analysis (Simplified action types)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WorkflowStepSpec:
    """
    A workflow step with simplified action types.

    Simplified action_type values (no API-related types):
    - "LLM_TASK": Pure LLM reasoning/judgment task (default)
    - "FILE_READ": Read from a file
    - "FILE_WRITE": Write to a file
    - "USER_INTERACTION": Requires user input
    """
    step_id: str  # step.<action_name>
    description: str  # concise action description
    prerequisites: list[str]  # var_ids that must exist
    produces: list[str]  # var_ids this step creates
    is_validation_gate: bool  # true if checks evidence
    action_type: str = "LLM_TASK"  # LLM_TASK | FILE_READ | FILE_WRITE | USER_INTERACTION
    source_text: str = ""  # verbatim anchor


@dataclass
class FlowStep:
    """A step within alternative or exception flows."""
    description: str
    action_type: str = "LLM_TASK"
    source_text: str = ""


@dataclass
class AlternativeFlowSpec:
    """Alternative execution path."""
    flow_id: str
    condition: str
    description: str
    steps: list[FlowStep]
    source_text: str
    provenance: str = "EXPLICIT"


@dataclass
class ExceptionFlowSpec:
    """Failure-handling path."""
    flow_id: str
    condition: str
    log_ref: str
    steps: list[FlowStep]
    source_text: str
    provenance: str = "EXPLICIT"


@dataclass
class StructuredSpec:
    """Combined output of Step 3A + 3B."""
    variables: list[VariableSpec]
    workflow_steps: list[WorkflowStepSpec]
    alternative_flows: list[AlternativeFlowSpec]
    exception_flows: list[ExceptionFlowSpec]


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: SPL Output (Simplified - no APIs, no files)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SPLSpec:
    """Final SPL specification (simplified)."""
    skill_id: str
    spl_text: str


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    """Complete output of the simplified pipeline."""
    skill_id: str
    section_bundle: SectionBundle
    structured_spec: StructuredSpec
    spl_spec: SPLSpec
    clarification_context: Optional[Any] = None  # Legacy: ClarificationContext if HITL was used
    structural_guidance: Optional[Any] = None  # NEW: SectionGuidance from Step 0
