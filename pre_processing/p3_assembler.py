"""
P3 — Skill Package Assembler (pure code, with optional LLM fallback).

Responsibilities:
- Consume FileReferenceGraph + FileRoleMap (P2 output)
- Read full content for priority-1 files; head lines for priority-2 files
- Skip priority-3 files entirely
- Concatenate into a single merged_doc_text with clear file boundary markers
- Output: SkillPackage (ready for Step 1 LLM input)

LLM fallback (priority-2 only):
  If a priority-2 file has no extractable head content (empty head_lines), P3
  reads up to _FALLBACK_READ_CHARS of the file and calls `summarize_fn` to
  produce a 2-3 sentence summary.  This prevents silent "(no head comment)"
  placeholders from reaching Step 1.
  If no `summarize_fn` is provided, P3 falls back to the first 20 lines of the
  raw file content instead (better than nothing, still no LLM required).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from models.data_models import FileReferenceGraph, SkillPackage

logger = logging.getLogger(__name__)

# Maximum characters read for LLM fallback summarization
_FALLBACK_READ_CHARS = 4000


# ─── Boundary markers ───────────────────────────────────────────────────────

def _boundary(rel_path: str, role: str, priority_label: str) -> str:
    return f"=== FILE: {rel_path} | role: {role} | priority: {priority_label} ==="


# ─── Summary helpers ─────────────────────────────────────────────────────────

def _read_fallback_content(file_path: Path) -> str:
    """Read up to _FALLBACK_READ_CHARS of a file for summarization."""
    try:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
        return raw[:_FALLBACK_READ_CHARS]
    except Exception as exc:
        return f"[ERROR: could not read file — {exc}]"


def _head_is_empty(head_lines: list[str]) -> bool:
    """Return True if head_lines contain no meaningful content."""
    if not head_lines:
        return True
    joined = " ".join(head_lines).strip()
    return not joined or joined in {"(no head comment)", "(empty)"}


# ─── Main entry point ───────────────────────────────────────────────────────

def assemble_skill_package(
        graph: FileReferenceGraph,
        file_role_map: dict[str, Any],
        summarize_fn: Optional[Callable[[str, str], str]] = None,
) -> SkillPackage:
    """
    P3: Assemble the merged document text for Step 1.

    Priority semantics:
        1 = must_read       → include full file content
        2 = include_summary → include head_lines (with LLM fallback if empty)
        3 = omit            → skip entirely

    Args:
        graph:         Output of P1.
        file_role_map: Output of P2 (dict of path → {role, read_priority, ...}).
        summarize_fn:  Optional callable(rel_path, file_content) → summary_str.
                       Called only when a priority-2 file has empty head_lines.
                       If None, falls back to raw first-20-lines instead.

    Returns:
        SkillPackage ready to be fed into Step 1.
    """
    root = Path(graph.root_path)
    sections: list[str] = []

    # Sort by read_priority ascending (1 before 2), then by path for determinism
    ordered = sorted(
        file_role_map.items(),
        key=lambda kv: (kv[1].get("read_priority", 3), kv[0]),
    )

    for rel_path, role_entry in ordered:
        priority: int = role_entry.get("read_priority", 3)
        if priority == 3:
            continue

        node = graph.nodes.get(rel_path)
        if node is None:
            continue

        role = role_entry.get("role", "unknown")
        file_path = root / rel_path

        if priority == 1:
            # Full content — no summarization needed
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                content = f"[ERROR: could not read file — {exc}]"
            header = _boundary(rel_path, role, "MUST_READ")
            sections.append(f"{header}\n{content}")

        elif priority == 2:
            summary, preamble = _get_priority2_summary(
                node=node,
                file_path=file_path,
                rel_path=rel_path,
                summarize_fn=summarize_fn,
            )
            header = _boundary(rel_path, role, "SUMMARY")
            sections.append(f"{header}\n{preamble}\n{summary}")

    merged_doc_text = "\n\n".join(sections)

    return SkillPackage(
        skill_id=graph.skill_id,
        root_path=graph.root_path,
        frontmatter=graph.frontmatter,
        merged_doc_text=merged_doc_text,
        file_role_map=file_role_map,
    )


def _get_priority2_summary(
        node: Any,
        file_path: Path,
        rel_path: str,
        summarize_fn: Optional[Callable[[str, str], str]],
) -> tuple[str, str]:
    """
    Determine the summary text and preamble label for a priority-2 file.

    Strategy:
      1. Use head_lines if they contain meaningful content  →  fast path, no I/O
      2. head_lines are empty → read file content and either:
         a. Call summarize_fn (LLM)  →  2-3 sentence summary
         b. No summarize_fn          →  raw first 20 lines (graceful degradation)
    """
    if node.kind == "script":
        preamble_full = "[Script summary — head comment only, no source code]"
        preamble_llm = "[Script summary — LLM-generated from head content]"
        preamble_raw = "[Script — no head comment; showing first 20 lines]"
    else:
        preamble_full = "[First 20 lines only]"
        preamble_llm = "[LLM-generated summary — head content was empty]"
        preamble_raw = "[First 20 lines (head was empty)]"

    # Fast path: head_lines have content
    if not _head_is_empty(node.head_lines):
        return "\n".join(node.head_lines), preamble_full

    # Fallback: head_lines are empty
    logger.info("[P3] %s has empty head_lines — using fallback summary", rel_path)
    fallback_content = _read_fallback_content(file_path)

    if summarize_fn is not None:
        try:
            summary = summarize_fn(rel_path, fallback_content)
            logger.info("[P3] LLM summary generated for %s (%d chars)", rel_path, len(summary))
            return summary, preamble_llm
        except Exception as exc:
            logger.warning("[P3] LLM summary failed for %s: %s — using raw lines", rel_path, exc)

    # Final fallback: raw first 20 lines of file
    raw_lines = fallback_content.splitlines()[:20]
    return "\n".join(raw_lines), preamble_raw
