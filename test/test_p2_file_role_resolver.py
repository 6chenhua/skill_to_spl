"""
test_p2_file_role_resolver.py
Unit tests for P2 — File Role Resolver (LLM step).

INPUT  → rendered P2 USER prompt
OUTPUT → FileRoleMap dict validated by schema + business rules

Gold-standard expected output is defined in EXPECTED_FILE_ROLES below.
Live LLM tests compare the actual model response against these expectations.
"""

import json
import os
import pytest

# ---------------------------------------------------------------------------
# Shared input: simulated P1 output for mcp-builder
# (constructed from real file metadata observed in the fixture files)
# ---------------------------------------------------------------------------

# Reference sentences extracted from SKILL.md that mention other files
# (±1 line context, as P2_USER template specifies)
SKILL_MD_REFERENCE_SENTENCES = """\
[context] Load framework documentation:
[ref]     - **MCP Best Practices**: [📋 View Best Practices](./reference/mcp_best_practices.md) - Core guidelines
[context] For TypeScript (recommended):

[context] For TypeScript (recommended):
[ref]     - [⚡ TypeScript Guide](./reference/node_mcp_server.md) - TypeScript patterns and examples
[context] For Python:

[context] For Python:
[ref]     - [🐍 Python Guide](./reference/python_mcp_server.md) - Python patterns and examples
[context] After implementing your MCP server, create comprehensive evaluations.

[context] After implementing your MCP server, create comprehensive evaluations.
[ref]     **Load [✅ Evaluation Guide](./reference/evaluation.md) for complete evaluation guidelines.**
[context] Use evaluations to test whether LLMs can effectively use your MCP server.

[context] See language-specific guides for project setup:
[ref]     - [⚡ TypeScript Guide](./reference/node_mcp_server.md) - Project structure, package.json, tsconfig.json
[ref]     - [🐍 Python Guide](./reference/python_mcp_server.md) - Module organization, dependencies
"""

NODES_SUMMARY = """\
reference/evaluation.md [doc, 8941 bytes]
  # MCP Server Evaluation Guide
  ## Overview
  This document provides guidance on creating comprehensive evaluations for MCP servers.

reference/mcp_best_practices.md [doc, 7823 bytes]
  # MCP Server Best Practices
  ## Quick Reference
  ### Server Naming

reference/node_mcp_server.md [doc, 24107 bytes]
  # Node/TypeScript MCP Server Implementation Guide
  ## Overview
  This document provides Node/TypeScript-specific best practices.

reference/python_mcp_server.md [doc, 18240 bytes]
  # Python MCP Server Implementation Guide
  ## Overview
  This document provides Python-specific best practices.

scripts/connections.py [script, 3284 bytes]
  \"\"\"Lightweight connection handling for MCP servers.\"\"\"
  from abc import ABC, abstractmethod
  from contextlib import AsyncExitStack

scripts/evaluation.py [script, 8105 bytes]
  \"\"\"MCP Server Evaluation Harness
  This script evaluates MCP servers by running test questions against them.

scripts/example_evaluation.xml [data, 621 bytes]
  <evaluation>
     <qa_pair>

scripts/requirements.txt [data, 38 bytes]
  anthropic>=0.39.0
  mcp>=1.1.0
"""

EDGES_JSON = json.dumps({
    "SKILL.md": [
        "reference/mcp_best_practices.md",
        "reference/node_mcp_server.md",
        "reference/python_mcp_server.md",
        "reference/evaluation.md",
    ],
    "scripts/evaluation.py": ["connections"],
}, indent=2)


# ---------------------------------------------------------------------------
# Gold-standard expected output
# ---------------------------------------------------------------------------

EXPECTED_FILE_ROLES = {
    "reference/mcp_best_practices.md": {
        "role": "core_workflow",
        "read_priority": 1,
        "must_read_for_normalization": True,
    },
    "reference/node_mcp_server.md": {
        "role": "core_workflow",
        "read_priority": 1,
        "must_read_for_normalization": True,
    },
    "reference/python_mcp_server.md": {
        "role": "core_workflow",
        "read_priority": 1,
        "must_read_for_normalization": True,
    },
    "reference/evaluation.md": {
        "role": "core_workflow",
        "read_priority": 1,
        "must_read_for_normalization": True,
    },
    "scripts/connections.py": {
        "role": "support_script",
        "read_priority": 2,
        "must_read_for_normalization": False,
    },
    "scripts/evaluation.py": {
        "role": "support_script",
        "read_priority": 2,
        "must_read_for_normalization": False,
    },
    "scripts/example_evaluation.xml": {
        "role": "examples_only",
        "read_priority": 3,
        "must_read_for_normalization": False,
    },
    "scripts/requirements.txt": {
        "role": "data_asset",
        "read_priority": 3,
        "must_read_for_normalization": False,
    },
}

# All non-SKILL.md files that must appear in P2 output
ALL_CLASSIFIED_PATHS = set(EXPECTED_FILE_ROLES.keys())

VALID_ROLES = {
    "core_workflow", "supplementary", "examples_only",
    "core_script", "support_script", "data_asset", "unreferenced",
}


# ---------------------------------------------------------------------------
# Schema validator (reused by both static and live tests)
# ---------------------------------------------------------------------------

def validate_file_role_map(output: dict) -> list[str]:
    """Return list of schema/rule errors; empty list means valid."""
    errors = []

    if "file_roles" not in output:
        return ["Top-level key 'file_roles' is missing"]

    roles = output["file_roles"]

    # SKILL.md must never appear — it is always "primary"
    if "SKILL.md" in roles:
        errors.append("SKILL.md must not appear in file_roles (it is always 'primary')")

    # Every non-SKILL file must have an entry
    for path in ALL_CLASSIFIED_PATHS:
        if path not in roles:
            errors.append(f"Missing entry for '{path}'")

    for path, entry in roles.items():
        if entry.get("role") not in VALID_ROLES:
            errors.append(f"{path}: invalid role '{entry.get('role')}'")
        if entry.get("read_priority") not in {1, 2, 3}:
            errors.append(f"{path}: read_priority must be 1/2/3, got {entry.get('read_priority')}")
        if not isinstance(entry.get("must_read_for_normalization"), bool):
            errors.append(f"{path}: must_read_for_normalization must be bool")
        if not entry.get("reasoning"):
            errors.append(f"{path}: 'reasoning' field is empty or missing")

    return errors


# ---------------------------------------------------------------------------
# INPUT tests (no LLM required)
# ---------------------------------------------------------------------------

class TestP2Input:

    def test_system_prompt_not_empty(self):
        from templates import P2_SYSTEM
        assert len(P2_SYSTEM) > 100

    def test_rendered_user_contains_all_files(self):
        from templates import render_p2_user
        rendered = render_p2_user(
            skill_md_references=SKILL_MD_REFERENCE_SENTENCES,
            nodes_summary=NODES_SUMMARY,
            edges_json=EDGES_JSON,
        )
        for path in ALL_CLASSIFIED_PATHS:
            assert path in rendered, f"File '{path}' missing from P2 USER prompt"

    def test_rendered_user_contains_reference_link_context(self):
        from templates import render_p2_user
        rendered = render_p2_user(
            skill_md_references=SKILL_MD_REFERENCE_SENTENCES,
            nodes_summary=NODES_SUMMARY,
            edges_json=EDGES_JSON,
        )
        assert "mcp_best_practices.md" in rendered
        assert "node_mcp_server.md" in rendered
        assert "evaluation.md" in rendered

    def test_rendered_user_excludes_skill_md_from_nodes(self):
        """SKILL.md is the root document — its role is always primary,
        so the nodes_summary must not re-list it as a file to classify."""
        # nodes_summary fixture does not include SKILL.md — verify that
        assert "SKILL.md [" not in NODES_SUMMARY

    def test_rendered_user_contains_edges(self):
        from templates import render_p2_user
        rendered = render_p2_user(
            skill_md_references=SKILL_MD_REFERENCE_SENTENCES,
            nodes_summary=NODES_SUMMARY,
            edges_json=EDGES_JSON,
        )
        assert "evaluation.py" in rendered
        assert "connections" in rendered


# ---------------------------------------------------------------------------
# OUTPUT tests against gold-standard expected output (no LLM required)
# ---------------------------------------------------------------------------

class TestP2ExpectedOutput:
    """Validate the gold-standard EXPECTED_FILE_ROLES against schema + rules."""

    def test_expected_output_passes_schema(self):
        output = {"file_roles": {
            k: {**v, "reasoning": "test reasoning"}
            for k, v in EXPECTED_FILE_ROLES.items()
        }}
        errors = validate_file_role_map(output)
        assert errors == [], f"Gold-standard output has schema errors: {errors}"

    def test_all_four_reference_docs_are_priority_1(self):
        for path in ["reference/mcp_best_practices.md", "reference/node_mcp_server.md",
                     "reference/python_mcp_server.md", "reference/evaluation.md"]:
            entry = EXPECTED_FILE_ROLES[path]
            assert entry["read_priority"] == 1, f"{path} must be priority 1"
            assert entry["must_read_for_normalization"] is True

    def test_license_txt_not_in_expected_roles(self):
        """LICENSE.txt is excluded at P1 — should not appear in expected roles."""
        assert "LICENSE.txt" not in EXPECTED_FILE_ROLES

    def test_scripts_are_not_priority_1(self):
        """Scripts are never directly required for normalization."""
        for path in ["scripts/connections.py", "scripts/evaluation.py",
                     "scripts/example_evaluation.xml", "scripts/requirements.txt"]:
            assert EXPECTED_FILE_ROLES[path]["read_priority"] >= 2, (
                f"{path} should not be priority 1"
            )
            assert EXPECTED_FILE_ROLES[path]["must_read_for_normalization"] is False

    def test_xml_is_examples_or_data(self):
        entry = EXPECTED_FILE_ROLES["scripts/example_evaluation.xml"]
        assert entry["role"] in {"examples_only", "data_asset"}


# ---------------------------------------------------------------------------
# LIVE LLM tests
# ---------------------------------------------------------------------------

@pytest.mark.live_llm
class TestP2LiveLLM:

    def _call(self, llm_client):
        from templates import P2_SYSTEM, render_p2_user
        user = render_p2_user(
            skill_md_references=SKILL_MD_REFERENCE_SENTENCES,
            nodes_summary=NODES_SUMMARY,
            edges_json=EDGES_JSON,
        )
        raw = llm_client.call(system=P2_SYSTEM, user=user)
        return json.loads(raw)

    def test_schema_valid(self, llm_client):
        output = self._call(llm_client)
        errors = validate_file_role_map(output)
        assert errors == [], f"Live output schema errors: {errors}"

    def test_reference_docs_are_priority_1(self, llm_client):
        output = self._call(llm_client)
        for path in ["reference/mcp_best_practices.md", "reference/node_mcp_server.md",
                     "reference/python_mcp_server.md", "reference/evaluation.md"]:
            entry = output["file_roles"].get(path, {})
            assert entry.get("read_priority") == 1, (
                f"LLM gave {path} priority {entry.get('read_priority')}, expected 1"
            )

    def test_license_txt_not_in_llm_output(self, llm_client):
        """LICENSE.txt should not appear in LLM output since P1 excludes it."""
        output = self._call(llm_client)
        assert "LICENSE.txt" not in output.get("file_roles", {}), \
            "LICENSE.txt should be excluded from output (filtered by P1)"

    def test_reasoning_fields_non_empty(self, llm_client):
        output = self._call(llm_client)
        for path, entry in output["file_roles"].items():
            assert entry.get("reasoning", "").strip(), (
                f"Empty reasoning for {path}"
            )
