"""P1: Reference Graph Builder 相关模型.

此模块包含P1阶段用于构建文件引用图的数据结构.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.base import FileKind, SourceRef


@dataclass(slots=True)
class FileNode:
    """技能包中的单个文件.

    表示技能包中发现的一个文件，包含其元数据和内容摘要.

    Attributes:
        path: 相对于skill root的文件路径
        kind: 文件类型 (doc, script, data, document, image, audio)
        size_bytes: 文件大小（字节）
        head_lines: 前20行内容（文档）或注释头（脚本，≤5行）
        references: 本文件通过正则扫描发现的其他文件名
        source_ref: 源代码引用位置（可选）

    Examples:
        >>> node = FileNode(
        ...     path="docs/guide.md",
        ...     kind="doc",
        ...     size_bytes=1024,
        ...     head_lines=["# Guide", "This is..."],
        ...     references=["api.py"],
        ... )
    """

    path: str
    kind: FileKind
    size_bytes: int
    head_lines: list[str]
    references: list[str]
    source_ref: SourceRef | None = None

    def __hash__(self) -> int:
        """基于路径的哈希."""
        return hash(self.path)

    def __eq__(self, other: object) -> bool:
        """基于路径的相等性比较."""
        if not isinstance(other, FileNode):
            return NotImplemented
        return self.path == other.path

    def is_document(self) -> bool:
        """是否为文档类型."""
        return self.kind in ("doc", "document")

    def is_script(self) -> bool:
        """是否为脚本类型."""
        return self.kind == "script"

    def is_omittable(self) -> bool:
        """是否可在预处理中跳过."""
        return self.kind in ("image", "audio", "data")


@dataclass(slots=True)
class ScriptMetadata:
    """脚本文件的额外元数据.

    用于存储从脚本中提取的额外信息，如导入的库等.

    Attributes:
        imports: 导入的模块名列表
        classes: 定义的类名列表
        functions: 定义的函数名列表
    """

    imports: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FileReferenceGraph:
    """P1输出: 技能包的机械清单.

    包含技能包中所有文件的完整清单及其相互引用关系.

    Attributes:
        skill_id: 技能标识符（通常是目录名）
        root_path: 技能包根目录的绝对路径
        skill_md_content: SKILL.md文件的完整内容
        frontmatter: 从SKILL.md解析的YAML frontmatter
        nodes: 路径到FileNode的映射
        edges: 引用关系到被引用文件列表的映射
        docs_content: 所有.md文件的内容（用于后续处理）
        local_scripts: 发现的所有脚本文件路径
        referenced_libs: 脚本中引用的顶层库

    Examples:
        >>> graph = FileReferenceGraph(
        ...     skill_id="pdf",
        ...     root_path="/skills/pdf",
        ...     skill_md_content="# PDF Skill...",
        ...     frontmatter={"name": "PDF"},
        ...     nodes={},
        ...     edges={},
        ... )
    """

    skill_id: str
    root_path: str
    skill_md_content: str
    frontmatter: dict[str, Any]
    nodes: dict[str, FileNode]
    edges: dict[str, list[str]]
    docs_content: dict[str, str] = field(default_factory=dict)

    # CapabilityProfile Layer 1 (P1自动派生)
    local_scripts: list[str] = field(default_factory=list)
    referenced_libs: list[str] = field(default_factory=list)

    def get_node(self, path: str) -> FileNode | None:
        """获取指定路径的文件节点.

        Args:
            path: 相对于skill root的路径

        Returns:
            FileNode对象，如果不存在则返回None
        """
        return self.nodes.get(path)

    def get_references(self, path: str) -> list[str]:
        """获取指定文件引用的其他文件.

        Args:
            path: 相对于skill root的路径

        Returns:
            被引用的文件路径列表
        """
        return self.edges.get(path, [])

    def get_referrers(self, path: str) -> list[str]:
        """获取引用指定文件的其他文件.

        Args:
            path: 被引用的文件路径

        Returns:
            引用此文件的文件路径列表
        """
        return [src for src, refs in self.edges.items() if path in refs]

    def get_nodes_by_kind(self, kind: FileKind) -> list[FileNode]:
        """按类型获取文件节点.

        Args:
            kind: 文件类型

        Returns:
            该类型的所有文件节点
        """
        return [node for node in self.nodes.values() if node.kind == kind]

    def get_document_nodes(self) -> list[FileNode]:
        """获取所有文档类型节点."""
        return [node for node in self.nodes.values() if node.is_document()]

    def get_script_nodes(self) -> list[FileNode]:
        """获取所有脚本类型节点."""
        return [node for node in self.nodes.values() if node.is_script()]

    def get_omittable_nodes(self) -> list[FileNode]:
        """获取可跳过的节点（用于P2的priority=3）."""
        return [node for node in self.nodes.values() if node.is_omittable()]

    def add_node(self, node: FileNode) -> None:
        """添加文件节点.

        Args:
            node: 要添加的文件节点
        """
        self.nodes[node.path] = node

    def add_edge(self, from_path: str, to_path: str) -> None:
        """添加引用边.

        Args:
            from_path: 源文件路径
            to_path: 目标文件路径
        """
        if from_path not in self.edges:
            self.edges[from_path] = []
        if to_path not in self.edges[from_path]:
            self.edges[from_path].append(to_path)

    def file_count(self) -> int:
        """返回文件总数."""
        return len(self.nodes)

    def reference_count(self) -> int:
        """返回引用关系总数."""
        return sum(len(refs) for refs in self.edges.values())

    def summary(self) -> dict[str, int]:
        """返回统计摘要."""
        from collections import Counter

        kind_counts = Counter(node.kind for node in self.nodes.values())
        return {
            "total_files": self.file_count(),
            "total_references": self.reference_count(),
            **dict(kind_counts),
        }
