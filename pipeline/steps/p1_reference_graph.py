"""P1: Reference Graph Builder step."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from models import FileReferenceGraph
from pipeline.orchestrator.base import PipelineStep
from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.step_registry import registry
from pre_processing.p1_reference_graph import build_reference_graph


@registry.register
class P1ReferenceGraphStep(PipelineStep[Any, dict]):
    """P1: Build reference graph from skill files.

    This step recursively enumerates all files under the skill root,
    reads documentation files, and builds a graph of file references.

    Input:
        Initial pipeline inputs (not used, skill_root from context.config)

    Output:
        Dictionary containing:
        - skill_id: The skill package ID
        - nodes: List of FileNode dictionaries
        - edges: List of file reference edges
    """

    @property
    def name(self) -> str:
        """Step name for logging and checkpointing."""
        return "p1_reference_graph"

    @property
    def dependencies(self) -> list[str]:
        """P1 has no dependencies - it's the first step."""
        return []

    def execute(self, context: ExecutionContext, inputs: Any) -> dict:
        """Build reference graph.

        Args:
            context: Execution context with config
            inputs: Not used (empty dict or None)

        Returns:
            Dictionary with graph data
        """
        skill_root = context.config.skill_root
        context.logger.info("[P1] Building reference graph...")

        graph = build_reference_graph(skill_root)

        context.logger.info(
            "[P1] Found %d files, %d doc edges",
            len(graph.nodes),
            len(graph.edges),
        )

        # Convert to dictionary for serialization
        # graph.edges is dict[str, list[str]], not dataclass instances
        return {
            "skill_id": graph.skill_id,
            "nodes": [asdict(node) for node in graph.nodes.values()],
            "edges": dict(graph.edges),  # Already a dict, just copy it
        }
