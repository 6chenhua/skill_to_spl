"""
test_p1_reference_graph.py
Unit tests for P1 — Reference Graph Builder (pure code, no LLM).

P1 walks the skill directory, builds FileNode objects, and detects
cross-file references by scanning file content for path mentions.

Expected output for mcp-builder:
  - 9 FileNode objects (4 reference docs, SKILL.md, 3 scripts files)
  - LICENSE.txt is excluded (legal boilerplate, not needed for normalization)
  - Edges: SKILL.md → 4 reference files; evaluation.py → connections
  - local_scripts: connections.py, evaluation.py
  - referenced_libs: anthropic, mcp  (from requirements.txt / imports)
"""

import pytest
from conftest import read_fixture

# ---------------------------------------------------------------------------
# Ground-truth: expected FileReferenceGraph for mcp-builder
# ---------------------------------------------------------------------------

EXPECTED_NODES = {
    "SKILL.md",
    "reference/evaluation.md",
    "reference/mcp_best_practices.md",
    "reference/node_mcp_server.md",
    "reference/python_mcp_server.md",
    "scripts/connections.py",
    "scripts/evaluation.py",
    "scripts/example_evaluation.xml",
    "scripts/requirements.txt",
}

EXPECTED_KINDS = {
    "SKILL.md":                         "doc",
    "reference/evaluation.md":          "doc",
    "reference/mcp_best_practices.md":  "doc",
    "reference/node_mcp_server.md":     "doc",
    "reference/python_mcp_server.md":   "doc",
    "scripts/connections.py":           "script",
    "scripts/evaluation.py":            "script",
    "scripts/example_evaluation.xml":   "data",
    "scripts/requirements.txt":         "data",
}

# SKILL.md references all 4 reference docs (by relative path in markdown links)
EXPECTED_SKILL_MD_REFS = {
    "reference/evaluation.md",
    "reference/mcp_best_practices.md",
    "reference/node_mcp_server.md",
    "reference/python_mcp_server.md",
}

EXPECTED_LOCAL_SCRIPTS = {
    "scripts/connections.py",
    "scripts/evaluation.py",
}

EXPECTED_REFERENCED_LIBS = {"anthropic", "mcp"}


# ---------------------------------------------------------------------------
# Fixture: run P1 against the real fixture files
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def graph(tmp_path_factory):
    """Build a real FileReferenceGraph by running P1 on the fixture directory."""
    import shutil
    from conftest import FIXTURES_DIR

    # Copy fixtures into a clean tmp directory so P1 gets a real filesystem
    skill_root = tmp_path_factory.mktemp("skill") / "mcp-builder"
    shutil.copytree(str(FIXTURES_DIR), str(skill_root))

    from pre_processing.p1_reference_graph import build_reference_graph
    return build_reference_graph(skill_root=str(skill_root))


# ---------------------------------------------------------------------------
# Tests: graph structure
# ---------------------------------------------------------------------------

class TestP1NodeDiscovery:

    def test_all_files_discovered(self, graph):
        assert set(graph.nodes.keys()) == EXPECTED_NODES

    def test_skill_id(self, graph):
        assert graph.skill_id == "mcp-builder"

    def test_root_path_ends_with_skill_id(self, graph):
        assert graph.root_path.rstrip("/").endswith("mcp-builder")


class TestP1FileKinds:

    def test_doc_files(self, graph):
        for path in ["SKILL.md",
                     "reference/evaluation.md", "reference/mcp_best_practices.md",
                     "reference/node_mcp_server.md", "reference/python_mcp_server.md"]:
            assert graph.nodes[path].kind == "doc", f"{path} should be kind='doc'"

    def test_script_files(self, graph):
        for path in ["scripts/connections.py", "scripts/evaluation.py"]:
            assert graph.nodes[path].kind == "script", f"{path} should be kind='script'"

    def test_data_files(self, graph):
        for path in ["scripts/example_evaluation.xml", "scripts/requirements.txt"]:
            assert graph.nodes[path].kind == "data", f"{path} should be kind='data'"


class TestP1FileContent:

    def test_head_lines_not_empty(self, graph):
        for path, node in graph.nodes.items():
            assert len(node.head_lines) >= 1, f"{path} has empty head_lines"

    def test_skill_md_head_starts_with_frontmatter(self, graph):
        assert graph.nodes["SKILL.md"].head_lines[0].strip() == "---"

    def test_node_mcp_server_head(self, graph):
        first = graph.nodes["reference/node_mcp_server.md"].head_lines[0]
        assert "Node" in first or "TypeScript" in first or "#" in first

    def test_license_txt_excluded(self, graph):
        """LICENSE.txt should be excluded from the graph (legal boilerplate)."""
        assert "LICENSE.txt" not in graph.nodes

    def test_evaluation_xml_head(self, graph):
        first = graph.nodes["scripts/example_evaluation.xml"].head_lines[0]
        assert "<evaluation>" in first

    def test_size_bytes_positive(self, graph):
        for path, node in graph.nodes.items():
            assert node.size_bytes > 0, f"{path} has size_bytes=0"


class TestP1Edges:

    def test_skill_md_references_all_four_reference_docs(self, graph):
        actual_refs = set(graph.edges.get("SKILL.md", []))
        assert EXPECTED_SKILL_MD_REFS.issubset(actual_refs), (
            f"Missing refs: {EXPECTED_SKILL_MD_REFS - actual_refs}"
        )

    def test_evaluation_py_references_connections(self, graph):
        refs = graph.edges.get("scripts/evaluation.py", [])
        assert any("connections" in r for r in refs), (
            "evaluation.py imports connections — should appear in edges"
        )

    def test_license_txt_not_in_edges(self, graph):
        """LICENSE.txt should not appear in edges since it's excluded."""
        assert "LICENSE.txt" not in graph.edges

    def test_reference_docs_have_no_outgoing_refs(self, graph):
        for path in ["reference/evaluation.md", "reference/mcp_best_practices.md",
                     "reference/node_mcp_server.md", "reference/python_mcp_server.md"]:
            assert graph.edges.get(path, []) == [], (
                f"{path} should have no outgoing edges (self-contained doc)"
            )


class TestP1Scripts:

    def test_local_scripts_contains_py_files(self, graph):
        assert EXPECTED_LOCAL_SCRIPTS.issubset(set(graph.local_scripts)), (
            f"Missing scripts: {EXPECTED_LOCAL_SCRIPTS - set(graph.local_scripts)}"
        )

    def test_local_scripts_no_non_py_files(self, graph):
        for s in graph.local_scripts:
            assert s.endswith(".py"), f"Non-.py file in local_scripts: {s}"

    def test_referenced_libs_from_requirements(self, graph):
        libs = set(graph.referenced_libs)
        assert "anthropic" in libs, "anthropic missing from referenced_libs"
        assert "mcp" in libs, "mcp missing from referenced_libs"


class TestP1Frontmatter:

    def test_frontmatter_name(self, graph):
        assert graph.frontmatter.get("name") == "mcp-builder"

    def test_frontmatter_description_present(self, graph):
        assert len(graph.frontmatter.get("description", "")) > 10

    def test_frontmatter_license_field(self, graph):
        # SKILL.md has: license: Complete terms in LICENSE.txt
        assert "license" in graph.frontmatter
