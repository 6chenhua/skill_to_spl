"""预处理阶段模型 (P1-P3).

此模块包含预处理阶段使用的数据模型:
- P1: Reference Graph Builder
- P2: File Role Resolver
- P3: Skill Package Assembler
"""

from models.preprocessing.reference import FileNode, FileReferenceGraph
from models.preprocessing.roles import FileRoleEntry, FileRoleMap
from models.preprocessing.package import SkillPackage

__all__ = [
    "FileNode",
    "FileReferenceGraph",
    "FileRoleEntry",
    "FileRoleMap",
    "SkillPackage",
]
