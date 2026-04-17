# Step 3 设计文档 (Interface Inference)

## 概述

Step 3 负责从已结构化的文档中提取接口定义，包括工作流分析、实体提取和类型系统。Step 3 采用新的 W→IO→T 架构，将工作流分析、I/O分析和类型声明分离为三个子步骤。

## 架构位置

```
┌─────────────────────────────────────────────────────────────────┐
│                         Step 3                                  │
│              Interface Inference (LLM驱动)                      │
│                    新架构: W → IO → T                            │
├─────────────────────────────────────────────────────────────────┤
│  Step 3-W: Workflow Structure Analysis                          │
│  Step 3-IO: Global I/O + Type Analysis                          │
│  Step 3-T: Types Declaration                                    │
└─────────────────────────────────────────────────────────────────┘
                           ↓
                    [进入 Step 4]
```

## 新架构 W→IO→T

### Step 3-W: Workflow Structure Analysis

**文件位置**: `pipeline/llm_steps/step3/w.py`

**职责**:
- 从 WORKFLOW 章节提取工作流步骤
- **不推断 I/O**（将 I/O 分析留给 Step 3-IO）
- 识别替代流 (alternative_flows) 和异常流 (exception_flows)
- 识别验证门 (validation gates)

**输入**:
- `workflow_section`: WORKFLOW 文本
- `tools_section`: TOOLS 文本
- `evidence_section`: EVIDENCE 文本
- `available_tools`: 可用工具规范列表

**输出**:
```python
Step3WOutput(
    workflow_steps: list[WorkflowStepRaw],      # 工作流步骤（无I/O）
    alternative_flows: list[AlternativeFlowSpec],  # 替代流
    exception_flows: list[ExceptionFlowSpec]     # 异常流
)
```

**WorkflowStepRaw**:
```python
@dataclass
class WorkflowStepRaw:
    step_id: str           # 步骤ID (如 "S1", "S2")
    description: str       # 步骤描述
    action_type: str      # LLM_TASK | SCRIPT_CALL | VALIDATION_GATE
    tool_hint: str        # 工具提示/引用
    is_validation_gate: bool  # 是否为验证门
    source_text: str      # 源文本
```

**提示词**:
- 系统提示词: `prompts/step3_w_system.py` (S3W_SYSTEM_V1)
- 用户提示词模板: `prompts/step3_w_system.render_step3w_user()`

---

### Step 3-IO: Global I/O + Type Analysis

**文件位置**: `pipeline/llm_steps/step3/io.py`

**职责**:
- 分析所有工作流步骤的 I/O 关系
- 确保类型一致性（全局分析）
- 识别变量和文件类型
- 构建全局变量注册表

**输入**:
- `workflow_steps`: Step 3-W 的工作流步骤列表
- `workflow_text`: 原始 WORKFLOW 文本（用于上下文）
- `artifacts_text`: ARTIFACTS 章节文本（用于文件识别）

**输出**:
```python
Step3IOOutput(
    step_io_specs: dict[str, StepIOSpec],  # 每步的I/O规范
    global_registry: GlobalVarRegistry       # 全局变量注册表
)
```

**StepIOSpec**:
```python
@dataclass
class StepIOSpec:
    step_id: str
    prerequisites: dict[str, VarSpec]  # 前置条件（输入）
    produces: dict[str, VarSpec]       # 产出（输出）
```

**VarSpec**:
```python
@dataclass
class VarSpec:
    var_name: str
    type_expr: TypeExpr    # 类型表达式
    is_file: bool          # 是否为文件类型
    description: str       # 描述
```

**GlobalVarRegistry**:
```python
@dataclass
class GlobalVarRegistry:
    variables: dict[str, VarSpec]    # 变量名 -> 规范
    files: dict[str, VarSpec]       # 文件名 -> 规范
    
    def register(self, var_spec: VarSpec) -> None:
        """注册变量，自动去重和合并类型"""
```

**提示词**:
- 系统提示词: `prompts/step3_io_system.py` (S3IO_SYSTEM_V1)
- 用户提示词模板: `prompts/step3_io_system.render_step3io_user()`

---

### Step 3-T: Types Declaration

**文件位置**: `pipeline/llm_steps/step3/t.py`

**职责**:
- 为复杂类型生成 TYPES 声明
- 将类型定义转换为 SPL 格式
- 去重和规范化类型名称

**输入**:
- `registry`: Step 3-IO 生成的 GlobalVarRegistry

**输出**:
```python
Step3TOutput(
    types_spl: str,              # [DEFINE_TYPES:] 块文本
    type_registry: dict,          # 类型名称 -> 定义
    declared_names: list[str]     # 声明的类型名称列表
)
```

**类型系统** (models/step3_types.py):

```python
@dataclass(frozen=True)
class TypeExpr:
    """类型表达式 - 支持简单、枚举、数组、结构体"""
    kind: str  # "simple" | "enum" | "array" | "struct"
    type_name: str = ""           # 简单类型名称
    values: tuple[str, ...] = ()  # 枚举值
    element_type: TypeExpr = None # 数组元素类型
    fields: dict[str, TypeExpr] = {}  # 结构体字段
    
    @classmethod
    def simple(cls, type_name: str) -> TypeExpr:
        """创建简单类型: text, image, audio, number, boolean"""
        
    @classmethod
    def enum(cls, values: list[str]) -> TypeExpr:
        """创建枚举类型"""
        
    @classmethod
    def array(cls, element_type: TypeExpr) -> TypeExpr:
        """创建数组类型: List[X]"""
        
    @classmethod
    def struct(cls, fields: dict[str, TypeExpr]) -> TypeExpr:
        """创建结构体类型: { field1: type1, field2: type2 }"""
```

**支持的简单类型**:
- `text` - 文本数据
- `image` - 图像数据
- `audio` - 音频数据
- `number` - 数值
- `boolean` - 布尔值

---

## Orchestrator (协调器)

**文件位置**: `pipeline/llm_steps/step3/orchestrator.py`

```python
async def run_step3_full(
    workflow_section: str,
    tools_section: str,
    evidence_section: str,
    artifacts_section: str,
    available_tools: list[dict],
    client: LLMClient,
    model: str = "gpt-4o-mini"
) -> dict[str, Any]:
    """
    运行完整的 Step 3: W → IO → T
    
    执行顺序:
    1. Step 3-W: 工作流结构分析
    2. Step 3-IO: 全局I/O和类型分析（依赖W的输出）
    3. Step 3-T: 类型声明生成（依赖IO的registry）
    
    返回: 组合输出字典
    """
```

**同步包装器**:
```python
def run_step3_full_sync(...) -> dict[str, Any]:
    """同步包装器，内部使用 asyncio.run()"""
    return asyncio.run(run_step3_full(...))
```

---

## 数据流向

```
┌─────────────────────────────────────────────────────────────┐
│  SectionBundle (来自 Step 1)                               │
│  ├── workflow: list[SectionItem]                          │
│  ├── tools: list[SectionItem]                             │
│  ├── evidence: list[SectionItem]                          │
│  └── artifacts: list[SectionItem]                         │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 3-W: Workflow Analysis                                │
│  ├── 格式化输入文本                                         │
│  ├── 调用LLM (step3_w_system)                              │
│  ├── 解析工作流步骤                                         │
│  ├── 解析替代流和异常流                                      │
│  └── 输出: Step3WOutput                                      │
│       ├── workflow_steps: list[WorkflowStepRaw]            │
│       ├── alternative_flows: list[AlternativeFlowSpec]     │
│       └── exception_flows: list[ExceptionFlowSpec]          │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 3-IO: Global I/O Analysis                             │
│  ├── 接收 workflow_steps                                    │
│  ├── 格式化步骤用于提示词                                    │
│  ├── 调用LLM (step3_io_system)                              │
│  ├── 解析每步的I/O规范                                       │
│  ├── 构建 GlobalVarRegistry                                 │
│  └── 输出: Step3IOOutput                                     │
│       ├── step_io_specs: dict[str, StepIOSpec]             │
│       └── global_registry: GlobalVarRegistry                │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 3-T: Types Declaration                                │
│  ├── 接收 global_registry                                   │
│  ├── 提取复杂类型                                            │
│  ├── 生成SPL类型声明文本                                     │
│  └── 输出: Step3TOutput                                      │
│       ├── types_spl: str                                    │
│       ├── type_registry: dict                               │
│       └── declared_names: list[str]                         │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  组合输出: dict[str, Any]                                   │
│  ├── workflow_steps: list[WorkflowStepRaw]                  │
│  ├── alternative_flows: list[AlternativeFlowSpec]           │
│  ├── exception_flows: list[ExceptionFlowSpec]               │
│  ├── step_io_specs: dict[str, StepIOSpec]                  │
│  ├── global_registry: GlobalVarRegistry                     │
│  ├── types_spl: str                                         │
│  ├── type_registry: dict                                    │
│  └── declared_names: list[str]                            │
└─────────────────────────────────────────────────────────────┘
                           ↓
                    [进入 Step 4]
```

---

## 关键设计决策

### 1. 三步分离架构

将 Step 3 分解为三个独立步骤:
- **W (Workflow)**: 专注工作流结构，不涉及I/O细节
- **IO (Input/Output)**: 全局视角分析I/O关系，确保类型一致性
- **T (Types)**: 将类型系统转换为SPL格式

**优势**:
- 每个步骤职责单一
- 便于独立测试和调试
- 类型分析可以在全局视角下进行（而不是每步孤立分析）

### 2. 全局变量注册表

`GlobalVarRegistry` 维护所有变量的单一来源:
- 自动去重（基于变量名和类型签名）
- 区分变量和文件类型
- 支持类型推导和合并

### 3. 类型表达式系统

`TypeExpr` 支持复杂的嵌套类型:
- 简单类型: `text`, `number`
- 枚举: `enum(["A", "B", "C"])`
- 数组: `List[text]`, `List[{name: text, age: number}]`
- 结构体: `{name: text, items: List[number]}`

### 4. 异步并行

Step 3-IO 和 Step 3-W 可以并行执行（如果输入允许），但当前实现是顺序的 W→IO→T，确保数据依赖得到满足。

---

## 与 Step 4 的集成

Step 3 的输出直接供给 Step 4:

| Step 3 输出 | Step 4 消费 | 用途 |
|------------|------------|------|
| `workflow_steps` | S4E | 生成 WORKER 的 MAIN_FLOW |
| `alternative_flows` | S4E | 生成 ALTERNATIVE_FLOW |
| `exception_flows` | S4E | 生成 EXCEPTION_FLOW |
| `global_registry` | S4C | 生成 VARIABLES 和 FILES |
| `types_spl` | S4C | 插入 [DEFINE_TYPES:] 块 |
| `type_registry` | S4C | 构建符号表 |

---

## 错误处理

| 步骤 | 错误情况 | 处理方式 |
|------|----------|----------|
| Step 3-W | LLM返回非JSON | 抛出异常，记录错误 |
| Step 3-W | 步骤解析失败 | 记录警告，跳过该步骤 |
| Step 3-IO | 类型解析失败 | 默认为 `text` 类型 |
| Step 3-IO | 变量冲突 | 使用签名去重 |
| Step 3-T | 无复杂类型 | 返回空 types_spl |

---

## 日志输出

```
================================================================================
Starting Step 3 Full (W -> IO -> T)
================================================================================
[Step 3-W] Workflow Structure Analysis
[Step 3-W] Extracted {n} steps
[Step 3-IO] Global I/O + Type Analysis
[Step 3-IO] Analyzed {n} steps, {v} vars, {f} files
[Step 3-T] TYPES Declaration
[Step 3-T] Generated {n} type declarations
================================================================================
Step 3 Complete
================================================================================
```

---

## 相关文件

- `pipeline/llm_steps/step3/orchestrator.py` - Step 3 协调器
- `pipeline/llm_steps/step3/w.py` - Step 3-W 实现
- `pipeline/llm_steps/step3/io.py` - Step 3-IO 实现
- `pipeline/llm_steps/step3/t.py` - Step 3-T 实现
- `models/step3_types.py` - 类型系统定义
- `prompts/step3_w_system.py` - Step 3-W 提示词
- `prompts/step3_io_system.py` - Step 3-IO 提示词
