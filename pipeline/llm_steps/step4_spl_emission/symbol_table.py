"""Symbol table extraction and formatting for Step 4."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Regex to match file declarations in DEFINE_FILES
# Files are defined in two-line format:
# "description"
# variable_name path : type
# Where path can be a filename or placeholders like "< >" (with spaces)
_FILE_NAME_RE = re.compile(
    r'^\s*"[^"]*"\s*\n\s+([a-z][a-z0-9_]+)\s+[^\n:]*?:',
    re.MULTILINE | re.IGNORECASE
)


def _extract_symbol_table(block_4c: str, types_spl: str = "") -> dict[str, list[str]]:
    """
    Extract TYPES, FILES and VARIABLES declared in the blocks.
    APIS are NOT included - they are passed separately to S4E.

    Handles both formats:
    - [DEFINE_TYPES:] ... [END_TYPES]
    - [DEFINE_VARIABLES:] ... [END_VARIABLES] [DEFINE_FILES:] ... [END_FILES]
    - [DEFINE_FILES:] ... [END_FILES] (no variables section)
    - [DEFINE_VARIABLES:] ... [END_VARIABLES] (no files section)

    Files are defined in two-line format:
    "description"
    variable_name path : type

    Variables can be in single-line or two-line format:
    "description" [READONLY] variable_name : type
    "description"
    [READONLY] variable_name : type

    Types are extracted from [DEFINE_TYPES:] block:
    "description" (optional)
    DeclaredName = <type_expr>
    """
    table: dict[str, list[str]] = {
        "types": [],
        "variables": [],
        "files": [],
    }
    if not block_4c:
        return table

    # Extract TYPES block if present (from types_spl or block_4c)
    types_block = types_spl if types_spl else block_4c
    type_start = types_block.find("[DEFINE_TYPES:]")
    type_end = types_block.find("[END_TYPES]")

    if type_start >= 0 and type_end > type_start:
        type_section = types_block[type_start:type_end]
        # Pattern: TypeName = <type_expr>
        # Optionally preceded by "description"
        type_matches = re.findall(
            r'^\s*(?:"[^"]*"\s*)?([A-Z][a-zA-Z0-9]*)\s*=',
            type_section,
            re.MULTILINE
        )
        table["types"] = type_matches

    # Extract VARIABLES block if present
    var_start = block_4c.find("[DEFINE_VARIABLES:]")
    var_end = block_4c.find("[END_VARIABLES]")

    if var_start >= 0 and var_end > var_start:
        var_block = block_4c[var_start:var_end]
        # Find all variable declarations
        # Pattern: "description" followed by optional READONLY and variable_name :
        # Handles both single-line and two-line formats
        var_matches = re.findall(
            r'(?:^\s*"[^"]*"(?:\s+READONLY)?\s+([a-z][a-z0-9_]+)\s*:)|'
            r'(?:^\s*"[^"]*"\s*\n\s*(?:READONLY\s+)?([a-z][a-z0-9_]+)\s*:)',
            var_block,
            re.MULTILINE | re.IGNORECASE
        )
        # Flatten matches (each match is a tuple from alternation)
        table["variables"] = [v for match in var_matches for v in match if v]

    # Extract FILES block if present
    file_start = block_4c.find("[DEFINE_FILES:]")
    file_end = block_4c.find("[END_FILES]")

    if file_start >= 0 and file_end > file_start:
        file_block = block_4c[file_start:file_end]
        # Files are always in two-line format:
        # "description"
        # variable_name path : type
        # Where path can contain spaces (e.g., "< >")
        file_matches = re.findall(
            r'^\s*"[^"]*"\s*\n\s+([a-z][a-z0-9_]+)\s+[^\n:]*?:',
            file_block,
            re.MULTILINE | re.IGNORECASE
        )
        table["files"] = file_matches

    return table


def _format_symbol_table(symbol_table: dict[str, list[str]]) -> str:
    """
    Render TYPES, FILES + VARIABLES as a reference block for S4A, S4B, and S4E.
    These are the names that may appear in DESCRIPTION_WITH_REFERENCES across
    all blocks. APIS are injected separately into S4E.

    Type names can be referenced in variable/file declarations and in
    DESCRIPTION_WITH_REFERENCES text.
    """
    mapping = {
        "types": "TYPES (reference in type expressions: DeclaredName = <TYPE>)",
        "variables": "VARIABLES (reference as <REF> var_name </REF>)",
        "files": "FILES (reference as <REF> file_name </REF>)",
    }
    lines = []
    for key, label in mapping.items():
        names = symbol_table.get(key, [])
        if names:
            lines.append(f"{label}:\n {', '.join(names)}")

    all_empty = not any(symbol_table.get(k) for k in mapping.keys())
    return "\n\n".join(lines) if not all_empty else "(no types, variables, or files declared)"
