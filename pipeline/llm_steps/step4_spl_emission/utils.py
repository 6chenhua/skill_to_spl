"""Utility functions for Step 4 SPL emission."""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def _to_pascal_case(text: str) -> str:
    """Convert a skill_id to PascalCase agent name."""
    # Remove non-alphanumeric characters and split into words
    words = re.split(r'[^a-zA-Z0-9]+', text)
    # Capitalize each word and join
    return ''.join(word.capitalize() for word in words if word)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences from text."""
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _build_review_summary() -> str:
    """Build review summary header."""
    return "## Review Summary\n"


# Legacy helper - kept for compatibility
def _split_spl_output(raw_text: str) -> tuple[str, str]:
    """Split SPL output from review summary.

    Args:
        raw_text: Raw SPL text potentially containing review summary

    Returns:
        Tuple of (spl_text, review_summary)
    """
    marker = "## Review Summary"
    idx = raw_text.find(marker)
    if idx >= 0:
        return raw_text[:idx].strip(), raw_text[idx:].strip()
    return raw_text.strip(), ""