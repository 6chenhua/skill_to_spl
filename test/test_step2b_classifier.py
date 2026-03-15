"""
test_step2b_classifier.py
Unit tests for Step 2B — Clause Classifier (pure code, no LLM).

Classification logic (from data_models.py):
    S_det = min(O, F, V)
    S_proc = min(A, V)

    HARD   : S_det >= 3 AND A >= 2 AND C <= 2
    MEDIUM : (S_det == 2 AND A >= 2) OR (S_det >= 3 AND C == 3)
    SOFT   : S_det <= 1 AND A >= 1
    NON    : A == 0

    risk_override  : SOFT → MEDIUM when R == 3
    downgraded     : HARD → MEDIUM when required effects not in capability_profile

    confidence = (S_det/3 * 0.6 + A/3 * 0.4) - C/9   (clamped 0–1)
    needs_review   : risk_override OR (HARD and conf < 0.75) OR (MEDIUM and conf < 0.60)
"""

import pytest
from data_models import RawClause, RawScores, ClassifiedClause, Classification

# ---------------------------------------------------------------------------
# CapabilityProfile for mcp-builder
# (no local_scripts that run code, no effects requiring special permissions)
# ---------------------------------------------------------------------------

CAPABILITY_PROFILE = {
    "local_scripts": ["scripts/connections.py", "scripts/evaluation.py"],
    "referenced_libs": ["anthropic", "mcp"],
    "available_effects": ["NETWORK", "WRITE"],  # evaluation.py writes reports; WebFetch is NETWORK
}


# ---------------------------------------------------------------------------
# Raw clause fixtures (from Step 2A gold-standard output)
# ---------------------------------------------------------------------------

def _make_clause(clause_id, section, source, text, clause_type, O, A, F, C, R, V):
    return RawClause(
        clause_id=clause_id,
        source_section=section,
        source_file=source,
        original_text=text,
        is_normative=A > 0,
        clause_type=clause_type,
        split=False,
        sub_clauses=[],
        scores=RawScores(O=O, A=A, F=F, C=C, R=R, V=V),
        score_rationale="test",
    )


RAW_CLAUSES = [
    # c-001: DO NOT use deprecated APIs — S_det=min(3,3,3)=3, A=3, C=0 → HARD
    _make_clause("c-001", "CONSTRAINTS", "reference/node_mcp_server.md",
                 "DO NOT use: server.tool(), server.setRequestHandler()...",
                 "rule", O=3, A=3, F=3, C=0, R=2, V=3),

    # c-002: MUST prioritize composability — S_det=min(2,2,2)=2, A=2, C=2 → MEDIUM
    _make_clause("c-002", "CONSTRAINTS", "reference/node_mcp_server.md",
                 "Your implementation MUST prioritize composability and code reuse",
                 "rule", O=2, A=2, F=2, C=2, R=1, V=2),

    # c-003: NEVER copy-paste — S_det=min(2,3,2)=2, A=3, C=0 → MEDIUM
    _make_clause("c-003", "CONSTRAINTS", "reference/node_mcp_server.md",
                 "NEVER copy-paste similar code between tools",
                 "rule", O=2, A=3, F=3, C=0, R=1, V=2),

    # c-004: API keys in env vars — S_det=min(3,3,3)=3, A=3, C=0, R=3 → HARD (no risk_override needed)
    _make_clause("c-004", "CONSTRAINTS", "reference/mcp_best_practices.md",
                 "Store API keys in environment variables, never in code",
                 "rule", O=3, A=3, F=3, C=0, R=3, V=3),

    # c-005: Sanitize file paths — S_det=min(2,3,2)=2, A=3, C=0 → MEDIUM
    _make_clause("c-005", "CONSTRAINTS", "reference/mcp_best_practices.md",
                 "Sanitize file paths to prevent directory traversal",
                 "rule", O=2, A=3, F=3, C=0, R=3, V=2),

    # c-006: snake_case tool names — S_det=min(3,3,3)=3, A=3, C=0 → HARD
    _make_clause("c-006", "CONSTRAINTS", "reference/mcp_best_practices.md",
                 "Use snake_case with service prefix for tool names",
                 "rule", O=3, A=3, F=3, C=0, R=1, V=3),

    # c-007: respect limit param — S_det=min(3,3,3)=3, A=3, C=0 → HARD
    _make_clause("c-007", "CONSTRAINTS", "reference/mcp_best_practices.md",
                 "Always respect the `limit` parameter",
                 "rule", O=3, A=3, F=3, C=0, R=2, V=3),

    # c-008: eval questions independent — S_det=min(2,2,2)=2, A=2, C=1 → MEDIUM
    _make_clause("c-008", "CONSTRAINTS", "reference/evaluation.md",
                 "Questions MUST be independent",
                 "rule", O=2, A=2, F=2, C=1, R=1, V=2),

    # c-009: eval non-destructive — S_det=min(2,2,2)=2, A=2, C=1 → MEDIUM
    _make_clause("c-009", "CONSTRAINTS", "reference/evaluation.md",
                 "Questions MUST require ONLY NON-DESTRUCTIVE AND IDEMPOTENT tool use",
                 "rule", O=2, A=2, F=2, C=1, R=1, V=2),

    # c-010: npm run build — S_det=min(3,3,3)=3, A=3, C=0 → HARD (step)
    _make_clause("c-010", "WORKFLOW", "reference/node_mcp_server.md",
                 "Always ensure `npm run build` completes successfully",
                 "step", O=3, A=3, F=3, C=0, R=2, V=3),

    # c-011: API coverage advisory — A=1, S_det=min(1,1,0)=0 → NON (V=0 → S_det=0)
    _make_clause("c-011", "NOTES", "SKILL.md",
                 "When uncertain, prioritize comprehensive API coverage",
                 "rule", O=1, A=1, F=1, C=3, R=0, V=0),
]


# ---------------------------------------------------------------------------
# Expected classifications
# ---------------------------------------------------------------------------

EXPECTED = {
    "c-001": {"classification": Classification.HARD,   "risk_override": False, "downgraded": False},
    "c-002": {"classification": Classification.MEDIUM, "risk_override": False, "downgraded": False},
    "c-003": {"classification": Classification.MEDIUM, "risk_override": False, "downgraded": False},
    "c-004": {"classification": Classification.HARD,   "risk_override": False, "downgraded": False},
    "c-005": {"classification": Classification.MEDIUM, "risk_override": False, "downgraded": False},
    "c-006": {"classification": Classification.HARD,   "risk_override": False, "downgraded": False},
    "c-007": {"classification": Classification.HARD,   "risk_override": False, "downgraded": False},
    "c-008": {"classification": Classification.MEDIUM, "risk_override": False, "downgraded": False},
    "c-009": {"classification": Classification.MEDIUM, "risk_override": False, "downgraded": False},
    "c-010": {"classification": Classification.HARD,   "risk_override": False, "downgraded": False},
    "c-011": {"classification": Classification.NON,    "risk_override": False, "downgraded": False},
}


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def classified(request):
    from step2b_classifier import classify_clauses
    return {c.clause_id: c for c in classify_clauses(RAW_CLAUSES, CAPABILITY_PROFILE)}


# ---------------------------------------------------------------------------
# Tests: S_det / S_proc calculations
# ---------------------------------------------------------------------------

class TestStep2BDerivedScores:

    def test_c001_s_det(self, classified):
        c = classified["c-001"]
        assert c.S_det == 3   # min(O=3, F=3, V=3)

    def test_c002_s_det(self, classified):
        c = classified["c-002"]
        assert c.S_det == 2   # min(O=2, F=2, V=2)

    def test_c011_s_det_zero(self, classified):
        c = classified["c-011"]
        assert c.S_det == 0   # min(O=1, F=1, V=0) = 0

    def test_c004_s_proc(self, classified):
        c = classified["c-004"]
        assert c.S_proc == 3  # min(A=3, V=3)


# ---------------------------------------------------------------------------
# Tests: classification results
# ---------------------------------------------------------------------------

class TestStep2BClassification:

    @pytest.mark.parametrize("clause_id", EXPECTED.keys())
    def test_classification(self, classified, clause_id):
        result = classified[clause_id]
        expected_cls = EXPECTED[clause_id]["classification"]
        assert result.classification == expected_cls, (
            f"{clause_id}: expected {expected_cls.value}, got {result.classification.value}"
        )

    def test_deprecated_api_is_hard(self, classified):
        assert classified["c-001"].classification == Classification.HARD

    def test_api_key_storage_is_hard(self, classified):
        assert classified["c-004"].classification == Classification.HARD

    def test_snake_case_is_hard(self, classified):
        assert classified["c-006"].classification == Classification.HARD

    def test_limit_param_is_hard(self, classified):
        assert classified["c-007"].classification == Classification.HARD

    def test_composability_is_medium(self, classified):
        assert classified["c-002"].classification == Classification.MEDIUM

    def test_copy_paste_is_medium(self, classified):
        assert classified["c-003"].classification == Classification.MEDIUM

    def test_eval_independence_is_medium(self, classified):
        assert classified["c-008"].classification == Classification.MEDIUM

    def test_npm_build_step_is_hard(self, classified):
        assert classified["c-010"].classification == Classification.HARD

    def test_api_coverage_advisory_is_non(self, classified):
        assert classified["c-011"].classification == Classification.NON


# ---------------------------------------------------------------------------
# Tests: risk_override and downgrade
# ---------------------------------------------------------------------------

class TestStep2BOverrides:

    def test_no_spurious_risk_overrides(self, classified):
        """R=3 on c-004 and c-005 but they are already HARD/MEDIUM — no override needed."""
        for clause_id in ["c-004", "c-005"]:
            c = classified[clause_id]
            # risk_override only applies if original classification would be SOFT
            assert c.risk_override is False or c.classification != Classification.SOFT

    def test_no_spurious_downgrades(self, classified):
        """None of the HARD clauses require EXEC effects not in the capability profile."""
        for clause_id, c in classified.items():
            assert c.downgraded is False, (
                f"{clause_id} was unexpectedly downgraded"
            )


# ---------------------------------------------------------------------------
# Tests: confidence and needs_review
# ---------------------------------------------------------------------------

class TestStep2BConfidence:

    def test_hard_clauses_have_high_confidence(self, classified):
        for clause_id in ["c-001", "c-004", "c-006", "c-007", "c-010"]:
            c = classified[clause_id]
            assert c.confidence >= 0.70, (
                f"{clause_id} (HARD) confidence too low: {c.confidence:.2f}"
            )

    def test_non_clause_has_low_confidence(self, classified):
        c = classified["c-011"]
        assert c.confidence < 0.40, (
            f"c-011 (NON) confidence too high: {c.confidence:.2f}"
        )

    def test_hard_high_confidence_no_review(self, classified):
        """HARD clauses with conf >= 0.75 should not need review."""
        for clause_id in ["c-001", "c-006", "c-007", "c-010"]:
            c = classified[clause_id]
            if c.confidence >= 0.75:
                assert c.needs_review is False, (
                    f"{clause_id}: confidence={c.confidence:.2f} but needs_review=True"
                )


# ---------------------------------------------------------------------------
# Tests: enforcement_backends
# ---------------------------------------------------------------------------

class TestStep2BEnforcementBackends:

    def test_deprecated_api_has_static_analysis_backend(self, classified):
        backends = set(classified["c-001"].enforcement_backends)
        assert "static_analysis" in backends or "ast_scan" in backends

    def test_non_clause_has_no_enforcement_backends(self, classified):
        assert classified["c-011"].enforcement_backends == []


# ---------------------------------------------------------------------------
# Edge-case: risk_override (SOFT → MEDIUM when R == 3)
# ---------------------------------------------------------------------------

class TestStep2BRiskOverride:

    def test_soft_clause_with_r3_gets_risk_override(self):
        """A SOFT clause (S_det=1) with R=3 must be promoted to MEDIUM."""
        from step2b_classifier import classify_clauses
        risky_soft = [
            _make_clause("c-risk", "CONSTRAINTS", "SKILL.md",
                         "Test risky soft clause",
                         "rule", O=1, A=2, F=1, C=1, R=3, V=1)
        ]
        results = {c.clause_id: c for c in classify_clauses(risky_soft, CAPABILITY_PROFILE)}
        c = results["c-risk"]
        assert c.classification == Classification.MEDIUM
        assert c.risk_override is True

    def test_soft_clause_with_r2_stays_soft(self):
        """R=2 does not trigger risk_override."""
        from step2b_classifier import classify_clauses
        soft_r2 = [
            _make_clause("c-soft", "CONSTRAINTS", "SKILL.md",
                         "Test soft low-risk clause",
                         "rule", O=1, A=2, F=1, C=1, R=2, V=1)
        ]
        results = {c.clause_id: c for c in classify_clauses(soft_r2, CAPABILITY_PROFILE)}
        c = results["c-soft"]
        assert c.classification == Classification.SOFT
        assert c.risk_override is False
