# Skill-to-CNL-P 第二阶段详细实施计划
## Phase B: 数据模型重构 (第3-5周)

> **版本**: 1.0
> **基于**: 重构计划v2.0 Phase B
> **创建日期**: 2026-04-17
> **预计工期**: 3周 (Week 3-5)

---

## 一、概述

### 目标
将 `models/data_models.py` (495行, 20+个数据类) 拆分为职责清晰的模块化结构，遵循单一职责原则(SRP)和接口隔离原则(ISP)。

### 当前问题
1. **单一文件职责过重**: 20+数据类混杂预处理、Pipeline步骤和API模型
2. **循环导入风险**: 不同阶段的模型互相依赖
3. **维护困难**: 修改一个模型需要理解整个文件
4. **测试复杂**: 测试特定模型需要导入整个文件

### 目标架构
```
models/
├── __init__.py          # 统一导出 + 向后兼容层
├── base.py              # 基础类型、协议、抽象基类
├── core.py              # 核心共享类型 (PipelineResult, TokenUsage等)
├── preprocessing/       # P1-P3 阶段模型
│   ├── __init__.py
│   ├── reference.py     # FileNode, FileReferenceGraph
│   ├── roles.py         # FileRoleEntry
│   └── package.py       # SkillPackage
├── pipeline_steps/      # Step 1-4 阶段模型
│   ├── __init__.py
│   ├── step1.py         # SectionBundle, SectionItem
│   ├── step3/           # Step 3 实体与工作流模型
│   │   ├── __init__.py
│   │   ├── entities.py  # EntitySpec, WorkflowStepSpec
│   │   ├── flows.py     # AlternativeFlowSpec, ExceptionFlowSpec
│   │   └── registry.py  # GlobalVarRegistry, VarSpec等
│   ├── step4.py         # SPLSpec, APISpec等
│   └── api.py           # 通用API定义模型
└── deprecated.py        # 向后兼容别名和弃用警告
```

---

## 二、详细任务分解

### Week 3: 模型拆分设计与基础实现

#### 任务 B1.1: 创建新目录结构 ✅
**目标**: 建立新的models目录结构
**工期**: 1天
**负责人**: Dev-1

```bash
# 创建目录结构
mkdir -p models/preprocessing models/pipeline_steps/step3

# 创建__init__.py文件
touch models/preprocessing/__init__.py
touch models/pipeline_steps/__init__.py
touch models/pipeline_steps/step3/__init__.py
```

**验收标准**:
- [ ] 目录结构符合设计
- [ ] 所有__init__.py已创建
- [ ] 现有`models/data_models.py`保持不动（作为参考）

---

#### 任务 B1.2: 实现 models/base.py
**目标**: 提取基础类型和协议
**工期**: 1天
**负责人**: Dev-1

**内容**:
```python
# models/base.py
"""基础类型和协议定义."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

T = TypeVar('T')

class Serializable(Protocol):
    """可序列化协议."""
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T: ...

class Validatable(Protocol):
    """可验证协议."""
    def validate(self) -> list[str]: ...  # 返回验证错误列表，空表示通过

@dataclass(frozen=True)
class SourceRef:
    """源代码引用位置."""
    file: str
    line: int = 0
    column: int = 0
    
    def __str__(self) -> str:
        if self.line:
            return f"{self.file}:{self.line}"
        return self.file

# 通用类型别名
Provenance = str  # "EXPLICIT" | "ASSUMED" | "LOW_CONFIDENCE"
Priority = int    # 1=must_read, 2=include_summary, 3=omit
FileKind = str    # "doc" | "script" | "data" | "document" | "image" | "audio"
```

**依赖**: B1.1
**验收标准**:
- [ ] 文件创建完成
- [ ] 包含Serializable和Validatable协议
- [ ] 包含SourceRef类
- [ ] 类型别名定义完成
- [ ] mypy类型检查通过

---

#### 任务 B1.3: 实现 models/core.py
**目标**: 核心共享类型
**工期**: 1天
**负责人**: Dev-1

**内容**:
```python
# models/core.py
"""核心共享类型 - 跨阶段使用的数据类."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from models.base import SourceRef

@dataclass
class TokenUsage:
    """单次LLM调用的token使用统计."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

@dataclass
class SessionUsage:
    """整个session的token使用聚合."""
    steps: dict[str, TokenUsage] = field(default_factory=dict)
    
    @property
    def total(self) -> TokenUsage:
        total = TokenUsage()
        for usage in self.steps.values():
            total += usage
        return total
    
    def add(self, step_name: str, usage: TokenUsage) -> None:
        self.steps[step_name] = usage

@dataclass
class ReviewItem:
    """人工审核标记项."""
    item: str
    reason: str
    question: str
    severity: str = "warning"  # "error" | "warning" | "info"
    source_ref: SourceRef | None = None
```

**依赖**: B1.2
**验收标准**:
- [ ] TokenUsage实现完成
- [ ] SessionUsage实现完成
- [ ] ReviewItem实现完成
- [ ] 单元测试覆盖率>90%

---

#### 任务 B1.4: 实现 models/preprocessing/
**目标**: P1-P3阶段模型
**工期**: 2天
**负责人**: Dev-2

**B1.4a: models/preprocessing/reference.py**
```python
"""P1: Reference Graph 相关模型."""
from dataclasses import dataclass, field
from typing import Any

from models.base import FileKind, SourceRef

@dataclass
class FileNode:
    """技能包中的单个文件."""
    path: str                          # 相对于skill root的路径
    kind: FileKind                     # 文件类型
    size_bytes: int
    head_lines: list[str]              # 前20行(文档)或注释头(脚本, ≤5行)
    references: list[str]              # 本文件引用的其他文件名
    source_ref: SourceRef | None = None

@dataclass  
class FileReferenceGraph:
    """P1输出: 技能包的机械清单."""
    skill_id: str
    root_path: str
    skill_md_content: str              # SKILL.md完整文本
    frontmatter: dict[str, Any]         # YAML frontmatter
    nodes: dict[str, FileNode]          # rel_path → FileNode
    edges: dict[str, list[str]]         # referencing_file → [referenced_files]
    docs_content: dict[str, str] = field(default_factory=dict)
    
    # CapabilityProfile Layer 1 (P1自动派生)
    local_scripts: list[str] = field(default_factory=list)   # 所有.py/.sh文件
    referenced_libs: list[str] = field(default_factory=list) # 顶层导入的库
```

**B1.4b: models/preprocessing/roles.py**
```python
"""P2: File Role Resolver 相关模型."""
from dataclasses import dataclass
from typing import TypeAlias

from models.base import Priority

@dataclass
class FileRoleEntry:
    """LLM分配的文件角色和读取优先级."""
    role: str                          # 来自taxonomy的角色
    read_priority: Priority            # 1=must_read, 2=include_summary, 3=omit
    must_read_for_normalization: bool
    reasoning: str                     # 引用源文本的一句话解释

# 类型别名: path → entry
FileRoleMap: TypeAlias = dict[str, FileRoleEntry]
```

**B1.4c: models/preprocessing/package.py**
```python
"""P3: Skill Package 相关模型."""
from dataclasses import dataclass, field
from typing import Any

from models.preprocessing.reference import FileReferenceGraph
from models.preprocessing.roles import FileRoleMap
from models.pipeline_steps.api import ToolSpec, UnifiedAPISpec

@dataclass
class SkillPackage:
    """P3输出: 组装好的带注解的Step 1输入."""
    skill_id: str
    root_path: str
    frontmatter: dict[str, Any]
    merged_doc_text: str               # 带文件边界标记的拼接内容
    file_role_map: FileRoleMap
    
    # API分析结果 (P2.5)
    scripts: list = field(default_factory=list)      # 已废弃: 使用tools
    tools: list[ToolSpec] = field(default_factory=list)
    unified_apis: list[UnifiedAPISpec] = field(default_factory=list)
    
    def get_doc_content(self, rel_path: str) -> str | None:
        """提取特定文件的原始内容."""
        # 从merged_doc_text解析
        pass  # TODO: 实现
```

**依赖**: B1.3
**验收标准**:
- [ ] reference.py实现完成
- [ ] roles.py实现完成
- [ ] package.py实现完成
- [ ] 从原data_models.py导入路径更新
- [ ] 单元测试通过

---

#### 任务 B1.5: 实现 models/pipeline_steps/step1.py
**目标**: Step 1 结构提取模型
**工期**: 1天
**负责人**: Dev-2

**内容**:
```python
"""Step 1: Structure Extraction 相关模型."""
from dataclasses import dataclass, field
from typing import Optional

from models.base import SourceRef

# 标准节名称
CANONICAL_SECTIONS = [
    "INTENT", "WORKFLOW", "CONSTRAINTS", "TOOLS",
    "ARTIFACTS", "EVIDENCE", "EXAMPLES", "NOTES"
]

@dataclass
class SectionItem:
    """标准节中的单个条目.文本保持原样."""
    text: str                          # 原样复制，永不转述
    source: str                        # 源文件名
    multi: bool = False                # 是否出现在多个节中
    source_ref: SourceRef | None = None

@dataclass
class SectionBundle:
    """Step 1输出: 8个标准节."""
    intent: list[SectionItem] = field(default_factory=list)
    workflow: list[SectionItem] = field(default_factory=list)
    constraints: list[SectionItem] = field(default_factory=list)
    tools: list[SectionItem] = field(default_factory=list)
    artifacts: list[SectionItem] = field(default_factory=list)
    evidence: list[SectionItem] = field(default_factory=list)
    examples: list[SectionItem] = field(default_factory=list)
    notes: list[SectionItem] = field(default_factory=list)
    
    def all_sections(self) -> dict[str, list[SectionItem]]:
        return {
            "INTENT": self.intent,
            "WORKFLOW": self.workflow,
            "CONSTRAINTS": self.constraints,
            "TOOLS": self.tools,
            "ARTIFACTS": self.artifacts,
            "EVIDENCE": self.evidence,
            "EXAMPLES": self.examples,
            "NOTES": self.notes,
        }
    
    def to_text(self, sections: Optional[list[str]] = None) -> str:
        """渲染选定(或全部)节为带标签的文本块."""
        target = self.all_sections()
        if sections:
            target = {k: v for k, v in target.items() if k in sections}
        
        parts = []
        for name, items in target.items():
            if items:
                block = "\n".join(
                    f" [{item.source}] {item.text}" + (" [MULTI]" if item.multi else "")
                    for item in items
                )
                parts.append(f"## {name}\n{block}")
        return "\n\n".join(parts)
    
    def is_empty(self) -> bool:
        """检查是否所有节都为空."""
        return all(len(items) == 0 for items in self.all_sections().values())
```

**依赖**: B1.2
**验收标准**:
- [ ] SectionItem实现完成
- [ ] SectionBundle实现完成
- [ ] all_sections, to_text, is_empty方法测试通过

---

#### 任务 B1.6: 实现 models/pipeline_steps/step3/
**目标**: Step 3 实体与工作流模型
**工期**: 2天
**负责人**: Dev-3

**B1.6a: models/pipeline_steps/step3/entities.py**
```python
"""Step 3: 实体和工作流步骤模型."""
from dataclasses import dataclass, field
from typing import Literal

from models.base import Provenance, SourceRef

# Action类型
ActionType = Literal[
    "EXTERNAL_API", "LLM_TASK", "EXEC_SCRIPT",
    "FILE_READ", "FILE_WRITE", "USER_INTERACTION", "LOCAL_CODE_SNIPPET"
]

# Entity种类
EntityKind = Literal["Artifact", "Run", "Evidence", "Record"]

@dataclass
class EntitySpec:
    """WORKER读取或产生的命名数据实体."""
    entity_id: str
    kind: EntityKind
    type_name: str
    schema_notes: str
    provenance_required: bool
    provenance: Provenance
    source_text: str
    
    # 文件路由字段
    is_file: bool = False              # True当kind=Artifact或from_omit_files=True
    file_path: str = ""               # 实际路径; "" → SPL中的"< >"
    from_omit_files: bool = False      # True如果来自P1 read_priority=3节点
    source_ref: SourceRef | None = None

@dataclass
class WorkflowStepSpec:
    """工作流中的单步，重写为SPL就绪形式."""
    step_id: str                       # step.<action_name> (snake_case)
    description: str                   # SPL就绪的COMMAND描述
    prerequisites: list[str]           # 执行前必须存在的entity_ids
    produces: list[str]                # 此步骤创建的entity_ids
    is_validation_gate: bool           # 是否来自EVIDENCE要求
    
    action_type: ActionType = "LLM_TASK"
    tool_hint: str = ""                # 显式声明的工具/脚本名
    source_text: str = ""              # 源中的原样锚点
    source_ref: SourceRef | None = None
```

**B1.6b: models/pipeline_steps/step3/flows.py**
```python
"""Step 3: 控制流模型 (Alternative和Exception流)."""
from dataclasses import dataclass
from typing import Literal

from models.base import Provenance, SourceRef

FlowType = Literal["alternative", "exception"]

@dataclass
class FlowStep:
    """ALTERNATIVE_FLOW或EXCEPTION_FLOW中的单步."""
    description: str = ""
    action_type: str = "LLM_TASK"
    tool_hint: str = ""
    source_text: str = ""
    source_ref: SourceRef | None = None

@dataclass
class AlternativeFlowSpec:
    """来自技能文档描述的完整替代执行路径."""
    flow_id: str                       # alt-001, alt-002, ...
    condition: str                       # 采用此替代路径的条件描述
    description: str                     # 一句话摘要
    steps: list[FlowStep]
    source_text: str
    provenance: Provenance
    source_ref: SourceRef | None = None

@dataclass
class ExceptionFlowSpec:
    """来自技能文档描述的失败处理路径."""
    flow_id: str                       # exc-001, exc-002, ...
    condition: str                     # 失败条件的描述
    log_ref: str                       # 可选LOG子句的文本; ""表示无LOG
    steps: list[FlowStep]
    source_text: str
    provenance: Provenance
    source_ref: SourceRef | None = None
```

**B1.6c: models/pipeline_steps/step3/registry.py**
```python
"""Step 3: 类型注册表和变量规格."""
from dataclasses import dataclass, field
from typing import Any

from models.base import SourceRef

@dataclass
class TypeExpression:
    """类型表达式表示."""
    base_type: str                     # "text", "number", "file", etc.
    is_list: bool = False
    is_optional: bool = False
    constraints: list[str] = field(default_factory=list)
    
    def to_spl(self) -> str:
        """转换为SPL类型表示."""
        type_str = self.base_type
        if self.is_list:
            type_str = f"List [{type_str}]"
        if self.is_optional:
            type_str = f"Optional [{type_str}]"
        return type_str

@dataclass
class VarSpec:
    """变量规格定义."""
    name: str
    type_expr: TypeExpression
    description: str
    is_required: bool = True
    provenance: str = "EXPLICIT"

@dataclass
class GlobalVarRegistry:
    """全局变量注册表."""
    variables: dict[str, VarSpec] = field(default_factory=dict)  # name -> VarSpec
    files: dict[str, VarSpec] = field(default_factory=dict)        # file path -> VarSpec
    step_io: dict[str, dict] = field(default_factory=dict)         # step_id -> {inputs, outputs}
    
    def register_variable(self, name: str, spec: VarSpec) -> None:
        self.variables[name] = spec
    
    def register_file(self, path: str, spec: VarSpec) -> None:
        self.files[path] = spec
```

**依赖**: B1.5
**验收标准**:
- [ ] entities.py实现完成
- [ ] flows.py实现完成
- [ ] registry.py实现完成
- [ ] 所有Literal类型正确导出

---

#### 任务 B1.7: 实现 models/pipeline_steps/api.py
**目标**: API定义相关模型
**工期**: 1天
**负责人**: Dev-3

**内容**:
```python
"""API定义相关模型 (Step 1.5, Step 4D)."""
from dataclasses import dataclass, field
from typing import Any

from models.base import SourceRef

@dataclass
class FunctionSpec:
    """Unified API中的单个函数/方法规格."""
    name: str                          # 函数/方法名
    signature: str                     # 代码片段或函数签名
    description: str                   # 函数描述
    input_schema: dict[str, str]       # 参数名 -> 类型
    output_schema: str                 # 返回类型
    source_ref: SourceRef | None = None

@dataclass
class UnifiedAPISpec:
    """统一API规格，聚合同一库的多个函数."""
    api_id: str                        # 唯一标识符，如"pypdf_from_doc1"
    api_name: str                      # SPL用的PascalCase名，如"PypdfProcessing"
    primary_library: str               # URL前缀的主库
    all_libraries: list[str]           # 涉及的所有库
    language: str                      # 编程语言
    functions: list[FunctionSpec]      # 此API中的所有函数
    combined_source: str               # 合并的源代码
    source_file: str                   # 源MD文件路径
    source_ref: SourceRef | None = None

@dataclass
class APISpec:
    """单工具的生成API规格 (旧格式，保持兼容)."""
    name: str                          # API名
    spl_text: str                      # LLM生成的完整DEFINE_API块
    input_params: list[dict[str, Any]]  # [{"name": str, "type": str, "required": bool}]
    output_params: list[dict[str, Any]] # [{"name": str, "type": str}]
    description: str                   # API简述
    source_ref: SourceRef | None = None

@dataclass
class ToolSpec:
    """用于DEFINE_APIS生成的统一API规格."""
    name: str                          # API名 (用于tool_hint引用)
    api_type: str                      # "SCRIPT" | "CODE_SNIPPET" | "NETWORK_API"
    url: str                           # scripts/<filename>.py | <library>.Class | https://...
    authentication: str                # "none" | "apikey" | "oauth"
    input_schema: dict[str, str]         # 参数名 -> 类型
    output_schema: str                 # 返回类型或"void"
    description: str                   # 简短功能描述
    source_text: str                   # 原始源代码/文本
    source_ref: SourceRef | None = None

@dataclass
class APISymbolTable:
    """技能的所有API定义集合."""
    apis: dict[str, APISpec] = field(default_factory=dict)              # api_name -> APISpec
    unified_apis: dict[str, UnifiedAPISpec] = field(default_factory=dict)  # api_name -> UnifiedAPISpec
    
    def to_text(self) -> str:
        """渲染所有API定义为S4E输入文本."""
        if not self.apis:
            return "(No APIs defined)"
        lines = ["# APIS (reference as <API_REF> api_name </API_REF>):", ""]
        for name, spec in self.apis.items():
            lines.append(f"API: {name}")
            lines.append(f" Description: {spec.description}")
            if spec.input_params:
                inputs = ", ".join(f"{p['name']}: {p['type']}" for p in spec.input_params)
                lines.append(f" Input: ({inputs})")
            if spec.output_params:
                outputs = ", ".join(f"{p['name']}: {p['type']}" for p in spec.output_params)
                lines.append(f" Output: ({outputs})")
            lines.append("")
        return "\n".join(lines)
    
    def get_api_names(self) -> list[str]:
        return list(self.apis.keys())
    
    def merge(self, other: APISymbolTable) -> APISymbolTable:
        """合并另一个符号表."""
        merged = APISymbolTable()
        merged.apis = {**self.apis, **other.apis}
        merged.unified_apis = {**self.unified_apis, **other.unified_apis}
        return merged
```

**依赖**: B1.6
**验收标准**:
- [ ] FunctionSpec实现完成
- [ ] UnifiedAPISpec实现完成
- [ ] APISpec和ToolSpec实现完成
- [ ] APISymbolTable实现完成

---

#### 任务 B1.8: 实现 models/pipeline_steps/step4.py
**目标**: Step 4 SPL输出模型
**工期**: 1天
**负责人**: Dev-4

**内容**:
```python
"""Step 4: SPL Emission 相关模型."""
from dataclasses import dataclass, field
from typing import Any

from models.core import ReviewItem

@dataclass
class SPLSpec:
    """Step 4输出: 最终规格化的SPL."""
    skill_id: str
    spl_text: str                      # 完整的SPL代码块
    review_summary: str                # 纯文本审查摘要
    clause_counts: dict[str, int] = field(default_factory=dict)  # {"HARD": N, ...}
    review_items: list[ReviewItem] = field(default_factory=list)  # 结构化审查项
    
    def get_section(self, section_name: str) -> str:
        """提取SPL中的特定节."""
        # 使用正则解析
        import re
        pattern = rf"\[DEFINE_{section_name.upper()}:.*?\[END_{section_name.upper()}\]"
        match = re.search(pattern, self.spl_text, re.DOTALL)
        return match.group(0) if match else ""
    
    def validate_syntax(self) -> list[str]:
        """基础SPL语法验证."""
        errors = []
        # 检查未闭合的块
        opens = self.spl_text.count("[DEFINE_")
        closes = self.spl_text.count("[END_")
        if opens != closes:
            errors.append(f"Mismatched blocks: {opens} opens, {closes} closes")
        return errors

@dataclass
class StructuredSpec:
    """Step 3合并输出 (Step 3A + Step 3B)."""
    from models.pipeline_steps.step3.entities import EntitySpec, WorkflowStepSpec
    from models.pipeline_steps.step3.flows import AlternativeFlowSpec, ExceptionFlowSpec
    
    entities: list[EntitySpec]
    workflow_steps: list[WorkflowStepSpec]
    alternative_flows: list[AlternativeFlowSpec] = field(default_factory=list)
    exception_flows: list[ExceptionFlowSpec] = field(default_factory=list)
    
    # 兼容性别名
    @property
    def interface(self) -> StructuredSpec:
        """InterfaceSpec兼容别名."""
        return self
```

**依赖**: B1.7
**验收标准**:
- [ ] SPLSpec实现完成
- [ ] StructuredSpec实现完成
- [ ] 验证方法测试通过

---

### Week 4: 核心结果模型与__init__.py

#### 任务 B2.1: 实现 models/pipeline_result.py
**目标**: PipelineResult和PipelineConfig
**工期**: 1.5天
**负责人**: Dev-4

**内容**:
```python
"""Pipeline结果和配置模型."""
from dataclasses import dataclass, field
from typing import Any, Optional
from pathlib import Path

from models.core import SessionUsage
from models.preprocessing.reference import FileReferenceGraph
from models.preprocessing.package import SkillPackage
from models.pipeline_steps.step1 import SectionBundle
from models.pipeline_steps.step4 import SPLSpec, StructuredSpec

@dataclass
class PipelineResult:
    """完整Pipeline运行的输出."""
    skill_id: str
    
    # 中间输出 (保留用于可追溯性/从checkpoint恢复)
    graph: FileReferenceGraph
    file_role_map: dict[str, Any]
    package: SkillPackage
    section_bundle: SectionBundle
    structured_spec: StructuredSpec
    
    # 最终输出
    spl_spec: SPLSpec
    
    # 元数据
    session_usage: SessionUsage = field(default_factory=SessionUsage)
    duration_seconds: float = 0.0
    checkpoints_saved: list[str] = field(default_factory=list)
    
    def get_token_summary(self) -> str:
        """获取token使用摘要."""
        total = self.session_usage.total
        lines = [
            f"Token Usage Summary for {self.skill_id}:",
            f"  Prompt: {total.prompt_tokens:,}",
            f"  Completion: {total.completion_tokens:,}",
            f"  Total: {total.total_tokens:,}",
            "",
            "By Step:",
        ]
        for step_name, usage in self.session_usage.steps.items():
            lines.append(f"  {step_name}: {usage.total_tokens:,} tokens")
        return "\n".join(lines)
    
    def save_checkpoints(self, output_dir: Path) -> None:
        """保存所有中间结果到checkpoint文件."""
        pass  # 实现略
```

**依赖**: B1.8
**验收标准**:
- [ ] PipelineResult实现完成
- [ ] 包含SessionUsage
- [ ] 包含所有中间输出字段
- [ ] 辅助方法测试通过

---

#### 任务 B2.2: 实现 models/__init__.py 主导出
**目标**: 统一导出接口
**工期**: 1天
**负责人**: Dev-1

**内容**:
```python
"""Models package - Unified exports for all data models."""

# Base types
from models.base import (
    SourceRef,
    Provenance,
    Priority,
    FileKind,
    Serializable,
    Validatable,
)

# Core types
from models.core import (
    TokenUsage,
    SessionUsage,
    ReviewItem,
)

# Preprocessing models
from models.preprocessing.reference import (
    FileNode,
    FileReferenceGraph,
)
from models.preprocessing.roles import (
    FileRoleEntry,
    FileRoleMap,
)
from models.preprocessing.package import (
    SkillPackage,
)

# Pipeline step models
from models.pipeline_steps.step1 import (
    SectionItem,
    SectionBundle,
    CANONICAL_SECTIONS,
)
from models.pipeline_steps.step3.entities import (
    EntitySpec,
    WorkflowStepSpec,
    ActionType,
    EntityKind,
)
from models.pipeline_steps.step3.flows import (
    FlowStep,
    AlternativeFlowSpec,
    ExceptionFlowSpec,
)
from models.pipeline_steps.step3.registry import (
    TypeExpression,
    VarSpec,
    GlobalVarRegistry,
)
from models.pipeline_steps.api import (
    FunctionSpec,
    UnifiedAPISpec,
    APISpec,
    ToolSpec,
    APISymbolTable,
)
from models.pipeline_steps.step4 import (
    SPLSpec,
    StructuredSpec,
)

# Pipeline result
from models.pipeline_result import PipelineResult

__all__ = [
    # Base
    "SourceRef",
    "Provenance",
    "Priority",
    "FileKind",
    "Serializable",
    "Validatable",
    # Core
    "TokenUsage",
    "SessionUsage",
    "ReviewItem",
    # Preprocessing
    "FileNode",
    "FileReferenceGraph",
    "FileRoleEntry",
    "FileRoleMap",
    "SkillPackage",
    # Step 1
    "SectionItem",
    "SectionBundle",
    "CANONICAL_SECTIONS",
    # Step 3
    "EntitySpec",
    "WorkflowStepSpec",
    "FlowStep",
    "AlternativeFlowSpec",
    "ExceptionFlowSpec",
    "TypeExpression",
    "VarSpec",
    "GlobalVarRegistry",
    "ActionType",
    "EntityKind",
    # API
    "FunctionSpec",
    "UnifiedAPISpec",
    "APISpec",
    "ToolSpec",
    "APISymbolTable",
    # Step 4
    "SPLSpec",
    "StructuredSpec",
    # Result
    "PipelineResult",
]
```

**依赖**: B2.1
**验收标准**:
- [ ] 所有新模型正确导出
- [ ] __all__列表完整
- [ ] 可以通过`from models import X`访问所有类型

---

#### 任务 B2.3: 实现 models/deprecated.py 兼容层
**目标**: 向后兼容别名和弃用警告
**工期**: 1.5天
**负责人**: Dev-2

**内容**:
```python
"""向后兼容别名和弃用警告.

此模块提供旧导入路径的兼容层，将在v3.0中移除。
"""
import warnings
from typing import Any

# 发出一次弃用警告
warnings.warn(
    "Importing from models.data_models is deprecated. "
    "Use 'from models import X' instead. "
    "This compatibility layer will be removed in v3.0.",
    DeprecationWarning,
    stacklevel=2,
)

# 从data_models导入所有内容作为兼容层
# 这些将在迁移完成后从data_models移除
from models import (
    FileNode,
    FileReferenceGraph,
    FileRoleEntry,
    SkillPackage,
    SectionItem,
    SectionBundle,
    EntitySpec,
    WorkflowStepSpec,
    AlternativeFlowSpec,
    ExceptionFlowSpec,
    InteractionRequirement,
    NeedsReviewItem,
    StructuredSpec,
    APISpec,
    FunctionSpec,
    UnifiedAPISpec,
    APISymbolTable,
    SPLSpec,
    PipelineResult,
    ToolSpec,
    ScriptSpec,
)

# 旧名称别名 (如果有重命名)
InterfaceSpec = StructuredSpec  # 旧名称，已弃用

__all__ = [
    # Preprocessing
    "FileNode",
    "FileReferenceGraph",
    "ScriptSpec",
    "ToolSpec",
    "FileRoleEntry",
    "SkillPackage",
    # Step 1
    "SectionItem",
    "SectionBundle",
    # Step 3
    "EntitySpec",
    "WorkflowStepSpec",
    "AlternativeFlowSpec",
    "ExceptionFlowSpec",
    "InteractionRequirement",
    # Legacy
    "NeedsReviewItem",
    "StructuredSpec",
    "InterfaceSpec",
    # Step 1.5
    "APISpec",
    "FunctionSpec",
    "UnifiedAPISpec",
    "APISymbolTable",
    # Step 4
    "SPLSpec",
    # Top-level
    "PipelineResult",
]
```

**依赖**: B2.2
**验收标准**:
- [ ] 所有旧导入路径可用
- [ ] 发出正确的DeprecationWarning
- [ ] 别名指向正确的新类型

---

### Week 5: 迁移与测试

#### 任务 B3.1: 更新现有导入路径
**目标**: 将所有`from models.data_models import`改为`from models import`
**工期**: 2天
**负责人**: Dev-3

**受影响文件清单**:
```
pipeline/orchestrator.py        - 导入PipelineResult, StructuredSpec等
pipeline/orchestrator_async.py
pipeline/llm_client.py          - TokenUsage相关
pre_processing/p1_reference_graph.py  - FileNode等
pre_processing/p2_file_roles.py
pre_processing/p3_assembler.py    - SkillPackage, ToolSpec等
pre_processing/p25_api_analyzer.py
pre_processing/script_analyzer.py
pre_processing/unified_api_extractor.py
pipeline/llm_steps/step1_structure_extraction.py
pipeline/llm_steps/step1_5_api_generation.py
pipeline/llm_steps/step3/*.py
pipeline/llm_steps/step4_spl_emission/*.py
simplified_pipeline/*.py
test/*.py
```

**迁移步骤**:
1. 对每个受影响文件:
   - 分析当前的导入
   - 替换为新导入路径
   - 运行import测试
   - 提交更改

2. 优先级顺序:
   - P1: pre_processing/ (低依赖)
   - P2: pipeline/llm_steps/ (中等依赖)
   - P3: pipeline/orchestrator.py (高依赖)

**依赖**: B2.3
**验收标准**:
- [ ] 所有文件导入路径更新
- [ ] 没有循环导入错误
- [ ] pytest可以加载所有模块

---

#### 任务 B3.2: 更新 models/data_models.py 为兼容转发
**目标**: 将原文件改为转发到新的模块化结构
**工期**: 0.5天
**负责人**: Dev-4

**内容**:
```python
"""数据模型 (已弃用 - 请使用 models 包).

此文件保留仅用于向后兼容。新代码请使用:
    from models import X

将在v3.0中移除。
"""
import warnings

warnings.warn(
    "models.data_models is deprecated. Use 'from models import X' instead. "
    "This module will be removed in v3.0.",
    DeprecationWarning,
    stacklevel=2,
)

# 转发到新模块
from models import (
    # Preprocessing
    FileNode,
    FileReferenceGraph,
    FileRoleEntry,
    SkillPackage,
    # Step 1
    SectionItem,
    SectionBundle,
    # Step 3
    EntitySpec,
    WorkflowStepSpec,
    FlowStep,
    AlternativeFlowSpec,
    ExceptionFlowSpec,
    # API
    APISpec,
    FunctionSpec,
    UnifiedAPISpec,
    APISymbolTable,
    ToolSpec,
    # Step 4
    SPLSpec,
    StructuredSpec,
    # Core
    PipelineResult,
)

# 保持InterfaceSpec别名
InterfaceSpec = StructuredSpec

__all__ = [
    "FileNode", "FileReferenceGraph", "FileRoleEntry", "SkillPackage",
    "SectionItem", "SectionBundle",
    "EntitySpec", "WorkflowStepSpec", "FlowStep",
    "AlternativeFlowSpec", "ExceptionFlowSpec",
    "APISpec", "FunctionSpec", "UnifiedAPISpec", "APISymbolTable", "ToolSpec",
    "SPLSpec", "StructuredSpec", "InterfaceSpec", "PipelineResult",
]
```

**依赖**: B3.1
**验收标准**:
- [ ] 原文件正确转发
- [ ] 旧导入仍然工作
- [ ] 发出弃用警告

---

#### 任务 B3.3: 全面测试
**目标**: 确保重构后的代码行为一致
**工期**: 1.5天
**负责人**: Dev-1 (主导), Dev-2, Dev-3, Dev-4 (协助)

**测试层级**:

1. **单元测试** (各模块开发者负责)
   ```
   pytest test/models/ -v
   ```
   - 每个模型类的序列化/反序列化
   - 边界条件测试
   - 类型检查

2. **集成测试**
   ```
   pytest test/test_pipeline.py -v
   ```
   - P1→P2→P3完整流程
   - Step 1→3→4完整流程

3. **回归测试**
   ```
   pytest test/ -v --tb=short
   ```
   - 所有现有测试通过
   - 使用示例技能包测试:
     ```bash
     python -m skill_to_cnlp --skill skills/pdf --output output/test
     ```

4. **类型检查**
   ```
   mypy models/ --strict
   mypy pipeline/ --strict
   mypy pre_processing/ --strict
   ```

**依赖**: B3.2
**验收标准**:
- [ ] 所有单元测试通过 (>80%覆盖率)
- [ ] 所有集成测试通过
- [ ] mypy无错误
- [ ] 示例技能包生成正确SPL
- [ ] 性能无显著回归 (<5%)

---

#### 任务 B3.4: 文档更新
**目标**: 更新文档反映新结构
**工期**: 1天
**负责人**: Dev-2

**更新内容**:
1. **AGENTS.md模型部分**
   - 更新"Structure"章节
   - 更新"WHERE TO LOOK"表格

2. **新增 models/README.md**
   ```markdown
   # Models Package
   
   ## 结构
   - base.py - 基础类型和协议
   - core.py - 核心共享类型
   - preprocessing/ - P1-P3模型
   - pipeline_steps/ - Step 1-4模型
   
   ## 使用
   ```python
   from models import FileNode, SectionBundle
   ```
   
   ## 迁移指南
   旧: `from models.data_models import X`
   新: `from models import X`
   ```

3. **代码注释**
   - 在每个模块添加docstring
   - 为关键类添加使用示例

**依赖**: B3.3
**验收标准**:
- [ ] AGENTS.md已更新
- [ ] models/README.md已创建
- [ ] 所有模块有docstring

---

## 三、风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|-----|-------|-----|---------|
| 循环导入 | 中 | 高 | 使用`TYPE_CHECKING`和延迟导入 |
| 导入路径遗漏 | 高 | 中 | 使用IDE全局搜索+自动化脚本验证 |
| 性能下降 | 低 | 中 | 基准测试对比，如有问题回滚到扁平导入 |
| 测试失败 | 中 | 高 | 每完成一个模块立即测试，早发现问题 |

---

## 四、验收标准汇总

### Week 3
- [ ] 新目录结构创建完成
- [ ] base.py, core.py实现完成并通过测试
- [ ] preprocessing/模块实现完成
- [ ] step1.py实现完成
- [ ] step3/目录实现完成
- [ ] api.py实现完成

### Week 4
- [ ] step4.py实现完成
- [ ] pipeline_result.py实现完成
- [ ] models/__init__.py正确导出所有类型
- [ ] models/deprecated.py兼容层实现

### Week 5
- [ ] 所有导入路径更新完成
- [ ] models/data_models.py改为转发模式
- [ ] 测试覆盖率>80%
- [ ] mypy类型检查通过
- [ ] 文档更新完成
- [ ] 示例技能包验证通过

---

## 五、文件变更清单

### 新增文件
```
models/base.py
models/core.py
models/pipeline_result.py
test/models/ (测试目录)
models/README.md

models/preprocessing/__init__.py
models/preprocessing/reference.py
models/preprocessing/roles.py
models/preprocessing/package.py

models/pipeline_steps/__init__.py
models/pipeline_steps/step1.py
models/pipeline_steps/api.py
models/pipeline_steps/step4.py

models/pipeline_steps/step3/__init__.py
models/pipeline_steps/step3/entities.py
models/pipeline_steps/step3/flows.py
models/pipeline_steps/step3/registry.py
```

### 修改文件
```
models/__init__.py        # 重写为新导出
models/data_models.py     # 改为转发模式
models/deprecated.py      # 新增兼容层

# 导入更新 (约15-20个文件)
pipeline/orchestrator.py
pipeline/orchestrator_async.py
pre_processing/p1_reference_graph.py
pre_processing/p2_file_roles.py
pre_processing/p3_assembler.py
pre_processing/p25_api_analyzer.py
pre_processing/script_analyzer.py
pre_processing/unified_api_extractor.py
pipeline/llm_steps/step1_structure_extraction.py
pipeline/llm_steps/step1_5_api_generation.py
pipeline/llm_steps/step3/*.py
pipeline/llm_steps/step4_spl_emission/*.py
simplified_pipeline/*.py
test/*.py
AGENTS.md
```

---

## 六、里程碑

| 里程碑 | 日期 | 交付物 |
|-------|------|-------|
| M1: Week 3结束 | 第3周末 | 所有新模型模块实现完成 |
| M2: Week 4结束 | 第4周末 | __init__.py和兼容层完成 |
| M3: Week 5结束 | 第5周末 | 迁移完成，测试通过，文档更新 |

---

## 七、附录

### A. 依赖关系图

```
base.py (无依赖)
  ↓
core.py
  ↓
preprocessing/
  - reference.py
  - roles.py
  - package.py (依赖api.py)
    ↓
pipeline_steps/
  - step1.py
  - api.py
  - step3/ (依赖base.py, core.py)
  - step4.py (依赖step3/)
    ↓
pipeline_result.py (依赖所有上游)
```

### B. 循环导入解决方案

如遇循环导入，使用以下模式:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.pipeline_steps.step3.entities import EntitySpec

# 实际使用时延迟导入
def process_entity(entity: "EntitySpec") -> None:
    from models.pipeline_steps.step3.entities import EntitySpec
    ...
```

### C. 弃用时间线

| 版本 | 行为 |
|-----|------|
| v2.x (当前) | `from models.data_models import X` 发出DeprecationWarning但可用 |
| v3.0 (未来) | 完全移除models/data_models.py，仅支持新导入路径 |

---

### D. 兼容层移除详细计划

#### Phase B 中的迁移准备 (当前)

**任务：更新所有内部导入路径**

在Week 5的任务B3.1中，我们需要更新所有内部导入路径：

```
# 需要更新的文件（约15-20个）
✓ pipeline/orchestrator.py
✓ pipeline/orchestrator_async.py  
✓ pre_processing/p1_reference_graph.py
✓ pre_processing/p2_file_roles.py
✓ pre_processing/p3_assembler.py
✓ pre_processing/p25_api_analyzer.py
✓ pre_processing/script_analyzer.py
✓ pre_processing/unified_api_extractor.py
✓ pipeline/llm_steps/step1_structure_extraction.py
✓ pipeline/llm_steps/step1_5_api_generation.py
✓ pipeline/llm_steps/step3/*.py
✓ pipeline/llm_steps/step4_spl_emission/*.py
✓ simplified_pipeline/*.py
✓ test/*.py
✓ AGENTS.md
```

**工具：自动化迁移脚本**

```python
#!/usr/bin/env python3
"""migrate_imports.py - Automated migration script for import paths."""

import re
from pathlib import Path

MIGRATION_RULES = [
    # Old import -> New import
    (
        r'from models\.data_models import',
        'from models import'
    ),
    (
        r'from models\.data_models import (.+)$',
        r'from models import \1'
    ),
]

def migrate_file(filepath: Path) -> bool:
    """Migrate imports in a single file."""
    content = filepath.read_text(encoding='utf-8')
    original = content
    
    for pattern, replacement in MIGRATION_RULES:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    if content != original:
        filepath.write_text(content, encoding='utf-8')
        print(f"Migrated: {filepath}")
        return True
    return False

def main():
    """Run migration on all Python files."""
    project_root = Path('.')
    python_files = project_root.rglob('*.py')
    
    migrated_count = 0
    for filepath in python_files:
        if 'models/' not in str(filepath):  # Skip models package itself
            if migrate_file(filepath):
                migrated_count += 1
    
    print(f"Total files migrated: {migrated_count}")

if __name__ == '__main__':
    main()
```

#### Phase C-D 后的清理 (未来)

**版本 v2.1+ (Phase C-D完成后)**

1. **确认无内部使用**:
   ```bash
   # 检查是否还有内部代码使用旧导入
   grep -r "from models.data_models import" --include="*.py" . || echo "No old imports found"
   ```

2. **强化警告**:
   - 将 `DeprecationWarning` 改为 `FutureWarning`（对用户可见）
   - 在文档中添加"即将移除"标记

**版本 v3.0 (正式发布)**

1. **移除兼容文件**:
   - 删除 `models/data_models.py`
   - 删除 `models/deprecated.py`
   - 从 `models/__init__.py` 中移除兼容层导入

2. **更新文档**:
   - 从迁移指南中移除旧路径说明
   - 更新所有示例代码
   - 发布迁移公告

3. **验证**:
   ```bash
   # 验证新结构
   python -c "from models import *; print('All imports OK')"
   
   # 验证旧导入确实失败
   python -c "from models.data_models import FileNode" 2>&1 | grep "ModuleNotFoundError"
   ```

#### 迁移检查清单

**对于每个要更新的文件：**

- [ ] 识别所有 `from models.data_models import` 语句
- [ ] 替换为 `from models import` 
- [ ] 运行文件确保无语法错误
- [ ] 运行相关测试
- [ ] 提交更改

**验证指标：**

- [ ] `grep -r "from models.data_models" --include="*.py" .` 返回空结果
- [ ] 所有测试通过
- [ ] CI/CD 构建成功
- [ ] 文档示例已更新

#### 回滚策略

如果v3.0移除后发现外部依赖仍使用旧导入：

1. **紧急补丁 (v3.0.1)**：
   - 临时恢复 `models/data_models.py` 作为转发层
   - 发出更强的弃用警告

2. **延期移除 (v3.1)**：
   - 给外部用户额外1个版本的迁移时间
   - 在 CHANGELOG 中明确标注

3. **完整移除 (v4.0)**：
   - 最终移除所有兼容层

---

**文档版本**: 1.0
**最后更新**: 2026-04-17
**作者**: Architecture Team
