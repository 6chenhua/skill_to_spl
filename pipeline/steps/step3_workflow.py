"""Step 3: Workflow Analysis step (W → IO → T)."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from models import SectionBundle
from models.pipeline_steps.step3.models import ActionType
from pipeline.llm_steps.step3 import run_step3_full_sync
from pipeline.orchestrator.base import PipelineStep
from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.step_registry import registry


@registry.register
class Step3WorkflowStep(PipelineStep[dict, dict]):
    """Step 3: Analyze workflow and extract entities.

    New architecture with three sub-steps:
    - Step 3-W: Workflow Structure Analysis
    - Step 3-IO: Global I/O + Type Analysis
    - Step 3-T: TYPES Declaration

    Input:
        Dictionary with Step 1 output (section_bundle)

    Output:
        Dictionary containing:
        - workflow_steps: List of WorkflowStep dicts
        - alternative_flows: List of AlternativeFlow dicts
        - exception_flows: List of ExceptionFlow dicts
        - step_io_specs: List of Step I/O spec dicts
        - global_registry: GlobalVarRegistry as dict
        - type_registry: Type registry dict
        - types_spl: TYPES declaration SPL text
        - declared_names: List of declared type names
    """

    @property
    def name(self) -> str:
        """Step name for logging and checkpointing."""
        return "step3_workflow"

    @property
    def dependencies(self) -> list[str]:
        """Step 3 depends on Step 1 output."""
        return ["step1_structure"]

    def execute(self, context: ExecutionContext, inputs: dict) -> dict:
        """Analyze workflow and extract entities.

        Args:
            context: Execution context with LLM client
            inputs: Dictionary with Step 1 output

        Returns:
            Dictionary with workflow analysis results
        """
        context.logger.info("[Step 3] Running workflow analysis (W → IO → T)...")

        # Get Step 1 output
        step1_data = inputs.get("step1_structure", inputs)

        # Reconstruct SectionBundle
        if isinstance(step1_data, dict) and "section_bundle" in step1_data:
            bundle_data = step1_data["section_bundle"]
        else:
            bundle_data = step1_data

        # Reconstruct SectionBundle with proper SectionItem objects
        from models import SectionItem
        
        def _reconstruct_section_items(items_data: list) -> list[SectionItem]:
            """Reconstruct SectionItem objects from dict/list data."""
            items = []
            for item_data in items_data:
                if isinstance(item_data, dict):
                    items.append(SectionItem(**item_data))
                elif isinstance(item_data, SectionItem):
                    items.append(item_data)
            return items
        
        bundle = SectionBundle(
            intent=_reconstruct_section_items(bundle_data.get("intent", [])),
            workflow=_reconstruct_section_items(bundle_data.get("workflow", [])),
            constraints=_reconstruct_section_items(bundle_data.get("constraints", [])),
            tools=_reconstruct_section_items(bundle_data.get("tools", [])),
            artifacts=_reconstruct_section_items(bundle_data.get("artifacts", [])),
            evidence=_reconstruct_section_items(bundle_data.get("evidence", [])),
            examples=_reconstruct_section_items(bundle_data.get("examples", [])),
            notes=_reconstruct_section_items(bundle_data.get("notes", [])),
        )

        # Get tools from P3 output (passed through inputs)
        available_tools: list[dict] = []
        p3_data = inputs.get("p3_assembler", {})
        if isinstance(p3_data, dict) and "tools" in p3_data:
            available_tools = [
                {"name": t.get("name", ""), "api_type": t.get("api_type", "SCRIPT")}
                for t in p3_data["tools"]
            ]

        # Get model override if configured
        model = context.config.get_step_model("step3") or context.config.llm_config.model

        # Run Step 3
        step3_result = run_step3_full_sync(
            workflow_section=bundle.to_text(["WORKFLOW"]),
            tools_section=bundle.to_text(["TOOLS"]),
            evidence_section=bundle.to_text(["EVIDENCE"]),
            artifacts_section=bundle.to_text(["ARTIFACTS"]),
            available_tools=available_tools,
            client=context.client,
            model=model,
        )

        # Convert WorkflowStepRaw to WorkflowStep for compatibility
        from models import WorkflowStep
        from models.step3_types import WorkflowStepRaw

        workflow_steps_raw = step3_result["workflow_steps"]
        workflow_steps = []

        for s in workflow_steps_raw:
            if isinstance(s, WorkflowStepRaw):
                workflow_steps.append(
                    WorkflowStep(
                        step_id=s.step_id,
                        description=s.description,
                        prerequisites=[],
                        produces=[],
                        action_type=s.action_type,
                        tool_hint=s.tool_hint,
                        is_validation_gate=s.is_validation_gate,
                        source_text=s.source_text,
                    )
                )
            elif isinstance(s, dict):
                workflow_steps.append(WorkflowStep(**s))
            else:
                workflow_steps.append(s)

        context.logger.info(
            "[Step 3] Extracted %d workflow steps, %d variables, %d files",
            len(workflow_steps),
            len(step3_result["global_registry"].variables),
            len(step3_result["global_registry"].files),
        )

        # Convert results to dictionary
        def _to_dict(obj):
            """Convert dataclass to dict, or return as-is if not dataclass."""
            if hasattr(obj, "__dataclass_fields__"):
                return asdict(obj)
            return obj

        def _convert_flow_steps(flows):
            """Convert flow steps from WorkflowStepRaw to dict."""
            result = []
            for flow in flows:
                if hasattr(flow, "__dataclass_fields__"):
                    flow_dict = asdict(flow)
                    # Also convert steps within the flow
                    if "steps" in flow_dict:
                        flow_dict["steps"] = [_to_dict(s) for s in flow_dict["steps"]]
                    result.append(flow_dict)
                else:
                    result.append(flow)
            return result

        result = {
            "workflow_steps": [_to_dict(s) for s in workflow_steps],
            "alternative_flows": _convert_flow_steps(step3_result.get("alternative_flows", [])),
            "exception_flows": _convert_flow_steps(step3_result.get("exception_flows", [])),
            "step_io_specs": [_to_dict(spec) for spec in step3_result["step_io_specs"]],
            "global_registry": asdict(step3_result["global_registry"]),
            "type_registry": step3_result.get("type_registry", {}),
            "types_spl": step3_result.get("types_spl", ""),
            "declared_names": step3_result.get("declared_names", []),
        }

        return result
