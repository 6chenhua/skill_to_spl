"""
Step 2A: Clause Extraction + Scoring

Extract normative clauses from all sections and score each on
the 6 rubric dimensions (O, A, F, C, R, V).
"""

from __future__ import annotations

import json
import logging

from models.data_models import RawClause, RawScores, SectionBundle
from pipeline.llm_client import LLMClient
from prompts import templates

logger = logging.getLogger(__name__)


def run_step2a_clause_extraction(
    bundle: SectionBundle,
    client: LLMClient,
) -> list[RawClause]:
    """
    Step 2A: Extract normative clauses from sections and score each on
    the 6 rubric dimensions (O, A, F, C, R, V).

    Focus on sections most likely to contain normative statements:
    WORKFLOW, CONSTRAINTS, TOOLS, EVIDENCE. Other sections may contain
    some normative content but with lower density.

    Returns:
        List of RawClause objects with scores and is_normative flags.
    """
    # Focus on sections with high normative statement density
    normative_sections = ["WORKFLOW", "CONSTRAINTS", "TOOLS", "EVIDENCE"]
    section_text = bundle.to_text(normative_sections)

    user_prompt = templates.render_step2a_user(
        section_bundle_text=section_text,
    )

    raw = client.call_json(
        step_name="step2a_clause_extraction",
        system=templates.STEP2A_SYSTEM,
        user=user_prompt,
    )

    if not isinstance(raw, list):
        # Some LLMs wrap the array: {"clauses": [...]}
        if isinstance(raw, dict):
            raw = raw.get("clauses", raw.get("items", []))

    clauses = [_parse_raw_clause(item, i) for i, item in enumerate(raw)]
    normative = sum(1 for c in clauses if c.is_normative)
    logger.info("[Step 2A] extracted %d clauses (%d normative)", len(clauses), normative)
    return clauses


def _parse_raw_clause(item: dict, index: int) -> RawClause:
    """Parse a single clause from LLM JSON output."""
    scores_raw = item.get("scores", {})
    scores = RawScores(
        O=int(scores_raw.get("O", 0)),
        A=int(scores_raw.get("A", 0)),
        F=int(scores_raw.get("F", 0)),
        C=int(scores_raw.get("C", 0)),
        R=int(scores_raw.get("R", 0)),
        V=int(scores_raw.get("V", 0)),
    )
    try:
        scores.validate()
    except ValueError as exc:
        logger.warning("[Step 2A] score validation failed for clause %d: %s", index, exc)
        # Clamp to valid range rather than failing the whole run
        scores = RawScores(
            O=max(0, min(3, scores.O)),
            A=max(0, min(3, scores.A)),
            F=max(0, min(3, scores.F)),
            C=max(0, min(3, scores.C)),
            R=max(0, min(3, scores.R)),
            V=max(0, min(3, scores.V)),
        )

    sub_clauses_raw = item.get("sub_clauses", [])
    sub_clauses = [_parse_raw_clause(s, index * 100 + i)
                   for i, s in enumerate(sub_clauses_raw)]

    return RawClause(
        clause_id=item.get("clause_id", f"c-{index:03d}"),
        source_section=item.get("source_section", "UNKNOWN"),
        source_file=item.get("source_file", "unknown"),
        original_text=item.get("original_text", ""),
        is_normative=bool(item.get("is_normative", True)),
        split=bool(item.get("split", False)),
        sub_clauses=sub_clauses,
        scores=scores,
        score_rationale=item.get("score_rationale", ""),
        clause_type=item.get("clause_type", "rule")  # 补充这一行
    )
