from __future__ import annotations

import dataclasses
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from models.data_models import (
    FileReferenceGraph,
)
from pipeline.llm_client import LLMClient, LLMParseError
from prompts import templates

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# P2 — File Role Resolver
# ─────────────────────────────────────────────────────────────────────────────

def run_p2_file_role_resolver(
    graph: FileReferenceGraph,
    client: LLMClient,
) -> dict[str, Any]:
    """
    P2: Determine the role and read priority of every non-SKILL.md file.

    Instead of sending the full SKILL.md, we extract only the sentences that
    reference other files (with ±1 line context).  This preserves the tone
    information the LLM needs while cutting token usage significantly.

    SKILL.md itself is always role="primary", read_priority=1 — fixed, not
    sent to the LLM for classification.

    Returns:
        dict mapping rel_path → FileRoleEntry dict (JSON-serializable).
        SKILL.md entry is added by this function, not by the LLM.
    """
    skill_md_references = _extract_skill_md_references(graph.skill_md_content, graph.edges)  # 提取skill.md中引用文件的那一行内容 --> 给llm判断tone用
    nodes_summary = _format_nodes_summary(graph)
    edges_json    = json.dumps(graph.edges, indent=2)

    user_prompt = templates.render_p2_user(
        skill_md_references=skill_md_references,
        nodes_summary=nodes_summary,
        edges_json=edges_json,
    )

    raw = client.call_json(
        step_name="p2_file_role_resolver",
        system=templates.P2_SYSTEM,
        user=user_prompt,
    )

    if isinstance(raw, dict) and "file_roles" in raw:
        file_roles = raw["file_roles"]
    else:
        file_roles = raw

    # Always inject SKILL.md as primary — the LLM doesn't output it
    file_roles["SKILL.md"] = {
        "role": "primary",
        "read_priority": 1,
        "must_read_for_normalization": True,
        "reasoning": "SKILL.md is the fixed anchor of every skill package.",
    }

    _validate_file_role_map(file_roles, graph)
    logger.info("[P2] resolved roles for %d files", len(file_roles))
    return file_roles


def _extract_skill_md_references(skill_md_content: str, edges: dict) -> str:
    """
    Extract lines from SKILL.md that reference other files, with ±1 line context.

    This gives the LLM the referencing tone (imperative vs optional) without
    sending the full SKILL.md content.
    """
    # Collect all basenames that SKILL.md references (from edges)
    referenced_names: set[str] = set()
    skill_md_refs = edges.get("SKILL.md", [])
    for ref_path in skill_md_refs:
        referenced_names.add(Path(ref_path).name.lower())

    if not referenced_names:
        return "(SKILL.md references no other files directly)"

    lines = skill_md_content.splitlines()
    result_blocks: list[str] = []
    seen_lines: set[int] = set()

    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(name in line_lower for name in referenced_names):
            # Include ±1 line context
            start = max(0, i - 1)
            end   = min(len(lines), i + 2)
            block_lines = []
            for j in range(start, end):
                if j not in seen_lines:
                    prefix = ">>>" if j == i else "   "
                    block_lines.append(f"{prefix} {lines[j]}")
                    seen_lines.add(j)
            if block_lines:
                result_blocks.append("\n".join(block_lines))

    return "\n\n".join(result_blocks) if result_blocks else "(no reference lines found)"


def _format_nodes_summary(graph: FileReferenceGraph) -> str:
    lines = []
    for path, node in sorted(graph.nodes.items()):
        head = " | ".join(node.head_lines[:3]) if node.head_lines else "(empty)"
        lines.append(f"  {path} [{node.kind}, {node.size_bytes}B]: {head}")
    return "\n".join(lines)


def _validate_file_role_map(file_roles: dict, graph: FileReferenceGraph) -> None:
    """Warn if any graph node is missing from the LLM output. SKILL.md is always injected."""
    for path in graph.nodes:
        if path == "SKILL.md":
            continue  # always injected by run_p2_file_role_resolver, not the LLM
        if path not in file_roles:
            logger.warning("[P2] no role assigned for: %s — defaulting to omit", path)
            file_roles[path] = {
                "role": "unreferenced",
                "read_priority": 3,
                "must_read_for_normalization": False,
                "reasoning": "No role returned by LLM; defaulting to omit.",
            }