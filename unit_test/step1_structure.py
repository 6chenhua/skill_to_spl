"""Unit test for Step 1: Structure Extraction.

This module allows running Step 1 (Structure Extraction) independently
by loading inputs from checkpoint files.

Input Requirements:
    - p3_package.json: Package data with merged_doc_text, tools, frontmatter
    - p3_assembler output dict containing:
        - skill_id: str
        - merged_doc_text: str
        - frontmatter: dict
        - file_role_map: dict
        - tools: list of tool dicts
        - unified_apis (optional): list of UnifiedAPISpec dicts

Output:
    - section_bundle: SectionBundle as dict with 8 canonical sections
    - network_apis: List of ToolSpec dicts
    - skill_id: str

Usage:
    # From code
    from unit_test.step1_structure import test_step1_structure
    result = test_step1_structure("output/pdf")

    # From command line
    python -m unit_test.step1_structure --checkpoint output/pdf/p3_package.json --output output/test_step1
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

from models import SectionBundle, SkillPackage, ToolSpec, UnifiedAPISpec, FunctionSpec
from pipeline.llm_client import LLMClient, LLMConfig
from pipeline.llm_steps.step1_structure_extraction import run_step1_structure_extraction
from pipeline.orchestrator.checkpoint import CheckpointManager

logger = logging.getLogger(__name__)


def load_p3_package(checkpoint_dir: str | Path) -> dict:
    """Load P3 package data from checkpoint files.

    Args:
        checkpoint_dir: Directory containing checkpoint files

    Returns:
        Dictionary with package data
    """
    checkpoint_path = Path(checkpoint_dir)

    # Load p3_package.json
    p3_file = checkpoint_path / "p3_package.json"
    if not p3_file.exists():
        raise FileNotFoundError(f"P3 package checkpoint not found: {p3_file}")

    with open(p3_file, "r", encoding="utf-8") as f:
        package_data = json.load(f)

    # Load step1_bundle.json for additional context if available
    step1_file = checkpoint_path / "step1_bundle.json"
    if step1_file.exists():
        with open(step1_file, "r", encoding="utf-8") as f:
            step1_data = json.load(f)
            # Merge useful fields
            if "section_bundle" in step1_data:
                package_data["section_bundle_preview"] = step1_data["section_bundle"]

    return package_data


def reconstruct_skill_package(package_data: dict, skill_root: str | None = None) -> SkillPackage:
    """Reconstruct SkillPackage from checkpoint data.

    Args:
        package_data: Dictionary loaded from checkpoint
        skill_root: Optional skill root path (auto-detected if not provided)

    Returns:
        Reconstructed SkillPackage object
    """
    # Parse tools
    tools_data = package_data.get("tools", [])
    tools = [ToolSpec(**tool_data) for tool_data in tools_data]

    # Auto-detect skill root from checkpoint dir if not provided
    if skill_root is None:
        skill_id = package_data.get("skill_id", "unknown")
        skill_root = f"skills/{skill_id}"

    # Create SkillPackage
    package = SkillPackage(
        skill_id=package_data["skill_id"],
        root_path=str(Path(skill_root).resolve()),
        frontmatter=package_data.get("frontmatter", {}),
        merged_doc_text=package_data.get("merged_doc_text", ""),
        file_role_map=package_data.get("file_role_map", {}),
        tools=tools,
    )

    # Add unified_apis if present
    if "unified_apis" in package_data:
        unified_apis = []
        for api_data in package_data["unified_apis"]:
            if isinstance(api_data, dict):
                # Convert nested functions
                functions_data = api_data.get("functions", [])
                functions = [
                    FunctionSpec(**f) if isinstance(f, dict) else f
                    for f in functions_data
                ]
                unified_apis.append(UnifiedAPISpec(**{**api_data, "functions": functions}))
            elif hasattr(api_data, "__dataclass_fields__"):
                unified_apis.append(UnifiedAPISpec(**api_data.__dict__))
        package.unified_apis = unified_apis

    return package


def test_step1_structure(
    checkpoint_dir: str | Path,
    output_dir: str | Path | None = None,
    model: str = "gpt-4o",
    api_key: str | None = None,
    skill_root: str | None = None,
) -> dict:
    """Run Step 1: Structure Extraction with checkpoint inputs.

    Args:
        checkpoint_dir: Directory containing p3_package.json
        output_dir: Optional output directory for results (defaults to checkpoint_dir/step1_test)
        model: LLM model to use
        api_key: Optional API key (reads from env if not provided)
        skill_root: Optional skill root path

    Returns:
        Dictionary with step1_structure output:
            - skill_id: str
            - section_bundle: SectionBundle as dict
            - network_apis: List of ToolSpec dicts
    """
    checkpoint_path = Path(checkpoint_dir)
    if output_dir is None:
        output_dir = checkpoint_path / "step1_test"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("=== Step 1: Structure Extraction ===")
    logger.info("Checkpoint: %s", checkpoint_path)
    logger.info("Output: %s", output_path)

    # Load P3 package data
    logger.info("Loading P3 package checkpoint...")
    package_data = load_p3_package(checkpoint_path)
    logger.info("Loaded package for skill: %s", package_data.get("skill_id", "unknown"))

    # Reconstruct SkillPackage
    package = reconstruct_skill_package(package_data, skill_root)
    logger.info("Reconstructed SkillPackage with %d tools", len(package.tools))

    # Initialize LLM client
    llm_config = LLMConfig(model=model, max_tokens=16000)
    client = LLMClient(config=llm_config, api_key=api_key)

    # Run Step 1
    logger.info("Running Step 1 structure extraction...")
    bundle, network_apis = run_step1_structure_extraction(
        package=package,
        client=client,
        model=model,
    )

    # Prepare output
    from dataclasses import asdict
    result = {
        "skill_id": package.skill_id,
        "section_bundle": asdict(bundle),
        "network_apis": [asdict(api) for api in network_apis],
    }

    # Save results
    result_file = output_path / "step1_structure_result.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info("Results saved to: %s", result_file)

    # Print summary
    total_items = sum(
        len(getattr(bundle, section.lower()))
        for section in ["INTENT", "WORKFLOW", "CONSTRAINTS", "TOOLS", "ARTIFACTS", "EVIDENCE", "EXAMPLES", "NOTES"]
    )
    logger.info("Extracted %d section items", total_items)
    logger.info("Extracted %d network APIs", len(network_apis))

    return result


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Run Step 1: Structure Extraction from checkpoint",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        required=True,
        help="Path to checkpoint directory containing p3_package.json",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory for results (default: checkpoint/step1_test)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o",
        help="LLM model to use (default: gpt-4o)",
    )
    parser.add_argument(
        "--skill-root",
        type=str,
        default=None,
        help="Skill root path (auto-detected if not provided)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key (reads from OPENAI_API_KEY env var if not provided)",
    )

    args = parser.parse_args()

    result = test_step1_structure(
        checkpoint_dir=args.checkpoint,
        output_dir=args.output,
        model=args.model,
        api_key=args.api_key,
        skill_root=args.skill_root,
    )

    print(f"\nStep 1 completed successfully!")
    print(f"  Skill ID: {result['skill_id']}")
    print(f"  Network APIs: {len(result['network_apis'])}")


if __name__ == "__main__":
    main()
