"""API定义相关模型 (Step 1.5, Step 4D).

此模块包含API规格定义和工具规格的数据结构.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.base import SourceRef


@dataclass(slots=True)
class FunctionSpec:
    """统一API中的单个函数/方法规格.

    Attributes:
        name: 函数/方法名
        signature: 代码片段或函数签名
        description: 函数描述
        input_schema: 输入参数 (param_name -> type)
        output_schema: 返回类型
        source_ref: 源代码引用位置

    Examples:
        >>> func = FunctionSpec(
        ...     name="extract_text",
        ...     signature="def extract_text(pdf_path: str) -> str:",
        ...     description="Extract text from PDF",
        ...     input_schema={"pdf_path": "str"},
        ...     output_schema="str",
        ... )
    """

    name: str
    signature: str
    description: str
    input_schema: dict[str, str]
    output_schema: str
    source_ref: SourceRef | None = None

    def get_param_type(self, param_name: str) -> str | None:
        """获取参数类型.

        Args:
            param_name: 参数名

        Returns:
            类型字符串，如果不存在则返回None
        """
        return self.input_schema.get(param_name)

    def has_param(self, param_name: str) -> bool:
        """检查是否有指定参数."""
        return param_name in self.input_schema


@dataclass(slots=True)
class UnifiedAPISpec:
    """统一API规格，聚合同一库的多个函数.

    Attributes:
        api_id: 唯一标识符，如"pypdf_from_doc1"
        api_name: SPL用的PascalCase名，如"PypdfProcessing"
        primary_library: URL前缀的主库
        all_libraries: 涉及的所有库
        language: 编程语言
        functions: 此API中的所有函数
        combined_source: 合并的源代码
        source_file: 源MD文件路径
        source_ref: 源代码引用位置

    Examples:
        >>> api = UnifiedAPISpec(
        ...     api_id="pypdf_api_001",
        ...     api_name="PypdfProcessing",
        ...     primary_library="pypdf",
        ...     all_libraries=["pypdf"],
        ...     language="python",
        ...     functions=[],
        ...     combined_source="...",
        ...     source_file="SKILL.md",
        ... )
    """

    api_id: str
    api_name: str
    primary_library: str
    all_libraries: list[str]
    language: str
    functions: list[FunctionSpec]
    combined_source: str
    source_file: str
    source_ref: SourceRef | None = None

    def get_function(self, name: str) -> FunctionSpec | None:
        """按名称获取函数规格.

        Args:
            name: 函数名

        Returns:
            FunctionSpec对象，如果不存在则返回None
        """
        for func in self.functions:
            if func.name == name:
                return func
        return None

    def get_function_names(self) -> list[str]:
        """获取所有函数名称."""
        return [func.name for func in self.functions]

    def add_function(self, func: FunctionSpec) -> None:
        """添加函数规格."""
        self.functions.append(func)

    def summary(self) -> dict[str, Any]:
        """返回统计摘要."""
        return {
            "api_id": self.api_id,
            "api_name": self.api_name,
            "function_count": len(self.functions),
            "function_names": self.get_function_names(),
            "primary_library": self.primary_library,
            "language": self.language,
        }


@dataclass(slots=True)
class APISpec:
    """单工具的生成API规格（旧格式，保持兼容）.

    Attributes:
        name: API名
        spl_text: LLM生成的完整DEFINE_API块
        input_params: 输入参数列表 [{"name": str, "type": str, "required": bool}]
        output_params: 输出参数列表 [{"name": str, "type": str}]
        description: API简述
        source_ref: 源代码引用位置

    Examples:
        >>> spec = APISpec(
        ...     name="PDFReader",
        ...     spl_text="[DEFINE_API: ...]",
        ...     input_params=[{"name": "path", "type": "str", "required": True}],
        ...     output_params=[{"name": "content", "type": "str"}],
        ...     description="Read PDF file",
        ... )
    """

    name: str
    spl_text: str
    input_params: list[dict[str, Any]]
    output_params: list[dict[str, Any]]
    description: str
    source_ref: SourceRef | None = None

    def get_input_param(self, name: str) -> dict[str, Any] | None:
        """按名称获取输入参数.

        Args:
            name: 参数名

        Returns:
            参数字典，如果不存在则返回None
        """
        for param in self.input_params:
            if param.get("name") == name:
                return param
        return None

    def get_output_param(self, name: str) -> dict[str, Any] | None:
        """按名称获取输出参数."""
        for param in self.output_params:
            if param.get("name") == name:
                return param
        return None


@dataclass(slots=True)
class ToolSpec:
    """用于DEFINE_APIS生成的统一API规格.

    Attributes:
        name: API名（用于tool_hint引用）
        api_type: 类型 (SCRIPT | CODE_SNIPPET | NETWORK_API)
        url: 脚本路径或库引用
        authentication: 认证方式 (none | apikey | oauth)
        input_schema: 参数名 -> 类型
        output_schema: 返回类型或"void"
        description: 简短功能描述
        source_text: 原始源代码/文本
        source_ref: 源代码引用位置

    Examples:
        >>> tool = ToolSpec(
        ...     name="read_pdf",
        ...     api_type="SCRIPT",
        ...     url="scripts/read_pdf.py",
        ...     authentication="none",
        ...     input_schema={"path": "str"},
        ...     output_schema="str",
        ...     description="Read PDF content",
        ... )
    """

    name: str
    api_type: str
    url: str
    authentication: str
    input_schema: dict[str, str]
    output_schema: str
    description: str
    source_text: str
    source_ref: SourceRef | None = None

    def __post_init__(self) -> None:
        """验证api_type."""
        valid_types = ("SCRIPT", "CODE_SNIPPET", "NETWORK_API")
        if self.api_type not in valid_types:
            raise ValueError(
                f"Invalid api_type '{self.api_type}'. Must be one of: {valid_types}"
            )

    def is_script(self) -> bool:
        """是否为脚本类型."""
        return self.api_type == "SCRIPT"

    def is_snippet(self) -> bool:
        """是否为代码片段类型."""
        return self.api_type == "CODE_SNIPPET"

    def is_network(self) -> bool:
        """是否为网络API类型."""
        return self.api_type == "NETWORK_API"

    def get_input_types(self) -> list[tuple[str, str]]:
        """获取输入参数类型列表."""
        return [(k, v) for k, v in self.input_schema.items()]


@dataclass(slots=True)
class APISymbolTable:
    """技能的所有API定义集合.

    包含旧格式和新格式的API定义，用于S4E输入.

    Attributes:
        apis: api_name -> APISpec（旧格式）
        unified_apis: api_name -> UnifiedAPISpec（新格式）

    Examples:
        >>> table = APISymbolTable()
        >>> table.apis["old_api"] = APISpec(...)
        >>> table.unified_apis["new_api"] = UnifiedAPISpec(...)
    """

    apis: dict[str, APISpec] = field(default_factory=dict)
    unified_apis: dict[str, UnifiedAPISpec] = field(default_factory=dict)

    def to_text(self) -> str:
        """渲染所有API定义为S4E输入文本.

        Returns:
            格式化的API定义文本
        """
        if not self.apis and not self.unified_apis:
            return "(No APIs defined)"

        lines = ["# APIS (reference as <API_REF> api_name </API_REF>):", ""]

        for name, spec in self.apis.items():
            lines.append(f"API: {name}")
            lines.append(f" Description: {spec.description}")
            if spec.input_params:
                inputs = ", ".join(
                    f"{p['name']}: {p['type']}" for p in spec.input_params
                )
                lines.append(f" Input: ({inputs})")
            if spec.output_params:
                outputs = ", ".join(
                    f"{p['name']}: {p['type']}" for p in spec.output_params
                )
                lines.append(f" Output: ({outputs})")
            lines.append("")

        # 新格式摘要
        if self.unified_apis:
            lines.append("# Unified APIs:")
            for name, spec in self.unified_apis.items():
                lines.append(f"API: {name} ({spec.api_name})")
                lines.append(f" Library: {spec.primary_library}")
                lines.append(f" Functions: {len(spec.functions)}")
                lines.append("")

        return "\n".join(lines)

    def get_api_names(self) -> list[str]:
        """返回所有API名称列表."""
        return list(self.apis.keys()) + list(self.unified_apis.keys())

    def get_api(self, name: str) -> APISpec | UnifiedAPISpec | None:
        """按名称获取API（任意格式）.

        Args:
            name: API名称

        Returns:
            API规格对象，如果不存在则返回None
        """
        if name in self.apis:
            return self.apis[name]
        if name in self.unified_apis:
            return self.unified_apis[name]
        return None

    def merge(self, other: APISymbolTable) -> APISymbolTable:
        """合并另一个符号表.

        Args:
            other: 要合并的符号表

        Returns:
            新的合并符号表
        """
        merged = APISymbolTable()
        merged.apis = {**self.apis, **other.apis}
        merged.unified_apis = {**self.unified_apis, **other.unified_apis}
        return merged

    def add_api(self, name: str, spec: APISpec | UnifiedAPISpec) -> None:
        """添加API到适当格式.

        Args:
            name: API名称
            spec: API规格
        """
        if isinstance(spec, UnifiedAPISpec):
            self.unified_apis[name] = spec
        else:
            self.apis[name] = spec

    def summary(self) -> dict[str, int]:
        """返回统计摘要."""
        return {
            "legacy_apis": len(self.apis),
            "unified_apis": len(self.unified_apis),
            "total": len(self.apis) + len(self.unified_apis),
        }
