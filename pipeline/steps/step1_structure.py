"""Step 1: Structure Extraction step."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from models import SectionBundle, SkillPackage, ToolSpec
from pipeline.llm_steps.step1_structure_extraction import run_step1_structure_extraction
from pipeline.orchestrator.base import PipelineStep
from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.step_registry import registry


@registry.register
class Step1StructureStep(PipelineStep[dict, dict]):
    """Step 1: Extract 8 canonical sections from SKILL.md.

    Uses LLM to parse the merged documentation into canonical sections:
    INTENT, WORKFLOW, CONSTRAINTS, TOOLS, ARTIFACTS, EVIDENCE, EXAMPLES, NOTES

    Also extracts network APIs from TOOLS section.

    Input:
        P3 output dictionary with package data

    Output:
        Dictionary containing:
        - section_bundle: SectionBundle as dict
        - network_apis: List of ToolSpec dicts
    """

    @property
    def name(self) -> str:
        """Step name for logging and checkpointing."""
        return "step1_structure"

    @property
    def dependencies(self) -> list[str]:
        """Step 1 depends on P3 output."""
        return ["p3_assembler"]

    def execute(self, context: ExecutionContext, inputs: dict) -> dict:
        """Extract structure from skill package.

        Args:
            context: Execution context with LLM client
            inputs: P3 output dictionary with package data

        Returns:
            Dictionary with section bundle and network APIs
        """
        context.logger.info("[Step 1] Extracting structure...")

        # Reconstruct SkillPackage from P3 output
        package_data = inputs if "merged_doc_text" in inputs else inputs.get("p3_assembler", inputs)

        # Get tools from package data
        tools_data = package_data.get("tools", [])
        from models import ToolSpec

        tools = [ToolSpec(**tool_data) for tool_data in tools_data]

        # Create SkillPackage with all required fields
        from pathlib import Path
        
        package = SkillPackage(
            skill_id=package_data["skill_id"],
            root_path=str(Path(context.config.skill_root).resolve()),
            frontmatter=package_data.get("frontmatter", {}),
            merged_doc_text=package_data["merged_doc_text"],
            file_role_map=package_data.get("file_role_map", {}),
            tools=tools,
        )

        # Add unified_apis if present
        if "unified_apis" in package_data:
            from models import UnifiedAPISpec

            package.unified_apis = [
                UnifiedAPISpec(**api_data) for api_data in package_data["unified_apis"]
            ]

        # Get model override if configured
        model = context.config.get_step_model("step1_structure_extraction")

        # Run Step 1
        bundle, network_apis = run_step1_structure_extraction(
            package=package,
            client=context.client,
            model=model,
        )

        context.logger.info(
            "[Step 1] Extracted %d items, %d network APIs",
            sum(len(getattr(bundle, s.lower())) for s in [
                "INTENT", "WORKFLOW", "CONSTRAINTS", "TOOLS",
                "ARTIFACTS", "EVIDENCE", "EXAMPLES", "NOTES"
            ]),
            len(network_apis),
        )

        # Convert to dictionary for serialization
        return {
            "section_bundle": asdict(bundle),
            "network_apis": [asdict(api) for api in network_apis],
        }
