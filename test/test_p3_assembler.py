"""
test_p3_assembler.py
Unit tests for P3 — Skill Package Assembler (pure code, no LLM).

P3 merges priority-1 files into merged_doc_text, with SKILL.md always first,
and collects omit_files (priority-3 data/image/audio files for S4C).
"""

import pytest
import shutil
from conftest import FIXTURES_DIR

# ---------------------------------------------------------------------------
# Input: FileRoleMap from P2
# ---------------------------------------------------------------------------

FILE_ROLE_MAP = {
    "reference/mcp_best_practices.md":  {"role": "core_workflow",  "read_priority": 1, "must_read_for_normalization": True},
    "reference/node_mcp_server.md":     {"role": "core_workflow",  "read_priority": 1, "must_read_for_normalization": True},
    "reference/python_mcp_server.md":   {"role": "core_workflow",  "read_priority": 1, "must_read_for_normalization": True},
    "reference/evaluation.md":          {"role": "core_workflow",  "read_priority": 1, "must_read_for_normalization": True},
    # LICENSE.txt is excluded at P1 — no entry here
    "scripts/connections.py":           {"role": "support_script", "read_priority": 2, "must_read_for_normalization": False},
    "scripts/evaluation.py":            {"role": "support_script", "read_priority": 2, "must_read_for_normalization": False},
    "scripts/example_evaluation.xml":   {"role": "examples_only",  "read_priority": 3, "must_read_for_normalization": False},
    "scripts/requirements.txt":         {"role": "data_asset",     "read_priority": 3, "must_read_for_normalization": False},
}

PRIORITY_1_FILES = [
    "SKILL.md",
    "reference/mcp_best_practices.md",
    "reference/node_mcp_server.md",
    "reference/python_mcp_server.md",
    "reference/evaluation.md",
]

# omit_files: priority=3 AND kind ∈ {data, image, audio}
# - scripts/example_evaluation.xml → kind=data ✓
# - scripts/requirements.txt       → kind=data ✓
# LICENSE.txt is excluded at P1, so no need to consider it here
EXPECTED_OMIT_PATHS = {"scripts/example_evaluation.xml", "scripts/requirements.txt"}


# ---------------------------------------------------------------------------
# Fixture: build real SkillPackage
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def package(tmp_path_factory):
    skill_root = tmp_path_factory.mktemp("skill") / "mcp-builder"
    shutil.copytree(str(FIXTURES_DIR), str(skill_root))

    from pre_processing.p1_reference_graph import build_reference_graph
    from pre_processing.p3_assembler import assemble_skill_package

    graph = build_reference_graph(skill_root=str(skill_root))
    return assemble_skill_package(
        graph=graph,
        file_role_map=FILE_ROLE_MAP,
    )


# ---------------------------------------------------------------------------
# Tests: identity
# ---------------------------------------------------------------------------

class TestP3Identity:

    def test_skill_id(self, package):
        assert package.skill_id == "mcp-builder"

    def test_frontmatter_name(self, package):
        assert package.frontmatter.get("name") == "mcp-builder"

    def test_file_role_map_preserved(self, package):
        for path in FILE_ROLE_MAP:
            assert path in package.file_role_map


# ---------------------------------------------------------------------------
# Tests: merged_doc_text content
# ---------------------------------------------------------------------------

class TestP3MergedDocText:

    def test_skill_md_content_present(self, package):
        assert "MCP Server Development Guide" in package.merged_doc_text

    def test_skill_md_first(self, package):
        """SKILL.md must appear before any reference file content."""
        skill_pos = package.merged_doc_text.find("MCP Server Development Guide")
        ref_pos   = package.merged_doc_text.find("MCP Server Best Practices")
        assert skill_pos < ref_pos, "SKILL.md content must precede reference docs"

    def test_all_priority1_files_included(self, package):
        snippets = {
            "reference/mcp_best_practices.md":  "MCP Server Best Practices",
            "reference/node_mcp_server.md":     "Node/TypeScript MCP Server Implementation Guide",
            "reference/python_mcp_server.md":   "Python MCP Server Implementation Guide",
            "reference/evaluation.md":          "MCP Server Evaluation Guide",
        }
        for path, snippet in snippets.items():
            assert snippet in package.merged_doc_text, (
                f"Priority-1 file content missing: {path} (expected '{snippet}')"
            )

    def test_boundary_markers_present(self, package):
        """Each included file must have a boundary marker so Step 1 can attribute sources."""
        for path in PRIORITY_1_FILES:
            assert path in package.merged_doc_text, (
                f"Boundary marker for '{path}' missing from merged_doc_text"
            )

    def test_license_excluded(self, package):
        assert "Apache License" not in package.merged_doc_text, (
            "LICENSE.txt (priority 3, doc) must not be in merged_doc_text"
        )

    def test_scripts_excluded(self, package):
        assert "AsyncExitStack" not in package.merged_doc_text, (
            "connections.py (priority 2, script) must not be in merged_doc_text"
        )
        assert "EVALUATION_PROMPT" not in package.merged_doc_text, (
            "evaluation.py (priority 2, script) must not be in merged_doc_text"
        )

    def test_xml_fixture_excluded(self, package):
        assert "compound interest" not in package.merged_doc_text, (
            "example_evaluation.xml (priority 3, data) must not be in merged_doc_text"
        )


# ---------------------------------------------------------------------------
# Tests: omit_files
# ---------------------------------------------------------------------------

class TestP3OmitFiles:

    def test_omit_files_are_correct(self, package):
        omit_paths = {
            (f["path"] if isinstance(f, dict) else f.path)
            for f in package.omit_files
        }
        assert omit_paths == EXPECTED_OMIT_PATHS, (
            f"Expected omit_files={EXPECTED_OMIT_PATHS}, got {omit_paths}"
        )

    def test_license_txt_not_in_graph_or_omit_files(self, package):
        """LICENSE.txt is excluded at P1 — should not exist in graph or omit_files."""
        # First verify it's not in the graph nodes
        assert "LICENSE.txt" not in package.file_role_map, \
            "LICENSE.txt should be excluded from file_role_map (filtered by P1)"
        # Then verify it's not in omit_files
        omit_paths = {
            (f["path"] if isinstance(f, dict) else f.path)
            for f in package.omit_files
        }
        assert "LICENSE.txt" not in omit_paths, \
            "LICENSE.txt should not be in omit_files"

    def test_reference_docs_not_in_omit_files(self, package):
        omit_paths = {
            (f["path"] if isinstance(f, dict) else f.path)
            for f in package.omit_files
        }
        for path in ["reference/evaluation.md", "reference/node_mcp_server.md"]:
            assert path not in omit_paths
