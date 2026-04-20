"""Unit test for Step 1.5: API Definition Generation.

This module allows running Step 1.5 (API Definition Generation) independently
by loading inputs from checkpoint files.

Input Requirements:
    - p3_package.json: Package data containing unified_apis
    - step1_structure.json (optional): Step 1 output for reference

    Required fields from checkpoint:
        - unified_apis: list of UnifiedAPISpec dicts with:
            - api_id: str
            - api_name: str
            - source: str
            - api_type: str (DOC or SCRIPT)
            - functions: list of FunctionSpec dicts with:
                - name: str
                - signature: str
                - description: str
                - return_type: str
                - parameters: list
                - is_async: bool
                - docstring: str

Output:
    - apis: Dict mapping API name to APISpec dict

Usage:
    # From code
    from unit_test.step1_5_api import test_step1_5_api
    result = test_step1_5_api("output/pdf")

    # From command line
    python -m unit_test.step1_5_api --checkpoint output/pdf/p3_package.json --output output/test_step1_5
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

from models import APISymbolTable, FunctionSpec, UnifiedAPISpec
from pipeline.llm_client import LLMClient, LLMConfig
from pipeline.llm_steps.step1_5_api_generation import generate_unified_api_definitions

logger = logging.getLogger(__name__)


def load_unified_apis(checkpoint_dir: str | Path) -> list[UnifiedAPISpec]:
    """Load unified APIs from P3 checkpoint.

    Args:
        checkpoint_dir: Directory containing checkpoint files

    Returns:
        List of UnifiedAPISpec objects
    """
    checkpoint_path = Path(checkpoint_dir)

    # Load p3_package.json
    p3_file = checkpoint_path / "p3_package.json"
    if not p3_file.exists():
        raise FileNotFoundError(f"P3 package checkpoint not found: {p3_file}")

    with open(p3_file, "r", encoding="utf-8") as f:
        package_data = json.load(f)

    unified_apis: list[UnifiedAPISpec] = []

    if "unified_apis" not in package_data:
        logger.warning("No unified_apis found in P3 package")
        return unified_apis

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

    return unified_apis


def test_step1_5_api(
    checkpoint_dir: str | Path,
    output_dir: str | Path | None = None,
    model: str = "gpt-4o",
    api_key: str | None = None,
    max_workers: int = 4,
) -> dict:
    """Run Step 1.5: API Definition Generation with checkpoint inputs.

    Args:
        checkpoint_dir: Directory containing p3_package.json with unified_apis
        output_dir: Optional output directory for results (defaults to checkpoint_dir/step1_5_test)
        model: LLM model to use
        api_key: Optional API key (reads from env if not provided)
        max_workers: Maximum parallel workers for API generation

    Returns:
        Dictionary with API definitions:
            - apis: Dict mapping API name to APISpec dict
    """
    checkpoint_path = Path(checkpoint_dir)
    if output_dir is None:
        output_dir = checkpoint_path / "step1_5_test"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("=== Step 1.5: API Definition Generation ===")
    logger.info("Checkpoint: %s", checkpoint_path)
    logger.info("Output: %s", output_path)

    # Load unified APIs
    logger.info("Loading unified APIs from P3 checkpoint...")
    unified_apis = load_unified_apis(checkpoint_path)
    logger.info("Loaded %d unified APIs", len(unified_apis))

    if not unified_apis:
        logger.warning("No unified APIs found, returning empty API table")
        result = {"apis": {}}

        # Save empty result
        result_file = output_path / "step1_5_api_result.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info("Empty results saved to: %s", result_file)
        return result

    # Log API details
    for api in unified_apis:
        logger.debug("  - %s (%s): %d functions", api.api_name, api.source, len(api.functions))

    # Initialize LLM client
    llm_config = LLMConfig(model=model, max_tokens=16000)
    client = LLMClient(config=llm_config, api_key=api_key)

    # Generate API definitions
    logger.info("Generating API definitions...")
    api_table = generate_unified_api_definitions(
        unified_apis=unified_apis,
        client=client,
        max_workers=max_workers,
        model=model,
    )

    logger.info("Generated %d API definitions", len(api_table.apis))

    # Prepare output
    from dataclasses import asdict
    result = {
        "apis": {
            name: asdict(spec) for name, spec in api_table.apis.items()
        },
    }

    # Save results
    result_file = output_path / "step1_5_api_result.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info("Results saved to: %s", result_file)

    # Also save a human-readable summary
    summary_file = output_path / "api_summary.txt"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"API Definitions Summary\n")
        f.write(f"=" * 50 + "\n\n")
        f.write(f"Total APIs: {len(api_table.apis)}\n\n")
        for name, spec in api_table.apis.items():
            f.write(f"\n{name}:\n")
            f.write(f"  Source: {spec.source}\n")
            if hasattr(spec, 'spl_block') and spec.spl_block:
                f.write(f"  SPL Block:\n")
                f.write(f"    {spec.spl_block[:200]}...\n" if len(spec.spl_block) > 200 else f"    {spec.spl_block}\n")

    logger.info("Summary saved to: %s", summary_file)

    return result


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Run Step 1.5: API Definition Generation from checkpoint",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        required=True,
        help="Path to checkpoint directory containing p3_package.json with unified_apis",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory for results (default: checkpoint/step1_5_test)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o",
        help="LLM model to use (default: gpt-4o)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum parallel workers (default: 4)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key (reads from OPENAI_API_KEY env var if not provided)",
    )

    args = parser.parse_args()

    result = test_step1_5_api(
        checkpoint_dir=args.checkpoint,
        output_dir=args.output,
        model=args.model,
        api_key=args.api_key,
        max_workers=args.max_workers,
    )

    print(f"\nStep 1.5 completed successfully!")
    print(f"  Generated APIs: {len(result['apis'])}")
    for api_name in result['apis'].keys():
        print(f"    - {api_name}")


if __name__ == "__main__":
    main()
