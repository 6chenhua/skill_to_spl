"""基础类型和协议定义.

此模块包含所有模型类使用的基础类型、协议和类型别名.
这些类型在导入时不依赖其他模块，避免循环导入问题.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

T = TypeVar('T')


# ═══════════════════════════════════════════════════════════════════════════════
# 协议定义
# ═══════════════════════════════════════════════════════════════════════════════

class Serializable(Protocol):
    """可序列化协议.

    实现此协议的对象可以转换为字典并从字典恢复.
    """

    def to_dict(self) -> dict[str, Any]:
        """转换为字典表示."""
        ...

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        """从字典创建实例."""
        ...


class Validatable(Protocol):
    """可验证协议.

    实现此协议的对象可以进行自验证并返回验证错误.
    """

    def validate(self) -> list[str]:
        """验证对象状态.

        Returns:
            验证错误列表，空列表表示验证通过.
        """
        ...


class Sourcable(Protocol):
    """可追溯源协议.

    实现此协议的对象包含源代码引用信息.
    """

    source_file: str
    source_line: int | None


# ═══════════════════════════════════════════════════════════════════════════════
# 基础数据类
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class SourceRef:
    """源代码引用位置.

    用于跟踪模型实例的来源文件和位置，便于调试和审查.

    Attributes:
        file: 源文件路径，相对于项目根目录
        line: 行号，从1开始计数，0表示未知
        column: 列号，从1开始计数，0表示未知

    Examples:
        >>> ref = SourceRef("skills/pdf/SKILL.md", line=15, column=8)
        >>> str(ref)
        'skills/pdf/SKILL.md:15'
        >>> ref_no_line = SourceRef("skills/pdf/SKILL.md")
        >>> str(ref_no_line)
        'skills/pdf/SKILL.md'
    """

    file: str
    line: int = 0
    column: int = 0

    def __str__(self) -> str:
        """返回可读的引用字符串."""
        if self.line > 0:
            return f"{self.file}:{self.line}"
        return self.file

    def __repr__(self) -> str:
        """返回详细的表示."""
        if self.column > 0:
            return f"SourceRef(file={self.file!r}, line={self.line}, column={self.column})"
        elif self.line > 0:
            return f"SourceRef(file={self.file!r}, line={self.line})"
        return f"SourceRef(file={self.file!r})"


# ═══════════════════════════════════════════════════════════════════════════════
# 类型别名
# ═══════════════════════════════════════════════════════════════════════════════

Provenance = str
"""来源可信度类型.

取值:
    - "EXPLICIT": 显式声明，高可信度
    - "ASSUMED": 合理推断，中等可信度
    - "LOW_CONFIDENCE": 低可信度，需要人工审查
"""

Priority = int
"""优先级类型.

取值:
    - 1: must_read (必须阅读)
    - 2: include_summary (包含摘要)
    - 3: omit (跳过)
"""

FileKind = str
"""文件类型.

取值:
    - "doc": 文档文件 (.md, .txt等)
    - "script": 脚本文件 (.py, .js等)
    - "data": 数据文件
    - "document": 文档资产
    - "image": 图片文件
    - "audio": 音频文件
"""

Confidence = float
"""置信度类型，范围0.0-1.0."""

# ═══════════════════════════════════════════════════════════════════════════════
# 常量定义
# ═══════════════════════════════════════════════════════════════════════════════

CANONICAL_SECTIONS: list[str] = [
    "INTENT",
    "WORKFLOW",
    "CONSTRAINTS",
    "TOOLS",
    "ARTIFACTS",
    "EVIDENCE",
    "EXAMPLES",
    "NOTES",
]
"""SKILL.md中的8个标准节名称."""

DEFAULT_PRIORITY_THRESHOLD: Priority = 2
"""默认优先级阈值，低于此值的文件会被跳过."""

MAX_HEAD_LINES: int = 20
"""读取文档文件时默认读取的前导行数."""

MAX_SCRIPT_COMMENT_LINES: int = 5
"""读取脚本文件时默认读取的注释行数."""

# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════


def validate_provenance(value: str) -> str:
    """验证来源可信度值.

    Args:
        value: 要验证的值

    Returns:
        验证后的值

    Raises:
        ValueError: 如果值不是有效的来源类型
    """
    valid = ("EXPLICIT", "ASSUMED", "LOW_CONFIDENCE")
    if value not in valid:
        raise ValueError(f"Invalid provenance '{value}'. Must be one of: {valid}")
    return value


def validate_priority(value: int) -> int:
    """验证优先级值.

    Args:
        value: 要验证的值

    Returns:
        验证后的值

    Raises:
        ValueError: 如果值不是有效的优先级
    """
    if not 1 <= value <= 3:
        raise ValueError(f"Invalid priority {value}. Must be 1, 2, or 3")
    return value


def validate_confidence(value: float) -> float:
    """验证置信度值.

    Args:
        value: 要验证的值

    Returns:
        验证后的值

    Raises:
        ValueError: 如果值不在0.0-1.0范围内
    """
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"Invalid confidence {value}. Must be between 0.0 and 1.0")
    return value
