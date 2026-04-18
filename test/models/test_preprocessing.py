"""Tests for models.preprocessing module."""

import pytest
from models.preprocessing.reference import FileNode, FileReferenceGraph
from models.preprocessing.roles import FileRoleEntry, FileRoleMap, RoleAssignment
from models.preprocessing.package import SkillPackage
from models.base import SourceRef


class TestFileNode:
    """Tests for FileNode dataclass."""

    def test_file_node_creation(self) -> None:
        """Test creating FileNode."""
        node = FileNode(
            path="docs/guide.md",
            kind="doc",
            size_bytes=1024,
            head_lines=["# Guide", "This is..."],
            references=["api.py"],
        )
        assert node.path == "docs/guide.md"
        assert node.kind == "doc"
        assert node.size_bytes == 1024

    def test_file_node_is_document(self) -> None:
        """Test is_document check."""
        doc_node = FileNode(path="test.md", kind="doc", size_bytes=100, head_lines=[], references=[])
        script_node = FileNode(path="test.py", kind="script", size_bytes=100, head_lines=[], references=[])
        assert doc_node.is_document() is True
        assert script_node.is_document() is False

    def test_file_node_is_script(self) -> None:
        """Test is_script check."""
        script_node = FileNode(path="test.py", kind="script", size_bytes=100, head_lines=[], references=[])
        doc_node = FileNode(path="test.md", kind="doc", size_bytes=100, head_lines=[], references=[])
        assert script_node.is_script() is True
        assert doc_node.is_script() is False

    def test_file_node_is_omittable(self) -> None:
        """Test is_omittable check."""
        image_node = FileNode(path="test.png", kind="image", size_bytes=100, head_lines=[], references=[])
        doc_node = FileNode(path="test.md", kind="doc", size_bytes=100, head_lines=[], references=[])
        assert image_node.is_omittable() is True
        assert doc_node.is_omittable() is False

    def test_file_node_equality(self) -> None:
        """Test FileNode equality based on path."""
        node1 = FileNode(path="test.md", kind="doc", size_bytes=100, head_lines=[], references=[])
        node2 = FileNode(path="test.md", kind="script", size_bytes=200, head_lines=["x"], references=["y"])
        node3 = FileNode(path="other.md", kind="doc", size_bytes=100, head_lines=[], references=[])
        assert node1 == node2  # Same path
        assert node1 != node3  # Different path

    def test_file_node_hash(self) -> None:
        """Test FileNode hash based on path."""
        node1 = FileNode(path="test.md", kind="doc", size_bytes=100, head_lines=[], references=[])
        node2 = FileNode(path="test.md", kind="script", size_bytes=200, head_lines=["x"], references=["y"])
        assert hash(node1) == hash(node2)  # Same path = same hash


class TestFileReferenceGraph:
    """Tests for FileReferenceGraph dataclass."""

    @pytest.fixture
    def sample_graph(self) -> FileReferenceGraph:
        """Create a sample graph for testing."""
        return FileReferenceGraph(
            skill_id="pdf",
            root_path="/skills/pdf",
            skill_md_content="# PDF Skill",
            frontmatter={"name": "PDF"},
            nodes={},
            edges={},
        )

    def test_graph_creation(self, sample_graph: FileReferenceGraph) -> None:
        """Test creating FileReferenceGraph."""
        assert sample_graph.skill_id == "pdf"
        assert sample_graph.root_path == "/skills/pdf"

    def test_graph_add_node(self, sample_graph: FileReferenceGraph) -> None:
        """Test adding node to graph."""
        node = FileNode(path="test.md", kind="doc", size_bytes=100, head_lines=[], references=[])
        sample_graph.add_node(node)
        assert "test.md" in sample_graph.nodes
        assert sample_graph.get_node("test.md") == node

    def test_graph_add_edge(self, sample_graph: FileReferenceGraph) -> None:
        """Test adding edge to graph."""
        sample_graph.add_edge("file1.md", "file2.md")
        assert "file1.md" in sample_graph.edges
        assert "file2.md" in sample_graph.edges["file1.md"]

    def test_graph_get_references(self, sample_graph: FileReferenceGraph) -> None:
        """Test getting references."""
        sample_graph.add_edge("file1.md", "file2.md")
        refs = sample_graph.get_references("file1.md")
        assert refs == ["file2.md"]

    def test_graph_get_referrers(self, sample_graph: FileReferenceGraph) -> None:
        """Test getting referrers."""
        sample_graph.add_edge("file1.md", "file3.md")
        sample_graph.add_edge("file2.md", "file3.md")
        referrers = sample_graph.get_referrers("file3.md")
        assert "file1.md" in referrers
        assert "file2.md" in referrers

    def test_graph_summary(self, sample_graph: FileReferenceGraph) -> None:
        """Test graph summary."""
        node1 = FileNode(path="a.md", kind="doc", size_bytes=100, head_lines=[], references=[])
        node2 = FileNode(path="b.py", kind="script", size_bytes=200, head_lines=[], references=[])
        sample_graph.add_node(node1)
        sample_graph.add_node(node2)
        summary = sample_graph.summary()
        assert summary["total_files"] == 2
        assert summary.get("doc", 0) == 1
        assert summary.get("script", 0) == 1


class TestFileRoleEntry:
    """Tests for FileRoleEntry dataclass."""

    def test_role_entry_creation(self) -> None:
        """Test creating FileRoleEntry."""
        entry = FileRoleEntry(
            role="documentation",
            read_priority=1,
            must_read_for_normalization=True,
            reasoning="Contains main description",
        )
        assert entry.role == "documentation"
        assert entry.read_priority == 1

    def test_role_entry_invalid_priority(self) -> None:
        """Test creating FileRoleEntry with invalid priority."""
        with pytest.raises(ValueError):
            FileRoleEntry(
                role="test",
                read_priority=4,  # Invalid
                must_read_for_normalization=True,
                reasoning="Test",
            )

    def test_role_entry_is_must_read(self) -> None:
        """Test is_must_read check."""
        p1 = FileRoleEntry(role="doc", read_priority=1, must_read_for_normalization=True, reasoning="x")
        p2 = FileRoleEntry(role="summary", read_priority=2, must_read_for_normalization=False, reasoning="y")
        assert p1.is_must_read() is True
        assert p2.is_must_read() is False

    def test_role_entry_is_omit(self) -> None:
        """Test is_omit check."""
        p3 = FileRoleEntry(role="asset", read_priority=3, must_read_for_normalization=False, reasoning="z")
        p1 = FileRoleEntry(role="doc", read_priority=1, must_read_for_normalization=True, reasoning="x")
        assert p3.is_omit() is True
        assert p1.is_omit() is False


class TestSkillPackage:
    """Tests for SkillPackage dataclass."""

    @pytest.fixture
    def sample_package(self) -> SkillPackage:
        """Create a sample package for testing."""
        return SkillPackage(
            skill_id="pdf",
            root_path="/skills/pdf",
            frontmatter={"name": "PDF"},
            merged_doc_text="=== FILE: SKILL.md ...",
            file_role_map={},
        )

    def test_package_creation(self, sample_package: SkillPackage) -> None:
        """Test creating SkillPackage."""
        assert sample_package.skill_id == "pdf"
        assert sample_package.root_path == "/skills/pdf"

    def test_package_get_doc_content(self, sample_package: SkillPackage) -> None:
        """Test extracting document content."""
        # Create a package with proper boundary markers
        package = SkillPackage(
            skill_id="test",
            root_path="/test",
            frontmatter={},
            merged_doc_text='=== FILE: doc.md | role: doc | priority: 1 ===\nHello World\n\n=== FILE: other.md | role: doc | priority: 1 ===\nOther content',
            file_role_map={},
        )
        content = package.get_doc_content("doc.md")
        assert content is not None
        assert "Hello World" in content

    def test_package_summary(self, sample_package: SkillPackage) -> None:
        """Test package summary."""
        summary = sample_package.summary()
        assert summary["skill_id"] == "pdf"
        assert "frontmatter_keys" in summary
