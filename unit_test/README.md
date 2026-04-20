# Unit Test 模块

本模块提供了对 pipeline 各步骤进行独立测试的功能。每个测试脚本可以从中间结果文件（checkpoint）中读取输入数据，单独运行某个步骤。

## 目录结构

```
unit_test/
├── __init__.py              # 模块初始化
├── README.md                # 本文件
├── run_all.py              # 批量运行所有测试
├── step1_structure.py       # Step 1: 结构提取测试
├── step1_5_api.py          # Step 1.5: API定义生成测试
├── step3_workflow.py       # Step 3: 工作流分析测试
├── step4_spl.py            # Step 4: SPL生成测试（完整流程）
└── step4_substeps.py       # Step 4: 单独子步骤测试（S0, S4A-F, S4E1-E2）
```

## 支持的步骤

### 完整步骤测试

| 测试文件 | 步骤名称 | 输入依赖 | 输出结果 |
|---------|---------|---------|---------|
| `step1_structure.py` | Step 1: 结构提取 | `p3_package.json` | `step1_structure_result.json` |
| `step1_5_api.py` | Step 1.5: API定义生成 | `p3_package.json` (需包含 unified_apis) | `step1_5_api_result.json` |
| `step3_workflow.py` | Step 3: 工作流分析 | `step1_bundle.json` | `step3_workflow_result.json`, `step3_types.spl` |
| `step4_spl.py` | Step 4: SPL生成 | `step3_structured_spec.json`, `step1_bundle.json`, `step1_5_api_result.json` | `step4_spl_result.json`, `{skill_id}.spl` |

### Step 4 子步骤测试

| 子步骤 | 名称 | 依赖 | 输出 |
|--------|------|------|------|
| `s4c` | Variables/Files | `step3_structured_spec.json` | `step4c_output.txt`, `symbol_table.json` |
| `s0` | DEFINE_AGENT Header | `step1_bundle.json` | `steps0_output.txt` |
| `s4a` | Persona/Audience/Concepts | S4C (symbol_table) | `step4a_output.txt` |
| `s4b` | Constraints | S4C (symbol_table) | `step4b_output.txt` |
| `s4d` | APIs | `step1_5_api_result.json` | `step4d_output.txt` |
| `s4e` | Worker | S4C + S4D | `step4e_output.txt` |
| `s4e1` | Nesting Detection | S4E | `step4e1_result.json` |
| `s4e2` | Nesting Fix | S4E + S4E1 | `step4e2_output.txt` |
| `s4f` | Examples | S4E2 (或 S4E) | `step4f_output.txt` |

## 中间结果文件说明

在中间结果目录（如 `output/pdf/`）中，你会找到以下文件：

```
output/pdf/
├── p1_graph.json                    # P1: 引用图
├── p2_file_role_map.json            # P2: 文件角色映射
├── p3_package.json                  # P3: 技能包（Step 1 输入）
├── step1_bundle.json                # Step 1: 结构提取结果
├── step3_structured_spec.json       # Step 3: 结构化规范（Step 4 输入）
├── step4a_persona.json              # Step 4A: Persona/Audience/Concepts
├── step4b_constraints.json            # Step 4B: Constraints
├── step4c_variables_files.json      # Step 4C: Variables/Files
├── step4d_apis.json                 # Step 4D: APIs
├── step4e1_nesting_detection.json   # Step 4E1: 嵌套检测
├── step4e2_nesting_fix.json        # Step 4E2: 嵌套修复
├── step4e_worker_original.json      # Step 4E: Worker (原始)
├── step4f_examples.json            # Step 4F: Examples
└── pdf.spl                         # 最终 SPL 输出
```

## 使用方法

### 1. 批量运行所有测试（推荐）

```bash
# 运行所有测试
python -m unit_test.run_all --checkpoint output/pdf --output output/unit_tests

# 从 Step 3 开始运行（自动跳过已完成的部分）
python -m unit_test.run_all --checkpoint output/pdf --from-step 3

# 运行指定范围
python -m unit_test.run_all --checkpoint output/pdf --from-step 1 --to-step 3

# 强制重新运行（不跳过已有输出）
python -m unit_test.run_all --checkpoint output/pdf --no-skip

# 使用特定模型
python -m unit_test.run_all --checkpoint output/pdf --model gpt-4o-mini
```

### 2. 单独运行某个步骤

```bash
# 运行 Step 1 测试
python -m unit_test.step1_structure --checkpoint output/pdf --output output/test_step1

# 运行 Step 1.5 测试
python -m unit_test.step1_5_api --checkpoint output/pdf --output output/test_step1_5

# 运行 Step 3 测试
python -m unit_test.step3_workflow --checkpoint output/pdf --output output/test_step3

# 运行 Step 4 测试（完整流程）
python -m unit_test.step4_spl --checkpoint output/pdf --output output/test_step4

# 使用特定的 LLM 模型
python -m unit_test.step1_structure --checkpoint output/pdf --model gpt-4o-mini

# 指定 API Key（或使用环境变量 OPENAI_API_KEY）
python -m unit_test.step1_structure --checkpoint output/pdf --api-key YOUR_API_KEY
```

### 3. 单独运行 Step 4 子步骤

```bash
# Step 4C: Variables/Files（必须先运行，生成 symbol_table）
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4c

# Step 0: DEFINE_AGENT Header
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s0

# Step 4A: Persona/Audience/Concepts
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4a

# Step 4B: Constraints
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4b

# Step 4D: APIs
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4d

# Step 4E: Worker（需要 S4C 和 S4D）
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4e

# Step 4E1: Nesting Detection（嵌套结构检测）
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4e1

# Step 4E2: Nesting Fix（嵌套结构修复）
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4e2

# Step 4F: Examples
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4f
```

### 4. 子步骤依赖顺序

如果要手动按顺序运行子步骤，请遵循以下依赖关系：

```
# 第一步：S4C（必须最先运行，生成 symbol_table）
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4c

# 第二步：并行运行 S4A, S4B, S0（依赖 S4C 的 symbol_table）
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4a
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4b
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s0

# 第三步：S4D（APIs，可以并行）
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4d

# 第四步：S4E（Worker，依赖 S4C 和 S4D）
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4e

# 第五步：S4E1 和 S4E2（嵌套检测和修复）
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4e1
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4e2

# 第六步：S4F（Examples，依赖 S4E 或 S4E2）
python -m unit_test.step4_substeps --checkpoint output/pdf --substep s4f
```

### 5. 代码中调用

```python
from unit_test.step1_structure import test_step1_structure
from unit_test.step1_5_api import test_step1_5_api
from unit_test.step3_workflow import test_step3_workflow
from unit_test.step4_spl import test_step4_spl

# 运行 Step 1
result1 = test_step1_structure(
    checkpoint_dir="output/pdf",
    output_dir="output/test_step1",
    model="gpt-4o",
)
```

### 6. 调用子步骤

```python
from unit_test.step4_substeps import test_substep

# 运行 S4C（生成 symbol_table）
result_s4c = test_substep(
    checkpoint_dir="output/pdf",
    substep="s4c",
    model="gpt-4o",
)
symbol_table_text = result_s4c["symbol_table_text"]

# 运行 S4A（需要 symbol_table）
result_s4a = test_substep(
    checkpoint_dir="output/pdf",
    substep="s4a",
    model="gpt-4o",
    symbol_table_text=symbol_table_text,
)

# 运行 S4E（需要 symbol_table 和 block_4d）
result_s4e = test_substep(
    checkpoint_dir="output/pdf",
    substep="s4e",
    model="gpt-4o",
    symbol_table_text=symbol_table_text,
    block_4d=result_s4d,  # 需要先运行 S4D
)

# 运行 S4E1（嵌套检测）
result_s4e1 = test_substep(
    checkpoint_dir="output/pdf",
    substep="s4e1",
    model="gpt-4o",
    worker_spl=result_s4e,  # S4E 的输出
)

# 运行 S4E2（嵌套修复）
result_s4e2 = test_substep(
    checkpoint_dir="output/pdf",
    substep="s4e2",
    model="gpt-4o",
    worker_spl=result_s4e,
    violations=result_s4e1.get("violations", []),
)

# 运行 Step 1.5
result1_5 = test_step1_5_api(
    checkpoint_dir="output/pdf",
    output_dir="output/test_step1_5",
    model="gpt-4o",
    max_workers=4,
)

# 运行 Step 3
result3 = test_step3_workflow(
    checkpoint_dir="output/pdf",
    output_dir="output/test_step3",
    model="gpt-4o",
)

# 运行 Step 4（完整 SPL 生成）
result4 = test_step4_spl(
    checkpoint_dir="output/pdf",
    output_dir="output/test_step4",
    model="gpt-4o",
)
```

## 各步骤输入输出详情

### Step 1: Structure Extraction

**输入文件**: `p3_package.json`

需要的字段：
- `skill_id`: str - 技能标识
- `merged_doc_text`: str - 合并后的文档文本
- `frontmatter`: dict - YAML frontmatter
- `file_role_map`: dict - 文件角色映射
- `tools`: list - 工具列表
- `unified_apis` (可选): list - 统一 API 规范

**输出文件**: `step1_structure_result.json`

包含：
- `skill_id`: str
- `section_bundle`: dict - 8个规范部分（INTENT, WORKFLOW, CONSTRAINTS, TOOLS, ARTIFACTS, EVIDENCE, EXAMPLES, NOTES）
- `network_apis`: list - 网络 API 列表

### Step 1.5: API Definition Generation

**输入文件**: `p3_package.json`

需要的字段：
- `unified_apis`: list of UnifiedAPISpec
  - `api_id`: str
  - `api_name`: str
  - `source`: str
  - `api_type`: str ("DOC" or "SCRIPT")
  - `functions`: list of FunctionSpec
    - `name`: str
    - `signature`: str
    - `description`: str
    - `return_type`: str
    - `parameters`: list
    - `is_async`: bool
    - `docstring`: str

**输出文件**: `step1_5_api_result.json`

包含：
- `apis`: dict - API 名称到 APISpec 的映射

### Step 3: Workflow Analysis

**输入文件**: `step1_bundle.json`

需要的字段：
- `section_bundle`: dict with 8 canonical sections
  - Each section is a list of SectionItem dicts
  - SectionItem: `{text: str, source: str, multi: bool}`

**输出文件**: `step3_workflow_result.json`, `step3_types.spl`

包含：
- `workflow_steps`: list of WorkflowStep
- `alternative_flows`: list of AlternativeFlow
- `exception_flows`: list of ExceptionFlow
- `step_io_specs`: list of Step I/O specs
- `global_registry`: GlobalVarRegistry
- `type_registry`: dict
- `types_spl`: str - TYPES 声明的 SPL 文本
- `declared_names`: list of declared type names

### Step 4: SPL Emission

**输入文件**:
- `step3_structured_spec.json` - Step 3 输出
- `step1_bundle.json` - Step 1 输出（用于 section_bundle）
- `step1_5_api_result.json` - Step 1.5 输出（用于 API 定义）

**输出文件**: `step4_spl_result.json`, `{skill_id}.spl`

包含：
- `spl_spec`: SPLSpec dict
  - `skill_id`: str
  - `spl_text`: str - 完整的 SPL 文本
  - `review_summary`: dict
  - `clause_counts`: dict
- `structured_spec`: StructuredSpec dict

### Step 4 子步骤详情

#### S4C: Variables/Files

**功能**: 生成 DEFINE_VARIABLES 和 DEFINE_FILES 块，提取符号表

**输入**: `step3_structured_spec.json` (entities, type_registry)

**输出**:
- `step4c_output.txt` - Variables/Files SPL 块
- `symbol_table.json` - 包含 types, variables, files 的符号表

**注意**: S4C 必须最先运行，因为其他子步骤需要 symbol_table

#### S0: DEFINE_AGENT Header

**功能**: 生成 DEFINE_AGENT 头信息

**输入**: `step1_bundle.json` (INTENT, NOTES sections)

**输出**: `steps0_output.txt` - DEFINE_AGENT 头

#### S4A: Persona/Audience/Concepts

**功能**: 生成 PERSONA, AUDIENCE, CONCEPTS 块

**输入**: 
- `step1_bundle.json` (INTENT, NOTES)
- S4C 输出的 symbol_table

**输出**: `step4a_output.txt`

#### S4B: Constraints

**功能**: 生成 DEFINE_CONSTRAINTS 块

**输入**:
- `step1_bundle.json` (CONSTRAINTS)
- S4C 输出的 symbol_table

**输出**: `step4b_output.txt`

#### S4D: APIs

**功能**: 生成 DEFINE_APIS 块

**输入**: `step1_5_api_result.json` 或原始 checkpoint 的 `step4d_apis.json`

**输出**: `step4d_output.txt`

**注意**: S4D 现在主要是合并 Step 1.5 预生成的 API SPL 块

#### S4E: Worker

**功能**: 生成完整的 WORKER 块，包含 MAIN_FLOW, ALTERNATIVE_FLOW, EXCEPTION_FLOW

**输入**:
- `step3_structured_spec.json` (workflow_steps, alternative_flows, exception_flows)
- S4C 的 symbol_table
- S4D 的 APIs block

**输出**: `step4e_output.txt`

#### S4E1: Nesting Detection

**功能**: 检测 Worker SPL 中非法的嵌套 BLOCK 结构

**输入**: S4E 输出的 Worker SPL

**输出**: `step4e1_result.json`

包含：
- `has_violations`: bool
- `violations`: list of violation dicts

#### S4E2: Nesting Fix

**功能**: 修复 S4E1 检测到的嵌套违规

**输入**:
- S4E 输出的 Worker SPL
- S4E1 的 violations 列表

**输出**: `step4e2_output.txt` - 修复后的 Worker SPL

#### S4F: Examples

**功能**: 生成 [EXAMPLES] 块

**输入**:
- `step1_bundle.json` (EXAMPLES section)
- S4E2 (或 S4E) 的 Worker SPL

**输出**: `step4f_output.txt`

**注意**: 如果没有 EXAMPLES section，会跳过此步骤

## 调试技巧

1. **查看中间结果**：每个测试会在输出目录保存详细的 JSON 结果文件

2. **日志输出**：设置日志级别查看详细输出
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

3. **部分输入缺失**：如果 checkpoint 缺少某些字段，测试脚本会尝试从其他 checkpoint 文件加载

4. **SPL 预览**：Step 4 测试会同时保存 `{skill_id}.spl` 文件，可以直接查看生成的 SPL

## 常见问题

**Q: 找不到 checkpoint 文件？**
A: 确保你指定的目录包含所需的 JSON 文件（如 `p3_package.json` 或 `step1_bundle.json`）

**Q: API Key 如何设置？**
A: 可以通过 `--api-key` 参数传入，或设置环境变量 `OPENAI_API_KEY`

**Q: 可以只运行部分步骤吗？**
A: 可以，每个步骤独立运行，只需确保输入 checkpoint 存在即可。例如，可以直接运行 Step 4 测试，无需先运行 Step 1-3。

**Q: 输出结果和完整 pipeline 运行结果一致吗？**
A: 应该一致，单元测试使用与 pipeline 相同的底层函数和数据模型。
