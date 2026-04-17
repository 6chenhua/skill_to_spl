"""核心共享类型 - 跨阶段使用的数据类.

此模块包含在Pipeline多个阶段间共享的核心数据类型，
如token使用统计、审查项等.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from models.base import SourceRef


# ═══════════════════════════════════════════════════════════════════════════════
# Token使用统计
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class TokenUsage:
    """单次LLM调用的token使用统计.

    Attributes:
        prompt_tokens: 提示中的token数量
        completion_tokens: 生成的token数量
        total_tokens: 总计token数量

    Examples:
        >>> usage1 = TokenUsage(prompt_tokens=100, completion_tokens=50)
        >>> usage2 = TokenUsage(prompt_tokens=200, completion_tokens=100)
        >>> total = usage1 + usage2
        >>> total.total_tokens
        450
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        """确保total_tokens正确计算."""
        object.__setattr__(
            self,
            "total_tokens",
            self.prompt_tokens + self.completion_tokens,
        )

    def __add__(self, other: TokenUsage) -> TokenUsage:
        """合并两个使用统计."""
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    def __repr__(self) -> str:
        """返回简洁的表示."""
        return (
            f"TokenUsage(p={self.prompt_tokens}, "
            f"c={self.completion_tokens}, "
            f"t={self.total_tokens})"
        )


@dataclass(slots=True)
class SessionUsage:
    """整个session的token使用聚合.

    跟踪Pipeline每个步骤的token使用情况，提供总计和分步统计.

    Attributes:
        steps: 步骤名称到TokenUsage的映射

    Examples:
        >>> usage = SessionUsage()
        >>> usage.add("step1", TokenUsage(100, 50))
        >>> usage.add("step2", TokenUsage(200, 100))
        >>> usage.total.total_tokens
        450
    """

    steps: dict[str, TokenUsage] = field(default_factory=dict)

    @property
    def total(self) -> TokenUsage:
        """所有步骤的总计."""
        total = TokenUsage()
        for usage in self.steps.values():
            total += usage
        return total

    def add(self, step_name: str, usage: TokenUsage) -> None:
        """添加一个步骤的使用统计.

        Args:
            step_name: 步骤名称
            usage: 该步骤的token使用
        """
        self.steps[step_name] = usage

    def get_step_usage(self, step_name: str) -> TokenUsage | None:
        """获取特定步骤的使用统计.

        Args:
            step_name: 步骤名称

        Returns:
            TokenUsage对象，如果不存在则返回None
        """
        return self.steps.get(step_name)

    def summary(self) -> str:
        """生成文本摘要."""
        lines = ["Token Usage Summary:", f"  Total: {self.total.total_tokens:,} tokens"]
        if self.steps:
            lines.append("")
            lines.append("By Step:")
            for name, usage in sorted(self.steps.items()):
                lines.append(f"  {name}: {usage.total_tokens:,} tokens")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 审查相关
# ═══════════════════════════════════════════════════════════════════════════════


class ReviewSeverity(Enum):
    """审查项严重级别."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(slots=True)
class ReviewItem:
    """人工审查标记项.

    当Pipeline遇到需要人工注意的内容时生成此对象.

    Attributes:
        item: 需要审查的内容描述
        reason: 为什么需要审查
        question: 向审查者提出的问题
        severity: 严重程度
        source_ref: 源代码引用位置

    Examples:
        >>> item = ReviewItem(
        ...     item="Ambiguous workflow step",
        ...     reason="Multiple interpretations possible",
        ...     question="Which interpretation is correct?",
        ...     severity=ReviewSeverity.WARNING,
        ... )
    """

    item: str
    reason: str
    question: str
    severity: ReviewSeverity = field(default=ReviewSeverity.WARNING)
    source_ref: SourceRef | None = None

    def __post_init__(self) -> None:
        """确保severity是枚举值."""
        if isinstance(self.severity, str):
            object.__setattr__(
                self, "severity", ReviewSeverity(self.severity.lower())
            )

    def format_for_display(self) -> str:
        """格式化为可读的审查报告格式."""
        lines = [
            f"[{self.severity.value.upper()}] {self.item}",
            f"  Reason: {self.reason}",
            f"  Question: {self.question}",
        ]
        if self.source_ref:
            lines.append(f"  Source: {self.source_ref}")
        return "\n".join(lines)


@dataclass(slots=True)
class ReviewSummary:
    """审查摘要 - 收集所有审查项.

    Attributes:
        items: 审查项列表
        skill_id: 关联的技能ID
    """

    skill_id: str
    items: list[ReviewItem] = field(default_factory=list)

    def add(self, item: ReviewItem) -> None:
        """添加审查项."""
        self.items.append(item)

    def has_errors(self) -> bool:
        """是否有错误级别的审查项."""
        return any(item.severity == ReviewSeverity.ERROR for item in self.items)

    def has_warnings(self) -> bool:
        """是否有警告级别的审查项."""
        return any(item.severity == ReviewSeverity.WARNING for item in self.items)

    def by_severity(self, severity: ReviewSeverity) -> list[ReviewItem]:
        """按严重级别筛选审查项."""
        return [item for item in self.items if item.severity == severity]

    def to_text(self) -> str:
        """生成文本报告."""
        if not self.items:
            return f"No review items for {self.skill_id}"

        lines = [f"Review Summary for {self.skill_id}:", ""]

        # 按严重级别分组
        for severity in ReviewSeverity:
            items = self.by_severity(severity)
            if items:
                lines.append(f"\n{severity.value.upper()} ({len(items)}):")
                for item in items:
                    lines.append(f"  - {item.item}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 检查结果
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class CheckResult:
    """检查结果 - 用于验证和检查操作.

    Attributes:
        passed: 是否通过
        message: 结果消息
        details: 详细说明
    """

    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, message: str = "", **details: Any) -> CheckResult:
        """创建成功结果."""
        return cls(passed=True, message=message, details=details)

    @classmethod
    def failure(cls, message: str, **details: Any) -> CheckResult:
        """创建失败结果."""
        return cls(passed=False, message=message, details=details)

    def __bool__(self) -> bool:
        """布尔值表示是否通过."""
        return self.passed
