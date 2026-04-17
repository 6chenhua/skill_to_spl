"""
P1 — Reference Graph Builder (pure code, no LLM).

Responsibilities:
- Recursively enumerate all files under the skill root
- Read all .md files in full; read script head comments (≤5 lines)
- Regex-scan each .md for filename references
- Output: FileReferenceGraph

No role judgment is made here — that is P2's job.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from models import FileNode, FileReferenceGraph

logger = logging.getLogger(__name__)


# ─── File classification ────────────────────────────────────────────────────

_DOC_EXTS    = {".md"}
_SCRIPT_EXTS = {".py", ".sh", ".js", ".ts"}
_DATA_EXTS   = {".json", ".yaml", ".yml", ".toml", ".csv"}

def _classify_kind(rel_path: str) -> str:
    ext = Path(rel_path).suffix.lower()
    if ext in _DOC_EXTS:    return "doc"
    if ext in _SCRIPT_EXTS: return "script"
    if ext in _DATA_EXTS:   return "data"
    return "asset"


# ─── File reference scanner ─────────────────────────────────────────────────

# Matches filenames with extensions appearing in markdown text, including
# backtick-quoted references (`forms.md`) and bare references (forms.md).
_FILE_REF_PATTERN = re.compile(
    r"`([^`]+\.[a-zA-Z]{1,6})`"                                          # `filename.ext`
    r"|(?<!\w)([\w/.-]+\.(?:md|py|sh|js|ts|json|yaml|yml|txt))(?!\w)",  # bare filename.ext
    re.IGNORECASE,
)

def _scan_references(text: str) -> list[str]:
    """
    Extract every filename reference (with extension) found in a text block.
    Returns sorted unique basenames (paths stripped — cross-references in skill docs
    are typically by basename only).
    """
    found: set[str] = set()
    for m in _FILE_REF_PATTERN.finditer(text):
        ref = m.group(1) or m.group(2)
        if ref:
            found.add(Path(ref).name)
    return sorted(found)


# ─── Head-line readers ──────────────────────────────────────────────────────

def _read_head_lines(path: Path, n: int = 20) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[:n]
    except Exception:
        return []


def _read_head_comment(path: Path, max_lines: int = 5) -> list[str]:
    """
    Read only the leading comment / docstring block of a script.
    Stops at the first non-comment, non-docstring line after the comment block.
    Does NOT parse the rest of the source file.
    """
    result: list[str] = []
    in_docstring = False
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for i, raw in enumerate(fh):
                if i >= 20:            # hard ceiling to avoid reading large files
                    break
                line = raw.rstrip()
                stripped = line.strip()

                if stripped.startswith(("#", "//")):
                    result.append(line)
                elif stripped.startswith(('"""', "'''")):
                    result.append(line)
                    in_docstring = not in_docstring
                elif in_docstring:
                    result.append(line)
                elif result and not in_docstring:
                    break              # comment block ended
    except Exception:
        pass
    return result[:max_lines]


# ─── Reference resolution ───────────────────────────────────────────────────

def _resolve_references(basenames: list[str], nodes: dict[str, FileNode]) -> list[str]:
    """Map bare basenames to the actual relative paths present in the graph."""
    index = {Path(p).name.lower(): p for p in nodes}
    resolved = []
    for name in basenames:
        canonical = index.get(name.lower())
        if canonical:
            resolved.append(canonical)
    return resolved


def _filter_existing_references(
    basenames: list[str],
    filename_to_path: dict[str, str],
    source_doc: str,
) -> list[str]:
    """
    Filter references to only include files that actually exist in the skill package.
    Logs warnings for dangling references.
    Returns basenames (not full paths) to maintain compatibility with FileNode.references.
    """
    existing = []
    missing = []
    for name in basenames:
        canonical = filename_to_path.get(name.lower())
        if canonical:
            existing.append(name)  # Keep original basename
        else:
            missing.append(name)

    if missing:
        logger.warning(
            "[P1] %s references non-existent files (filtered): %s",
            source_doc,
            missing,
        )

    return existing


# ─── Frontmatter parser ─────────────────────────────────────────────────────

def _parse_frontmatter(content: str) -> dict[str, Any]:
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end < 0:
        return {}
    try:
        return yaml.safe_load(content[3:end]) or {}
    except Exception:
        return {}


# ─── Skip rules ─────────────────────────────────────────────────────────────

_SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".venv", "venv"}
_SKIP_FILES = {
    ".DS_Store",
    # License files — these contain legal boilerplate, never needed for skill normalization
    "LICENSE.txt",
    "LICENSE",
    "COPYING",
    "NOTICE",
    "AUTHORS",
}

def _should_skip(path: Path) -> bool:
    for part in path.parts:
        if part.startswith(".") or part in _SKIP_DIRS:
            return True
    return path.name in _SKIP_FILES


# ─── Main entry point ───────────────────────────────────────────────────────

def build_reference_graph(skill_root: str) -> FileReferenceGraph:
    """
    P1: Build a complete file reference graph for a skill package.

    Args:
        skill_root: Path to the skill directory (must contain SKILL.md).

    Returns:
        FileReferenceGraph with all files enumerated and all doc→file edges recorded.

    Raises:
        FileNotFoundError: if SKILL.md is not present at skill_root.
    """
    root = Path(skill_root).resolve()
    skill_id = root.name

    skill_md_path = root / "SKILL.md"
    if not skill_md_path.exists():
        raise FileNotFoundError(f"SKILL.md not found in: {skill_root}")

    skill_md_content = skill_md_path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(skill_md_content)

    # ── Enumerate all files ─────────────────────────────────────────────────
    # Phase 1: First pass - collect all file paths to build filename index
    all_file_paths: list[Path] = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        if _should_skip(file_path.relative_to(root)):
            continue
        all_file_paths.append(file_path)

    # Build filename -> path index for reference validation
    filename_to_path: dict[str, str] = {}
    for file_path in all_file_paths:
        rel = str(file_path.relative_to(root))
        filename = Path(rel).name.lower()
        filename_to_path[filename] = rel

    # Phase 2: Second pass - process files with validated references
    nodes: dict[str, FileNode] = {}
    docs_content: dict[str, str] = {}  # NEW: Store full content for all .md files
    for file_path in all_file_paths:
        rel = str(file_path.relative_to(root))
        kind = _classify_kind(rel)
        size = file_path.stat().st_size

        if kind == "doc":
            content = file_path.read_text(encoding="utf-8", errors="replace")
            head_lines = content.splitlines()[:20]
            # Scan references and filter to only existing files
            raw_refs = _scan_references(content)
            refs = _filter_existing_references(raw_refs, filename_to_path, rel)
            docs_content[rel] = content  # NEW: Save full content for doc files
        elif kind == "script":
            head_lines = _read_head_comment(file_path, max_lines=5)
            refs = []  # script-internal references NOT included (avoids chain explosion)
        else:
            head_lines = []
            refs = []

        nodes[rel] = FileNode(
            path=rel,
            kind=kind,
            size_bytes=size,
            head_lines=head_lines,
            references=refs,
        )

    # ── Build edges (doc → referenced files only) ───────────────────────────
    edges: dict[str, list[str]] = {}
    for rel, node in nodes.items():
        if node.kind == "doc" and node.references:
            resolved = _resolve_references(node.references, nodes)
            if resolved:
                edges[rel] = resolved

    return FileReferenceGraph(
        skill_id=skill_id,
        root_path=str(root),
        skill_md_content=skill_md_content,
        frontmatter=frontmatter,
        nodes=nodes,
        edges=edges,
        docs_content=docs_content,  # NEW: Include full content for all .md files
    )
