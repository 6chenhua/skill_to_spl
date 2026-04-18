"""P2: File Role Resolver step."""
from __future__ import annotations

from typing import Any

from pipeline.orchestrator.base import PipelineStep
from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.step_registry import registry
from pre_processing.p2_file_roles import assign_file_priorities


@registry.register
class P2FileRolesStep(PipelineStep[dict, dict]):
    """P2: Assign file roles and read priorities.

    Rule-based role assignment:
    - doc (.md): priority=1, must_read=True
    - script (.py/.sh/.js/.ts): priority=2, must_read=True
    - data (.json/.yaml/.csv): priority=3, must_read=False
    - asset (other): priority=3, must_read=False

    Input:
        P1 output dictionary with graph data

    Output:
        Dictionary mapping file paths to role information:
        {
            "rel_path": {
                "role": "doc|script|data|asset",
                "read_priority": int,
                "must_read_for_normalization": bool,
                "reasoning": str,
            }
        }
    """

    @property
    def name(self) -> str:
        """Step name for logging and checkpointing."""
        return "p2_file_roles"

    @property
    def dependencies(self) -> list[str]:
        """P2 depends on P1 output."""
        return ["p1_reference_graph"]

    def execute(self, context: ExecutionContext, inputs: dict) -> dict:
        """Assign file roles.

        Args:
            context: Execution context
            inputs: P1 output dictionary

        Returns:
            Dictionary mapping paths to role information
        """
        from models import FileNode, FileReferenceGraph

        context.logger.info("[P2] Assigning file priorities...")

        # Reconstruct graph from P1 output
        skill_id = inputs["skill_id"]
        nodes_data = inputs["nodes"]
        edges_data = inputs["edges"]

        # Create nodes dict
        nodes: dict[str, FileNode] = {}
        for node_data in nodes_data:
            node = FileNode(**node_data)
            nodes[node.path] = node

        # Create edges from dict format
        # edges_data is dict[str, list[str]] mapping source -> [targets]
        # FileReferenceGraph expects edges as dict[str, list[str]], not FileEdge list
        edges: dict[str, list[str]] = edges_data

        # Create graph with required fields
        # Need to reconstruct from P1 output - P1 should have provided these
        from pathlib import Path
        root_path = str(Path(context.config.skill_root).resolve())
        skill_md_content = ""  # Will be populated by P1
        frontmatter: dict[str, Any] = {}
        
        # Get first node's path to extract root info (if available)
        for node in nodes.values():
            skill_md_path = Path(context.config.skill_root) / "SKILL.md"
            if skill_md_path.exists():
                skill_md_content = skill_md_path.read_text(encoding="utf-8")
            break

        graph = FileReferenceGraph(
            skill_id=skill_id,
            root_path=root_path,
            skill_md_content=skill_md_content,
            frontmatter=frontmatter,
            nodes=nodes,
            edges=edges,
        )

        # Assign roles
        file_role_map = assign_file_priorities(graph)

        context.logger.info(
            "[P2] Assigned priorities: %d docs (p1), %d scripts (p2), %d others (p3)",
            sum(1 for r in file_role_map.values() if r["read_priority"] == 1),
            sum(1 for r in file_role_map.values() if r["read_priority"] == 2),
            sum(1 for r in file_role_map.values() if r["read_priority"] == 3),
        )

        return file_role_map
