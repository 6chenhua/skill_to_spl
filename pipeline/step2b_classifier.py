"""
Step 2B — Clause Classification (pure code, no LLM).

Implements the Rubric v1 decision table from the design document exactly.
All classification logic lives here; the LLM (Step 2A) only provides scores.

Decision table (from source doc):
    S_det  = min(O, F, V)   — deterministic checkability bottleneck
    S_proc = min(A, V)      — process executability

    HARD   : S_det >= 3 AND A >= 2 AND C <= 2
    MEDIUM : (S_det == 2 AND A >= 2) OR (S_det >= 3 AND C == 3)
    SOFT   : S_det <= 1 AND A >= 1
    NON    : A == 0  (catches everything else)
    Risk override: R == 3 → never purely SOFT → upgrade to MEDIUM
    Environment override: HARD clause requires unavailable capability → downgrade to MEDIUM
"""

from __future__ import annotations

from typing import Optional

from models.data_models import (
    Classification,
    ClassifiedClause,
    RawClause,
    RawScores,
)


# ─── Public entry point ──────────────────────────────────────────────────────

def classify_clause(
    raw: RawClause,
    capability_profile: Optional[dict] = None,
) -> ClassifiedClause:
    """
    Classify a single scored clause using the Rubric v1 decision table.

    Args:
        raw:                A scored clause from Step 2A.
        capability_profile: Optional environment model.
                            If provided, HARD clauses that require unavailable
                            effects are downgraded to MEDIUM.
                            Expected shape: {"available_effects": ["READ", "EXEC", ...]}

    Returns:
        ClassifiedClause with all derived fields populated.
    """
    s = raw.scores
    S_det  = min(s.O, s.F, s.V)
    S_proc = min(s.A, s.V)

    # Step 1: intrinsic classification (text-only rubric)
    classification = _classify_intrinsic(S_det, s.A, s.C)
    original_classification = classification

    # Step 2: environment correction (extrinsic rubric)
    if capability_profile is not None:
        classification = _apply_env_rubric(classification, s, capability_profile)

    # Track if HARD clause was downgraded to MEDIUM by capability profile
    downgraded = (original_classification == Classification.HARD and 
                  classification == Classification.MEDIUM)

    # Step 3: risk override — R==3 must never stay purely SOFT
    risk_override = False
    if s.R == 3 and classification == Classification.SOFT:
        classification = Classification.MEDIUM
        risk_override = True

    confidence    = _compute_confidence(S_det, s)
    needs_review  = _compute_needs_review(classification, confidence, risk_override)
    backends      = _recommend_backends(classification, s)

    return ClassifiedClause(
        clause_id=raw.clause_id,
        original_text=raw.original_text,
        source_section=raw.source_section,
        source_file=raw.source_file,
        scores=s,
        S_det=S_det,
        S_proc=S_proc,
        classification=classification,
        risk_override=risk_override,
        confidence=confidence,
        needs_review=needs_review,
        enforcement_backends=backends,
        score_rationale=raw.score_rationale,
        clause_type=raw.clause_type,  # Propagate from RawClause
        downgraded=downgraded,  # True when HARD clause downgraded to MEDIUM by capability profile
    )


def classify_all(
    raw_clauses: list[RawClause],
    capability_profile: Optional[dict] = None,
) -> list[ClassifiedClause]:
    """
    Classify a full list of raw clauses.

    Split clauses (raw.split == True) are flattened: the parent is replaced by
    its sub-clauses, each classified independently. This matches the design
    principle that sub-clauses may land in different enforcement tiers.
    """
    results: list[ClassifiedClause] = []
    for raw in raw_clauses:
        if not raw.is_normative:
            continue
        if raw.split and raw.sub_clauses:
            # Flatten: classify sub-clauses individually
            for sub in raw.sub_clauses:
                results.append(classify_clause(sub, capability_profile))
        else:
            results.append(classify_clause(raw, capability_profile))
    return results


# ─── Decision table ──────────────────────────────────────────────────────────

def _classify_intrinsic(S_det: int, A: int, C: int) -> Classification:
    """
    Intrinsic classification based solely on rubric scores (text-only rubric).
    Priority order matters — NON is checked first to avoid misclassification
    of zero-actionability clauses.
    """
    # NON_COMPILABLE: actionability is zero → cannot become a gate or step
    if A == 0:
        return Classification.NON

    # COMPILABLE_HARD: deterministically checkable, actionable, low context-dependence
    if S_det >= 3 and A >= 2 and C <= 2:
        return Classification.HARD

    # COMPILABLE_MEDIUM: partially checkable with review/evidence requirements
    if (S_det == 2 and A >= 2) or (S_det >= 3 and C == 3):
        return Classification.MEDIUM

    # COMPILABLE_SOFT: low checkability but meaningful as guidance
    if S_det <= 1 and A >= 1:
        return Classification.SOFT

    # Catch-all for the uncovered middle ground → MEDIUM (conservative choice)
    return Classification.MEDIUM


def _apply_env_rubric(
    base: Classification,
    scores: RawScores,
    capability_profile: dict,
) -> Classification:
    """
    Environment (extrinsic) correction.

    Design principle: "The same clause can be Hard in one environment and only
    Medium in another." If the runtime environment lacks the effects required
    by a HARD clause, downgrade it to MEDIUM.
    """
    if base != Classification.HARD:
        return base

    required   = _infer_required_effects(scores)
    available  = set(capability_profile.get("available_effects", []))
    if not all(e in available for e in required):
        return Classification.MEDIUM
    return base


def _infer_required_effects(scores: RawScores) -> list[str]:
    """
    Map score profile to the runtime effects a HARD clause requires.
    Used for the environment-rubric correction.
    """
    effects = []
    if scores.O == 3:
        effects.append("READ")       # deterministic observability needs sensor/read access
    if scores.A == 3:
        effects.append("EXEC")       # deterministic actionability needs execution capability
    if scores.V == 3:
        effects.append("LOGGING")    # deterministic verifiability needs log/audit access
    return effects


# ─── Derived metrics ─────────────────────────────────────────────────────────

def _compute_confidence(S_det: int, scores: RawScores) -> float:
    """
    Enforceability confidence in [0.0, 1.0].

    Formula: weighted average of deterministic checkability (S_det/3) and
    actionability (A/3), penalised by context-dependence.
    Context penalty grows with C to reflect that high context-dependence
    makes enforcement unreliable even when scores are high.
    """
    base      = S_det / 3.0
    a_factor  = scores.A / 3.0
    c_penalty = scores.C / 9.0
    raw = (base * 0.6 + a_factor * 0.4) - c_penalty
    return round(max(0.0, min(1.0, raw)), 2)


def _compute_needs_review(
    cls: Classification,
    confidence: float,
    risk_override: bool,
) -> bool:
    """
    Flag clauses that need human review before being used as hard enforcement gates.

    Triggers:
    - Low-confidence HARD clause (risk of fake enforcement)
    - Low-confidence MEDIUM clause (risk of wrong evidence requirement)
    - Any risk override (forced upgrade from SOFT deserves human inspection)
    """
    if risk_override:
        return True
    if cls == Classification.HARD and confidence < 0.75:
        return True
    if cls == Classification.MEDIUM and confidence < 0.60:
        return True
    return False


def _recommend_backends(cls: Classification, scores: RawScores) -> list[str]:
    """
    Recommend enforcement backends based on classification and score profile.
    These are recommendations only — final choice belongs to the deployer.
    """
    if cls == Classification.HARD:
        backends = []
        if scores.V == 3:
            backends.append("tool_validator")      # exit code / SUCCESS: token parsing
        if scores.F == 3:
            backends.append("schema_validation")   # JSON Schema / Zod / Pydantic
        backends.append("rego_deny")               # Policy engine (OPA)
        backends.append("workflow_gate")           # prerequisite enforcement
        return backends
    elif cls == Classification.MEDIUM:
        return ["require_review_gate", "evidence_requirement", "parameterized_check"]
    elif cls == Classification.SOFT:
        return ["rubric_scoring", "heuristic_linter", "llm_judge_warn"]
    else:  # NON_COMPILABLE
        return ["interaction_policy"]
