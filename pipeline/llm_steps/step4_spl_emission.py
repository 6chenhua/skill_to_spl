"""
step4_spl_emission.py
─────────────────────
Step 4: SPL Emission (five + one focused LLM calls).

Changes from prior version:
  1. DEFINE_CONSTRAINTS (S4B) now receives ALL rule clauses (HARD/MEDIUM/SOFT/NON).
  2. MAIN_FLOW (S4E) includes ALL workflow steps — NETWORK and validation-gate
     steps are no longer filtered out.
  3. ALTERNATIVE_FLOW driven by StructuredSpec.alternative_flows (Step 3B output),
     not by MEDIUM clause text.
  4. EXCEPTION_FLOW driven by StructuredSpec.exception_flows (Step 3B output),
     not auto-generated from validation gates.
  5. S4F (Round 3) generates [EXAMPLES] block separately using the WORKER
     SPL + bundle.EXAMPLES — success_criteria no longer needed.
  6. DEFINE_GUARDRAIL removed (not in grammar); [THROW] removed.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from models.data_models import (
    ClassifiedClause,
    Classification,
    EntitySpec,
    SectionBundle,
    SPLSpec,
    StructuredSpec,
    WorkflowStepSpec,
)
from pipeline.llm_client import LLMClient
from prompts import templates

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_step4_spl_emission(
        bundle: SectionBundle,
        classified_clauses: list[ClassifiedClause],
        interface_spec: StructuredSpec,
        skill_id: str,
        client: LLMClient,
) -> SPLSpec:
    """
    Step 4: Emit the final normalized SPL specification.

    Round 1 — independent, run in parallel:
      4a  PERSONA / AUDIENCE / CONCEPTS
      4b  DEFINE_CONSTRAINTS   (all 4 tiers: HARD / MEDIUM / SOFT / GUIDELINE)
      4c  DEFINE_VARIABLES + DEFINE_FILES
      4d  DEFINE_APIS          (NETWORK steps only — DEFINE_GUARDRAIL removed)

    After Round 1: extract symbol table from 4b, 4c, 4d.

    Round 2 — depends on symbol table:
      4e  DEFINE_WORKER        (MAIN_FLOW + ALTERNATIVE_FLOW + EXCEPTION_FLOW)

    Round 3 — depends on Round 2:
      4f  [EXAMPLES] block     (uses generated WORKER SPL + bundle.EXAMPLES)
    """
    inputs = _prepare_step4_inputs(bundle, classified_clauses, interface_spec)

    # ── Round 1 ───────────────────────────────────────────────────────────────
    logger.info("[Step 4] Round 1: launching 4 parallel block generators")

    def call_4a() -> str:
        return client.call(
            "step4a_persona",
            templates.S4A_SYSTEM,
            templates.render_s4a_user(
                inputs["intent_text"], inputs["notes_text"]
            ),
        )

    def call_4b() -> str:
        if not inputs["has_constraints"]:
            return ""
        return client.call(
            "step4b_constraints",
            templates.S4B_SYSTEM,
            templates.render_s4b_user(inputs["constraints_text"]),
        )

    def call_4c() -> str:
        if not inputs["has_entities"]:
            return ""
        return client.call(
            "step4c_variables_files",
            templates.S4C_SYSTEM,
            templates.render_s4c_user(inputs["has_entities"], inputs["omit_files_text"]),
        )

    def call_4d() -> str:
        if not inputs["has_network_steps"]:
            return ""
        return client.call(
            "step4d_apis",
            templates.S4D_SYSTEM,
            templates.render_s4d_user(
                network_steps_json=inputs["network_steps_json"],
            ),
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        block_4a = pool.submit(call_4a).result()
        block_4b = pool.submit(call_4b).result()
        block_4c = pool.submit(call_4c).result()
        block_4d = pool.submit(call_4d).result()

    # ── Symbol table ──────────────────────────────────────────────────────────
    symbol_table = _extract_symbol_table(block_4b, block_4c, block_4d)
    logger.info("[Step 4] Symbol table: %d names extracted", len(symbol_table))

    # ── Round 2 ───────────────────────────────────────────────────────────────
    logger.info("[Step 4] Round 2: generating WORKER")
    s4e_system, s4e_user = templates.render_s4e_user(
        workflow_steps_json=inputs["workflow_steps_json"],
        workflow_prose=inputs["workflow_prose"],
        alternative_flows_json=inputs["alternative_flows_json"],
        exception_flows_json=inputs["exception_flows_json"],
        symbol_table=_format_symbol_table(symbol_table),
    )
    block_4e = client.call(step_name="step4e_worker", system=s4e_system, user=s4e_user)

    # ── Round 3 ───────────────────────────────────────────────────────────────
    logger.info("[Step 4] Round 3: generating EXAMPLES")
    block_4f = ""
    if inputs["has_examples"]:
        block_4f = client.call(
            "step4f_examples",
            templates.S4F_SYSTEM,
            templates.render_s4f_user(
                worker_spl=block_4e,
                examples_text=inputs["examples_text"],
            ),
        )

    # ── Assemble ──────────────────────────────────────────────────────────────
    spl_text = _assemble_spl(
        skill_id, block_4a, block_4b, block_4c, block_4d, block_4e, block_4f
    )
    review_summary = _build_review_summary(classified_clauses, interface_spec)
    clause_counts = _count_clauses(classified_clauses)

    logger.info("[Step 4] SPL assembled (%d chars)", len(spl_text))
    return SPLSpec(
        skill_id=skill_id,
        spl_text=spl_text,
        review_summary=review_summary,
        clause_counts=clause_counts,
    )


# ── Input preparation ─────────────────────────────────────────────────────────

def _format_constraints_for_s4b(clauses: list[ClassifiedClause]) -> str:
    """
    Format ALL rule-type clauses for S4B: HARD, MEDIUM, SOFT, and NON/GUIDELINE.
    S4B_SYSTEM maps each tier to the correct SPL syntax.
    """
    if not clauses:
        return "(No constraints found)"

    by_tier = {
        "HARD": [c for c in clauses if c.classification == Classification.HARD],
        "MEDIUM": [c for c in clauses if c.classification == Classification.MEDIUM],
        "SOFT": [c for c in clauses if c.classification == Classification.SOFT],
        "NON": [c for c in clauses if c.classification == Classification.NON],
    }

    tier_labels = {
        "HARD": "HARD constraints (emit as hard gates with LOG):",
        "MEDIUM": "MEDIUM constraints (emit as [MEDIUM] with LOG):",
        "SOFT": "SOFT constraints (emit as [SOFT], no LOG):",
        "NON": "GUIDELINE constraints (emit as [GUIDELINE], no LOG):",
    }

    lines = []
    for tier, label in tier_labels.items():
        tier_clauses = by_tier[tier]
        if not tier_clauses:
            continue
        lines.append(label)
        lines.append("")
        for c in tier_clauses:
            lines.append(f"Constraint ID: {c.clause_id}")
            lines.append(f"Requirement:   {c.original_text}")
            lines.append(f"Source:        {c.source_file}")
            lines.append(f"Confidence:    {c.confidence:.2f}")
            if c.needs_review:
                lines.append("Needs Review:  Yes")
            if c.risk_override:
                lines.append("Risk Override: Upgraded from SOFT due to R=3")
            if getattr(c, "downgraded", False):
                lines.append("Capability Downgrade: Originally HARD")
            lines.append("")

    return "\n".join(lines)


def _format_entities_for_s4c(entities: list[EntitySpec]) -> str:
    if not entities:
        return "(No entities found)"

    variables = [e for e in entities if e.kind != "Artifact"]
    files = [e for e in entities if e.kind == "Artifact"]
    lines = []

    if variables:
        lines.append("VARIABLES (in-memory data structures → DEFINE_VARIABLES):")
        lines.append("")
        for e in variables:
            readonly = "[READONLY] " if e.provenance_required else ""
            lines.append(f"Variable: {readonly}{e.entity_id}")
            lines.append(f"Type:     {e.type_name}")
            lines.append(f"Kind:     {e.kind}")
            if e.schema_notes:
                lines.append(f"Schema:   {e.schema_notes}")
            lines.append(f"Provenance: {e.provenance}")
            if e.source_text:
                lines.append(f"Source:   {e.source_text[:120]}")
            lines.append("")

    if files:
        lines.append("FILES (disk artifacts → DEFINE_FILES):")
        lines.append("")
        for e in files:
            path_display = getattr(e, "file_path", "") or "< >"
            lines.append(f"File: {e.entity_id}")
            lines.append(f"Path: {path_display}")
            lines.append(f"Type: {e.type_name}")
            if e.schema_notes:
                lines.append(f"Description: {e.schema_notes}")
            lines.append(f"Provenance: {e.provenance}")
            if getattr(e, "from_omit_files", False):
                lines.append("Note: Sourced from P1 omit-files (priority=3)")
            lines.append("")

    return "\n".join(lines)


def _format_omit_files_for_s4c(omit_files: list[EntitySpec]) -> str:
    if not omit_files:
        return "(No omit files found)"
    lines = ["Additional files from skill package (P1 priority=3, not merged into main doc):"]
    lines.append("")
    for e in omit_files:
        path_display = getattr(e, "file_path", "") or "< >"
        lines.append(f"- {e.entity_id}: {path_display}")
        lines.append(f"  Type: {e.type_name}")
        lines.append(f"  Kind: {e.kind}")
        lines.append("")
    return "\n".join(lines)


def _prepare_step4_inputs(
        bundle: SectionBundle,
        classified_clauses: list[ClassifiedClause],
        structured_spec: StructuredSpec,
) -> dict:
    """
    Pre-compute all inputs for the five Step 4 calls.

    Routing:
      S4A  ← bundle[INTENT + NOTES]
      S4B  ← ALL rule-type clauses (HARD + MEDIUM + SOFT + NON)
      S4C  ← structured_spec.entities + omit_files
      S4D  ← NETWORK steps (API declaration only)
      S4E  ← ALL workflow steps (MAIN_FLOW)
             + alternative_flows (from Step 3B)
             + exception_flows   (from Step 3B, NOT auto-generated)
      S4F  ← generated WORKER SPL (block_4e) + bundle.EXAMPLES
    """
    # S4A
    intent_text = bundle.to_text(["INTENT"])
    notes_text = bundle.to_text(["NOTES"])

    # S4B — ALL rule-type clauses across all classification tiers
    rule_clauses = [
        c for c in classified_clauses
        if getattr(c, "clause_type", "") == "rule"
    ]
    constraints_text = _format_constraints_for_s4b(rule_clauses)

    # S4C — entities + omit-files
    entities_text = _format_entities_for_s4c(structured_spec.entities)
    omit_files = [e for e in structured_spec.entities
                  if getattr(e, "from_omit_files", False)]
    omit_files_text = _format_omit_files_for_s4c(omit_files)

    # S4D — NETWORK steps for API declaration
    network_steps = [
        s for s in structured_spec.workflow_steps
        if "NETWORK" in s.effects
    ]
    network_steps_json = json.dumps(
        [_step_to_dict(s) for s in network_steps],
        indent=2, ensure_ascii=False,
    )

    # S4E — ALL workflow steps go to MAIN_FLOW (no filtering)
    workflow_steps_json = json.dumps(
        [_step_to_dict(s) for s in structured_spec.workflow_steps],
        indent=2, ensure_ascii=False,
    )
    workflow_prose = bundle.to_text(["WORKFLOW"])

    # S4E — alternative flows (from Step 3B)
    alternative_flows_json = json.dumps(
        [dataclasses.asdict(f) for f in structured_spec.alternative_flows],
        indent=2, ensure_ascii=False,
    )

    # S4E — exception flows (from Step 3B, not auto-generated)
    exception_flows_json = json.dumps(
        [dataclasses.asdict(f) for f in structured_spec.exception_flows],
        indent=2, ensure_ascii=False,
    )

    # S4F — original examples from bundle (used after block_4e is generated)
    examples_text = bundle.to_text(["EXAMPLES"])

    return {
        "intent_text": intent_text,
        "notes_text": notes_text,
        "constraints_text": constraints_text,
        "entities_text": entities_text,
        "omit_files_text": omit_files_text,
        "network_steps_json": network_steps_json,
        "workflow_steps_json": workflow_steps_json,
        "workflow_prose": workflow_prose,
        "alternative_flows_json": alternative_flows_json,
        "exception_flows_json": exception_flows_json,
        "examples_text": examples_text,
        # control flags
        "has_constraints": bool(rule_clauses),
        "has_entities": bool(structured_spec.entities),
        "has_network_steps": bool(network_steps),
        "has_examples": bool(examples_text.strip()),
    }


def _step_to_dict(s: WorkflowStepSpec) -> dict:
    return {
        "step_id": s.step_id,
        "description": s.description,
        "prerequisites": s.prerequisites,
        "produces": s.produces,
        "is_validation_gate": s.is_validation_gate,
        "effects": s.effects,
        "tool_hint": s.tool_hint,
        "source_text": s.source_text,
        "execution_mode": getattr(s, "execution_mode", "LLM_PROMPT"),
    }


# ── Symbol table ──────────────────────────────────────────────────────────────

_CONSTRAINT_NAME_RE = re.compile(r"^\s{1,12}(?:\[MEDIUM\]\s+|\[SOFT\]\s+|\[GUIDELINE\]\s+)?([A-Z][A-Za-z0-9]+):\s",
                                 re.MULTILINE)
_VARIABLE_NAME_RE = re.compile(r'^\s{1,12}"[^"]+"\s+(?:READONLY\s+)?([a-z][a-z0-9_]+):', re.MULTILINE)
_FILE_NAME_RE = re.compile(r'^\s{1,12}"[^"]+"\s+([a-z][a-z0-9_]+)\s+<', re.MULTILINE)
_API_NAME_RE = re.compile(r'"[^"]+"\s+([A-Z][A-Za-z0-9]+)\s+<(?:none|apikey|oauth)>')


def _extract_symbol_table(
        block_4b: str,
        block_4c: str,
        block_4d: str,
) -> dict[str, list[str]]:
    table: dict[str, list[str]] = {
        "constraint_aspects": [],
        "variables": [],
        "files": [],
        "apis": [],
    }
    if block_4b:
        table["constraint_aspects"] = _CONSTRAINT_NAME_RE.findall(block_4b)
    if block_4c:
        parts = block_4c.split("[END_VARIABLES]")
        var_block = parts[0] if len(parts) > 1 else block_4c
        file_block = parts[1] if len(parts) > 1 else ""
        table["variables"] = _VARIABLE_NAME_RE.findall(var_block)
        table["files"] = _FILE_NAME_RE.findall(file_block)
    if block_4d:
        table["apis"] = _API_NAME_RE.findall(block_4d)
    return table


def _format_symbol_table(symbol_table: dict[str, list[str]]) -> str:
    mapping = {
        "constraint_aspects": "CONSTRAINTS  (use as condition in [EXCEPTION_FLOW: AspectName_violated])",
        "variables": "VARIABLES    (use in <REF> var_name </REF>)",
        "files": "FILES        (use in <REF> file_name </REF>)",
        "apis": "APIS         (use in [CALL ApiName ...])",
    }
    lines = []
    for key, label in mapping.items():
        names = symbol_table.get(key, [])
        if names:
            lines.append(f"{label}:\n  {', '.join(names)}")
    return "\n\n".join(lines) if lines else "(no symbols defined in earlier blocks)"


# ── Assembly ──────────────────────────────────────────────────────────────────

def _assemble_spl(
        skill_id: str,
        block_4a: str,
        block_4b: str,
        block_4c: str,
        block_4d: str,
        block_4e: str,
        block_4f: str,
) -> str:
    """
    Concatenate all blocks in canonical SPL order.

    block_4f ([EXAMPLES] block) is inserted INSIDE the WORKER, before
    [END_WORKER].  If [END_WORKER] is not found, 4f is appended separately.
    """
    header = (
        f"# SPL specification — {skill_id}\n"
        f"# Generated by skill-to-cnlp pipeline\n"
    )

    # Insert S4F [EXAMPLES] block into the WORKER before [END_WORKER]
    worker_block = _strip_fences(block_4e.strip())
    if block_4f:
        examples_block = _strip_fences(block_4f.strip())
        if "[END_WORKER]" in worker_block:
            worker_block = worker_block.replace(
                "[END_WORKER]",
                examples_block + "\n[END_WORKER]",
                1,
            )
        else:
            worker_block = worker_block + "\n\n" + examples_block

    blocks = [header]
    for raw_block in (block_4a, block_4b, block_4c, block_4d):
        cleaned = _strip_fences(raw_block.strip())
        if cleaned:
            blocks.append(cleaned)
    if worker_block:
        blocks.append(worker_block)

    return "\n\n".join(blocks)


def _strip_fences(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


# ── Review summary ────────────────────────────────────────────────────────────

def _build_review_summary(
        classified_clauses: list[ClassifiedClause],
        structured_spec: StructuredSpec,
) -> str:
    counts = _count_clauses(classified_clauses)
    lines = [
        "## Review Summary\n",
        "Clauses emitted: "
        + "  ".join(f"{k.split('_')[-1]}={v}" for k, v in counts.items()),
        "",
    ]

    needs_review = [c for c in classified_clauses if c.needs_review]
    if needs_review:
        lines.append("### Items requiring human review (NEEDS_REVIEW: true)")
        for c in needs_review:
            lines.append(
                f"- [{c.clause_id}] {c.classification.value}: "
                f"{c.original_text[:100]}"
            )
        lines.append("")

    low_conf = [c for c in classified_clauses if c.confidence < 0.6]
    if low_conf:
        lines.append("### Low-confidence clauses (confidence < 0.6)")
        for c in low_conf:
            lines.append(
                f"- [{c.clause_id}] confidence={c.confidence:.2f}: "
                f"{c.original_text[:100]}"
            )
        lines.append("")

    downgraded = [c for c in classified_clauses if getattr(c, "downgraded", False)]
    if downgraded:
        lines.append("### Downgraded clauses (HARD → MEDIUM by capability profile)")
        for c in downgraded:
            lines.append(
                f"- [{c.clause_id}] {c.classification.value}: "
                f"{c.original_text[:100]}"
            )
        lines.append("")

    return "\n".join(lines)


def _count_clauses(classified_clauses: list[ClassifiedClause]) -> dict[str, int]:
    counts = {c.value: 0 for c in Classification}
    for clause in classified_clauses:
        counts[clause.classification.value] += 1
    return counts


# Legacy helper — kept for compatibility
def _split_spl_output(raw_text: str) -> tuple[str, str]:
    marker = "## Review Summary"
    idx = raw_text.find(marker)
    if idx >= 0:
        return raw_text[:idx].strip(), raw_text[idx:].strip()
    return raw_text.strip(), ""
