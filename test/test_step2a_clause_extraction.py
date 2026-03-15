"""
test_step2a_clause_extraction.py
Unit tests for Step 2A — Clause Extraction + Scoring (LLM step).

INPUT  → SectionBundle (7 sections, EXAMPLES excluded)
OUTPUT → list[RawClause] with 6-dim scores and clause_type

Gold-standard: 11 expected clauses derived from the real mcp-builder source files.
"""

import json
import os
import pytest

# ---------------------------------------------------------------------------
# Input: SectionBundle (Step 1 output) — using real content
# ---------------------------------------------------------------------------

SECTION_BUNDLE_TEXT = """\
[INTENT]
- Create MCP (Model Context Protocol) servers that enable LLMs to interact with external services through well-designed tools. [source: SKILL.md]
- The quality of an MCP server is measured by how well it enables LLMs to accomplish real-world tasks. [source: SKILL.md]

[WORKFLOW]
- Creating a high-quality MCP server involves four main phases: Phase 1: Deep Research and Planning, Phase 2: Implementation, Phase 3: Review and Test, Phase 4: Create Evaluations. [source: SKILL.md]
- Load framework documentation before implementation: MCP Best Practices, TypeScript Guide, Python Guide, Evaluation Guide. [source: SKILL.md]
- Always ensure `npm run build` completes successfully before considering the implementation complete. [source: reference/node_mcp_server.md]
- Create 10 human-readable questions requiring ONLY READ-ONLY, INDEPENDENT, NON-DESTRUCTIVE, and IDEMPOTENT operations to answer. [source: reference/evaluation.md]
- Follow the process: Tool Inspection → Content Exploration → Question Generation → Answer Verification. [source: reference/evaluation.md]
- Use Zod (TypeScript) or Pydantic (Python) for input schema validation. [source: SKILL.md]

[CONSTRAINTS]
- DO NOT use: Old deprecated APIs such as `server.tool()`, `server.setRequestHandler(ListToolsRequestSchema, ...)`, or manual handler registration [source: reference/node_mcp_server.md]
- Your implementation MUST prioritize composability and code reuse: extract common functionality, build shared API clients, centralize error handling logic. [source: reference/node_mcp_server.md]
- NEVER copy-paste similar code between tools [source: reference/node_mcp_server.md]
- Store API keys in environment variables, never in code [source: reference/mcp_best_practices.md]
- Sanitize file paths to prevent directory traversal [source: reference/mcp_best_practices.md]
- Use snake_case with service prefix for tool names: format `{service}_{action}_{resource}` [source: reference/mcp_best_practices.md]
- Always respect the `limit` parameter [source: reference/mcp_best_practices.md]
- Questions MUST be independent — each should NOT depend on the answer to any other question [source: reference/evaluation.md]
- Questions MUST require ONLY NON-DESTRUCTIVE AND IDEMPOTENT tool use [source: reference/evaluation.md]
- Questions must not be solvable with straightforward keyword search [source: reference/evaluation.md]
- DO NOT let the MCP server restrict the kinds of questions you create [source: reference/evaluation.md]

[TOOLS]
- McpServer.registerTool() with Zod inputSchema and outputSchema [source: reference/node_mcp_server.md]
- FastMCP @mcp.tool decorator with Pydantic models [source: reference/python_mcp_server.md]
- WebFetch to load TypeScript SDK README [source: SKILL.md]
- WebFetch to load Python SDK README [source: SKILL.md]

[ARTIFACTS]
- {service}-mcp-server/ project directory with src/index.ts, package.json, tsconfig.json, dist/ [source: reference/node_mcp_server.md]
- Evaluation XML file: <evaluation><qa_pair><question>...<answer>... (10 QA pairs) [source: reference/evaluation.md]

[EVIDENCE]
- npm run build completes without errors [source: reference/node_mcp_server.md]
- 10 QA pairs with verified answers covering realistic multi-tool-call scenarios [source: reference/evaluation.md]

[NOTES]
- TypeScript is the recommended language: high-quality SDK support, broad usage, static typing. [source: SKILL.md]
- Python (FastMCP) is acceptable for local servers or when the user prefers Python. [source: SKILL.md]
- Streamable HTTP for remote servers; stdio for local servers. [source: SKILL.md]
- When uncertain, prioritize comprehensive API coverage. [source: SKILL.md]
- Error messages should guide agents toward solutions with specific suggestions and next steps. [source: SKILL.md]
"""

# ---------------------------------------------------------------------------
# Gold-standard expected clauses
# ---------------------------------------------------------------------------

EXPECTED_CLAUSES = [
    {
        "clause_id": "c-001",
        "source_section": "CONSTRAINTS",
        "source_file": "reference/node_mcp_server.md",
        "original_text": "DO NOT use: Old deprecated APIs such as `server.tool()`, `server.setRequestHandler(ListToolsRequestSchema, ...)`, or manual handler registration",
        "is_normative": True,
        "clause_type": "rule",
        "scores": {"O": 3, "A": 3, "F": 3, "C": 0, "R": 2, "V": 3},
    },
    {
        "clause_id": "c-002",
        "source_section": "CONSTRAINTS",
        "source_file": "reference/node_mcp_server.md",
        "original_text": "Your implementation MUST prioritize composability and code reuse",
        "is_normative": True,
        "clause_type": "rule",
        "scores": {"O": 2, "A": 2, "F": 2, "C": 2, "R": 1, "V": 2},
    },
    {
        "clause_id": "c-003",
        "source_section": "CONSTRAINTS",
        "source_file": "reference/node_mcp_server.md",
        "original_text": "NEVER copy-paste similar code between tools",
        "is_normative": True,
        "clause_type": "rule",
        "scores": {"O": 2, "A": 3, "F": 3, "C": 0, "R": 1, "V": 2},
    },
    {
        "clause_id": "c-004",
        "source_section": "CONSTRAINTS",
        "source_file": "reference/mcp_best_practices.md",
        "original_text": "Store API keys in environment variables, never in code",
        "is_normative": True,
        "clause_type": "rule",
        "scores": {"O": 3, "A": 3, "F": 3, "C": 0, "R": 3, "V": 3},
    },
    {
        "clause_id": "c-005",
        "source_section": "CONSTRAINTS",
        "source_file": "reference/mcp_best_practices.md",
        "original_text": "Sanitize file paths to prevent directory traversal",
        "is_normative": True,
        "clause_type": "rule",
        "scores": {"O": 2, "A": 3, "F": 3, "C": 0, "R": 3, "V": 2},
    },
    {
        "clause_id": "c-006",
        "source_section": "CONSTRAINTS",
        "source_file": "reference/mcp_best_practices.md",
        "original_text": "Use snake_case with service prefix for tool names: format `{service}_{action}_{resource}`",
        "is_normative": True,
        "clause_type": "rule",
        "scores": {"O": 3, "A": 3, "F": 3, "C": 0, "R": 1, "V": 3},
    },
    {
        "clause_id": "c-007",
        "source_section": "CONSTRAINTS",
        "source_file": "reference/mcp_best_practices.md",
        "original_text": "Always respect the `limit` parameter",
        "is_normative": True,
        "clause_type": "rule",
        "scores": {"O": 3, "A": 3, "F": 3, "C": 0, "R": 2, "V": 3},
    },
    {
        "clause_id": "c-008",
        "source_section": "CONSTRAINTS",
        "source_file": "reference/evaluation.md",
        "original_text": "Questions MUST be independent — each should NOT depend on the answer to any other question",
        "is_normative": True,
        "clause_type": "rule",
        "scores": {"O": 2, "A": 2, "F": 2, "C": 1, "R": 1, "V": 2},
    },
    {
        "clause_id": "c-009",
        "source_section": "CONSTRAINTS",
        "source_file": "reference/evaluation.md",
        "original_text": "Questions MUST require ONLY NON-DESTRUCTIVE AND IDEMPOTENT tool use",
        "is_normative": True,
        "clause_type": "rule",
        "scores": {"O": 2, "A": 2, "F": 2, "C": 1, "R": 1, "V": 2},
    },
    {
        "clause_id": "c-010",
        "source_section": "WORKFLOW",
        "source_file": "reference/node_mcp_server.md",
        "original_text": "Always ensure `npm run build` completes successfully before considering the implementation complete",
        "is_normative": True,
        "clause_type": "step",
        "scores": {"O": 3, "A": 3, "F": 3, "C": 0, "R": 2, "V": 3},
    },
    {
        "clause_id": "c-011",
        "source_section": "NOTES",
        "source_file": "SKILL.md",
        "original_text": "When uncertain, prioritize comprehensive API coverage",
        "is_normative": False,
        "clause_type": "rule",
        "scores": {"O": 1, "A": 1, "F": 1, "C": 3, "R": 0, "V": 0},
    },
]

VALID_CLAUSE_TYPES = {"rule", "step"}
SCORE_DIMS = {"O", "A", "F", "C", "R", "V"}


# ---------------------------------------------------------------------------
# Schema validator
# ---------------------------------------------------------------------------

def validate_raw_clauses(clauses: list[dict]) -> list[str]:
    errors = []
    ids_seen = set()
    for i, clause in enumerate(clauses):
        ref = f"clause[{i}]"
        for field in ["clause_id", "source_section", "source_file", "original_text",
                      "is_normative", "clause_type", "scores", "score_rationale"]:
            if field not in clause:
                errors.append(f"{ref}: missing '{field}'")

        if clause.get("clause_id") in ids_seen:
            errors.append(f"{ref}: duplicate clause_id '{clause['clause_id']}'")
        ids_seen.add(clause.get("clause_id"))

        if clause.get("clause_type") not in VALID_CLAUSE_TYPES:
            errors.append(f"{ref}: invalid clause_type '{clause.get('clause_type')}'")

        scores = clause.get("scores", {})
        for dim in SCORE_DIMS:
            if dim not in scores:
                errors.append(f"{ref}: missing score dimension '{dim}'")
            elif not (0 <= scores[dim] <= 3):
                errors.append(f"{ref}: score {dim}={scores[dim]} out of range [0,3]")

        if not clause.get("score_rationale", "").strip():
            errors.append(f"{ref}: score_rationale is empty")

    return errors


# ---------------------------------------------------------------------------
# INPUT tests
# ---------------------------------------------------------------------------

class TestStep2AInput:

    def test_system_prompt_not_empty(self):
        from templates import STEP2A_SYSTEM
        assert len(STEP2A_SYSTEM) > 100

    def test_examples_section_absent_from_input(self):
        """Step 2A must NOT receive the EXAMPLES section."""
        assert "[EXAMPLES]" not in SECTION_BUNDLE_TEXT

    def test_rendered_user_contains_constraints_section(self):
        from templates import render_step2a_user
        rendered = render_step2a_user(section_bundle_text=SECTION_BUNDLE_TEXT)
        assert "[CONSTRAINTS]" in rendered

    def test_rendered_user_contains_normative_triggers(self):
        from templates import render_step2a_user
        rendered = render_step2a_user(section_bundle_text=SECTION_BUNDLE_TEXT)
        assert "DO NOT use" in rendered
        assert "NEVER copy-paste" in rendered
        assert "environment variables, never in code" in rendered

    def test_system_prompt_defines_all_six_score_dims(self):
        from templates import STEP2A_SYSTEM
        for dim in ["O", "A", "F", "C", "R", "V"]:
            assert dim in STEP2A_SYSTEM, f"Score dimension {dim} missing from STEP2A_SYSTEM"

    def test_system_prompt_defines_clause_types(self):
        from templates import STEP2A_SYSTEM
        assert "rule" in STEP2A_SYSTEM
        assert "step" in STEP2A_SYSTEM


# ---------------------------------------------------------------------------
# OUTPUT tests (gold-standard validation, no LLM)
# ---------------------------------------------------------------------------

class TestStep2AExpectedOutput:

    def test_sample_passes_schema(self):
        sample = [{**c, "score_rationale": "test"} for c in EXPECTED_CLAUSES]
        errors = validate_raw_clauses(sample)
        assert errors == [], f"Gold-standard has schema errors: {errors}"

    def test_deprecated_api_rule_present(self):
        texts = [c["original_text"] for c in EXPECTED_CLAUSES]
        assert any("DO NOT use" in t for t in texts)

    def test_deprecated_api_rule_has_high_scores(self):
        c = next(c for c in EXPECTED_CLAUSES if "DO NOT use" in c["original_text"])
        assert c["scores"]["O"] == 3
        assert c["scores"]["F"] == 3
        assert c["scores"]["V"] == 3

    def test_env_var_rule_has_high_risk_score(self):
        c = next(c for c in EXPECTED_CLAUSES if "environment variables" in c["original_text"])
        assert c["scores"]["R"] == 3, "API key exposure is high-risk"

    def test_api_coverage_advisory_has_low_scores(self):
        c = next(c for c in EXPECTED_CLAUSES if "comprehensive API coverage" in c["original_text"])
        assert c["scores"]["O"] <= 1
        assert c["scores"]["V"] == 0
        assert c["is_normative"] is False

    def test_npm_build_is_step_type(self):
        c = next(c for c in EXPECTED_CLAUSES if "npm run build" in c["original_text"])
        assert c["clause_type"] == "step"

    def test_all_constraint_section_items_are_normative_or_advisory(self):
        for c in EXPECTED_CLAUSES:
            if c["source_section"] == "NOTES":
                # NOTES items can be non-normative
                pass
            elif c["source_section"] == "CONSTRAINTS":
                # All CONSTRAINTS items should be normative
                assert c["is_normative"] is True, (
                    f"CONSTRAINTS item should be normative: {c['original_text']}"
                )

    def test_no_duplicate_clause_ids(self):
        ids = [c["clause_id"] for c in EXPECTED_CLAUSES]
        assert len(ids) == len(set(ids))

    def test_clause_types_are_valid(self):
        for c in EXPECTED_CLAUSES:
            assert c["clause_type"] in VALID_CLAUSE_TYPES

    def test_scores_in_range(self):
        for c in EXPECTED_CLAUSES:
            for dim, val in c["scores"].items():
                assert 0 <= val <= 3, (
                    f"Score {dim}={val} out of range in clause {c['clause_id']}"
                )


# ---------------------------------------------------------------------------
# LIVE LLM tests
# ---------------------------------------------------------------------------

@pytest.mark.live_llm
class TestStep2ALiveLLM:

    def _call(self, llm_client):
        from templates import STEP2A_SYSTEM, render_step2a_user
        user = render_step2a_user(section_bundle_text=SECTION_BUNDLE_TEXT)
        raw = llm_client.call(system=STEP2A_SYSTEM, user=user)
        return json.loads(raw)

    def test_schema_valid(self, llm_client):
        clauses = self._call(llm_client)
        errors = validate_raw_clauses(clauses)
        assert errors == [], f"Schema errors: {errors}"

    def test_deprecated_api_clause_extracted(self, llm_client):
        clauses = self._call(llm_client)
        texts = [c["original_text"] for c in clauses]
        assert any("DO NOT use" in t or "server.tool()" in t for t in texts)

    def test_env_var_clause_extracted(self, llm_client):
        clauses = self._call(llm_client)
        texts = [c["original_text"] for c in clauses]
        assert any("environment variables" in t for t in texts)

    def test_api_advisory_has_low_observability(self, llm_client):
        clauses = self._call(llm_client)
        advisory = [c for c in clauses if "comprehensive API coverage" in c["original_text"]]
        if advisory:
            assert advisory[0]["scores"]["O"] <= 1

    def test_npm_build_classified_as_step(self, llm_client):
        clauses = self._call(llm_client)
        npm = [c for c in clauses if "npm run build" in c["original_text"]]
        if npm:
            assert npm[0]["clause_type"] == "step"

    def test_minimum_clause_count(self, llm_client):
        clauses = self._call(llm_client)
        assert len(clauses) >= 8, f"Only {len(clauses)} clauses extracted; expected ≥8"
