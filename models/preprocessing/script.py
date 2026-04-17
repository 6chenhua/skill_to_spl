"""Script metadata models for preprocessing.

This module contains models for script analysis and metadata extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.base import SourceRef


@dataclass(slots=True)
class ScriptSpec:
    """Extracted metadata for a script file.

    Represents an API/tool that can be called, used in DEFINE_APIS block
    when the script is referenced in workflow steps.

    Attributes:
        name: Script filename (e.g., "fill_fillable_fields.py")
        path: Relative path from skill root (e.g., "scripts/fill_fillable_fields.py")
        input_schema: Parameter name to type annotation mapping
        output_schema: Return type annotation or "void"
        description: One-line summary from docstring or first comment
        main_function: Primary callable name (e.g., "fill_pdf_fields")
        source_text: Original source code for context
        source_ref: Source code reference

    Examples:
        >>> spec = ScriptSpec(
        ...     name="extract_text.py",
        ...     path="scripts/extract_text.py",
        ...     input_schema={"pdf_path": "str"},
        ...     output_schema="str",
        ...     description="Extract text from PDF",
        ...     main_function="extract_text",
        ... )
    """

    name: str
    path: str
    input_schema: dict[str, str]
    output_schema: str
    description: str
    main_function: str
    source_text: str = ""
    source_ref: SourceRef | None = None

    def get_param_type(self, param_name: str) -> str | None:
        """Get parameter type by name.

        Args:
            param_name: Parameter name

        Returns:
            Type string, or None if not found
        """
        return self.input_schema.get(param_name)

    def has_param(self, param_name: str) -> bool:
        """Check if script has parameter."""
        return param_name in self.input_schema

    def summary(self) -> dict[str, Any]:
        """Return summary statistics."""
        return {
            "name": self.name,
            "path": self.path,
            "main_function": self.main_function,
            "input_count": len(self.input_schema),
            "output": self.output_schema,
            "description": self.description,
        }
