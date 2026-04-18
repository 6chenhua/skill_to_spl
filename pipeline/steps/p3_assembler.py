"""P3: Skill Package Assembler step."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from models import FileNode
from pipeline.orchestrator.base import PipelineStep
from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.step_registry import registry
from pre_processing.p3_assembler import assemble_skill_package


@registry.register
class P3AssemblerStep(PipelineStep[dict, dict]):
    """P3: Assemble skill package with merged documentation.

    Reads file contents, extracts API specs from scripts,
    and creates a consolidated package for Step 1.

    Input:
        Dictionary with "p1_output" and "p2_output" keys

    Output:
        Dictionary containing SkillPackage data:
        - skill_id: Package ID
        - merged_doc_text: Consolidated documentation
        - tools: List of ToolSpec dictionaries
        - unified_apis: List of UnifiedAPISpec dictionaries (if available)
    """

    @property
    def name(self) -> str:
        """Step name for logging and checkpointing."""
        return "p3_assembler"

    @property
    def dependencies(self) -> list[str]:
        """P3 depends on P1 and P2 outputs."""
        return ["p1_reference_graph", "p2_file_roles"]

    def execute(self, context: ExecutionContext, inputs: dict) -> dict:
        """Assemble skill package.

        Args:
            context: Execution context with LLM client
            inputs: Dictionary with P1 and P2 outputs

        Returns:
            Dictionary with package data
        """
        context.logger.info("[P3] Assembling skill package...")

        # Get P1 output
        p1_output = inputs.get("p1_reference_graph", inputs)

        # Reconstruct graph
        from models import FileNode, FileReferenceGraph, SkillPackage, ToolSpec

        nodes: dict[str, FileNode] = {}
        for node_data in p1_output["nodes"]:
            node = FileNode(**node_data)
            nodes[node.path] = node

        # Create edges from dict format
        # edges_data is dict[str, list[str]] mapping source -> [targets]
        # FileReferenceGraph expects edges as dict[str, list[str]], not FileEdge list
        edges: dict[str, list[str]] = p1_output["edges"]

        # Create graph with required fields
        from pathlib import Path
        root_path = str(Path(context.config.skill_root).resolve())
        skill_md_content = p1_output.get("skill_md_content", "")
        frontmatter = p1_output.get("frontmatter", {})

        graph = FileReferenceGraph(
            skill_id=p1_output["skill_id"],
            root_path=root_path,
            skill_md_content=skill_md_content,
            frontmatter=frontmatter,
            nodes=nodes,
            edges=edges,
        )

        # Get P2 output (file role map)
        # Note: In parallel execution, we might need to get this differently
        # For now, we assume the inputs dict contains both
        file_role_map_data = inputs.get("p2_file_roles", {})

        # Convert to FileRoleMap format expected by assembler
        file_role_map = file_role_map_data

        # Assemble package
        package = assemble_skill_package(
            graph=graph,
            file_role_map=file_role_map,
            client=context.client,
        )

        context.logger.info(
            "[P3] Assembled with %d pre-extracted tools", len(package.tools)
        )
        if getattr(package, "unified_apis", None):
            context.logger.info(
                "[P3] Extracted %d unified APIs", len(package.unified_apis)
            )

        # Convert to dictionary
        result = {
            "skill_id": package.skill_id,
            "merged_doc_text": package.merged_doc_text,
            "tools": [asdict(tool) for tool in package.tools],
        }

        if hasattr(package, "unified_apis") and package.unified_apis:
            from models import UnifiedAPISpec

            result["unified_apis"] = [
                asdict(api) if isinstance(api, UnifiedAPISpec) else api
                for api in package.unified_apis
            ]

        return result
