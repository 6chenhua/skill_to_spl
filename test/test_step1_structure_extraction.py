"""
test_step1_structure_extraction.py
Unit tests for Step 1 — Structure Extraction (LLM step).

INPUT  → merged_doc_text (P3 output)
OUTPUT → SectionBundle with 8 sections: INTENT WORKFLOW CONSTRAINTS TOOLS
         ARTIFACTS EVIDENCE EXAMPLES NOTES

Every normative/instructional sentence from the source files must land
in exactly one section. Nothing may be silently dropped.
"""

import json
import os
import pytest
from conftest import read_fixture

# ---------------------------------------------------------------------------
# Input: merged_doc_text (real content from fixture files, abbreviated
# for test clarity — full content is in FIXTURES_DIR)
# ---------------------------------------------------------------------------

# Build the real merged doc text from actual fixtures
def _build_merged_doc() -> str:
    parts = []
    files_in_order = [
        ("SKILL.md",                        "primary",       1),
        ("reference/mcp_best_practices.md", "core_workflow", 1),
        ("reference/node_mcp_server.md",    "core_workflow", 1),
        ("reference/python_mcp_server.md",  "core_workflow", 1),
        ("reference/evaluation.md",         "core_workflow", 1),
    ]
    for rel_path, role, priority in files_in_order:
        content = read_fixture(rel_path)
        parts.append(
            f"=== FILE: {rel_path} (role: {role}, priority: {priority}) ===\n{content}"
        )
    return "\n\n".join(parts)


MERGED_DOC_TEXT = _build_merged_doc()

# ---------------------------------------------------------------------------
# Gold-standard expected SectionBundle (key items only)
# Each entry: (section_name, text_substring, source_file)
# ---------------------------------------------------------------------------

EXPECTED_ITEMS = [
    # INTENT
    ("INTENT", "Create MCP (Model Context Protocol) servers that enable LLMs to interact with external services through well-designed tools", "SKILL.md"),
    ("INTENT", "quality of an MCP server is measured by how well it enables LLMs to accomplish real-world tasks", "SKILL.md"),

    # WORKFLOW — key process steps
    ("WORKFLOW", "Phase 1", "SKILL.md"),
    ("WORKFLOW", "npm run build", "reference/node_mcp_server.md"),
    ("WORKFLOW", "10", "reference/evaluation.md"),   # 10 evaluation questions

    # CONSTRAINTS — must/never/do not statements
    ("CONSTRAINTS", "DO NOT use", "reference/node_mcp_server.md"),          # deprecated API prohibition
    ("CONSTRAINTS", "NEVER copy-paste", "reference/node_mcp_server.md"),    # code reuse rule
    ("CONSTRAINTS", "environment variables, never in code", "reference/mcp_best_practices.md"),  # API key storage
    ("CONSTRAINTS", "snake_case", "reference/mcp_best_practices.md"),       # tool naming
    ("CONSTRAINTS", "MUST be independent", "reference/evaluation.md"),      # evaluation rule
    ("CONSTRAINTS", "NON-DESTRUCTIVE", "reference/evaluation.md"),          # evaluation rule

    # TOOLS — frameworks and external resources
    ("TOOLS", "registerTool", "reference/node_mcp_server.md"),
    ("TOOLS", "FastMCP", "reference/python_mcp_server.md"),

    # ARTIFACTS — produced files/structures
    ("ARTIFACTS", "{service}-mcp-server", "reference/node_mcp_server.md"),  # project dir structure
    ("ARTIFACTS", "evaluation", "reference/evaluation.md"),                  # evaluation XML

    # EVIDENCE — verification/quality criteria
    ("EVIDENCE", "npm run build", "reference/node_mcp_server.md"),

    # EXAMPLES — concrete instances
    ("EXAMPLES", "qa_pair", "SKILL.md"),           # the XML QA pair example

    # NOTES — advisory/background
    ("NOTES", "TypeScript", "SKILL.md"),            # language recommendation
]

# Items that must NOT appear in the wrong section
MISPLACEMENT_CHECKS = [
    # "TypeScript is recommended" is advisory → must not be in CONSTRAINTS
    ("CONSTRAINTS", "TypeScript is the recommended language"),
    ("CONSTRAINTS", "TypeScript (recommended)"),
    # Pure annotation fields → not constraints
    ("CONSTRAINTS", "readOnlyHint"),
]

EIGHT_SECTIONS = ["INTENT", "WORKFLOW", "CONSTRAINTS", "TOOLS",
                  "ARTIFACTS", "EVIDENCE", "EXAMPLES", "NOTES"]

VALID_SOURCES = {
    "SKILL.md",
    "reference/mcp_best_practices.md",
    "reference/node_mcp_server.md",
    "reference/python_mcp_server.md",
    "reference/evaluation.md",
}


# ---------------------------------------------------------------------------
# Schema validator
# ---------------------------------------------------------------------------

def validate_section_bundle(output: dict) -> list[str]:
    errors = []
    for section in EIGHT_SECTIONS:
        if section not in output:
            errors.append(f"Missing section: {section}")
            continue
        for i, item in enumerate(output[section]):
            if not item.get("text", "").strip():
                errors.append(f"{section}[{i}]: text is empty")
            if item.get("source") not in VALID_SOURCES:
                errors.append(f"{section}[{i}]: invalid source '{item.get('source')}'")
            if "multi" not in item:
                errors.append(f"{section}[{i}]: missing 'multi' field")
    return errors


# ---------------------------------------------------------------------------
# INPUT tests (no LLM required)
# ---------------------------------------------------------------------------

class TestStep1Input:

    def test_merged_doc_contains_skill_md(self):
        assert "MCP Server Development Guide" in MERGED_DOC_TEXT

    def test_merged_doc_contains_node_mcp_server(self):
        assert "Node/TypeScript MCP Server Implementation Guide" in MERGED_DOC_TEXT

    def test_merged_doc_contains_deprecated_api_rule(self):
        assert "DO NOT use" in MERGED_DOC_TEXT
        assert "server.tool()" in MERGED_DOC_TEXT

    def test_merged_doc_contains_evaluation_guide(self):
        assert "MCP Server Evaluation Guide" in MERGED_DOC_TEXT

    def test_merged_doc_has_boundary_markers(self):
        for path in ["SKILL.md", "reference/mcp_best_practices.md",
                     "reference/node_mcp_server.md", "reference/evaluation.md"]:
            assert path in MERGED_DOC_TEXT, f"Boundary marker missing: {path}"

    def test_system_prompt_defines_eight_sections(self):
        from templates import STEP1_SYSTEM
        for section in EIGHT_SECTIONS:
            assert section in STEP1_SYSTEM, f"Section {section} missing from STEP1_SYSTEM"

    def test_system_prompt_has_verbatim_instruction(self):
        from templates import STEP1_SYSTEM
        # Step 1 must instruct the LLM to preserve exact wording
        assert any(kw in STEP1_SYSTEM for kw in ["verbatim", "VERBATIM", "exact", "word-for-word"])

    def test_rendered_user_prompt_contains_merged_doc(self):
        from templates import render_step1_user
        rendered = render_step1_user(merged_doc_text=MERGED_DOC_TEXT)
        assert "MCP Server Development Guide" in rendered
        assert "DO NOT use" in rendered


# ---------------------------------------------------------------------------
# OUTPUT tests (gold-standard expected items, no LLM)
# ---------------------------------------------------------------------------

# We define a compact expected bundle as a dict for schema testing
EXPECTED_BUNDLE_SAMPLE = {
    "INTENT": [
        {"text": "Create MCP (Model Context Protocol) servers that enable LLMs to interact with external services through well-designed tools.", "source": "SKILL.md", "multi": False},
        {"text": "The quality of an MCP server is measured by how well it enables LLMs to accomplish real-world tasks.", "source": "SKILL.md", "multi": False},
    ],
    "WORKFLOW": [
        {"text": "Creating a high-quality MCP server involves four main phases: Phase 1: Deep Research and Planning, Phase 2: Implementation, Phase 3: Review and Test, Phase 4: Create Evaluations.", "source": "SKILL.md", "multi": False},
        {"text": "Always ensure `npm run build` completes successfully before considering the implementation complete.", "source": "reference/node_mcp_server.md", "multi": False},
        {"text": "Create 10 human-readable questions requiring ONLY READ-ONLY, INDEPENDENT, NON-DESTRUCTIVE, and IDEMPOTENT operations to answer.", "source": "reference/evaluation.md", "multi": False},
    ],
    "CONSTRAINTS": [
        {"text": "DO NOT use: Old deprecated APIs such as `server.tool()`, `server.setRequestHandler(ListToolsRequestSchema, ...)`, or manual handler registration", "source": "reference/node_mcp_server.md", "multi": False},
        {"text": "Your implementation MUST prioritize composability and code reuse", "source": "reference/node_mcp_server.md", "multi": False},
        {"text": "NEVER copy-paste similar code between tools", "source": "reference/node_mcp_server.md", "multi": False},
        {"text": "Store API keys in environment variables, never in code", "source": "reference/mcp_best_practices.md", "multi": False},
        {"text": "Use snake_case with service prefix for tool names: `{service}_{action}_{resource}`", "source": "reference/mcp_best_practices.md", "multi": False},
        {"text": "Questions MUST be independent — each should NOT depend on the answer to any other question", "source": "reference/evaluation.md", "multi": False},
        {"text": "Questions MUST require ONLY NON-DESTRUCTIVE AND IDEMPOTENT tool use", "source": "reference/evaluation.md", "multi": False},
    ],
    "TOOLS": [
        {"text": "McpServer from @modelcontextprotocol/sdk/server/mcp.js, server.registerTool() for tool registration", "source": "reference/node_mcp_server.md", "multi": False},
        {"text": "FastMCP: mcp = FastMCP(\"service_mcp\"), @mcp.tool decorator for tool registration", "source": "reference/python_mcp_server.md", "multi": False},
        {"text": "WebFetch to load TypeScript SDK: https://raw.githubusercontent.com/modelcontextprotocol/typescript-sdk/main/README.md", "source": "SKILL.md", "multi": False},
        {"text": "WebFetch to load Python SDK: https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md", "source": "SKILL.md", "multi": False},
    ],
    "ARTIFACTS": [
        {"text": "{service}-mcp-server/ project directory with src/index.ts, package.json, tsconfig.json, dist/", "source": "reference/node_mcp_server.md", "multi": False},
        {"text": "Evaluation XML file with <evaluation><qa_pair><question>...<answer>... structure (10 QA pairs)", "source": "reference/evaluation.md", "multi": False},
    ],
    "EVIDENCE": [
        {"text": "npm run build completes without errors (TypeScript compilation check)", "source": "reference/node_mcp_server.md", "multi": False},
        {"text": "Evaluation QA pairs verified by solving each question manually before submitting", "source": "reference/evaluation.md", "multi": False},
    ],
    "EXAMPLES": [
        {"text": 'QA pair: <question>Find discussions about AI model launches with animal codenames. One model needed a specific safety designation... What number X was being determined for the model named after a spotted wild cat?</question><answer>3</answer>', "source": "SKILL.md", "multi": False},
        {"text": "server.registerTool('example_search_users', { title, description, inputSchema: UserSearchInputSchema, annotations }, async (params) => { ... })", "source": "reference/node_mcp_server.md", "multi": False},
    ],
    "NOTES": [
        {"text": "TypeScript is the recommended language: high-quality SDK support, broad usage, static typing, good AI code generation.", "source": "SKILL.md", "multi": False},
        {"text": "Python (FastMCP) is acceptable for local servers or when the user prefers Python.", "source": "SKILL.md", "multi": False},
        {"text": "Streamable HTTP for remote servers (stateless JSON). stdio for local servers.", "source": "SKILL.md", "multi": False},
    ],
}


class TestStep1ExpectedOutput:

    def test_sample_bundle_passes_schema(self):
        errors = validate_section_bundle(EXPECTED_BUNDLE_SAMPLE)
        assert errors == [], f"Gold-standard sample has errors: {errors}"

    def test_constraints_has_deprecated_api_rule(self):
        texts = [i["text"] for i in EXPECTED_BUNDLE_SAMPLE["CONSTRAINTS"]]
        assert any("DO NOT use" in t for t in texts)

    def test_constraints_has_no_copy_paste_rule(self):
        texts = [i["text"] for i in EXPECTED_BUNDLE_SAMPLE["CONSTRAINTS"]]
        assert any("NEVER copy-paste" in t for t in texts)

    def test_constraints_has_env_var_rule(self):
        texts = [i["text"] for i in EXPECTED_BUNDLE_SAMPLE["CONSTRAINTS"]]
        assert any("environment variables" in t for t in texts)

    def test_constraints_has_snake_case_rule(self):
        texts = [i["text"] for i in EXPECTED_BUNDLE_SAMPLE["CONSTRAINTS"]]
        assert any("snake_case" in t for t in texts)

    def test_constraints_has_evaluation_independence(self):
        texts = [i["text"] for i in EXPECTED_BUNDLE_SAMPLE["CONSTRAINTS"]]
        assert any("independent" in t.lower() for t in texts)

    def test_notes_has_typescript_recommendation(self):
        texts = [i["text"] for i in EXPECTED_BUNDLE_SAMPLE["NOTES"]]
        assert any("TypeScript" in t and ("recommended" in t or "preferred" in t) for t in texts)

    def test_typescript_recommendation_not_in_constraints(self):
        texts = [i["text"] for i in EXPECTED_BUNDLE_SAMPLE["CONSTRAINTS"]]
        assert not any("TypeScript is the recommended" in t for t in texts), (
            "Advisory language recommendation must be in NOTES, not CONSTRAINTS"
        )

    def test_deprecated_api_attributed_to_node_mcp_server(self):
        for item in EXPECTED_BUNDLE_SAMPLE["CONSTRAINTS"]:
            if "DO NOT use" in item["text"]:
                assert item["source"] == "reference/node_mcp_server.md"

    def test_env_var_rule_attributed_to_mcp_best_practices(self):
        for item in EXPECTED_BUNDLE_SAMPLE["CONSTRAINTS"]:
            if "environment variables" in item["text"]:
                assert item["source"] == "reference/mcp_best_practices.md"

    def test_evaluation_rules_attributed_to_evaluation_md(self):
        for item in EXPECTED_BUNDLE_SAMPLE["CONSTRAINTS"]:
            if "MUST be independent" in item["text"] or "NON-DESTRUCTIVE" in item["text"]:
                assert item["source"] == "reference/evaluation.md"

    def test_examples_section_has_qa_pair(self):
        texts = [i["text"] for i in EXPECTED_BUNDLE_SAMPLE["EXAMPLES"]]
        assert any("qa_pair" in t or "answer" in t.lower() for t in texts)

    def test_all_eight_sections_non_empty(self):
        for section in EIGHT_SECTIONS:
            assert len(EXPECTED_BUNDLE_SAMPLE.get(section, [])) > 0, (
                f"Section {section} is empty in gold-standard output"
            )


# ---------------------------------------------------------------------------
# LIVE LLM tests
# ---------------------------------------------------------------------------

@pytest.mark.live_llm
class TestStep1LiveLLM:

    def _call(self, llm_client):
        from templates import STEP1_SYSTEM, render_step1_user
        user = render_step1_user(merged_doc_text=MERGED_DOC_TEXT)
        raw = llm_client.call(system=STEP1_SYSTEM, user=user)
        return json.loads(raw)

    def test_schema_valid(self, llm_client):
        output = self._call(llm_client)
        errors = validate_section_bundle(output)
        assert errors == [], f"Live output schema errors: {errors}"

    def test_all_sections_present_and_non_empty(self, llm_client):
        output = self._call(llm_client)
        for section in EIGHT_SECTIONS:
            assert section in output
            assert len(output[section]) > 0, f"Section {section} is empty"

    def test_deprecated_api_rule_in_constraints(self, llm_client):
        output = self._call(llm_client)
        texts = [i["text"] for i in output.get("CONSTRAINTS", [])]
        assert any("DO NOT use" in t or "server.tool()" in t for t in texts), (
            "Deprecated API prohibition must appear in CONSTRAINTS"
        )

    def test_typescript_advisory_in_notes_not_constraints(self, llm_client):
        output = self._call(llm_client)
        constraint_texts = [i["text"] for i in output.get("CONSTRAINTS", [])]
        note_texts = [i["text"] for i in output.get("NOTES", [])]
        assert not any("TypeScript is the recommended" in t for t in constraint_texts)
        assert any("TypeScript" in t for t in note_texts)

    def test_nothing_dropped_minimum_item_count(self, llm_client):
        output = self._call(llm_client)
        total = sum(len(v) for v in output.values())
        assert total >= 30, f"Only {total} items total; likely content was dropped"
