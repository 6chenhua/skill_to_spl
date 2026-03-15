"""
Data models for the skill-to-CNL-P normalization pipeline.

All dataclasses are pure data containers — no business logic.
Pipeline stages produce and consume these types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Pre-processing: P1 — Reference Graph Builder
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FileNode:
    """Represents a single file in the skill package."""
    path: str                    # relative to skill root
    kind: str                    # "doc" | "script" | "data" | "document" | "image" | "audio"
    size_bytes: int
    head_lines: list[str]        # first 20 lines (doc) or head comment (script ≤5 lines)
    references: list[str]        # other filenames mentioned in this file (regex scan)


@dataclass
class FileReferenceGraph:
    """Output of P1. The mechanical inventory of a skill package."""
    skill_id: str
    root_path: str
    skill_md_content: str        # full text of SKILL.md (anchor for P2)
    frontmatter: dict[str, Any]  # parsed YAML frontmatter from SKILL.md
    nodes: dict[str, FileNode]   # rel_path → FileNode
    edges: dict[str, list[str]]  # referencing_file → [referenced_files]

    # ── CapabilityProfile Layer 1 (auto-derived by P1) ──────────────────────
    # These fields enable environment-aware classification in Step 2B.
    # local_scripts: all .py / .sh files found in the package → implies EXEC capability.
    # referenced_libs: top-level imports found in script head comments → implies
    #   specific tool capabilities (e.g. "requests" → NETWORK, "boto3" → REMOTE_RUN).
    local_scripts: list[str] = field(default_factory=list)
    referenced_libs: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Pre-processing: P2 — File Role Resolver (LLM output)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FileRoleEntry:
    """LLM-assigned role and read priority for a single file."""
    role: str                           # from taxonomy (see prompts/p2_file_role_resolver.py)
    read_priority: int                  # 1=must_read, 2=include_summary, 3=omit
    must_read_for_normalization: bool
    reasoning: str                      # one sentence citing specific source text


# FileRoleMap: dict[str, FileRoleEntry]  (path → entry)
# Defined as a type alias; stored as plain dict in SkillPackage for JSON-serializability.


# ─────────────────────────────────────────────────────────────────────────────
# Pre-processing: P3 — Skill Package Assembler
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SkillPackage:
    """Output of P3. The assembled, annotated input for Step 1."""
    skill_id: str
    root_path: str
    frontmatter: dict[str, Any]
    merged_doc_text: str                # concatenated content with file boundary markers
    file_role_map: dict[str, Any]       # path → FileRoleEntry dict (serializable)


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Structure Extraction
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SectionItem:
    """A single item within a canonical section. Text is always verbatim."""
    text: str           # verbatim from source — never paraphrased
    source: str         # source filename
    multi: bool = False # True if this item appears in multiple sections


@dataclass
class SectionBundle:
    """
    Output of Step 1. Eight canonical sections covering the full skill document.
    All text is verbatim; nothing is dropped.
    """
    intent:      list[SectionItem] = field(default_factory=list)
    workflow:    list[SectionItem] = field(default_factory=list)
    constraints: list[SectionItem] = field(default_factory=list)
    tools:       list[SectionItem] = field(default_factory=list)
    artifacts:   list[SectionItem] = field(default_factory=list)
    evidence:    list[SectionItem] = field(default_factory=list)
    examples:    list[SectionItem] = field(default_factory=list)
    notes:       list[SectionItem] = field(default_factory=list)

    def all_sections(self) -> dict[str, list[SectionItem]]:
        return {
            "INTENT":      self.intent,
            "WORKFLOW":    self.workflow,
            "CONSTRAINTS": self.constraints,
            "TOOLS":       self.tools,
            "ARTIFACTS":   self.artifacts,
            "EVIDENCE":    self.evidence,
            "EXAMPLES":    self.examples,
            "NOTES":       self.notes,
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
                    f"  [{item.source}] {item.text}" + (" [MULTI]" if item.multi else "")
                    for item in items
                )
                parts.append(f"## {name}\n{block}")
        return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2A — Clause Extraction + Scoring (LLM output)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RawScores:
    """Six rubric dimensions scored by the LLM (0–3 each)."""
    O: int  # Observability
    A: int  # Actionability
    F: int  # Formalizability
    C: int  # Context dependence
    R: int  # Risk / Safety criticality
    V: int  # Verifiability

    def validate(self) -> None:
        for dim, val in [("O", self.O), ("A", self.A), ("F", self.F),
                         ("C", self.C), ("R", self.R), ("V", self.V)]:
            if not (0 <= val <= 3):
                raise ValueError(f"Score {dim}={val} out of range [0,3]")


@dataclass
class RawClause:
    """
    A single normative clause as output by Step 2A LLM.
    May be a parent (split=True) or leaf clause.

    clause_type drives SPL routing in Step 4:
      "rule" → DEFINE_CONSTRAINTS
               Hard/Medium: with LOG; Hard violation → EXCEPTION_FLOW;
               Medium not met → ALTERNATIVE_FLOW;
               Soft: [SOFT] prefix; Non-Compilable: [GUIDELINE] prefix.
               Hard + Medium rules also drive APPLY_CONSTRAINTS on WORKER INPUTS/OUTPUTS.
      "step" → WORKER MAIN_FLOW COMMAND variant determined by execution_mode
               in the corresponding WorkflowStepSpec.
    """
    clause_id: str
    source_section: str
    source_file: str
    original_text: str
    is_normative: bool
    clause_type: str                   # "rule" | "step" | "prerequisite" | "guidance"
    split: bool
    sub_clauses: list[RawClause]       # non-empty only when split=True
    scores: RawScores
    score_rationale: str


# ─────────────────────────────────────────────────────────────────────────────
# Step 2B — Classification (pure code)
# ─────────────────────────────────────────────────────────────────────────────

class Classification(str, Enum):
    HARD   = "COMPILABLE_HARD"
    MEDIUM = "COMPILABLE_MEDIUM"
    SOFT   = "COMPILABLE_SOFT"
    NON    = "NON_COMPILABLE"


@dataclass
class ClassifiedClause:
    """
    Output of Step 2B. A RawClause enriched with deterministic classification.

    clause_type is propagated from RawClause and is the primary routing key for Step 4.
    downgraded=True means the clause was originally HARD but was downgraded to MEDIUM
    because the runtime capability profile does not support the required effects.
    """
    clause_id: str
    original_text: str
    source_section: str
    source_file: str
    scores: RawScores
    S_det: int                          # min(O, F, V) — deterministic checkability
    S_proc: int                         # min(A, V)    — process executability
    classification: Classification
    clause_type: str                    # propagated from RawClause
    risk_override: bool                 # True if R==3 forced upgrade from SOFT→MEDIUM
    downgraded: bool                    # True if capability profile forced HARD→MEDIUM
    confidence: float                   # [0.0, 1.0] enforceability confidence
    needs_review: bool
    enforcement_backends: list[str]
    score_rationale: str


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Structured Entity and Step Extraction (LLM output)
#
# Design notes:
#   - No DEFINE_GUARDRAIL: the new SPL grammar has no GUARDRAIL_INSTRUCTION.
#     INSTRUCTION := WORKER_INSTRUCTION only.
#   - EXCEPTION_FLOW is driven by runtime failure signals (not validation gates):
#       * Hard rule clause violation (APPLY_CONSTRAINTS check fails on data)
#       * API call failure (NETWORK in effects)
#       * Execution step failure (EXEC/WRITE in effects, required produces not found)
#   - is_validation_gate is retained to mark steps that check evidence requirements;
#     these steps generate EXCEPTION_FLOW on failure but do NOT become GUARDRAIL blocks.
#   - NON_COMPILABLE clauses → InteractionRequirement → [INPUT DISPLAY] in MAIN_FLOW.
#   - APPLY_CONSTRAINTS goes on WORKER INPUTS/OUTPUTS, not on individual COMMANDs.
#   - execution_mode determines which GENERAL_COMMAND variant is emitted in MAIN_FLOW.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EntitySpec:
    """
    A named data entity (variable or file) that the WORKER reads or produces.

    Routing to SPL:
      kind in {Run, Evidence, Record}  → DEFINE_VARIABLES
      kind == "Artifact"               → DEFINE_FILES (leaf file declaration)
      from_omit_files == True          → DEFINE_FILES (P1 read_priority=3 data/document files)

    file_path: use actual path if known, empty string → emit as "< >" (runtime upload).
    """
    entity_id: str
    kind: str                           # Artifact | Run | Evidence | Record
    type_name: str
    schema_notes: str                   # enriched by EXAMPLES section when available
    provenance_required: bool
    provenance: str                     # EXPLICIT | ASSUMED | LOW_CONFIDENCE
    source_text: str
    # ── file routing fields ──────────────────────────────────────────────────
    is_file: bool = False               # True when kind=Artifact OR from_omit_files=True
    file_path: str = ""                 # actual path; "" → "< >" in SPL
    from_omit_files: bool = False       # True if sourced from P1 read_priority=3 nodes


@dataclass
class WorkflowStepSpec:
    """
    A single step in the skill workflow, rewritten into SPL-ready form.

    execution_mode drives the GENERAL_COMMAND variant in MAIN_FLOW:
      "PROMPT_TO_CODE" — step describes running a specific script/tool;
                         tool_hint is non-empty and step involves code execution.
                         Emits: [COMMAND PROMPT_TO_CODE description RESULT var: type]
      "CODE"           — source document contains a literal code block for this step.
                         Emits: [COMMAND CODE description RESULT var: type]
      "LLM_PROMPT"     — step is a reasoning/judgment task for the LLM.
                         Emits: [COMMAND description RESULT var: type]

    "NETWORK" in effects  → [CALL ApiName ...] in MAIN_FLOW + DEFINE_APIS (via S4D).
    is_validation_gate=True → step checks an evidence requirement; failure triggers
                              EXCEPTION_FLOW (step_id_failed) in the WORKER.
    "EXEC" or "WRITE" in effects, with provenance_required produces → failure triggers
                              EXCEPTION_FLOW as well.
    """
    step_id: str                        # step.<action_name>  (snake_case)
    description: str                    # SPL-ready COMMAND description
    prerequisites: list[str]            # entity_ids that must exist before this step
    produces: list[str]                 # entity_ids this step creates
    is_validation_gate: bool            # True if derived from EVIDENCE requirements
    effects: list[str]                  # READ | WRITE | NETWORK | EXEC | REMOTE_RUN
    execution_mode: str                 # PROMPT_TO_CODE | CODE | LLM_PROMPT
    tool_hint: str                      # explicit tool/script name if stated, else ""
    provenance: str                     # EXPLICIT | ASSUMED
    source_text: str                    # verbatim anchor in source


@dataclass
class InteractionRequirement:
    """
    Derived from NON_COMPILABLE clause.step entries.
    Represents a point where the agent must interact with the user before proceeding.

    SPL mapping in WORKER MAIN_FLOW (placed just before gates_step):
      interaction_type == "ASK"   → [INPUT DISPLAY "prompt" VALUE answer: text]
      interaction_type == "STOP"  → [INPUT DISPLAY "prompt" VALUE confirmed: boolean]
                                     + DECISION [IF confirmed == false]
                                         COMMAND [DISPLAY Cannot proceed: reason]
                                       [END_IF]
      interaction_type == "ELICIT"→ [INPUT DISPLAY "prompt" VALUE choice: text]
    """
    req_id: str
    condition: str                      # when this interaction is triggered
    interaction_type: str               # ASK | STOP | ELICIT
    prompt: str                         # question or message to present to user
    gates_step: str                     # step_id this interaction precedes (or "" if general)
    source_text: str                    # verbatim original NON clause text


@dataclass
class SuccessCriteria:
    """
    What the skill considers "done".
    Used in S4E to annotate the WORKER [OUTPUTS] REQUIRED block.
    """
    description: str
    deterministic: bool
    provenance: str                     # EXPLICIT | LOW_CONFIDENCE
    source_text: str


@dataclass
class NeedsReviewItem:
    """
    Human review flag. NOT consumed by Step 4 SPL emission.
    Goes only to review_summary for human inspection.
    """
    item: str
    reason: str
    question: str


@dataclass
class StructuredSpec:
    """
    Output of Step 3 (formerly InterfaceSpec).
    Renamed to StructuredSpec to reflect the actual job: structured extraction
    and naming, not interface contract inference.

    Step 4 routing:
      entities (kind=Artifact or from_omit_files)  → S4C  DEFINE_FILES
      entities (kind in Run/Evidence/Record)        → S4C  DEFINE_VARIABLES
      workflow_steps (NETWORK in effects)           → S4D  DEFINE_APIS
      workflow_steps (NETWORK in effects)           → S4E  [CALL ApiName] + EXCEPTION_FLOW on failure
      workflow_steps (execution_mode=PROMPT_TO_CODE)→ S4E  [COMMAND PROMPT_TO_CODE ...]
      workflow_steps (execution_mode=CODE)          → S4E  [COMMAND CODE ...]
      workflow_steps (execution_mode=LLM_PROMPT)    → S4E  [COMMAND ...]
      workflow_steps (is_validation_gate=True,      → S4E  EXCEPTION_FLOW on step failure
                      or EXEC/WRITE + provenance_required)
      interaction_requirements                      → S4E  [INPUT DISPLAY ...] in MAIN_FLOW
      success_criteria                              → S4E  [OUTPUTS] REQUIRED annotation
      needs_review_items                            → review_summary only (not SPL)

    Hard + Medium clause.rule (from ClassifiedClauses, passed separately to S4B and S4E):
      → S4B  DEFINE_CONSTRAINTS (Hard: LOG; Medium: LOG; Soft: [SOFT]; Non: [GUIDELINE])
      → S4E  APPLY_CONSTRAINTS on WORKER INPUTS/OUTPUTS
      → S4E  Hard clause.rule violation → EXCEPTION_FLOW
      → S4E  Medium clause.rule not met → ALTERNATIVE_FLOW
    """
    entities: list[EntitySpec]
    workflow_steps: list[WorkflowStepSpec]
    interaction_requirements: list[InteractionRequirement]
    success_criteria: SuccessCriteria
    needs_review_items: list[NeedsReviewItem]  # human review only, not for SPL


# Keep InterfaceSpec as alias for backward compatibility during transition
InterfaceSpec = StructuredSpec


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — SPL Emission (LLM output)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SPLSpec:
    """Output of Step 4. The final normalized SPL specification."""
    skill_id: str
    spl_text: str                       # the complete SPL code block
    review_summary: str                 # plain-text review summary (NEEDS_REVIEW items etc.)
    clause_counts: dict[str, int]       # {"HARD": N, "MEDIUM": N, "SOFT": N, "NON": N}


# ─────────────────────────────────────────────────────────────────────────────
# Top-level pipeline result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    """The complete output of a full pipeline run."""
    skill_id: str

    # intermediate outputs (kept for traceability / rerun from checkpoint)
    graph: FileReferenceGraph
    file_role_map: dict[str, Any]
    package: SkillPackage
    section_bundle: SectionBundle
    raw_clauses: list[RawClause]
    classified_clauses: list[ClassifiedClause]
    structured_spec: StructuredSpec

    # final output
    spl_spec: SPLSpec

    # diagnostics
    needs_review_count: int = 0
    low_confidence_count: int = 0
