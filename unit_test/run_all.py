"""批量运行所有单元测试。

这个脚本可以按顺序运行所有 pipeline 步骤的单元测试，
自动处理步骤之间的依赖关系。

Usage:
    # 运行所有测试
    python -m unit_test.run_all --checkpoint output/pdf --output output/unit_tests

    # 运行指定范围的测试
    python -m unit_test.run_all --checkpoint output/pdf --from-step 1 --to-step 4

    # 从 Step 3 开始运行（自动使用之前的 checkpoint）
    python -m unit_test.run_all --checkpoint output/pdf --from-step 3

    # 使用特定模型
    python -m unit_test.run_all --checkpoint output/pdf --model gpt-4o-mini
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from unit_test.step1_structure import test_step1_structure
from unit_test.step1_5_api import test_step1_5_api
from unit_test.step3_workflow import test_step3_workflow
from unit_test.step4_spl import test_step4_spl

logger = logging.getLogger(__name__)


def check_checkpoint_exists(checkpoint_dir: Path, step: int) -> bool:
    """检查指定步骤的 checkpoint 是否存在。

    Args:
        checkpoint_dir: Checkpoint 目录
        step: 步骤编号 (1, 1.5, 3, 4)

    Returns:
        是否存在
    """
    if step == 1:
        return (checkpoint_dir / "p3_package.json").exists()
    elif step == 1.5:
        return (checkpoint_dir / "p3_package.json").exists()
    elif step == 3:
        return (checkpoint_dir / "step1_bundle.json").exists()
    elif step == 4:
        return (checkpoint_dir / "step3_structured_spec.json").exists()
    return False


def run_all_tests(
    checkpoint_dir: str | Path,
    output_dir: str | Path,
    from_step: float = 1,
    to_step: float = 4,
    model: str = "gpt-4o",
    api_key: str | None = None,
    max_workers: int = 4,
    skip_existing: bool = True,
) -> dict[str, Any]:
    """批量运行所有单元测试。

    Args:
        checkpoint_dir: 输入 checkpoint 目录
        output_dir: 输出目录
        from_step: 起始步骤 (1, 1.5, 3, 4)
        to_step: 结束步骤 (1, 1.5, 3, 4)
        model: LLM 模型
        api_key: API Key
        max_workers: 最大并行工作数
        skip_existing: 如果输出已存在则跳过

    Returns:
        所有结果的汇总
    """
    checkpoint_path = Path(checkpoint_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = {}
    start_time = time.time()

    # Step 1: Structure Extraction
    if from_step <= 1 <= to_step:
        logger.info("=" * 60)
        logger.info("Running Step 1: Structure Extraction")
        logger.info("=" * 60)

        step1_output = output_path / "step1_test"

        if skip_existing and (step1_output / "step1_structure_result.json").exists():
            logger.info("Step 1 output exists, skipping...")
            with open(step1_output / "step1_structure_result.json", "r", encoding="utf-8") as f:
                results["step1"] = json.load(f)
        elif check_checkpoint_exists(checkpoint_path, 1):
            try:
                result = test_step1_structure(
                    checkpoint_dir=checkpoint_path,
                    output_dir=step1_output,
                    model=model,
                    api_key=api_key,
                )
                results["step1"] = result
                logger.info("Step 1 completed successfully!\n")
            except Exception as e:
                logger.error(f"Step 1 failed: {e}")
                results["step1"] = {"error": str(e)}
        else:
            logger.warning(f"Step 1: Required checkpoint not found in {checkpoint_path}")
            results["step1"] = {"error": "Checkpoint not found"}

    # Step 1.5: API Definition Generation
    if from_step <= 1.5 <= to_step:
        logger.info("=" * 60)
        logger.info("Running Step 1.5: API Definition Generation")
        logger.info("=" * 60)

        step1_5_output = output_path / "step1_5_test"

        if skip_existing and (step1_5_output / "step1_5_api_result.json").exists():
            logger.info("Step 1.5 output exists, skipping...")
            with open(step1_5_output / "step1_5_api_result.json", "r", encoding="utf-8") as f:
                results["step1_5"] = json.load(f)
        elif check_checkpoint_exists(checkpoint_path, 1.5):
            try:
                result = test_step1_5_api(
                    checkpoint_dir=checkpoint_path,
                    output_dir=step1_5_output,
                    model=model,
                    api_key=api_key,
                    max_workers=max_workers,
                )
                results["step1_5"] = result
                logger.info("Step 1.5 completed successfully!\n")
            except Exception as e:
                logger.error(f"Step 1.5 failed: {e}")
                results["step1_5"] = {"error": str(e)}
        else:
            logger.warning(f"Step 1.5: Required checkpoint not found in {checkpoint_path}")
            results["step1_5"] = {"error": "Checkpoint not found"}

    # Step 3: Workflow Analysis
    if from_step <= 3 <= to_step:
        logger.info("=" * 60)
        logger.info("Running Step 3: Workflow Analysis")
        logger.info("=" * 60)

        step3_output = output_path / "step3_test"

        if skip_existing and (step3_output / "step3_workflow_result.json").exists():
            logger.info("Step 3 output exists, skipping...")
            with open(step3_output / "step3_workflow_result.json", "r", encoding="utf-8") as f:
                results["step3"] = json.load(f)
        elif check_checkpoint_exists(checkpoint_path, 3):
            try:
                result = test_step3_workflow(
                    checkpoint_dir=checkpoint_path,
                    output_dir=step3_output,
                    model=model,
                    api_key=api_key,
                )
                results["step3"] = result
                logger.info("Step 3 completed successfully!\n")
            except Exception as e:
                logger.error(f"Step 3 failed: {e}")
                results["step3"] = {"error": str(e)}
        else:
            logger.warning(f"Step 3: Required checkpoint not found in {checkpoint_path}")
            results["step3"] = {"error": "Checkpoint not found"}

    # Step 4: SPL Emission
    if from_step <= 4 <= to_step:
        logger.info("=" * 60)
        logger.info("Running Step 4: SPL Emission")
        logger.info("=" * 60)

        step4_output = output_path / "step4_test"

        if skip_existing and (step4_output / "step4_spl_result.json").exists():
            logger.info("Step 4 output exists, skipping...")
            with open(step4_output / "step4_spl_result.json", "r", encoding="utf-8") as f:
                results["step4"] = json.load(f)
        elif check_checkpoint_exists(checkpoint_path, 4):
            try:
                result = test_step4_spl(
                    checkpoint_dir=checkpoint_path,
                    output_dir=step4_output,
                    model=model,
                    api_key=api_key,
                )
                results["step4"] = result
                logger.info("Step 4 completed successfully!\n")
            except Exception as e:
                logger.error(f"Step 4 failed: {e}")
                results["step4"] = {"error": str(e)}
        else:
            logger.warning(f"Step 4: Required checkpoint not found in {checkpoint_path}")
            results["step4"] = {"error": "Checkpoint not found"}

    # Summary
    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("All Tests Summary")
    logger.info("=" * 60)
    logger.info(f"Total time: {elapsed:.2f}s")
    logger.info(f"Steps run: {len([r for r in results.values() if 'error' not in r])}/{len(results)}")

    for step_name, result in results.items():
        if "error" in result:
            logger.error(f"  {step_name}: FAILED - {result['error']}")
        else:
            logger.info(f"  {step_name}: SUCCESS")

    # Save summary
    summary_file = output_path / "test_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump({
            "total_time": elapsed,
            "steps_completed": len([r for r in results.values() if "error" not in r]),
            "steps_total": len(results),
            "results": results,
        }, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"\nSummary saved to: {summary_file}")

    return results


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Run all or specified pipeline step unit tests",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        required=True,
        help="Path to checkpoint directory",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/unit_tests",
        help="Output directory for all test results (default: output/unit_tests)",
    )
    parser.add_argument(
        "--from-step",
        type=float,
        default=1,
        choices=[1, 1.5, 3, 4],
        help="Start from which step (default: 1)",
    )
    parser.add_argument(
        "--to-step",
        type=float,
        default=4,
        choices=[1, 1.5, 3, 4],
        help="Run until which step (default: 4)",
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
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Don't skip existing outputs, re-run all",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    results = run_all_tests(
        checkpoint_dir=args.checkpoint,
        output_dir=args.output,
        from_step=args.from_step,
        to_step=args.to_step,
        model=args.model,
        api_key=args.api_key,
        max_workers=args.max_workers,
        skip_existing=not args.no_skip,
    )

    # Print final summary
    print("\n" + "=" * 60)
    print("Test Run Complete!")
    print("=" * 60)
    success_count = sum(1 for r in results.values() if "error" not in r)
    total_count = len(results)
    print(f"Success: {success_count}/{total_count} steps")

    if success_count == total_count:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed, check logs above")
        sys.exit(1)


if __name__ == "__main__":
    main()
