"""Step 4: SPL Emission 相关模型.

此模块包含Step 4阶段用于SPL生成和输出的数据结构.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from models.base import CANONICAL_SECTIONS, SourceRef
from models.core import ReviewItem


@dataclass(slots=True)
class SPLSpec:
    """Step 4输出: 最终规格化的SPL.

    包含生成的完整SPL代码和相关元数据.

    Attributes:
        skill_id: 技能标识符
        spl_text: 完整的SPL代码块
        review_summary: 纯文本审查摘要
        clause_counts: 条款统计 {"HARD": N, "MEDIUM": N, ...}
        review_items: 结构化审查项列表
        metadata: 额外元数据

    Examples:
        >>> spec = SPLSpec(
        ...     skill_id="pdf",
        ...     spl_text="[DEFINE_PERSONA: ...]",
        ...     review_summary="No issues found",
        ...     clause_counts={"HARD": 2, "MEDIUM": 1},
        ... )
    """

    skill_id: str
    spl_text: str
    review_summary: str
    clause_counts: dict[str, int] = field(default_factory=dict)
    review_items: list[ReviewItem] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """统计条款数量."""
        if not self.clause_counts:
            self._count_clauses()

    def _count_clauses(self) -> None:
        """统计各种条款数量."""
        counts = {"HARD": 0, "MEDIUM": 0, "SOFT": 0, "NON": 0}
        for clause_type in counts:
            counts[clause_type] = self.spl_text.count(f"[{clause_type}:")
        object.__setattr__(self, "clause_counts", counts)

    def get_section(self, section_name: str) -> str:
        """提取SPL中的特定节.

        Args:
            section_name: 节名称（如 "PERSONA", "CONSTRAINTS"）

        Returns:
            节内容，如果不存在则返回空字符串
        """
        pattern = rf"\[DEFINE_{re.escape(section_name.upper())}:.*?\[END_{re.escape(section_name.upper())}\]"
        match = re.search(pattern, self.spl_text, re.DOTALL)
        return match.group(0) if match else ""

    def has_section(self, section_name: str) -> bool:
        """检查SPL是否包含特定节.

        Args:
            section_name: 节名称

        Returns:
            如果存在返回True
        """
        return f"[DEFINE_{section_name.upper()}:" in self.spl_text

    def validate_syntax(self) -> list[str]:
        """基础SPL语法验证.

        Returns:
            验证错误列表，空列表表示验证通过
        """
        errors = []

        # 检查未闭合的块
        opens = self.spl_text.count("[DEFINE_")
        closes = self.spl_text.count("[END_")
        if opens != closes:
            errors.append(f"Mismatched blocks: {opens} opens, {closes} closes")

        # 检查必需的节
        required_sections = ["PERSONA", "WORKER"]
        for section in required_sections:
            if not self.has_section(section):
                errors.append(f"Missing required section: {section}")

        # 检查引用格式
        ref_pattern = r"<REF>.*?</REF>"
        refs = re.findall(ref_pattern, self.spl_text)
        for ref in refs:
            if not ref.replace("<REF>", "").replace("</REF>", "").strip():
                errors.append(f"Empty reference: {ref}")

        return errors

    def is_valid(self) -> bool:
        """检查SPL是否通过语法验证.

        Returns:
            如果有效返回True
        """
        return len(self.validate_syntax()) == 0

    def get_clause_count(self, clause_type: str) -> int:
        """获取指定类型的条款数量.

        Args:
            clause_type: 条款类型 (HARD, MEDIUM, SOFT, NON)

        Returns:
            条款数量
        """
        return self.clause_counts.get(clause_type.upper(), 0)

    def has_review_items(self) -> bool:
        """是否有需要审查的项."""
        return len(self.review_items) > 0

    def get_review_text(self) -> str:
        """生成格式化的审查报告."""
        if not self.review_items:
            return f"No review items for {self.skill_id}"

        lines = [f"Review Summary for {self.skill_id}:", ""]
        for i, item in enumerate(self.review_items, 1):
            lines.append(f"{i}. [{item.severity.value.upper()}] {item.item}")
            lines.append(f"   Reason: {item.reason}")
            lines.append(f"   Question: {item.question}")
            if item.source_ref:
                lines.append(f"   Source: {item.source_ref}")
            lines.append("")
        return "\n".join(lines)

    def summary(self) -> dict[str, Any]:
        """返回统计摘要."""
        return {
            "skill_id": self.skill_id,
            "spl_length": len(self.spl_text),
            "sections": [
                s for s in CANONICAL_SECTIONS if self.has_section(s)
            ],
            "clause_counts": self.clause_counts,
            "review_items": len(self.review_items),
            "is_valid": self.is_valid(),
        }


@dataclass(slots=True)
class SPLBlock:
    """单个SPL块.

    用于Step 4中生成和组装各个子块（S4A, S4B等）.

    Attributes:
        block_id: 块标识符（如 "4a", "4b"）
        block_type: 块类型（如 "PERSONA", "VARIABLES"）
        content: 块内容
        metadata: 元数据
        source_ref: 源代码引用位置
    """

    block_id: str
    block_type: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    source_ref: SourceRef | None = None

    def __len__(self) -> int:
        """返回内容长度."""
        return len(self.content)

    def is_empty(self) -> bool:
        """内容是否为空."""
        return not self.content or not self.content.strip()

    def to_spl(self) -> str:
        """转换为SPL格式."""
        if self.is_empty():
            return ""
        return self.content.strip()


@dataclass(slots=True)
class SPLAssembly:
    """SPL组装结果.

    用于收集和组装Step 4的所有子块.

    Attributes:
        skill_id: 技能标识符
        blocks: 所有块的列表
        final_spl: 最终组装的SPL（如果已组装）
    """

    skill_id: str
    blocks: list[SPLBlock] = field(default_factory=list)
    final_spl: str = ""

    def add_block(self, block: SPLBlock) -> None:
        """添加块."""
        self.blocks.append(block)

    def get_block(self, block_id: str) -> SPLBlock | None:
        """按ID获取块."""
        for block in self.blocks:
            if block.block_id == block_id:
                return block
        return None

    def get_blocks_by_type(self, block_type: str) -> list[SPLBlock]:
        """按类型获取块."""
        return [b for b in self.blocks if b.block_type == block_type]

    def assemble(self) -> str:
        """组装所有块为最终SPL.

        Returns:
            完整的SPL文本
        """
        # 按特定顺序组装
        order = [
            "s0",  # DEFINE_AGENT
            "4a",  # PERSONA
            "4b",  # CONSTRAINTS
            "4c",  # VARIABLES, FILES, TYPES
            "4d",  # APIS
            "4e",  # WORKER
            "4f",  # EXAMPLES
        ]

        parts = []
        for block_id in order:
            block = self.get_block(block_id)
            if block and not block.is_empty():
                parts.append(block.to_spl())

        self.final_spl = "\n\n".join(parts)
        return self.final_spl

    def summary(self) -> dict[str, Any]:
        """返回统计摘要."""
        return {
            "skill_id": self.skill_id,
            "block_count": len(self.blocks),
            "blocks": [b.block_id for b in self.blocks],
            "total_length": sum(len(b) for b in self.blocks),
            "final_length": len(self.final_spl),
        }
