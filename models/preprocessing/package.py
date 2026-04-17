"""P3: Skill Package 相关模型.

此模块包含P3阶段组装技能包使用的数据结构.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from models.base import SourceRef

if TYPE_CHECKING:
    from models.pipeline_steps.api import ToolSpec, UnifiedAPISpec


@dataclass(slots=True)
class SkillPackage:
    """P3输出: 组装好的带注解的Step 1输入.

    包含预处理阶段收集和生成的所有信息，用于后续Pipeline步骤.

    Attributes:
        skill_id: 技能标识符
        root_path: 技能包根目录
        frontmatter: SKILL.md的YAML frontmatter
        merged_doc_text: 带文件边界标记的拼接内容
        file_role_map: 文件角色映射
        scripts: 已废弃: 使用tools替代
        tools: 统一的API规格列表（来自P2.5）
        unified_apis: 统一API规格列表（新格式）

    Examples:
        >>> package = SkillPackage(
        ...     skill_id="pdf",
        ...     root_path="/skills/pdf",
        ...     frontmatter={"name": "PDF Skill"},
        ...     merged_doc_text="=== FILE: SKILL.md ...",
        ...     file_role_map={},
        ... )
    """

    skill_id: str
    root_path: str
    frontmatter: dict[str, Any]
    merged_doc_text: str
    file_role_map: dict[str, Any]

    # API分析结果 (P2.5)
    # 使用字段()和default_factory避免可变默认值问题
    scripts: list = field(default_factory=list)  # 已废弃: 使用tools
    tools: list["ToolSpec"] = field(default_factory=list)
    unified_apis: list["UnifiedAPISpec"] = field(default_factory=list)

    def get_tool_count(self) -> int:
        """获取工具总数（包括遗留和统一格式）."""
        return len(self.tools) + len(self.unified_apis)

    def get_tool_by_name(self, name: str) -> "ToolSpec | None":
        """按名称获取工具.

        Args:
            name: 工具名称

        Returns:
            ToolSpec对象，如果不存在则返回None
        """
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def get_unified_api_by_id(self, api_id: str) -> "UnifiedAPISpec | None":
        """按ID获取统一API.

        Args:
            api_id: API标识符

        Returns:
            UnifiedAPISpec对象，如果不存在则返回None
        """
        for api in self.unified_apis:
            if api.api_id == api_id:
                return api
        return None

    def get_doc_content(self, rel_path: str) -> str | None:
        """提取特定文件的原始内容.

        从merged_doc_text中解析出指定文件的内容.

        Args:
            rel_path: 相对于skill root的路径

        Returns:
            文件内容，如果不存在则返回None
        """
        import re

        pattern = rf"=== FILE: {re.escape(rel_path)} \| role: [^|]+ \| priority: \d+ ===\n(.*?)(?=\n=== FILE: |\Z)"
        match = re.search(pattern, self.merged_doc_text, re.DOTALL)
        return match.group(1).strip() if match else None

    def get_file_count(self) -> int:
        """获取文件总数（从merged_doc_text解析）."""
        return self.merged_doc_text.count("=== FILE:")

    def get_frontmatter_value(self, key: str, default: Any = None) -> Any:
        """安全地获取frontmatter值.

        Args:
            key: 键名
            default: 默认值

        Returns:
            键值或默认值
        """
        return self.frontmatter.get(key, default)

    def summary(self) -> dict[str, Any]:
        """返回统计摘要."""
        return {
            "skill_id": self.skill_id,
            "file_count": self.get_file_count(),
            "frontmatter_keys": list(self.frontmatter.keys()),
            "legacy_tools": len(self.scripts),
            "unified_tools": len(self.tools),
            "unified_apis": len(self.unified_apis),
        }
