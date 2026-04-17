"""P2: File Role Resolver 相关模型.

此模块包含P2阶段用于文件角色解析的数据结构.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from models.base import Priority, SourceRef


@dataclass(slots=True)
class FileRoleEntry:
    """LLM分配的文件角色和读取优先级.

    表示P2阶段对单个文件的角色判定结果.

    Attributes:
        role: 来自taxonomy的角色标识符
        read_priority: 读取优先级 (1=必须, 2=摘要, 3=省略)
        must_read_for_normalization: 归一化时是否必须阅读
        reasoning: 一句话解释，引用具体源文本
        source_ref: 源代码引用位置（可选）

    角色Taxonomy示例:
        - "documentation": 主文档文件
        - "reference": 参考资料
        - "implementation": 实现文件
        - "example": 示例文件
        - "template": 模板文件
        - "test": 测试文件
        - "config": 配置文件
        - "asset": 资源文件（图片、音频等）

    Examples:
        >>> entry = FileRoleEntry(
        ...     role="documentation",
        ...     read_priority=1,
        ...     must_read_for_normalization=True,
        ...     reasoning="Contains main skill description",
        ... )
    """

    role: str
    read_priority: Priority
    must_read_for_normalization: bool
    reasoning: str
    source_ref: SourceRef | None = None

    def __post_init__(self) -> None:
        """验证read_priority范围."""
        if not 1 <= self.read_priority <= 3:
            raise ValueError(f"read_priority must be 1, 2, or 3, got {self.read_priority}")

    def is_must_read(self) -> bool:
        """是否为必须阅读文件."""
        return self.read_priority == 1

    def is_include_summary(self) -> bool:
        """是否需要包含摘要."""
        return self.read_priority == 2

    def is_omit(self) -> bool:
        """是否可以省略."""
        return self.read_priority == 3

    def should_read_full(self) -> bool:
        """是否应该读取完整内容."""
        return self.is_must_read()


# 类型别名: path -> entry
FileRoleMap: TypeAlias = dict[str, FileRoleEntry]
"""文件路径到角色条目的映射类型."""


@dataclass(slots=True)
class RoleAssignment:
    """角色分配结果集合.

    用于组织和查询一组文件的角色分配.

    Attributes:
        assignments: 路径到角色条目的映射
    """

    assignments: FileRoleMap

    def get_priority_1_files(self) -> list[str]:
        """获取优先级1（必须阅读）的文件路径."""
        return [
            path
            for path, entry in self.assignments.items()
            if entry.is_must_read()
        ]

    def get_priority_2_files(self) -> list[str]:
        """获取优先级2（包含摘要）的文件路径."""
        return [
            path
            for path, entry in self.assignments.items()
            if entry.is_include_summary()
        ]

    def get_priority_3_files(self) -> list[str]:
        """获取优先级3（省略）的文件路径."""
        return [
            path
            for path, entry in self.assignments.items()
            if entry.is_omit()
        ]

    def get_by_role(self, role: str) -> list[tuple[str, FileRoleEntry]]:
        """获取指定角色的所有文件.

        Args:
            role: 角色标识符

        Returns:
            (路径, 角色条目) 元组列表
        """
        return [
            (path, entry)
            for path, entry in self.assignments.items()
            if entry.role == role
        ]

    def get_entry(self, path: str) -> FileRoleEntry | None:
        """获取指定路径的角色条目.

        Args:
            path: 文件路径

        Returns:
            角色条目，如果不存在则返回None
        """
        return self.assignments.get(path)

    def summary(self) -> dict[str, int]:
        """返回统计摘要."""
        from collections import Counter

        role_counts = Counter(entry.role for entry in self.assignments.values())
        priority_counts = Counter(entry.read_priority for entry in self.assignments.values())

        return {
            "total_files": len(self.assignments),
            "must_read": priority_counts.get(1, 0),
            "include_summary": priority_counts.get(2, 0),
            "omit": priority_counts.get(3, 0),
            **{f"role_{role}": count for role, count in role_counts.items()},
        }
