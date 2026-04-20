"""Unit test for Step 4 individual sub-steps.

这个模块允许单独运行 Step 4 的每个子步骤（S0, S4A-F, S4E1-E2），
用于调试特定的子步骤而无需运行完整的 Step 4。

子步骤依赖关系：
    S4C (Variables/Files) ─┐
                          ├→ S4A, S4B, S0 (并行)
    S4D (APIs) ────────────┤
                          ↓
                         S4E (Worker) → S4E1 (检测) → S4E2 (修复)
                          ↓
                         S4F (Examples)

Usage:
    # 运行 S4C (必须先运行，生成 symbol_table)
    python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4c

    # 运行 S4A
    python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4a

    # 运行 S4E (需要 S4C 输出的 symbol_table)
    python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4e

    # 运行 S4E1 (嵌套检测)
    python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4e1

    # 运行 S4E2 (嵌套修复)
    python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4e2
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import (
    AlternativeFlow,
    EntitySpec,
    ExceptionFlow,
    SectionBundle,
    SectionItem,
    SPLSpec,
    StructuredSpec,
    WorkflowStep,
)
from models.pipeline_steps.step3.models import FlowStep
from pipeline.llm_client import LLMClient, LLMConfig
from pipeline.llm_steps.step4_spl_emission import (
    _assemble_spl,
    _build_review_summary,
    _call_4a,
    _call_4b,
    _call_4c,
    _call_4e,
    _call_4f,
    _call_s0,
    _extract_symbol_table,
    _format_symbol_table,
    _prepare_step4_inputs_parallel,
    validate_and_fix_worker_nesting,
)

logger = logging.getLogger(__name__)

# Available sub-steps
SUBSTEPS = ["s0", "s4a", "s4b", "s4c", "s4d", "s4e", "s4e1", "s4e2", "s4f"]


def load_step3_results(checkpoint_dir: Path) -> dict:
    """加载 Step 3 的结果。"""
    step3_file = checkpoint_dir / "step3_structured_spec.json"
    if not step3_file.exists():
        raise FileNotFoundError(f"Step 3 results not found: {step3_file}")

    with open(step3_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_step1_bundle(checkpoint_dir: Path) -> SectionBundle:
    """加载 Step 1 的 section bundle。"""
    step1_file = checkpoint_dir / "step1_bundle.json"
    if not step1_file.exists():
        raise FileNotFoundError(f"Step 1 bundle not found: {step1_file}")

    with open(step1_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    bundle_data = data.get("section_bundle", data)

    def _reconstruct_section_items(items_data: list) -> list[SectionItem]:
        items = []
        for item_data in items_data:
            if isinstance(item_data, dict):
                items.append(SectionItem(**item_data))
            elif isinstance(item_data, SectionItem):
                items.append(item_data)
        return items

    return SectionBundle(
        intent=_reconstruct_section_items(bundle_data.get("intent", [])),
        workflow=_reconstruct_section_items(bundle_data.get("workflow", [])),
        constraints=_reconstruct_section_items(bundle_data.get("constraints", [])),
        tools=_reconstruct_section_items(bundle_data.get("tools", [])),
        artifacts=_reconstruct_section_items(bundle_data.get("artifacts", [])),
        evidence=_reconstruct_section_items(bundle_data.get("evidence", [])),
        examples=_reconstruct_section_items(bundle_data.get("examples", [])),
        notes=_reconstruct_section_items(bundle_data.get("notes", [])),
    )


def load_step1_5_results(checkpoint_dir: Path) -> dict:
    """加载 Step 1.5 的 API 结果。"""
    # 优先从单元测试输出加载，否则从原始 checkpoint 加载
    api_file = checkpoint_dir / "step1_5_test" / "step1_5_api_result.json"
    if api_file.exists():
        with open(api_file, "r", encoding="utf-8") as f:
            return json.load(f)

    # 尝试从 checkpoint 目录本身加载
    api_file = checkpoint_dir / "step1_5_api_result.json"
    if api_file.exists():
        with open(api_file, "r", encoding="utf-8") as f:
            return json.load(f)

    logger.warning("Step 1.5 results not found, S4D will be skipped")
    return {"apis": {}}


def load_previous_substep_output(checkpoint_dir: Path, substep: str) -> Any:
    """加载之前子步骤的输出。"""
    substep_file = checkpoint_dir / f"step{substep}_test" / f"step{substep}_output.txt"

    # 尝试从单元测试输出目录加载
    test_output = checkpoint_dir / f"step4_substep_test" / f"step{substep}_output.txt"
    if test_output.exists():
        with open(test_output, "r", encoding="utf-8") as f:
            return f.read()

    # 尝试从原始 checkpoint 加载
    original_files = {
        "s4c": "step4c_variables_files.json",
        "s4a": "step4a_persona.json",
        "s4b": "step4b_constraints.json",
        "s4d": "step4d_apis.json",
        "s4e": "step4e_worker_original.json",
        "s4e1": "step4e1_nesting_detection.json",
        "s4e2": "step4e2_nesting_fix.json",
        "s4f": "step4f_examples.json",
        "s0": None,  # S0 通常不单独保存
    }

    if substep in original_files and original_files[substep]:
        file_path = checkpoint_dir / original_files[substep]
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 有些文件保存的是字符串，有些是 dict
                if isinstance(data, str):
                    return data
                elif isinstance(data, dict) and "content" in data:
                    return data["content"]
                return json.dumps(data, indent=2)

    return None


def reconstruct_entities(step3_data: dict) -> list[EntitySpec]:
    """从 Step 3 数据重建 EntitySpec 列表。"""
    entities = []
    for entity_data in step3_data.get("entities", []):
        if isinstance(entity_data, dict):
            entities.append(EntitySpec(**entity_data))
    return entities


def reconstruct_workflow_steps(step3_data: dict) -> list[WorkflowStep]:
    """从 Step 3 数据重建 WorkflowStep 列表。"""
    workflow_steps = []
    for step_data in step3_data.get("workflow_steps", []):
        if isinstance(step_data, dict):
            workflow_steps.append(WorkflowStep(**step_data))
    return workflow_steps


def reconstruct_flows(step3_data: dict) -> tuple[list[AlternativeFlow], list[ExceptionFlow]]:
    """从 Step 3 数据重建 Flow 列表。"""
    alternative_flows = []
    exception_flows = []

    for flow_data in step3_data.get("alternative_flows", []):
        if isinstance(flow_data, dict):
            steps = []
            for step_data_item in flow_data.get("steps", []):
                if isinstance(step_data_item, dict):
                    valid_fields = {k: v for k, v in step_data_item.items() if k in FlowStep.__dataclass_fields__}
                    steps.append(FlowStep(**valid_fields))
            flow_data["steps"] = steps
            alternative_flows.append(AlternativeFlow(**flow_data))

    for flow_data in step3_data.get("exception_flows", []):
        if isinstance(flow_data, dict):
            steps = []
            for step_data_item in flow_data.get("steps", []):
                if isinstance(step_data_item, dict):
                    valid_fields = {k: v for k, v in step_data_item.items() if k in FlowStep.__dataclass_fields__}
                    steps.append(FlowStep(**valid_fields))
            flow_data["steps"] = steps
            exception_flows.append(ExceptionFlow(**flow_data))

    return alternative_flows, exception_flows


def run_s4c(
    checkpoint_dir: Path,
    output_dir: Path,
    client: LLMClient,
    model: str,
) -> dict:
    """运行 S4C: Variables/Files。"""
    logger.info("=" * 60)
    logger.info("Running S4C: Variables/Files")
    logger.info("=" * 60)

    # 加载输入
    step3_data = load_step3_results(checkpoint_dir)
    bundle = load_step1_bundle(checkpoint_dir)
    entities = reconstruct_entities(step3_data)
    type_registry = step3_data.get("type_registry", {})

    logger.info("Loaded %d entities", len(entities))

    # 准备输入
    s4c_inputs = {
        "entities_text": _format_entities(entities),
        "omit_files_text": "",
        "has_entities": bool(entities),
        "types_text": _format_types(type_registry),
        "type_registry": type_registry,
    }

    # 运行 S4C
    block_4c = _call_4c(client, s4c_inputs, model=model, output_dir=output_dir)

    # 提取 symbol_table
    symbol_table = _extract_symbol_table(block_4c)
    symbol_table_text = _format_symbol_table(symbol_table)

    # 保存结果
    result = {
        "block": block_4c,
        "symbol_table": symbol_table,
        "symbol_table_text": symbol_table_text,
    }

    output_file = output_dir / "step4c_output.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(block_4c)
    logger.info("S4C output saved to: %s", output_file)

    symbol_file = output_dir / "symbol_table.json"
    with open(symbol_file, "w", encoding="utf-8") as f:
        json.dump(symbol_table, f, indent=2)
    logger.info("Symbol table saved to: %s", symbol_file)

    logger.info("S4C completed: %d types, %d variables, %d files",
                len(symbol_table.get("types", [])),
                len(symbol_table["variables"]),
                len(symbol_table["files"]))

    return result


def run_s0(
    checkpoint_dir: Path,
    output_dir: Path,
    client: LLMClient,
    model: str,
) -> str:
    """运行 S0: DEFINE_AGENT header。"""
    logger.info("=" * 60)
    logger.info("Running S0: DEFINE_AGENT Header")
    logger.info("=" * 60)

    bundle = load_step1_bundle(checkpoint_dir)
    step3_data = load_step3_results(checkpoint_dir)
    skill_id = step3_data.get("skill_id", "unknown")

    intent_text = bundle.to_text(["INTENT"])
    notes_text = bundle.to_text(["NOTES"])

    block_s0 = _call_s0(client, skill_id, intent_text, notes_text, model=model, output_dir=output_dir)

    output_file = output_dir / "steps0_output.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(block_s0)
    logger.info("S0 output saved to: %s", output_file)

    return block_s0


def run_s4a(
    checkpoint_dir: Path,
    output_dir: Path,
    client: LLMClient,
    model: str,
    symbol_table_text: str | None = None,
) -> str:
    """运行 S4A: Persona/Audience/Concepts。"""
    logger.info("=" * 60)
    logger.info("Running S4A: Persona/Audience/Concepts")
    logger.info("=" * 60)

    bundle = load_step1_bundle(checkpoint_dir)

    # 如果没有提供 symbol_table，尝试加载
    if symbol_table_text is None:
        symbol_table = load_previous_substep_output(checkpoint_dir, "s4c")
        if symbol_table:
            symbol_table_text = symbol_table if isinstance(symbol_table, str) else json.dumps(symbol_table)
        else:
            logger.warning("No symbol_table found, S4A may produce suboptimal results")
            symbol_table_text = ""

    s4a_inputs = {
        "intent_text": bundle.to_text(["INTENT"]),
        "notes_text": bundle.to_text(["NOTES"]),
    }

    block_4a = _call_4a(client, s4a_inputs, symbol_table_text, model=model, output_dir=output_dir)

    output_file = output_dir / "step4a_output.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(block_4a)
    logger.info("S4A output saved to: %s", output_file)

    return block_4a


def run_s4b(
    checkpoint_dir: Path,
    output_dir: Path,
    client: LLMClient,
    model: str,
    symbol_table_text: str | None = None,
) -> str:
    """运行 S4B: Constraints。"""
    logger.info("=" * 60)
    logger.info("Running S4B: Constraints")
    logger.info("=" * 60)

    bundle = load_step1_bundle(checkpoint_dir)

    # 如果没有提供 symbol_table，尝试加载
    if symbol_table_text is None:
        symbol_table = load_previous_substep_output(checkpoint_dir, "s4c")
        if symbol_table:
            symbol_table_text = symbol_table if isinstance(symbol_table, str) else json.dumps(symbol_table)
        else:
            logger.warning("No symbol_table found, S4B may produce suboptimal results")
            symbol_table_text = ""

    constraints_text = bundle.to_text(["CONSTRAINTS"])
    has_constraints = bool(constraints_text.strip())

    s4b_inputs = {
        "constraints_text": constraints_text,
        "has_constraints": has_constraints,
    }

    block_4b = _call_4b(client, s4b_inputs, symbol_table_text, model=model, output_dir=output_dir)

    output_file = output_dir / "step4b_output.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(block_4b)
    logger.info("S4B output saved to: %s", output_file)

    return block_4b


def run_s4d(
    checkpoint_dir: Path,
    output_dir: Path,
    client: LLMClient,
    model: str,
) -> str:
    """运行 S4D: APIs。"""
    logger.info("=" * 60)
    logger.info("Running S4D: APIs")
    logger.info("=" * 60)

    # 加载 Step 1.5 的 API 结果
    api_results = load_step1_5_results(checkpoint_dir)

    # S4D 现在主要是合并 API SPL 块
    from pipeline.llm_steps.step1_5_api_generation import merge_api_spl_blocks
    from models import APISymbolTable, APISpec

    api_table = APISymbolTable(
        apis={
            name: APISpec(**spec_data)
            for name, spec_data in api_results.get("apis", {}).items()
        }
    )

    block_4d = merge_api_spl_blocks(api_table)

    output_file = output_dir / "step4d_output.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(block_4d)
    logger.info("S4D output saved to: %s", output_file)
    logger.info("APIs block: %d chars", len(block_4d))

    return block_4d


def run_s4e(
    checkpoint_dir: Path,
    output_dir: Path,
    client: LLMClient,
    model: str,
    symbol_table_text: str | None = None,
    block_4d: str | None = None,
) -> str:
    """运行 S4E: Worker。"""
    logger.info("=" * 60)
    logger.info("Running S4E: Worker")
    logger.info("=" * 60)

    # 加载输入
    step3_data = load_step3_results(checkpoint_dir)
    bundle = load_step1_bundle(checkpoint_dir)

    workflow_steps = reconstruct_workflow_steps(step3_data)
    alternative_flows, exception_flows = reconstruct_flows(step3_data)

    # 加载 symbol_table
    if symbol_table_text is None:
        symbol_table = load_previous_substep_output(checkpoint_dir, "s4c")
        if symbol_table:
            if isinstance(symbol_table, str):
                symbol_table_text = symbol_table
            else:
                symbol_table_text = json.dumps(symbol_table)
        else:
            logger.warning("No symbol_table found for S4E")
            symbol_table_text = ""

    # 加载 APIs
    if block_4d is None:
        block_4d = load_previous_substep_output(checkpoint_dir, "s4d") or ""

    # 准备 S4E 输入
    import dataclasses
    api_steps = [s for s in workflow_steps if s.action_type in ["EXTERNAL_API", "EXEC_SCRIPT", "LOCAL_CODE_SNIPPET"]]
    api_steps_list = [_step_to_dict(s) for s in api_steps]

    s4e_inputs = {
        "workflow_steps_json": json.dumps([_step_to_dict(s) for s in workflow_steps], indent=2, ensure_ascii=False),
        "workflow_prose": bundle.to_text(["WORKFLOW"]),
        "alternative_flows_json": json.dumps([dataclasses.asdict(f) for f in alternative_flows], indent=2, ensure_ascii=False),
        "exception_flows_json": json.dumps([dataclasses.asdict(f) for f in exception_flows], indent=2, ensure_ascii=False),
        "tools_list": api_steps_list,
    }

    block_4e = _call_4e(client, s4e_inputs, symbol_table_text, block_4d, model=model, output_dir=output_dir)

    output_file = output_dir / "step4e_output.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(block_4e)
    logger.info("S4E output saved to: %s", output_file)
    logger.info("Worker block: %d chars", len(block_4e))

    return block_4e


def run_s4e1(
    checkpoint_dir: Path,
    output_dir: Path,
    client: LLMClient,
    model: str,
    worker_spl: str | None = None,
) -> dict:
    """运行 S4E1: Nesting Detection。"""
    logger.info("=" * 60)
    logger.info("Running S4E1: Nesting Detection")
    logger.info("=" * 60)

    if worker_spl is None:
        worker_spl = load_previous_substep_output(checkpoint_dir, "s4e")
        if not worker_spl:
            raise ValueError("S4E output not found. Please run S4E first.")

    # 运行嵌套检测
    _, detection_result = validate_and_fix_worker_nesting(
        client, worker_spl, model=model, output_dir=output_dir
    )

    # 保存结果
    output_file = output_dir / "step4e1_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(detection_result, f, indent=2)
    logger.info("S4E1 result saved to: %s", output_file)

    if detection_result.get("has_violations"):
        logger.warning("Found %d nested BLOCK violations", len(detection_result.get("violations", [])))
        for v in detection_result.get("violations", [])[:5]:
            logger.warning("  - %s inside %s", v.get("inner_block", "?"), v.get("outer_block", "?"))
    else:
        logger.info("No nested BLOCK violations found")

    return detection_result


def run_s4e2(
    checkpoint_dir: Path,
    output_dir: Path,
    client: LLMClient,
    model: str,
    worker_spl: str | None = None,
    violations: list | None = None,
) -> str:
    """运行 S4E2: Nesting Fix。"""
    logger.info("=" * 60)
    logger.info("Running S4E2: Nesting Fix")
    logger.info("=" * 60)

    if worker_spl is None:
        worker_spl = load_previous_substep_output(checkpoint_dir, "s4e")
        if not worker_spl:
            raise ValueError("S4E output not found. Please run S4E first.")

    # 如果没有提供 violations，尝试加载 S4E1 的结果
    if violations is None:
        s4e1_file = output_dir / "step4e1_result.json"
        if s4e1_file.exists():
            with open(s4e1_file, "r", encoding="utf-8") as f:
                detection_result = json.load(f)
                violations = detection_result.get("violations", [])
        else:
            # 从 checkpoint 目录加载
            s4e1_file = checkpoint_dir / "step4e1_nesting_detection.json"
            if s4e1_file.exists():
                with open(s4e1_file, "r", encoding="utf-8") as f:
                    detection_result = json.load(f)
                    violations = detection_result.get("violations", [])
            else:
                violations = []

    if not violations:
        logger.info("No violations to fix, returning original S4E output")
        fixed_spl = worker_spl
    else:
        logger.info("Fixing %d violations...", len(violations))
        from pipeline.llm_steps.step4_spl_emission.nesting_validation import _call_4e2_async
        import asyncio

        fixed_spl = asyncio.run(_call_4e2_async(client, worker_spl, violations, model=model, output_dir=output_dir))

    output_file = output_dir / "step4e2_output.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(fixed_spl)
    logger.info("S4E2 output saved to: %s", output_file)

    return fixed_spl


def run_s4f(
    checkpoint_dir: Path,
    output_dir: Path,
    client: LLMClient,
    model: str,
    worker_spl: str | None = None,
) -> str:
    """运行 S4F: Examples。"""
    logger.info("=" * 60)
    logger.info("Running S4F: Examples")
    logger.info("=" * 60)

    bundle = load_step1_bundle(checkpoint_dir)
    examples_text = bundle.to_text(["EXAMPLES"])

    if not examples_text.strip():
        logger.info("No examples found in bundle, skipping S4F")
        return ""

    # 加载 worker_spl
    if worker_spl is None:
        worker_spl = load_previous_substep_output(checkpoint_dir, "s4e2") or load_previous_substep_output(checkpoint_dir, "s4e")
        if not worker_spl:
            logger.warning("No worker SPL found, S4F may produce suboptimal results")
            worker_spl = ""

    s4f_inputs = {
        "examples_text": examples_text,
        "has_examples": True,
    }

    block_4f = _call_4f(client, s4f_inputs, worker_spl, model=model, output_dir=output_dir)

    output_file = output_dir / "step4f_output.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(block_4f)
    logger.info("S4F output saved to: %s", output_file)

    return block_4f


# Helper functions

def _format_entities(entities: list[EntitySpec]) -> str:
    """格式化实体列表为文本。"""
    lines = []
    for e in entities:
        lines.append(f"Entity: {e.entity_id}")
        lines.append(f"  Kind: {e.kind}")
        lines.append(f"  Type: {e.type_name}")
        lines.append(f"  Schema: {e.schema_notes}")
        lines.append(f"  Source: {e.source_text[:100]}..." if len(e.source_text) > 100 else f"  Source: {e.source_text}")
        lines.append("")
    return "\n".join(lines)


def _format_types(type_registry: dict) -> str:
    """格式化类型注册表为文本。"""
    if not type_registry:
        return ""
    return json.dumps(type_registry, indent=2, ensure_ascii=False)


def _step_to_dict(s: WorkflowStep) -> dict:
    """将 WorkflowStep 转换为 dict。"""
    return asdict(s)


def test_substep(
    checkpoint_dir: str | Path,
    substep: str,
    output_dir: str | Path | None = None,
    model: str = "gpt-4o",
    api_key: str | None = None,
    **kwargs,
) -> Any:
    """运行指定的 Step 4 子步骤。

    Args:
        checkpoint_dir: Checkpoint 目录
        substep: 子步骤名称 (s0, s4a, s4b, s4c, s4d, s4e, s4e1, s4e2, s4f)
        output_dir: 输出目录
        model: LLM 模型
        api_key: API Key
        **kwargs: 额外参数（如 symbol_table_text, block_4d 等）

    Returns:
        子步骤的输出结果
    """
    checkpoint_path = Path(checkpoint_dir)
    if output_dir is None:
        output_dir = checkpoint_path / "step4_substep_test"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("=" * 60)
    logger.info("Step 4 Sub-step Test: %s", substep.upper())
    logger.info("=" * 60)
    logger.info("Checkpoint: %s", checkpoint_path)
    logger.info("Output: %s", output_path)

    # Initialize LLM client
    llm_config = LLMConfig(model=model, max_tokens=16000)
    client = LLMClient(config=llm_config, api_key=api_key)

    substep_lower = substep.lower()

    if substep_lower == "s4c":
        return run_s4c(checkpoint_path, output_path, client, model)
    elif substep_lower == "s0":
        return run_s0(checkpoint_path, output_path, client, model)
    elif substep_lower == "s4a":
        return run_s4a(checkpoint_path, output_path, client, model, kwargs.get("symbol_table_text"))
    elif substep_lower == "s4b":
        return run_s4b(checkpoint_path, output_path, client, model, kwargs.get("symbol_table_text"))
    elif substep_lower == "s4d":
        return run_s4d(checkpoint_path, output_path, client, model)
    elif substep_lower == "s4e":
        return run_s4e(checkpoint_path, output_path, client, model, kwargs.get("symbol_table_text"), kwargs.get("block_4d"))
    elif substep_lower == "s4e1":
        return run_s4e1(checkpoint_path, output_path, client, model, kwargs.get("worker_spl"))
    elif substep_lower == "s4e2":
        return run_s4e2(checkpoint_path, output_path, client, model, kwargs.get("worker_spl"), kwargs.get("violations"))
    elif substep_lower == "s4f":
        return run_s4f(checkpoint_path, output_path, client, model, kwargs.get("worker_spl"))
    else:
        raise ValueError(f"Unknown substep: {substep}. Available: {', '.join(SUBSTEPS)}")


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Run individual Step 4 sub-steps",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        required=True,
        help="Path to checkpoint directory",
    )
    parser.add_argument(
        "--substep",
        type=str,
        required=True,
        choices=SUBSTEPS,
        help=f"Which substep to run ({', '.join(SUBSTEPS)})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory (default: checkpoint/step4_substep_test)",
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

    try:
        result = test_substep(
            checkpoint_dir=args.checkpoint,
            substep=args.substep,
            output_dir=args.output,
            model=args.model,
            api_key=args.api_key,
        )

        print(f"\n{'=' * 60}")
        print(f"Sub-step {args.substep.upper()} completed successfully!")
        print(f"{'=' * 60}")

        if isinstance(result, dict):
            if "block" in result:
                print(f"Output block: {len(result['block'])} chars")
            if "symbol_table" in result:
                st = result["symbol_table"]
                print(f"Symbol table: {len(st.get('types', []))} types, "
                      f"{len(st.get('variables', {}))} variables, "
                      f"{len(st.get('files', {}))} files")
            if result.get("has_violations"):
                print(f"Violations found: {len(result.get('violations', []))}")
        elif isinstance(result, str):
            print(f"Output: {len(result)} chars")

    except Exception as e:
        logger.error(f"Sub-step failed: {e}")
        raise


if __name__ == "__main__":
    main()
