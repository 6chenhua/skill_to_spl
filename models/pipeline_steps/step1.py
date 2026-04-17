"""Step 1: Structure Extraction 相关模型.

此模块包含Step 1阶段用于结构提取的数据结构.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from models.base import CANONICAL_SECTIONS, SourceRef


@dataclass(slots=True)
class SectionItem:
    """标准节中的单个条目.文本保持原样.

    从SKILL.md的各节中提取的原始文本条目，保留原始内容和来源信息.

    Attributes:
        text: 原始文本内容，永不转述
        source: 来源文件名
        multi: 是否出现在多个节中
        source_ref: 源代码引用位置（可选）

    Examples:
        >>> item = SectionItem(
        ...     text="Extract text from PDF files",
        ...     source="SKILL.md",
        ...     multi=False,
        ... )
    """

    text: str
    source: str
    multi: bool = False
    source_ref: SourceRef | None = None

    def __hash__(self) -> int:
        """基于内容和来源的哈希."""
        return hash((self.text, self.source))

    def __eq__(self, other: object) -> bool:
        """基于内容和来源的相等性比较."""
        if not isinstance(other, SectionItem):
            return NotImplemented
        return self.text == other.text and self.source == other.source

    def is_empty(self) -> bool:
        """检查内容是否为空."""
        return not self.text or not self.text.strip()

    def word_count(self) -> int:
        """返回内容字数."""
        return len(self.text.split())


@dataclass(slots=True)
class SectionBundle:
    """Step 1输出: 8个标准节.

    包含SKILL.md中提取的所有标准节内容，所有文本保持原样.

    Attributes:
        intent: INTENT节内容
        workflow: WORKFLOW节内容
        constraints: CONSTRAINTS节内容
        tools: TOOLS节内容
        artifacts: ARTIFACTS节内容
        evidence: EVIDENCE节内容
        examples: EXAMPLES节内容
        notes: NOTES节内容

    Examples:
        >>> bundle = SectionBundle()
        >>> bundle.intent.append(SectionItem("PDF processing", "SKILL.md"))
        >>> bundle.workflow.append(SectionItem("Step 1: Read file", "SKILL.md"))
    """

    intent: list[SectionItem] = field(default_factory=list)
    workflow: list[SectionItem] = field(default_factory=list)
    constraints: list[SectionItem] = field(default_factory=list)
    tools: list[SectionItem] = field(default_factory=list)
    artifacts: list[SectionItem] = field(default_factory=list)
    evidence: list[SectionItem] = field(default_factory=list)
    examples: list[SectionItem] = field(default_factory=list)
    notes: list[SectionItem] = field(default_factory=list)

    def all_sections(self) -> dict[str, list[SectionItem]]:
        """获取所有节作为字典.

        Returns:
            节名称到内容列表的映射
        """
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

    def get_section(self, name: str) -> list[SectionItem]:
        """获取指定节的内容.

        Args:
            name: 节名称 (如 "INTENT", "WORKFLOW")

        Returns:
            SectionItem列表
        """
        return self.all_sections().get(name.upper(), [])

    def to_text(self, sections: Optional[list[str]] = None) -> str:
        """渲染选定（或全部）节为带标签的文本块.

        Args:
            sections: 要渲染的节名称列表，None表示全部

        Returns:
            格式化的文本
        """
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

    def has_section(self, name: str) -> bool:
        """检查指定节是否有内容.

        Args:
            name: 节名称

        Returns:
            如果节有内容返回True
        """
        return len(self.get_section(name)) > 0

    def total_items(self) -> int:
        """返回所有节的条目总数."""
        return sum(len(items) for items in self.all_sections().values())

    def non_empty_sections(self) -> list[str]:
        """返回非空节的名称列表."""
        return [
            name for name in CANONICAL_SECTIONS if self.has_section(name)
        ]

    def summary(self) -> dict[str, Any]:
        """返回统计摘要."""
        return {
            "total_items": self.total_items(),
            "non_empty_sections": len(self.non_empty_sections()),
            "sections": {
                name: len(items) for name, items in self.all_sections().items()
            },
        }

    def find_items_with_text(self, text: str) -> list[tuple[str, SectionItem]]:
        """查找包含指定文本的所有条目.

        Args:
            text: 要搜索的文本

        Returns:
            (节名称, SectionItem) 元组列表
        """
        results = []
        for name, items in self.all_sections().items():
            for item in items:
                if text.lower() in item.text.lower():
                    results.append((name, item))
        return results

    def merge(self, other: SectionBundle) -> SectionBundle:
        """合并另一个SectionBundle的内容.

        Args:
            other: 要合并的SectionBundle

        Returns:
            新的SectionBundle
        """
        merged = SectionBundle()
        for name in CANONICAL_SECTIONS:
            section = self.get_section(name) + other.get_section(name)
            setattr(merged, name.lower(), section)
        return merged
