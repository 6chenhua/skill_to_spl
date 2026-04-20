"""Unit test for Step 3: Workflow Analysis.

This module allows running Step 3 (Workflow Analysis) independently
by loading inputs from checkpoint files.

Step 3 is composed of three sub-steps:
    - Step 3-W: Workflow Structure Analysis
    - Step 3-IO: Global I/O + Type Analysis
    - Step 3-T: TYPES Declaration

Input Requirements:
    - step1_bundle.json: SectionBundle with canonical sections

    Required fields:
        - section_bundle: dict with 8 canonical sections:
            - intent: list of SectionItem dicts
            - workflow: list of SectionItem dicts
            - constraints: list of SectionItem dicts
            - tools: list of SectionItem dicts
            - artifacts: list of SectionItem dicts
            - evidence: list of SectionItem dicts
            - examples: list of SectionItem dicts
            - notes: list of SectionItem dicts

    Optional inputs:
        - p3_package.json: For available_tools list

Output:
    - workflow_steps: List of WorkflowStep dicts
    - alternative_flows: List of AlternativeFlow dicts
    - exception_flows: List of ExceptionFlow dicts
    - step_io_specs: List of Step I/O spec dicts
    - global_registry: GlobalVarRegistry as dict
    - type_registry: Type registry dict
    - types_spl: TYPES declaration SPL text
    - declared_names: List of declared type names

Usage:
    # From code
    from unit_test.step3_workflow import test_step3_workflow
    result = test_step3_workflow("output/pdf")

    # From command line
    python -m unit_test.step3_workflow --checkpoint output/pdf/step1_bundle.json --output output/test_step3
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import SectionBundle, SectionItem
from models.pipeline_steps.step3.models import (
    AlternativeFlow,
    ExceptionFlow,
    WorkflowStep,
)
from models.step3_types import WorkflowStepRaw
from pipeline.llm_client import LLMClient, LLMConfig
from pipeline.llm_steps.step3 import run_step3_full_sync

logger = logging.getLogger(__name__)


def load_section_bundle(checkpoint_dir: str | Path) -> SectionBundle:
    """Load SectionBundle from Step 1 checkpoint.

    Args:
        checkpoint_dir: Directory containing step1_bundle.json

    Returns:
        Reconstructed SectionBundle object
    """
    checkpoint_path = Path(checkpoint_dir)

    # Load step1_bundle.json
    step1_file = checkpoint_path / "step1_bundle.json"
    if not step1_file.exists():
        raise FileNotFoundError(f"Step 1 bundle checkpoint not found: {step1_file}")

    with open(step1_file, "r", encoding="utf-8") as f:
        step1_data = json.load(f)

    bundle_data = step1_data.get("section_bundle", step1_data)

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

    return bundle


def load_available_tools(checkpoint_dir: str | Path) -> list[dict]:
    """Load available tools from P3 package checkpoint.

    Args:
        checkpoint_dir: Directory containing checkpoint files

    Returns:
        List of tool dictionaries with name and api_type
    """
    checkpoint_path = Path(checkpoint_dir)

    # Try to load from p3_package.json
    p3_file = checkpoint_path / "p3_package.json"
    if p3_file.exists():
        with open(p3_file, "r", encoding="utf-8") as f:
            p3_data = json.load(f)

        if "tools" in p3_data:
            return [
                {"name": t.get("name", ""), "api_type": t.get("api_type", "SCRIPT")}
                for t in p3_data["tools"]
            ]

    return []


def test_step3_workflow(
    checkpoint_dir: str | Path,
    output_dir: str | Path | None = None,
    model: str = "gpt-4o",
    api_key: str | None = None,
) -> dict:
    """Run Step 3: Workflow Analysis with checkpoint inputs.

    Args:
        checkpoint_dir: Directory containing step1_bundle.json
        output_dir: Optional output directory for results (defaults to checkpoint_dir/step3_test)
        model: LLM model to use
        api_key: Optional API key (reads from env if not provided)

    Returns:
        Dictionary with workflow analysis results:
            - workflow_steps: List of WorkflowStep dicts
            - alternative_flows: List of AlternativeFlow dicts
            - exception_flows: List of ExceptionFlow dicts
            - step_io_specs: List of Step I/O spec dicts
            - global_registry: GlobalVarRegistry as dict
            - type_registry: Type registry dict
            - types_spl: TYPES declaration SPL text
            - declared_names: List of declared type names
    """
    checkpoint_path = Path(checkpoint_dir)
    if output_dir is None:
        output_dir = checkpoint_path / "step3_test"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("=== Step 3: Workflow Analysis ===")
    logger.info("Checkpoint: %s", checkpoint_path)
    logger.info("Output: %s", output_path)

    # Load SectionBundle from Step 1
    logger.info("Loading SectionBundle from Step 1 checkpoint...")
    bundle = load_section_bundle(checkpoint_path)
    logger.info("Loaded SectionBundle with sections: intent=%d, workflow=%d, constraints=%d, "
                "tools=%d, artifacts=%d, evidence=%d, examples=%d, notes=%d",
                len(bundle.intent), len(bundle.workflow), len(bundle.constraints),
                len(bundle.tools), len(bundle.artifacts), len(bundle.evidence),
                len(bundle.examples), len(bundle.notes))

    # Load available tools from P3
    logger.info("Loading available tools from P3 checkpoint...")
    available_tools = load_available_tools(checkpoint_path)
    logger.info("Loaded %d available tools", len(available_tools))

    # Initialize LLM client
    llm_config = LLMConfig(model=model, max_tokens=16000)
    client = LLMClient(config=llm_config, api_key=api_key)

    # Prepare section texts
    workflow_section = bundle.to_text(["WORKFLOW"])
    tools_section = bundle.to_text(["TOOLS"])
    evidence_section = bundle.to_text(["EVIDENCE"])
    artifacts_section = bundle.to_text(["ARTIFACTS"])

    # Log section sizes
    logger.info("Workflow section: %d chars", len(workflow_section))
    logger.info("Tools section: %d chars", len(tools_section))
    logger.info("Evidence section: %d chars", len(evidence_section))
    logger.info("Artifacts section: %d chars", len(artifacts_section))

    # Run Step 3
    logger.info("Running Step 3 workflow analysis (W → IO → T)...")
    step3_result = run_step3_full_sync(
        workflow_section=workflow_section,
        tools_section=tools_section,
        evidence_section=evidence_section,
        artifacts_section=artifacts_section,
        available_tools=available_tools,
        client=client,
        model=model,
    )

    # Convert WorkflowStepRaw to WorkflowStep for compatibility
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

    logger.info("Extracted %d workflow steps", len(workflow_steps))
    logger.info("Global registry: %d variables, %d files",
                len(step3_result["global_registry"].variables),
                len(step3_result["global_registry"].files))

    # Convert results to dictionary
    from dataclasses import asdict

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

    # Save results
    result_file = output_path / "step3_workflow_result.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info("Results saved to: %s", result_file)

    # Also save types_spl separately for easy viewing
    if result["types_spl"]:
        types_file = output_path / "step3_types.spl"
        with open(types_file, "w", encoding="utf-8") as f:
            f.write(result["types_spl"])
        logger.info("TYPES SPL saved to: %s", types_file)

    return result


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Run Step 3: Workflow Analysis from checkpoint",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        required=True,
        help="Path to checkpoint directory containing step1_bundle.json",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory for results (default: checkpoint/step3_test)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o",
        help="LLM model to use (default: gpt-4o)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key (reads from OPENAI_API_KEY env var if not provided)",
    )

    args = parser.parse_args()

    result = test_step3_workflow(
        checkpoint_dir=args.checkpoint,
        output_dir=args.output,
        model=args.model,
        api_key=args.api_key,
    )

    print(f"\nStep 3 completed successfully!")
    print(f"  Workflow Steps: {len(result.get('workflow_steps', []))}")
    print(f"  Alternative Flows: {len(result.get('alternative_flows', []))}")
    print(f"  Exception Flows: {len(result.get('exception_flows', []))}")
    print(f"  Variables: {len(result.get('global_registry', {}).get('variables', {}))}")
    print(f"  Files: {len(result.get('global_registry', {}).get('files', {}))}")
    print(f"  TYPES Declarations: {len(result.get('declared_names', []))}")


if __name__ == "__main__":
    main()
