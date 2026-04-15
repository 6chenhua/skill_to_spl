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


def _extract_symbol_table(block_4c: str) -> dict[str, list[str]]:
    """
    Extract FILES and VARIABLES declared in the DEFINE_VARIABLES/DEFINE_FILES
    block (4c). APIS are NOT included - they are passed separately to S4E.

    Handles both formats:
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
    """
    table: dict[str, list[str]] = {
        "variables": [],
        "files": [],
    }
    if not block_4c:
        return table

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
    Render FILES + VARIABLES as a reference block for S4A, S4B, and S4E.
    These are the names that may appear in DESCRIPTION_WITH_REFERENCES across
    all three blocks. APIS are injected separately into S4E.
    """
    mapping = {
        "variables": "VARIABLES (reference as <REF> var_name </REF>)",
        "files": "FILES (reference as <REF> file_name </REF>)",
    }
    lines = []
    for key, label in mapping.items():
        names = symbol_table.get(key, [])
        if names:
            lines.append(f"{label}:\n {', '.join(names)}")
    return "\n\n".join(lines) if lines else "(no variables or files declared)"
