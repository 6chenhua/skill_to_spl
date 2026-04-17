# Step 4 设计文档 (SPL Emission)

## 概述

Step 4 是管道的最终阶段，负责将所有先前步骤的输出组装成最终的 SPL (Skill Processing Language) 规范。Step 4 采用依赖驱动的并行执行架构，包含六个子步骤（S4A-S4F），以最大化 LLM 调用的并行度。

## 架构位置

```
┌─────────────────────────────────────────────────────────────────┐
│                         Step 4                                  │
│              SPL Emission (LLM驱动)                           │
│         依赖驱动并行执行: S4A, S4B, S4C, S4D, S4E, S4F         │
├─────────────────────────────────────────────────────────────────┤
│  S4A: PERSONA / AUDIENCE / CONCEPTS                            │
│  S4B: CONSTRAINTS                                              │
│  S4C: VARIABLES + FILES (→ symbol_table)                       │
│  S4D: APIS (每个工具独立LLM调用)                               │
│  S4E: WORKER (MAIN + ALTERNATIVE + EXCEPTION_FLOW)               │
│  S4F: EXAMPLES                                                  │
└─────────────────────────────────────────────────────────────────┘
                           ↓
                    SPL Specification (最终输出)
```

## 依赖驱动的并行执行架构

Step 4 的核心优化是识别并并行化独立的 LLM 调用：

```
Phase 1: S4C 和 S4D 同时启动（相互独立）
    │
    ├─→ S4C: 生成 VARIABLES + FILES
    │      (依赖: interface_spec.entities + type_registry)
    │
    └─→ S4D: 生成 APIS
           (依赖: workflow_steps 中的 NETWORK 效果)
    
Phase 2: 当 S4C 完成 → 提取 symbol_table → 立即启动 S4A + S4B
    │
    ├─→ S4A: 生成 PERSONA (依赖: symbol_table + INTENT/NOTES)
    │
    └─→ S4B: 生成 CONSTRAINTS (依赖: symbol_table + CONSTRAINTS)
    
    注: S4A/S4B 不等待 S4D 完成（关键优化！）

Phase 3: 合并点 - S4E 需要 symbol_table（来自S4C）和 apis_spl（来自S4D）
    │
    └─→ S4E: 生成 WORKER
           (依赖: symbol_table + apis_spl + workflow/flows)

Phase 4: S4E 完成后 → S4F
    │
    └─→ S4F: 生成 EXAMPLES (依赖: S4E 输出)

Phase 5: 组装最终 SPL
```

## 六个子步骤详解

### S4A: Persona / Audience / Concepts

**文件**: `pipeline/llm_steps/step4_spl_emission/substep_calls.py::`_call_4a()``

**职责**:
- 生成 [DEFINE_PERSONA:] 块
- 定义 ROLE, DOMAIN, EXPERTISE
- 生成 [DEFINE_AUDIENCE:] 块
- 生成 [DEFINE_CONCEPTS:] 块

**输入**:
- `intent_text`: INTENT 章节文本
- `notes_text`: NOTES 章节文本
- `symbol_table_text`: 符号表（来自 S4C）

**输出**: SPL 文本块

```spl
[DEFINE_PERSONA:]
ROLE: {role}
DOMAIN: {domain}
EXPERTISE: {expertise_level}
"""SOURCE_REF: SKILL.md:1"""
"""CONFIDENCE: 1.0"""
"""NEEDS_REVIEW: false"""
[END_PERSONA]

[DEFINE_AUDIENCE:]
TARGET_USERS: {target_users}
"""SOURCE_REF: SKILL.md:10"""
[END_AUDIENCE]

[DEFINE_CONCEPTS:]
{concept1}: {definition1}
{concept2}: {definition2}
[END_CONCEPTS]
```

---

### S4B: Constraints

**文件**: `pipeline/llm_steps/step4_spl_emission/substep_calls.py::`_call_4b()``

**职责**:
- 生成 [DEFINE_CONSTRAINTS:] 块
- 分类约束级别: HARD(强制)/MEDIUM(偏好)/SOFT(指导)

**输入**:
- `constraints_text`: CONSTRAINTS 章节文本
- `symbol_table_text`: 符号表（来自 S4C）

**输出**: SPL 文本块

```spl
[DEFINE_CONSTRAINTS:]
Security: [SOFT: guidance only]
  Do not process sensitive documents without encryption
  """SOURCE_REF: SKILL.md:50"""
  """CONFIDENCE: 0.8"""
  
Format: [HARD: strict]
  Output must be valid PDF
  """SOURCE_REF: SKILL.md:55"""
  """CONFIDENCE: 0.95"""
[END_CONSTRAINTS]
```

---

### S4C: Variables + Files

**文件**: `pipeline/llm_steps/step4_spl_emission/substep_calls.py::`_call_4c()``

**职责**:
- 生成 [DEFINE_VARIABLES:] 块
- 生成 [DEFINE_FILES:] 块
- 提取符号表供后续步骤使用

**输入**:
- `entities_text`: 实体描述文本
- `omit_files_text`: 省略文件列表
- `types_text`: 类型定义文本（来自 Step 3-T）
- `type_registry`: 类型注册表

**输出**: SPL 文本块 + 符号表

```spl
[DEFINE_VARIABLES:]
<VAR>input_path</VAR>: <TYPE>text</TYPE>
<VAR>page_numbers</VAR>: <TYPE>List[number]</TYPE>
[END_VARIABLES]

[DEFINE_FILES:]
<FILE>input_file</FILE>: <MIME>application/pdf</MIME>
<FILE>output_file</FILE>: <MIME>application/pdf</MIME>
[END_DEFINE_FILES]
```

**符号表提取**:
- 从 S4C 输出解析所有定义的变量和文件
- 格式化为结构化文本供 S4A/S4B/S4E 使用

---

### S4D: APIs

**文件**: `pipeline/llm_steps/step4_spl_emission/substep_calls.py::`_call_4d()``

**职责**:
- 为每个工具生成 API 定义
- **关键优化**: 每个工具独立 LLM 调用（最大化并行度）

**输入**:
- `tool`: 单个工具规范（dict）
  - name: 工具名称
  - description: 功能描述
  - action_type: EXTERNAL_API | EXEC_SCRIPT | LOCAL_CODE_SNIPPET
  - input/output: I/O 模式

**输出**: SPL 文本块

```spl
[DEFINE_APIS:]
<API>extract_text</API>:
  URL: scripts/extract_text.py
  INPUT: { "pdf_path": "text", "pages": "List[number]" }
  OUTPUT: "text"
  """SOURCE_REF: scripts/extract_text.py:1"""
[END_APIS]
```

**并行策略**:
```python
# 为每个工具启动独立 LLM 调用
futures_4d = [
    pool.submit(_call_4d, client, tool, model=model) 
    for tool in tools_list
]
# 等待所有调用完成
block_4d_parts = [f.result() for f in futures_4d]
```

---

### S4E: Worker (Main + Alternative + Exception Flows)

**文件**: `pipeline/llm_steps/step4_spl_emission/substep_calls.py::`_call_4e()``

**职责**:
- 生成完整的 [DEFINE_WORKER:] 块
- 包含 MAIN_FLOW、ALTERNATIVE_FLOW、EXCEPTION_FLOW
- 嵌套验证和修复（S4E1/S4E2）

**输入**:
- `workflow_steps_json`: 工作流步骤 JSON
- `workflow_prose`: 原始 WORKFLOW 文本
- `alternative_flows_json`: 替代流 JSON
- `exception_flows_json`: 异常流 JSON
- `symbol_table`: 符号表
- `apis_spl`: API 定义（来自 S4D）
- `tools_json`: 工具列表 JSON

**输出**: SPL 文本块

```spl
[DEFINE_WORKER: "PDF processing worker" pdf_worker]
[INPUTS]
REQUIRED <REF>input_file</REF>
OPTIONAL <REF>password</REF>
[END_INPUTS]

[OUTPUTS]
REQUIRED <REF>output_file</REF>
[END_OUTPUTS]

[MAIN_FLOW]
[SEQUENTIAL_BLOCK]
COMMAND-1 [CODE Open PDF file RESULT pdf_doc: document]
COMMAND-2 [CODE Extract text from pages RESULT text: text]
[END_SEQUENTIAL_BLOCK]
[END_MAIN_FLOW]

[ALTERNATIVE_FLOW "handle password"]
[WHEN password_required]
COMMAND-1 [CODE Decrypt PDF RESULT decrypted: document]
[END_ALTERNATIVE_FLOW]

[EXCEPTION_FLOW "file not found"]
[WHEN FileNotFoundError]
RAISE ERROR file_not_found
[END_EXCEPTION_FLOW]
[END_WORKER]
```

**嵌套验证 (S4E1 + S4E2)**:
- S4E1: 检测非法的嵌套 BLOCK 结构
- S4E2: 修复嵌套问题（通过扁平化）

---

### S4F: Examples

**文件**: `pipeline/llm_steps/step4_spl_emission/substep_calls.py::`_call_4f()``

**职责**:
- 将 EXAMPLES 章节转换为 SPL 格式
- 注入到 WORKER 块内部（[END_WORKER] 之前）

**输入**:
- `examples_text`: EXAMPLES 章节文本
- `worker_spl`: 生成的 WORKER 块（用于上下文）

**输出**: SPL 文本块

```spl
[EXAMPLES]
Example 1:
Input: input.pdf (2 pages)
Output: extracted_text.txt
Steps:
  1. Open input.pdf
  2. Extract text from pages 1-2
  3. Save to output file
[END_EXAMPLES]
```

**注入位置**:
- 在 WORKER 块的 `[END_WORKER]` 标签之前插入
- 保持语义完整性

---

## Orchestrator (协调器)

**文件**: `pipeline/llm_steps/step4_spl_emission/orchestrator.py`

### 主入口函数

```python
def run_step4_spl_emission(
    bundle: SectionBundle,
    interface_spec: StructuredSpec,
    tools: list,
    skill_id: str,
    client: LLMClient,
    model: str | None = None,
    types_spl: str = "",
    type_registry: dict | None = None,
) -> SPLSpec:
    """
    Step 4: Emit the final normalized SPL specification.
    
    依赖驱动的并行执行:
    1. S4C 和 S4D 同时启动
    2. S4C 完成后提取 symbol_table，启动 S4A + S4B
    3. S4D 完成后，与 symbol_table 合并启动 S4E
    4. S4E 完成后启动 S4F
    5. 组装最终 SPL
    """
```

### 并行执行实现

```python
with ThreadPoolExecutor(max_workers=4) as pool:
    # Phase 1: 启动 S4C 和 S4D
    future_4c = pool.submit(_call_4c, client, s4c_inputs, model=model)
    futures_4d = [
        pool.submit(_call_4d, client, tool, model=model) 
        for tool in tools_list
    ]
    
    # Phase 2: S4C 完成后提取符号表
    block_4c = future_4c.result()
    symbol_table = _extract_symbol_table(block_4c, types_spl)
    symbol_table_text = _format_symbol_table(symbol_table)
    
    # 启动 S4A 和 S4B（不等待 S4D）
    future_4a = pool.submit(_call_4a, client, s4a_inputs, symbol_table_text, model=model)
    future_4b = pool.submit(_call_4b, client, s4b_inputs, symbol_table_text, model=model)
    
    # Phase 3: 等待 S4D 完成
    block_4d_parts = [f.result() for f in futures_4d]
    block_4d = "\n\n".join(block_4d_parts)
    
    # 启动 S4E（需要 symbol_table 和 apis_spl）
    future_4e = pool.submit(_call_4e, client, s4e_inputs, symbol_table_text, block_4d, model=model)
    
    # Phase 4: 收集 S4A 和 S4B 结果
    block_4a = future_4a.result()
    block_4b = future_4b.result()
    
    # Phase 5: 等待 S4E，启动 S4F
    block_4e = future_4e.result()
    block_4f = _call_4f(client, s4f_inputs, block_4e, model=model)
```

---

## 输入准备

**文件**: `pipeline/llm_steps/step4_spl_emission/inputs.py`

### _prepare_step4_inputs_v2

准备所有子步骤的输入数据（轻量级，无 LLM 调用）：

```python
def _prepare_step4_inputs_v2(
    bundle: SectionBundle,
    interface_spec: StructuredSpec,
    tools: list,
    type_registry: dict | None = None,
) -> tuple[dict, dict, dict, dict, dict, dict]:
    """
    准备 S4A, S4B, S4C, S4D, S4E, S4F 的输入数据
    
    Returns: (s4a_inputs, s4b_inputs, s4c_inputs, s4d_inputs, s4e_inputs, s4f_inputs)
    """
```

**输入数据映射**:

| 子步骤 | 来源 | 关键输入 |
|--------|------|----------|
| S4A | bundle | intent_text, notes_text |
| S4B | bundle | constraints_text |
| S4C | interface_spec.entities + type_registry | entities_text, types_text |
| S4D | interface_spec.workflow_steps | tools_list (API步骤) |
| S4E | bundle + interface_spec | workflow_steps, flows |
| S4F | bundle | examples_text |

---

## 符号表 (Symbol Table)

**文件**: `pipeline/llm_steps/step4_spl_emission/symbol_table.py`

### 提取和格式化

```python
def _extract_symbol_table(block_4c: str, types_spl: str = "") -> dict:
    """
    从 S4C 输出提取符号表
    
    Returns:
    {
        "types": [...],       # 类型定义
        "variables": [...],   # 变量定义
        "files": [...],       # 文件定义
    }
    """

def _format_symbol_table(symbol_table: dict) -> str:
    """格式化为文本供其他步骤使用"""
```

---

## 组装 (Assembly)

**文件**: `pipeline/llm_steps/step4_spl_emission/assembly.py`

### 最终 SPL 组装

```python
def _assemble_spl(
    skill_id: str,
    define_agent_header: str,
    block_4a: str,  # PERSONA/AUDIENCE/CONCEPTS
    block_4b: str,  # CONSTRAINTS
    block_4c: str,  # VARIABLES/FILES
    block_4d: str,  # APIS
    block_4e: str,  # WORKER
    block_4f: str,  # EXAMPLES
) -> str:
    """
    按规范顺序连接所有块，包装在 DEFINE_AGENT 中
    
    结构:
    [DEFINE_AGENT: AGENT_NAME]
    # SPL_PROMPT content (blocks 4a-4f)
    [END_AGENT]
    
    注: block_4f (EXAMPLES) 插入在 WORKER 内部 [END_WORKER] 之前
    """
```

**组装顺序**:
```
[DEFINE_AGENT: {AgentName}]

# Block 4A
[DEFINE_PERSONA:]
...
[END_PERSONA]

[DEFINE_AUDIENCE:]
...
[END_AUDIENCE]

[DEFINE_CONCEPTS:]
...
[END_CONCEPTS]

# Block 4B
[DEFINE_CONSTRAINTS:]
...
[END_CONSTRAINTS]

# Block 4C
[DEFINE_VARIABLES:]
...
[END_VARIABLES]

[DEFINE_FILES:]
...
[END_DEFINE_FILES]

# Block 4D
[DEFINE_APIS:]
...
[END_APIS]

# Block 4E (+ 4F)
[DEFINE_WORKER: ...]
...
[EXAMPLES]  # Block 4F 插入这里
...
[END_WORKER]

[END_AGENT]
```

---

## 数据流向

```
┌─────────────────────────────────────────────────────────────┐
│  SectionBundle (来自 Step 1)                               │
│  StructuredSpec (来自 Step 3)                                │
│  type_registry (来自 Step 3-T)                             │
│  tools (合并的网络API + 脚本API)                            │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Input Preparation (_prepare_step4_inputs_v2)               │
│  ├── S4A: intent_text, notes_text                          │
│  ├── S4B: constraints_text                                   │
│  ├── S4C: entities_text, types_text, type_registry        │
│  ├── S4D: tools_list (过滤出API相关步骤)                   │
│  ├── S4E: workflow_steps, flows, workflow_prose           │
│  └── S4F: examples_text                                    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: Parallel S4C + S4D                                │
│  ├─ S4C: Generate VARIABLES/FILES ───────────→ block_4c     │
│  │                                          ↓              │
│  │                              extract symbol_table        │
│  │                                          ↓              │
│  │                              format symbol_table_text   │
│  │                                          ↓              │
│  └─ S4D: Generate APIS (per-tool parallel) ─→ block_4d    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: S4A + S4B (并行，依赖 symbol_table)               │
│  ├─ S4A: Generate PERSONA ─────────────────→ block_4a     │
│  └─ S4B: Generate CONSTRAINTS ─────────────→ block_4b     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: S4E (合并点)                                       │
│  S4E: Generate WORKER                                       │
│  (依赖: symbol_table + block_4d + workflow/flows)           │
│  ├── 检测嵌套违规 (S4E1)                                     │
│  ├── 修复嵌套问题 (S4E2)                                     │
│  └───────────────────────────────────────────→ block_4e     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: S4F (依赖 S4E)                                     │
│  S4F: Generate EXAMPLES ─────────────────────→ block_4f     │
│  (注入到 block_4e 的 [END_WORKER] 之前)                      │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 5: Assembly                                           │
│  _assemble_spl(skill_id, "", 4a, 4b, 4c, 4d, 4e, 4f)       │
│  └── Final SPL Text                                         │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  SPLSpec                                                    │
│  ├── skill_id                                               │
│  ├── spl_text                                               │
│  ├── review_summary                                         │
│  └── clause_counts                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 关键设计决策

### 1. 依赖驱动的并行化

识别并利用子步骤间的依赖关系：
- **独立步骤**: S4C 和 S4D 可以并行
- **早期启动**: S4A/S4B 可以在 S4C 完成后立即启动（无需等待 S4D）
- **合并点**: S4E 必须等待所有依赖完成

### 2. 每工具独立 LLM 调用

S4D 为每个工具启动独立 LLM 调用：
- 最大化并行度
- 单个失败不影响其他工具
- 便于调试和追踪

### 3. 符号表作为中心数据

S4C 生成的符号表是多个后续步骤的输入：
- 单一来源的变量/文件定义
- 确保一致性
- 避免重复提取

### 4. 嵌套验证和修复

S4E1 + S4E2 的两阶段验证：
- 检测 SPL 语法违规
- 自动修复（扁平化嵌套）
- 提高输出质量

### 5. EXAMPLES 注入

S4F 输出注入到 WORKER 块内部：
- 保持语义完整性
- 符合 SPL 语法规范

---

## 日志输出

```
[Step 4] Phase 1: Launching S4C (variables/files) and S4D (apis per tool) in parallel
[Step 4] Phase 1: Launching S4D with {n} tools (individual LLM calls)
[Step 4] Phase 2: Waiting for S4C to extract symbol_table...
[Step 4] Symbol table extracted - types: {t}, variables: {v}, files: {f}
[Step 4] Phase 2: Launching S4A (persona) and S4B (constraints) in parallel
[Step 4] Phase 3: Waiting for S4D to complete...
[Step 4] Phase 3: S4D completed - {n} API definitions generated
[Step 4] Phase 3: Launching S4E (worker)
[Step 4] Phase 4: Waiting for S4E to complete...
[Step 4] Phase 5: Generating S4F (examples)
[Step 4] SPL assembled ({n} chars)
```

---

## 错误处理

| 步骤 | 错误情况 | 处理方式 |
|------|----------|----------|
| S4A | LLM调用失败 | 返回空块 |
| S4B | 无约束 | 返回空块 |
| S4C | 无实体 | 返回空块 |
| S4D | 单个工具失败 | 记录警告，继续其他工具 |
| S4E | 嵌套违规 | S4E2 自动修复 |
| S4F | 无示例 | 返回空块 |

---

## 相关文件

- `pipeline/llm_steps/step4_spl_emission/orchestrator.py` - 主协调器
- `pipeline/llm_steps/step4_spl_emission/substep_calls.py` - 子步骤调用
- `pipeline/llm_steps/step4_spl_emission/inputs.py` - 输入准备
- `pipeline/llm_steps/step4_spl_emission/assembly.py` - SPL组装
- `pipeline/llm_steps/step4_spl_emission/symbol_table.py` - 符号表提取
- `pipeline/llm_steps/step4_spl_emission/nesting_validation.py` - 嵌套验证
- `prompts/step4_e1_system.py` - S4E1 提示词
- `prompts/step4_e2_system.py` - S4E2 提示词
- `prompts/step4_system.py` - S4A/S4B/S4C/S4D/S4E/S4F 提示词
- `pipeline/spl_formatter.py` - SPL 格式化
