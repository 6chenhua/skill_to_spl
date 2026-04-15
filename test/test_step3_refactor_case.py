"""
TDD Test Cases for Step 3 Refactor
===================================

测试覆盖重构后的 Step 3 架构：
- Step3-W: Workflow Structure Analysis
- Step3-IO: Global I/O + Type Analysis
- Step3-T: TYPES Declaration

测试用例设计原则：
1. 每个测试用例验证一个明确的输入→输出转换
2. 输入数据是精简、结构化的（不是原始JSON堆）
3. 输出数据有明确的schema约束
4. 边界情况：空输入、单步骤、多步骤、复杂类型
"""

import pytest
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


# =============================================================================
# Schema Definitions (先定义输出的数据结构)
# =============================================================================

@dataclass
class TypeExpr:
    """
    类型表达式 - 表示一个数据的类型

    支持四种类型：
    1. 简单基础类型: "text" | "image" | "audio" | "number" | "boolean"
    2. 枚举类型: EnumType(values=["red", "green", "blue"])
    3. 数组类型: ArrayType(element_type=TypeExpr(...))
    4. 结构化类型: StructType(fields={"name": TypeExpr(...), ...})

    序列化格式（用于LLM输出）：
    - 简单类型: "text"
    - 枚举: ["red", "green", "blue"]
    - 数组: "List[text]" 或 "List[{field: text}]"
    - 结构体: "{field1: text, field2: number}"
    """
    kind: str  # "simple" | "enum" | "array" | "struct"
    # simple时: type_name = "text" | "image" | "audio" | "number" | "boolean"
    type_name: Optional[str] = None
    # enum时: values = ["red", "green", ...]
    values: Optional[list[str]] = None
    # array时: element_type = TypeExpr(...)
    element_type: Optional['TypeExpr'] = None
    # struct时: fields = {"field_name": TypeExpr(...), ...}
    fields: Optional[dict[str, 'TypeExpr']] = None

    def to_dict(self) -> dict | str | list:
        """序列化为LLM输出的JSON格式"""
        if self.kind == "simple":
            return self.type_name
        elif self.kind == "enum":
            return self.values
        elif self.kind == "array":
            return f"List[{self.element_type.to_dict()}]"
        elif self.kind == "struct":
            if not self.fields:
                return "{}"
            field_strs = [f"{k}: {v.to_dict()}" for k, v in self.fields.items()]
            return "{" + ", ".join(field_strs) + "}"
        raise ValueError(f"Unknown kind: {self.kind}")

    @classmethod
    def from_dict(cls, data: Any) -> 'TypeExpr':
        """从LLM输出的JSON解析"""
        if isinstance(data, str):
            # 可能是简单类型或数组类型
            if data in ("text", "image", "audio", "number", "boolean"):
                return cls(kind="simple", type_name=data)
            elif data.startswith("List[") and data.endswith("]"):
                inner = data[5:-1]
                return cls(kind="array", element_type=cls.from_dict(inner))
            else:
                raise ValueError(f"Unknown simple type: {data}")
        elif isinstance(data, list):
            # 枚举类型
            return cls(kind="enum", values=data)
        elif isinstance(data, dict):
            # 结构体
            fields = {k: cls.from_dict(v) for k, v in data.items()}
            return cls(kind="struct", fields=fields)
        else:
            raise ValueError(f"Unknown type data: {data}")


@dataclass
class VarSpec:
    """
    变量规格 - 表示一个步骤的输入或输出变量

    包含：
    - var_name: 变量名
    - type_expr: 类型表达式
    - is_file: 是否为文件（用于区分 VARIABLES 和 FILES）
    - description: 可选的变量描述
    """
    var_name: str
    type_expr: TypeExpr
    is_file: bool = False
    description: str = ""


@dataclass
class StepIOSpec:
    """
    单个步骤的I/O规格

    输入输出都是 VarSpec 的字典，key是变量名
    """
    step_id: str
    prerequisites: dict[str, VarSpec]  # var_name -> VarSpec
    produces: dict[str, VarSpec]  # var_name -> VarSpec


@dataclass
class GlobalVarRegistry:
    """
    全局变量注册表 - 所有步骤共享的变量定义

    来自对所有步骤 prerequisites + produces 的去重合并
    """
    variables: dict[str, VarSpec]  # var_name -> VarSpec (is_file=False)
    files: dict[str, VarSpec]  # var_name -> VarSpec (is_file=True)


@dataclass
class WorkflowStepRaw:
    """
    Step3-W的输出：不含I/O的原始步骤结构

    只包含从WORKFLOW文本中提取的动作描述，
    不包含数据依赖（prerequisites/produces）
    """
    step_id: str  # "step.<action_name>"
    description: str  # SPL-ready动作描述
    action_type: str  # LLM_TASK | EXEC_SCRIPT | FILE_READ | FILE_WRITE | USER_INTERACTION | EXTERNAL_API | LOCAL_CODE_SNIPPET
    tool_hint: str = ""  # 工具名（如果有）
    is_validation_gate: bool = False  # 是否为验证门
    source_text: str = ""  # 原始文本锚点


@dataclass
class TypeDecl:
    """
    Step3-T的输出：类型声明

    对应 SPL [DEFINE_TYPES:] 中的一个条目
    """
    declared_name: str  # PascalCase类型名
    type_expr: TypeExpr  # 类型定义（枚举或结构体）
    description: str = ""  # 类型描述


@dataclass
class Step3WOutput:
    """Step3-W的完整输出"""
    workflow_steps: list[WorkflowStepRaw]
    alternative_flows: list[Any]  # 暂时用Any
    exception_flows: list[Any]  # 暂时用Any


@dataclass
class Step3IOOutput:
    """Step3-IO的完整输出"""
    step_io_specs: dict[str, StepIOSpec]  # step_id -> StepIOSpec
    global_registry: GlobalVarRegistry  # 全局变量注册表


@dataclass
class Step3TOutput:
    """Step3-T的完整输出"""
    type_decls: list[TypeDecl]  # 所有声明的类型
    type_registry: dict[str, str]  # inline_signature -> declared_name 映射


# =============================================================================
# Test Case 1: Step3-W (Workflow Structure Analysis)
# =============================================================================

class TestStep3W:
    """
    Step3-W: Workflow Structure Analysis

    输入：
    - workflow_section: WORKFLOW部分的文本
    - tools_section: TOOLS部分的文本
    - evidence_section: EVIDENCE部分的文本

    输出：
    - list[WorkflowStepRaw]: 不含I/O的步骤列表

    测试要点：
    1. 正确提取步骤的描述和action_type
    2. 不生成prerequisites/produces
    3. 正确识别validation gate
    """

    # -------------------------------------------------------------------------
    # Input Test Case 1.1: PDF表单填充（典型场景）
    # -------------------------------------------------------------------------

    @pytest.fixture
    def pdf_form_workflow_input(self):
        """
        PDF表单填充的WORKFLOW输入

        注意：这是精简后的输入格式，不是原始JSON
        """
        return {
            "workflow_section": """
## WORKFLOW

1. Check if the PDF has fillable form fields
   Run: `python scripts/check_fillable_fields.py <file.pdf>`
   Result: Prints whether fillable fields exist

2. If fillable: Extract form field information
   Run: `python scripts/extract_form_field_info.py <input.pdf> <field_info.json>`
   Output: field_info.json with field metadata

3. Create field_values.json with values to enter
   This is a manual step where user provides the values.

4. Fill the PDF with provided values
   Run: `python scripts/fill_fillable_fields.py <input.pdf> <field_values.json> <output.pdf>`
""",
            "tools_section": """
## TOOLS

- check_fillable_fields.py: Checks if PDF has fillable fields
- extract_form_field_info.py: Extracts field metadata from PDF
- fill_fillable_fields.py: Fills PDF form with values
""",
            "evidence_section": """
## EVIDENCE

- Verify that field_info.json is produced and contains field list
- Verify that output.pdf is created and non-empty
""",
            "available_tools": [
                {"name": "check_fillable_fields.py", "api_type": "SCRIPT"},
                {"name": "extract_form_field_info.py", "api_type": "SCRIPT"},
                {"name": "fill_fillable_fields.py", "api_type": "SCRIPT"},
            ]
        }

    def test_extract_workflow_steps(self, pdf_form_workflow_input):
        """
        TC-3W-1.1: 提取工作流步骤（不含I/O）

        验证点：
        1. 正确提取所有步骤
        2. 步骤不含prerequisites/produces
        3. action_type正确分类
        4. tool_hint正确匹配
        """
        # Expected Output
        expected = Step3WOutput(
            workflow_steps=[
                WorkflowStepRaw(
                    step_id="step.check_fillable_fields",
                    description="Check if the PDF has fillable form fields",
                    action_type="EXEC_SCRIPT",
                    tool_hint="check_fillable_fields.py",
                    is_validation_gate=False,
                    source_text="Run: `python scripts/check_fillable_fields.py <file.pdf>`"
                ),
                WorkflowStepRaw(
                    step_id="step.extract_form_field_info",
                    description="Extract form field information from PDF",
                    action_type="EXEC_SCRIPT",
                    tool_hint="extract_form_field_info.py",
                    is_validation_gate=False,
                    source_text="Run: `python scripts/extract_form_field_info.py <input.pdf> <field_info.json>`"
                ),
                WorkflowStepRaw(
                    step_id="step.create_field_values",
                    description="Create field_values.json with values to enter",
                    action_type="USER_INTERACTION",
                    tool_hint="",
                    is_validation_gate=False,
                    source_text="This is a manual step where user provides the values."
                ),
                WorkflowStepRaw(
                    step_id="step.fill_fillable_fields",
                    description="Fill the PDF with provided values",
                    action_type="EXEC_SCRIPT",
                    tool_hint="fill_fillable_fields.py",
                    is_validation_gate=False,
                    source_text="Run: `python scripts/fill_fillable_fields.py <input.pdf> <field_values.json> <output.pdf>`"
                ),
            ],
            alternative_flows=[],
            exception_flows=[]
        )

        # 这里应该调用实际的Step3-W函数
        # actual = run_step3w_workflow_analysis(...)
        # assert actual == expected

        # 验证点
        assert len(expected.workflow_steps) == 4
        assert all(s.prerequisites is None for s in expected.workflow_steps)  # 不应该有这个字段
        assert all(s.produces is None for s in expected.workflow_steps)  # 不应该有这个字段
        assert expected.workflow_steps[2].action_type == "USER_INTERACTION"

    def test_validation_gate_detection(self, pdf_form_workflow_input):
        """
        TC-3W-1.2: 验证门检测

        验证点：
        1. EVIDENCE中描述的验证步骤被标记为is_validation_gate=True
        """
        # 修改evidence_section，添加明确的验证门描述
        input_with_gate = {
            **pdf_form_workflow_input,
            "evidence_section": """
## EVIDENCE

Before filling: Verify that field_info.json is produced and contains valid field list.
If field_info.json is empty or malformed, stop and report error.
"""
        }

        # Expected: 第一个步骤的is_validation_gate应该为True（如果EVIDENCE明确要求验证）
        # 这里的逻辑需要进一步细化

    def test_empty_workflow(self):
        """
        TC-3W-1.3: 空工作流处理

        验证点：
        1. 空输入返回空列表
        2. 不抛出异常
        """
        empty_input = {
            "workflow_section": "",
            "tools_section": "",
            "evidence_section": "",
            "available_tools": []
        }

        expected = Step3WOutput(
            workflow_steps=[],
            alternative_flows=[],
            exception_flows=[]
        )

        # actual = run_step3w_workflow_analysis(...)
        # assert actual == expected


# =============================================================================
# Test Case 2: Step3-IO (Global I/O + Type Analysis)
# =============================================================================

class TestStep3IO:
    """
    Step3-IO: Global I/O + Type Analysis

    输入：
    - workflow_steps: list[WorkflowStepRaw]（来自Step3-W）
    - original_workflow_text: 原始WORKFLOW文本（用于推断I/O）
    - original_artifacts_text: 原始ARTIFACTS文本（用于识别文件）

    输出：
    - step_io_specs: dict[str, StepIOSpec]（每个步骤的I/O）
    - global_registry: GlobalVarRegistry（去重合并的全局变量）

    测试要点：
    1. 全局分析所有步骤，确保类型一致
    2. 正确推断每个步骤的输入输出
    3. 去重合并后的全局变量类型一致
    4. 正确识别文件vs变量
    """

    @pytest.fixture
    def pdf_form_steps_input(self):
        """
        Step3-IO的输入：来自Step3-W的步骤 + 原始文本
        """
        return {
            "workflow_steps": [
                WorkflowStepRaw(
                    step_id="step.check_fillable_fields",
                    description="Check if the PDF has fillable form fields",
                    action_type="EXEC_SCRIPT",
                    tool_hint="check_fillable_fields.py"
                ),
                WorkflowStepRaw(
                    step_id="step.extract_form_field_info",
                    description="Extract form field information from PDF",
                    action_type="EXEC_SCRIPT",
                    tool_hint="extract_form_field_info.py"
                ),
                WorkflowStepRaw(
                    step_id="step.create_field_values",
                    description="Create field_values.json with values to enter",
                    action_type="USER_INTERACTION",
                    tool_hint=""
                ),
                WorkflowStepRaw(
                    step_id="step.fill_fillable_fields",
                    description="Fill the PDF with provided values",
                    action_type="EXEC_SCRIPT",
                    tool_hint="fill_fillable_fields.py"
                ),
            ],
            "original_workflow_text": """
1. Check if the PDF has fillable form fields
   Run: `python scripts/check_fillable_fields.py <file.pdf>`
   Result: Prints whether fillable fields exist (boolean result)

2. If fillable: Extract form field information
   Run: `python scripts/extract_form_field_info.py <input.pdf> <field_info.json>`
   Output: field_info.json with field metadata (field_id, page, rect, type)

3. Create field_values.json with values to enter
   Format: {field_id: value, ...} for each field

4. Fill the PDF with provided values
   Run: `python scripts/fill_fillable_fields.py <input.pdf> <field_values.json> <output.pdf>`
""",
            "original_artifacts_text": """
## ARTIFACTS

- input.pdf: The PDF file to process
- field_info.json: Extracted field metadata
- field_values.json: User-provided values
- output.pdf: Filled PDF output
"""
        }

    def test_global_io_analysis(self, pdf_form_steps_input):
        """
        TC-3IO-2.1: 全局I/O分析

        验证点：
        1. 每个步骤的prerequisites/produces正确推断
        2. 类型表达式正确生成
        3. 所有步骤的类型全局一致
        """
        # Expected Output
        expected = Step3IOOutput(
            step_io_specs={
                "step.check_fillable_fields": StepIOSpec(
                    step_id="step.check_fillable_fields",
                    prerequisites={
                        "input_pdf": VarSpec(
                            var_name="input_pdf",
                            type_expr=TypeExpr(kind="simple", type_name="text"),  # PDF文件路径
                            is_file=True,
                            description="The PDF file to process"
                        )
                    },
                    produces={
                        "fillable_check_result": VarSpec(
                            var_name="fillable_check_result",
                            type_expr=TypeExpr(kind="simple", type_name="boolean"),
                            is_file=False,
                            description="Whether the PDF has fillable fields"
                        )
                    }
                ),
                "step.extract_form_field_info": StepIOSpec(
                    step_id="step.extract_form_field_info",
                    prerequisites={
                        "input_pdf": VarSpec(
                            var_name="input_pdf",
                            type_expr=TypeExpr(kind="simple", type_name="text"),
                            is_file=True,
                            description="The PDF file to process"
                        ),
                        "fillable_check_result": VarSpec(
                            var_name="fillable_check_result",
                            type_expr=TypeExpr(kind="simple", type_name="boolean"),
                            is_file=False,
                            description="Whether the PDF has fillable fields"
                        )
                    },
                    produces={
                        "field_info_json": VarSpec(
                            var_name="field_info_json",
                            type_expr=TypeExpr(
                                kind="array",
                                element_type=TypeExpr(
                                    kind="struct",
                                    fields={
                                        "field_id": TypeExpr(kind="simple", type_name="text"),
                                        "page": TypeExpr(kind="simple", type_name="number"),
                                        "rect": TypeExpr(kind="array",
                                                         element_type=TypeExpr(kind="simple", type_name="number")),
                                        "type": TypeExpr(kind="simple", type_name="text")
                                    }
                                )
                            ),
                            is_file=True,
                            description="Extracted field metadata"
                        )
                    }
                ),
                "step.create_field_values": StepIOSpec(
                    step_id="step.create_field_values",
                    prerequisites={
                        "field_info_json": VarSpec(
                            var_name="field_info_json",
                            type_expr=TypeExpr(
                                kind="array",
                                element_type=TypeExpr(
                                    kind="struct",
                                    fields={
                                        "field_id": TypeExpr(kind="simple", type_name="text"),
                                        "page": TypeExpr(kind="simple", type_name="number"),
                                        "rect": TypeExpr(kind="array",
                                                         element_type=TypeExpr(kind="simple", type_name="number")),
                                        "type": TypeExpr(kind="simple", type_name="text")
                                    }
                                )
                            ),
                            is_file=True,
                            description="Extracted field metadata"
                        )
                    },
                    produces={
                        "field_values_json": VarSpec(
                            var_name="field_values_json",
                            type_expr=TypeExpr(
                                kind="struct",
                                fields={
                                    "field_id": TypeExpr(kind="simple", type_name="text")
                                }
                            ),
                            is_file=True,
                            description="User-provided field values"
                        )
                    }
                ),
                "step.fill_fillable_fields": StepIOSpec(
                    step_id="step.fill_fillable_fields",
                    prerequisites={
                        "input_pdf": VarSpec(
                            var_name="input_pdf",
                            type_expr=TypeExpr(kind="simple", type_name="text"),
                            is_file=True
                        ),
                        "field_values_json": VarSpec(
                            var_name="field_values_json",
                            type_expr=TypeExpr(
                                kind="struct",
                                fields={
                                    "field_id": TypeExpr(kind="simple", type_name="text")
                                }
                            ),
                            is_file=True
                        )
                    },
                    produces={
                        "output_pdf": VarSpec(
                            var_name="output_pdf",
                            type_expr=TypeExpr(kind="simple", type_name="text"),
                            is_file=True,
                            description="Filled PDF output"
                        )
                    }
                )
            },
            global_registry=GlobalVarRegistry(
                variables={
                    "fillable_check_result": VarSpec(
                        var_name="fillable_check_result",
                        type_expr=TypeExpr(kind="simple", type_name="boolean"),
                        is_file=False
                    )
                },
                files={
                    "input_pdf": VarSpec(
                        var_name="input_pdf",
                        type_expr=TypeExpr(kind="simple", type_name="text"),
                        is_file=True
                    ),
                    "field_info_json": VarSpec(
                        var_name="field_info_json",
                        type_expr=TypeExpr(
                            kind="array",
                            element_type=TypeExpr(
                                kind="struct",
                                fields={
                                    "field_id": TypeExpr(kind="simple", type_name="text"),
                                    "page": TypeExpr(kind="simple", type_name="number"),
                                    "rect": TypeExpr(kind="array",
                                                     element_type=TypeExpr(kind="simple", type_name="number")),
                                    "type": TypeExpr(kind="simple", type_name="text")
                                }
                            )
                        ),
                        is_file=True
                    ),
                    "field_values_json": VarSpec(
                        var_name="field_values_json",
                        type_expr=TypeExpr(
                            kind="struct",
                            fields={
                                "field_id": TypeExpr(kind="simple", type_name="text")
                            }
                        ),
                        is_file=True
                    ),
                    "output_pdf": VarSpec(
                        var_name="output_pdf",
                        type_expr=TypeExpr(kind="simple", type_name="text"),
                        is_file=True
                    )
                }
            )
        )

        # 验证点
        # 1. 每个步骤都有prerequisites和produces
        assert all(spec.prerequisites is not None for spec in expected.step_io_specs.values())
        assert all(spec.produces is not None for spec in expected.step_io_specs.values())

        # 2. 全局注册表中的变量类型与步骤中一致
        step2_field_info = expected.step_io_specs["step.extract_form_field_info"].produces["field_info_json"]
        step3_field_info = expected.step_io_specs["step.create_field_values"].prerequisites["field_info_json"]
        global_field_info = expected.global_registry.files["field_info_json"]

        # 类型应该完全一致
        assert step2_field_info.type_expr.to_dict() == step3_field_info.type_expr.to_dict()
        assert step2_field_info.type_expr.to_dict() == global_field_info.type_expr.to_dict()

    def test_type_consistency_across_steps(self, pdf_form_steps_input):
        """
        TC-3IO-2.2: 跨步骤类型一致性

        验证点：
        1. 同一个变量在不同步骤中类型必须一致
        2. 不能出现"类型漂移"

        场景：假设LLM错误地为同一变量生成了不同类型
        """
        # 错误案例（应该被检测出来）
        # Step2 produces: tables: List[{rows: List[text]}]
        # Step3 expects:  tables: List[{data: List[text]}]
        # 这是类型不一致，应该在全局分析中被纠正

        # 正确案例：两种类型的to_dict()输出应该相同
        type1 = TypeExpr(
            kind="array",
            element_type=TypeExpr(
                kind="struct",
                fields={
                    "field_id": TypeExpr(kind="simple", type_name="text"),
                    "page": TypeExpr(kind="simple", type_name="number")
                }
            )
        )

        type2 = TypeExpr(
            kind="array",
            element_type=TypeExpr(
                kind="struct",
                fields={
                    "field_id": TypeExpr(kind="simple", type_name="text"),
                    "page": TypeExpr(kind="simple", type_name="number")
                }
            )
        )

        assert type1.to_dict() == type2.to_dict()

    def test_file_vs_variable_distinction(self, pdf_form_steps_input):
        """
        TC-3IO-2.3: 文件vs变量区分

        验证点：
        1. is_file字段正确设置
        2. 全局注册表正确分类variables和files
        """
        # 输入中明确标注了哪些是文件
        # field_info.json -> is_file=True
        # fillable_check_result -> is_file=False

        expected_types = {
            ("input_pdf", True),
            ("field_info_json", True),
            ("field_values_json", True),
            ("output_pdf", True),
            ("fillable_check_result", False),
        }

        # 实际实现需要验证这些
        # actual = run_step3io(...)
        # for var_name, spec in actual.global_registry.variables.items():
        #     assert (var_name, spec.is_file) in expected_types


# =============================================================================
# Test Case 3: Step3-T (TYPES Declaration)
# =============================================================================

class TestStep3T:
    """
    Step3-T: TYPES Declaration

    输入：
    - global_registry: GlobalVarRegistry（来自Step3-IO）

    输出：
    - type_decls: list[TypeDecl]（所有声明的类型）
    - type_registry: dict[str, str]（inline_signature -> declared_name映射）

    测试要点：
    1. 只为非简单类型生成TYPE声明
    2. 类型命名合理（PascalCase）
    3. type_registry正确映射
    """

    @pytest.fixture
    def global_registry_with_complex_types(self):
        """
        包含复杂类型的全局注册表
        """
        return GlobalVarRegistry(
            variables={
                "processing_result": VarSpec(
                    var_name="processing_result",
                    type_expr=TypeExpr(
                        kind="struct",
                        fields={
                            "success": TypeExpr(kind="simple", type_name="boolean"),
                            "message": TypeExpr(kind="simple", type_name="text"),
                            "data": TypeExpr(
                                kind="array",
                                element_type=TypeExpr(
                                    kind="struct",
                                    fields={
                                        "id": TypeExpr(kind="simple", type_name="text"),
                                        "value": TypeExpr(kind="simple", type_name="number")
                                    }
                                )
                            )
                        }
                    ),
                    is_file=False
                ),
                "status": VarSpec(
                    var_name="status",
                    type_expr=TypeExpr(kind="enum", values=["pending", "running", "completed", "failed"]),
                    is_file=False
                ),
                "simple_var": VarSpec(
                    var_name="simple_var",
                    type_expr=TypeExpr(kind="simple", type_name="text"),
                    is_file=False
                )
            },
            files={}
        )

    def test_types_generation(self, global_registry_with_complex_types):
        """
        TC-3T-3.1: 类型声明生成

        验证点：
        1. 简单类型不生成TYPE声明
        2. 枚举类型生成TYPE声明
        3. 结构体类型生成TYPE声明
        4. 类型命名合理
        """
        # Expected Output
        expected = Step3TOutput(
            type_decls=[
                TypeDecl(
                    declared_name="ProcessingResult",
                    type_expr=TypeExpr(
                        kind="struct",
                        fields={
                            "success": TypeExpr(kind="simple", type_name="boolean"),
                            "message": TypeExpr(kind="simple", type_name="text"),
                            "data": TypeExpr(
                                kind="array",
                                element_type=TypeExpr(
                                    kind="struct",
                                    fields={
                                        "id": TypeExpr(kind="simple", type_name="text"),
                                        "value": TypeExpr(kind="simple", type_name="number")
                                    }
                                )
                            )
                        }
                    ),
                    description="Processing result with success status and data"
                ),
                TypeDecl(
                    declared_name="Status",
                    type_expr=TypeExpr(kind="enum", values=["pending", "running", "completed", "failed"]),
                    description="Processing status enumeration"
                ),
                # 注意：嵌套的结构体也可能需要单独声明
                # TypeDecl(declared_name="DataItem", ...)
            ],
            type_registry={
                "{success: boolean, message: text, data: List[{id: text, value: number}]}": "ProcessingResult",
                '["pending", "running", "completed", "failed"]': "Status",
            }
        )

        # 验证点
        # 1. 不为简单类型生成声明
        type_names = [d.declared_name for d in expected.type_decls]
        assert "SimpleVar" not in type_names  # text类型不需要声明

        # 2. 枚举和结构体生成声明
        assert "ProcessingResult" in type_names
        assert "Status" in type_names

        # 3. type_registry正确映射
        assert "{success: boolean, message: text, data: List[{id: text, value: number}]}" in expected.type_registry

    def test_nested_type_extraction(self, global_registry_with_complex_types):
        """
        TC-3T-3.2: 嵌套类型提取

        验证点：
        1. 嵌套的结构体被提取为独立类型
        2. type_registry包含嵌套类型的映射
        """
        # 对于 ProcessingResult.data 中的嵌套结构体
        # 应该生成一个独立的 DataItem 类型

        # 这个测试用例需要根据实际需求调整
        pass


# =============================================================================
# Test Case 4: TypeExpr Serialization/Deserialization
# =============================================================================

class TestTypeExpr:
    """
    TypeExpr的序列化/反序列化测试

    确保LLM输出的JSON能被正确解析
    """

    def test_simple_type_serialization(self):
        """
        TC-TypeExpr-4.1: 简单类型序列化
        """
        type_expr = TypeExpr(kind="simple", type_name="text")
        assert type_expr.to_dict() == "text"

        # 反序列化
        parsed = TypeExpr.from_dict("text")
        assert parsed.kind == "simple"
        assert parsed.type_name == "text"

    def test_enum_type_serialization(self):
        """
        TC-TypeExpr-4.2: 枚举类型序列化
        """
        type_expr = TypeExpr(kind="enum", values=["red", "green", "blue"])
        assert type_expr.to_dict() == ["red", "green", "blue"]

        # 反序列化
        parsed = TypeExpr.from_dict(["red", "green", "blue"])
        assert parsed.kind == "enum"
        assert parsed.values == ["red", "green", "blue"]

    def test_array_type_serialization(self):
        """
        TC-TypeExpr-4.3: 数组类型序列化
        """
        type_expr = TypeExpr(
            kind="array",
            element_type=TypeExpr(kind="simple", type_name="text")
        )
        assert type_expr.to_dict() == "List[text]"

        # 反序列化
        parsed = TypeExpr.from_dict("List[text]")
        assert parsed.kind == "array"
        assert parsed.element_type.kind == "simple"
        assert parsed.element_type.type_name == "text"

    def test_struct_type_serialization(self):
        """
        TC-TypeExpr-4.4: 结构体类型序列化
        """
        type_expr = TypeExpr(
            kind="struct",
            fields={
                "name": TypeExpr(kind="simple", type_name="text"),
                "age": TypeExpr(kind="simple", type_name="number")
            }
        )
        # 序列化后应该是类似 "{name: text, age: number}" 的字符串
        serialized = type_expr.to_dict()
        assert "name: text" in str(serialized)
        assert "age: number" in str(serialized)

        # 反序列化
        # 这里需要确定结构体的JSON表示格式
        # 可能是 {"name": "text", "age": "number"}
        parsed = TypeExpr.from_dict({"name": "text", "age": "number"})
        assert parsed.kind == "struct"
        assert "name" in parsed.fields
        assert parsed.fields["name"].type_name == "text"

    def test_nested_type_serialization(self):
        """
        TC-TypeExpr-4.5: 嵌套类型序列化
        """
        type_expr = TypeExpr(
            kind="array",
            element_type=TypeExpr(
                kind="struct",
                fields={
                    "id": TypeExpr(kind="simple", type_name="text"),
                    "tags": TypeExpr(
                        kind="array",
                        element_type=TypeExpr(kind="simple", type_name="text")
                    )
                }
            )
        )
        # 应该序列化为 "List[{id: text, tags: List[text]}]"
        serialized = type_expr.to_dict()
        assert "List[" in str(serialized)

        # 反序列化
        # 需要确定嵌套类型的JSON表示格式


# =============================================================================
# Test Case 5: Integration Tests
# =============================================================================

class TestStep3Integration:
    """
    Step3各步骤的集成测试

    验证端到端的输入输出转换
    """

    @pytest.fixture
    def complete_pdf_skill_input(self):
        """
        完整的PDF技能输入（包含所有section）
        """
        return {
            "workflow_section": """
## WORKFLOW

1. Check if the PDF has fillable form fields
2. Extract form field information
3. Create field values JSON
4. Fill the PDF with values
""",
            "tools_section": """
## TOOLS
- check_fillable_fields.py
- extract_form_field_info.py
- fill_fillable_fields.py
""",
            "evidence_section": """
## EVIDENCE
- Verify output exists
""",
            "artifacts_section": """
## ARTIFACTS
- input.pdf: Input PDF file
- output.pdf: Output PDF file
- field_info.json: Field metadata
- field_values.json: Field values
""",
            "available_tools": [
                {"name": "check_fillable_fields.py", "api_type": "SCRIPT"},
                {"name": "extract_form_field_info.py", "api_type": "SCRIPT"},
                {"name": "fill_fillable_fields.py", "api_type": "SCRIPT"},
            ]
        }

    def test_end_to_end_step3(self, complete_pdf_skill_input):
        """
        TC-Integration-5.1: 端到端Step3流程

        验证：
        1. Step3-W → Step3-IO → Step3-T 的数据流正确
        2. 最终输出的类型声明可用于Step4-C
        """
        # Step 3-W
        # step3w_output = run_step3w(...)

        # Step 3-IO
        # step3io_output = run_step3io(step3w_output, ...)

        # Step 3-T
        # step3t_output = run_step3t(step3io_output)

        # 验证最终输出
        # 1. type_decls不为空（如果有复杂类型）
        # 2. global_registry包含所有变量
        # 3. type_registry正确映射

        pass


# =============================================================================
# Test Case 6: Edge Cases
# =============================================================================

class TestEdgeCases:
    """
    边界情况测试
    """

    def test_single_step_workflow(self):
        """
        TC-Edge-6.1: 单步骤工作流

        验证：
        1. 单步骤也能正确处理
        2. prerequisites可能为空（第一步）
        """
        pass

    def test_circular_dependency_detection(self):
        """
        TC-Edge-6.2: 循环依赖检测

        验证：
        1. 如果检测到循环依赖，应该如何处理
        2. 是否需要抛出异常或标记needs_review
        """
        pass

    def test_empty_type_inference(self):
        """
        TC-Edge-6.3: 无法推断类型的情况

        验证：
        1. 如果原文没有提供类型信息，如何处理
        2. 是否使用默认类型（如"text"）
        """
        pass

    def test_conflicting_file_classification(self):
        """
        TC-Edge-6.4: 文件分类冲突

        场景：
        - 同一个变量在一个步骤中被标记为is_file=True
        - 但在另一个步骤中被标记为is_file=False

        验证：
        1. 全局分析应该如何解决这种冲突
        """
        pass


# =============================================================================
# Prompt Input Format Tests (关键：验证输入格式不是"一堆JSON")
# =============================================================================

class TestPromptInputFormat:
    """
    验证每个步骤的LLM输入格式是结构化的、精简的

    核心原则：不要直接丢一堆JSON给LLM
    """

    def test_step3w_prompt_format(self):
        """
        TC-Prompt-7.1: Step3-W的Prompt格式

        验证：
        1. 输入不是原始JSON
        2. 输入是结构化的、人类可读的文本
        3. 输入包含必要的上下文（tools列表、evidence等）
        """
        # 预期的Prompt格式示例
        expected_prompt_structure = """
## Workflow Description

<workflow_text>

## Available Tools

- Tool 1: <name> (<api_type>)
- Tool 2: <name> (<api_type>)

## Evidence Requirements

<evidence_text>

---

Extract the workflow steps. For each step:
- step_id: step.<action_name>
- description: concise action description
- action_type: choose from LLM_TASK, EXEC_SCRIPT, FILE_READ, FILE_WRITE, USER_INTERACTION, EXTERNAL_API, LOCAL_CODE_SNIPPET
- tool_hint: match tool name if applicable
- is_validation_gate: true if this step verifies an evidence requirement

Output JSON format:
{
  "workflow_steps": [...]
}
"""
        pass

    def test_step3io_prompt_format(self):
        """
        TC-Prompt-7.2: Step3-IO的Prompt格式

        验证：
        1. 输入包含所有步骤（全局分析）
        2. 输入包含原始workflow文本（用于推断I/O）
        3. 输入包含artifacts信息（用于识别文件）
        """
        expected_prompt_structure = """
## Workflow Steps (from prior analysis)

Step 1: step.check_fillable_fields
  Description: Check if the PDF has fillable form fields
  Action Type: EXEC_SCRIPT
  Tool Hint: check_fillable_fields.py

Step 2: step.extract_form_field_info
  Description: Extract form field information from PDF
  Action Type: EXEC_SCRIPT
  Tool Hint: extract_form_field_info.py

...

## Original Workflow Text (for I/O inference)

<workflow_text>

## Artifacts (for file identification)

- input.pdf: The PDF file to process
- field_info.json: Extracted field metadata
- field_values.json: User-provided values
- output.pdf: Filled PDF output

---

Analyze ALL steps together to infer data flow:

For each step, output:
- step_id
- prerequisites: {var_name: type_expression, ...}
- produces: {var_name: type_expression, ...}

Type expression format:
- Simple: "text", "image", "audio", "number", "boolean"
- Enum: ["value1", "value2", ...]
- Array: "List[<type>]"
- Struct: {"field": type, ...}

CRITICAL: The same variable must have CONSISTENT type across all steps where it appears.

Output JSON format:
{
  "step_io_specs": {...},
  "global_vars": [...]
}
"""
        pass

    def test_step3t_prompt_format(self):
        """
        TC-Prompt-7.3: Step3-T的Prompt格式

        验证：
        1. 输入是去重后的类型表达式列表
        2. 输入不包含整个global_registry（太大）
        """
        expected_prompt_structure = """
## Complex Type Expressions (non-simple types)

The following type expressions were used in the workflow:

1. Type: Array of struct
   Expression: List[{field_id: text, page: number, rect: List[number], type: text}]
   Used in: field_info_json (step.extract_form_field_info produces)

2. Type: Enum
   Expression: ["pending", "running", "completed", "failed"]
   Used in: status (step.check_status produces)

---

Generate TYPE declarations for these complex types:

For each type:
- declared_name: PascalCase (e.g., "FieldInfo", "ProcessingStatus")
- type_expression: the original expression
- description: brief description

Output JSON format:
{
  "type_decls": [
    {
      "declared_name": "FieldInfo",
      "type_expression": {...},
      "description": "..."
    }
  ],
  "type_registry": {
    "<inline_signature>": "DeclaredName",
    ...
  }
}
"""
        pass


# =============================================================================
# 运行测试
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])