"""Tests for models.base module."""

import pytest
from models.base import (
    CANONICAL_SECTIONS,
    DEFAULT_PRIORITY_THRESHOLD,
    FileKind,
    MAX_HEAD_LINES,
    MAX_SCRIPT_COMMENT_LINES,
    Priority,
    Provenance,
    SourceRef,
    validate_confidence,
    validate_priority,
    validate_provenance,
)


class TestSourceRef:
    """Tests for SourceRef dataclass."""

    def test_source_ref_creation_with_line(self) -> None:
        """Test creating SourceRef with line number."""
        ref = SourceRef(file="skills/pdf/SKILL.md", line=15, column=8)
        assert ref.file == "skills/pdf/SKILL.md"
        assert ref.line == 15
        assert ref.column == 8

    def test_source_ref_creation_without_line(self) -> None:
        """Test creating SourceRef without line number."""
        ref = SourceRef(file="skills/pdf/SKILL.md")
        assert ref.file == "skills/pdf/SKILL.md"
        assert ref.line == 0
        assert ref.column == 0

    def test_source_ref_str_with_line(self) -> None:
        """Test string representation with line."""
        ref = SourceRef(file="skills/pdf/SKILL.md", line=15)
        assert str(ref) == "skills/pdf/SKILL.md:15"

    def test_source_ref_str_without_line(self) -> None:
        """Test string representation without line."""
        ref = SourceRef(file="skills/pdf/SKILL.md")
        assert str(ref) == "skills/pdf/SKILL.md"

    def test_source_ref_repr(self) -> None:
        """Test repr with all fields."""
        ref = SourceRef(file="test.md", line=10, column=5)
        repr_str = repr(ref)
        assert "SourceRef" in repr_str
        assert "test.md" in repr_str

    def test_source_ref_immutable(self) -> None:
        """Test that SourceRef is frozen (immutable)."""
        ref = SourceRef(file="test.md", line=10)
        with pytest.raises(AttributeError):
            ref.file = "other.md"


class TestValidationFunctions:
    """Tests for validation functions."""

    def test_validate_provenance_valid(self) -> None:
        """Test validating valid provenance values."""
        assert validate_provenance("EXPLICIT") == "EXPLICIT"
        assert validate_provenance("ASSUMED") == "ASSUMED"
        assert validate_provenance("LOW_CONFIDENCE") == "LOW_CONFIDENCE"

    def test_validate_provenance_invalid(self) -> None:
        """Test validating invalid provenance values."""
        with pytest.raises(ValueError):
            validate_provenance("INVALID")

    def test_validate_priority_valid(self) -> None:
        """Test validating valid priority values."""
        assert validate_priority(1) == 1
        assert validate_priority(2) == 2
        assert validate_priority(3) == 3

    def test_validate_priority_invalid(self) -> None:
        """Test validating invalid priority values."""
        with pytest.raises(ValueError):
            validate_priority(0)
        with pytest.raises(ValueError):
            validate_priority(4)

    def test_validate_confidence_valid(self) -> None:
        """Test validating valid confidence values."""
        assert validate_confidence(0.0) == 0.0
        assert validate_confidence(0.5) == 0.5
        assert validate_confidence(1.0) == 1.0

    def test_validate_confidence_invalid(self) -> None:
        """Test validating invalid confidence values."""
        with pytest.raises(ValueError):
            validate_confidence(-0.1)
        with pytest.raises(ValueError):
            validate_confidence(1.1)


class TestConstants:
    """Tests for module constants."""

    def test_canonical_sections(self) -> None:
        """Test canonical sections constant."""
        assert len(CANONICAL_SECTIONS) == 8
        assert "INTENT" in CANONICAL_SECTIONS
        assert "WORKFLOW" in CANONICAL_SECTIONS
        assert "CONSTRAINTS" in CANONICAL_SECTIONS
        assert "EXAMPLES" in CANONICAL_SECTIONS

    def test_default_priority_threshold(self) -> None:
        """Test default priority threshold."""
        assert DEFAULT_PRIORITY_THRESHOLD == 2

    def test_max_head_lines(self) -> None:
        """Test max head lines constant."""
        assert MAX_HEAD_LINES == 20

    def test_max_script_comment_lines(self) -> None:
        """Test max script comment lines constant."""
        assert MAX_SCRIPT_COMMENT_LINES == 5
