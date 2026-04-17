"""Step 3: Entity and Workflow Analysis 相关模型.

此模块包含Step 3阶段用于实体提取和工作流分析的数据结构.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Any

from models.base import Provenance, SourceRef


# ═══════════════════════════════════════════════════════════════════════════════
# 类型别名和常量
# ═══════════════════════════════════════════════════════════════════════════════

ActionType = Literal[
    "EXTERNAL_API",
    "LLM_TASK",
    "EXEC_SCRIPT",
    "FILE_READ",
    "FILE_WRITE",
    "USER_INTERACTION",
    "LOCAL_CODE_SNIPPET",
]
"""Action类型.

取值:
    - EXTERNAL_API: 调用外部API/服务
    - LLM_TASK: LLM推理或判断任务
    - EXEC_SCRIPT: 运行或生成脚本
    - FILE_READ: 读取文件
    - FILE_WRITE: 写入文件
    - USER_INTERACTION: 需要用户输入
    - LOCAL_CODE_SNIPPET: 执行字面代码块
"""

EntityKind = Literal["Artifact", "Run", "Evidence", "Record"]
"""Entity种类.

取值:
    - Artifact: 文件产出
    - Run: 运行时变量
    - Evidence: 证据要求
    - Record: 记录数据
"""

InteractionType = Literal["ASK", "STOP", "ELICIT"]
"""交互类型.

取值:
    - ASK: 询问用户
    - STOP: 停止并请求确认
    - ELICIT: 引出选择
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 实体模型
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class EntitySpec:
    """WORKER读取或产生的命名数据实体.

    表示工作流中使用的数据实体，可以是文件或内存变量.

    Attributes:
        entity_id: 实体标识符
        kind: 实体种类 (Artifact | Run | Evidence | Record)
        type_name: SPL类型名称
        schema_notes: 模式说明，可用时由EXAMPLES节丰富
        provenance_required: 是否需要来源
        provenance: 来源可信度 (EXPLICIT | ASSUMED | LOW_CONFIDENCE)
        source_text: 源文本原样
        is_file: True当kind=Artifact或from_omit_files=True
        file_path: 实际路径; "" → SPL中的"< >"
        from_omit_files: True如果来自P1 read_priority=3节点
        source_ref: 源代码引用位置

    Examples:
        >>> entity = EntitySpec(
        ...     entity_id="pdf_file",
        ...     kind="Artifact",
        ...     type_name="PDFDocument",
        ...     schema_notes="Input PDF file",
        ...     provenance_required=True,
        ...     provenance="EXPLICIT",
        ...     source_text="From SKILL.md",
        ...     is_file=True,
        ...     file_path="input.pdf",
        ... )
    """

    entity_id: str
    kind: EntityKind
    type_name: str
    schema_notes: str
    provenance_required: bool
    provenance: Provenance
    source_text: str
    is_file: bool = False
    file_path: str = ""
    from_omit_files: bool = False
    source_ref: SourceRef | None = None

    def __post_init__(self) -> None:
        """根据kind自动设置is_file."""
        if self.kind == "Artifact" and not self.is_file:
            object.__setattr__(self, "is_file", True)

    def is_input(self) -> bool:
        """是否为输入实体."""
        return self.entity_id.startswith("input") or self.provenance_required

    def is_output(self) -> bool:
        """是否为输出实体."""
        return self.entity_id.startswith("output")


@dataclass(slots=True)
class WorkflowStep:
    """工作流中的单步，重写为SPL就绪形式.

    Attributes:
        step_id: 步骤标识符 (step.<action_name> snake_case)
        description: SPL就绪的COMMAND描述
        prerequisites: 执行前必须存在的entity_ids
        produces: 此步骤创建的entity_ids
        is_validation_gate: 是否来自EVIDENCE要求
        action_type: 动作类型
        tool_hint: 显式声明的工具/脚本名
        source_text: 源中的原样锚点
        source_ref: 源代码引用位置

    Examples:
        >>> step = WorkflowStep(
        ...     step_id="step.read_pdf",
        ...     description="Read PDF file",
        ...     prerequisites=["pdf_file"],
        ...     produces=["pdf_content"],
        ...     is_validation_gate=False,
        ...     action_type="FILE_READ",
        ... )
    """

    step_id: str
    description: str
    prerequisites: list[str]
    produces: list[str]
    is_validation_gate: bool
    action_type: ActionType = "LLM_TASK"
    tool_hint: str = ""
    source_text: str = ""
    source_ref: SourceRef | None = None

    def is_ready(self, available: set[str]) -> bool:
        """检查此步骤是否可以执行（所有前置条件满足）.

        Args:
            available: 已可用的实体集合

        Returns:
            如果就绪返回True
        """
        return all(p in available for p in self.prerequisites)

    def get_new_outputs(self, available: set[str]) -> list[str]:
        """返回执行后将新增的产出实体.

        Args:
            available: 当前可用实体集合

        Returns:
            新产出实体列表
        """
        return [p for p in self.produces if p not in available]


@dataclass(slots=True)
class FlowStep:
    """ALTERNATIVE_FLOW或EXCEPTION_FLOW中的单步.

    Attributes:
        description: 简洁的动作描述
        action_type: 动作类型
        tool_hint: 显式工具/API名
        source_text: 技能文档中的原样锚点
        source_ref: 源代码引用位置
    """

    description: str = ""
    action_type: str = "LLM_TASK"
    tool_hint: str = ""
    source_text: str = ""
    source_ref: SourceRef | None = None


@dataclass(slots=True)
class AlternativeFlow:
    """来自技能文档描述的完整替代执行路径.

    Attributes:
        flow_id: 流程标识符 (alt-001, alt-002, ...)
        condition: 采用此替代路径的条件描述
        description: 一句话摘要
        steps: 此替代过程的有序步骤
        source_text: 技能文档中的原样锚点
        provenance: 来源可信度
        source_ref: 源代码引用位置

    Examples:
        >>> flow = AlternativeFlow(
        ...     flow_id="alt-001",
        ...     condition="If PDF is encrypted",
        ...     description="Use password to decrypt",
        ...     steps=[FlowStep(description="Prompt for password")],
        ...     provenance="EXPLICIT",
        ... )
    """

    flow_id: str
    condition: str
    description: str
    steps: list[FlowStep]
    source_text: str
    provenance: Provenance
    source_ref: SourceRef | None = None


@dataclass(slots=True)
class ExceptionFlow:
    """来自技能文档描述的失败处理路径.

    Attributes:
        flow_id: 流程标识符 (exc-001, exc-002, ...)
        condition: 失败条件的描述
        log_ref: 可选LOG子句的文本; ""表示无LOG
        steps: 有序的恢复/优雅停止步骤
        source_text: 技能文档中的原样锚点
        provenance: 来源可信度
        source_ref: 源代码引用位置

    Examples:
        >>> flow = ExceptionFlow(
        ...     flow_id="exc-001",
        ...     condition="PDF read fails",
        ...     log_ref="Failed to read PDF",
        ...     steps=[FlowStep(description="Log error")],
        ...     provenance="EXPLICIT",
        ... )
    """

    flow_id: str
    condition: str
    log_ref: str
    steps: list[FlowStep]
    source_text: str
    provenance: Provenance
    source_ref: SourceRef | None = None


@dataclass(slots=True)
class InteractionRequirement:
    """从NON_COMPILABLE子句派生.

    表示代理在继续前必须与用户交互的点.

    Attributes:
        req_id: 要求标识符
        condition: 触发此交互的条件
        interaction_type: 交互类型 (ASK | STOP | ELICIT)
        prompt: 呈现给用户的问题或消息
        gates_step: 此交互前置于的step_id (或""如果通用)
        source_text: NON子句原样文本
        source_ref: 源代码引用位置

    SPL映射:
        ASK → [INPUT DISPLAY "prompt" VALUE answer: text]
        STOP → [INPUT DISPLAY "prompt" VALUE confirmed: boolean] + DECISION
        ELICIT → [INPUT DISPLAY "prompt" VALUE choice: text]
    """

    req_id: str
    condition: str
    interaction_type: InteractionType
    prompt: str
    gates_step: str
    source_text: str
    source_ref: SourceRef | None = None


@dataclass(slots=True)
class StructuredSpec:
    """Step 3合并输出 (Step 3A + Step 3B).

    Attributes:
        entities: 实体列表
        workflow_steps: 工作流步骤列表
        alternative_flows: 替代流程列表
        exception_flows: 异常流程列表
        interaction_requirements: 交互要求列表
        source_ref: 源代码引用位置
    """

    entities: list[EntitySpec]
    workflow_steps: list[WorkflowStep]
    alternative_flows: list[AlternativeFlow] = field(default_factory=list)
    exception_flows: list[ExceptionFlow] = field(default_factory=list)
    interaction_requirements: list[InteractionRequirement] = field(
        default_factory=list
    )
    source_ref: SourceRef | None = None

    def get_entity(self, entity_id: str) -> EntitySpec | None:
        """按ID获取实体."""
        for e in self.entities:
            if e.entity_id == entity_id:
                return e
        return None

    def get_step(self, step_id: str) -> WorkflowStep | None:
        """按ID获取步骤."""
        for s in self.workflow_steps:
            if s.step_id == step_id:
                return s
        return None

    def get_file_entities(self) -> list[EntitySpec]:
        """获取所有文件类型实体."""
        return [e for e in self.entities if e.is_file]

    def get_variable_entities(self) -> list[EntitySpec]:
        """获取所有变量类型实体."""
        return [e for e in self.entities if not e.is_file]


# 兼容别名
InterfaceSpec = StructuredSpec


# ═══════════════════════════════════════════════════════════════════════════════
# 类型系统模型
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class TypeSpec:
    """类型规格定义.

    Attributes:
        base_type: 基础类型 (text, number, file等)
        is_list: 是否为列表
        is_optional: 是否为可选
        constraints: 约束条件列表
    """

    base_type: str
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


@dataclass(slots=True)
class VarSpec:
    """变量规格定义.

    Attributes:
        name: 变量名
        type_spec: 类型规格
        description: 描述
        is_required: 是否必需
        provenance: 来源
    """

    name: str
    type_spec: TypeSpec
    description: str
    is_required: bool = True
    provenance: str = "EXPLICIT"


@dataclass(slots=True)
class VarRegistry:
    """全局变量注册表.

    Attributes:
        variables: 变量名到VarSpec的映射
        files: 文件路径到VarSpec的映射
        step_io: step_id到{inputs, outputs}的映射
    """

    variables: dict[str, VarSpec] = field(default_factory=dict)
    files: dict[str, VarSpec] = field(default_factory=dict)
    step_io: dict[str, dict[str, Any]] = field(default_factory=dict)

    def register_variable(self, name: str, spec: VarSpec) -> None:
        """注册变量."""
        self.variables[name] = spec

    def register_file(self, path: str, spec: VarSpec) -> None:
        """注册文件."""
        self.files[path] = spec

    def get_variable(self, name: str) -> VarSpec | None:
        """获取变量."""
        return self.variables.get(name)

    def get_file(self, path: str) -> VarSpec | None:
        """获取文件."""
        return self.files.get(path)

    def register_step_io(
        self, step_id: str, inputs: list[str], outputs: list[str]
    ) -> None:
        """注册步骤的输入输出."""
        self.step_io[step_id] = {"inputs": inputs, "outputs": outputs}
