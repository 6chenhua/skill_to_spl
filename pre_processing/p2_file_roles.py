"""
P2 — File Role Resolver (Rule-based, no LLM).

Assigns read priority based on file type:
- doc (.md): priority=1 (must read all content, examples go to SPL EXAMPLE section)
- script (.py/.sh/.js/.ts): priority=2 (handled by P2.5 API analysis in P3)
- data (.json/.yaml/.csv): priority=3 (skip)
- asset (other): priority=3 (skip)
"""
from __future__ import annotations

import logging
from typing import Any

from models import FileReferenceGraph

logger = logging.getLogger(__name__)


def assign_file_priorities(graph: FileReferenceGraph) -> dict[str, dict[str, Any]]:
    """
    P2: Assign file roles and read priorities based on file type (rule-based).

    This replaces the previous LLM-based approach with a simple, deterministic
    rule system:

    - doc (.md): priority=1, must_read=True
      Rationale: All doc content is needed, even examples will go to SPL EXAMPLE section

    - script (.py/.sh/.js/.ts): priority=2, must_read=True
      Rationale: Scripts are analyzed by P2.5 (merged into P3) to extract API specs

    - data (.json/.yaml/.csv): priority=3, must_read=False
      Rationale: Data files are typically config or sample data, not needed for normalization

    - asset (other): priority=3, must_read=False
      Rationale: Binary files, images, etc. are not processed

    Args:
        graph: Output of P1 (FileReferenceGraph)

    Returns:
        dict mapping rel_path -> {role, read_priority, must_read_for_normalization, reasoning}
    """
    file_roles: dict[str, dict[str, Any]] = {}

    for path, node in graph.nodes.items():
        if node.kind == "doc":
            # All doc files: priority=1
            # Even example docs need to be read because examples go to SPL EXAMPLE section
            file_roles[path] = {
                "role": "doc",
                "read_priority": 1,
                "must_read_for_normalization": True,
                "reasoning": f"Document file ({node.kind}), priority=1 for full content extraction",
            }
        elif node.kind == "script":
            # All scripts: priority=2
            # Will be processed by P2.5 (merged into P3) for API spec extraction
            file_roles[path] = {
                "role": "script",
                "read_priority": 2,
                "must_read_for_normalization": True,
                "reasoning": f"Script file ({node.kind}), priority=2 for P2.5 API analysis",
            }
        elif node.kind == "data":
            # Data files: priority=3 (skip)
            file_roles[path] = {
                "role": "data",
                "read_priority": 3,
                "must_read_for_normalization": False,
                "reasoning": f"Data file ({node.kind}), priority=3 (skip)",
            }
        else:
            # Assets and other: priority=3 (skip)
            file_roles[path] = {
                "role": "asset",
                "read_priority": 3,
                "must_read_for_normalization": False,
                "reasoning": f"Asset file ({node.kind}), priority=3 (skip)",
            }

    logger.info(
        "[P2] Assigned priorities: %d docs (p1), %d scripts (p2), %d others (p3)",
        sum(1 for r in file_roles.values() if r["read_priority"] == 1),
        sum(1 for r in file_roles.values() if r["read_priority"] == 2),
        sum(1 for r in file_roles.values() if r["read_priority"] == 3),
    )

    return file_roles
