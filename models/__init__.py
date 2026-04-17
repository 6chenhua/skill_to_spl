"""Models package - Unified exports for all data models.

This module provides a unified import interface for all data models
used in the skill-to-CNL-P pipeline. All models are pure data containers
with no business logic.

Migration Guide:
    Old: from models.data_models import X
    New: from models import X

Example:
    >>> from models import FileNode, SectionBundle, EntitySpec
    >>> node = FileNode(path="doc.md", kind="doc", ...)
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════
# Base Types
# ═══════════════════════════════════════════════════════════════════════════════

from models.base import (
    CANONICAL_SECTIONS,
    DEFAULT_PRIORITY_THRESHOLD,
    FileKind,
    MAX_HEAD_LINES,
    MAX_SCRIPT_COMMENT_LINES,
    Priority,
    Provenance,
    Serializable,
    SourceRef,
    Validatable,
    validate_confidence,
    validate_priority,
    validate_provenance,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Core Types
# ═══════════════════════════════════════════════════════════════════════════════

from models.core import (
    CheckResult,
    ReviewItem,
    ReviewSeverity,
    ReviewSummary,
    SessionUsage,
    TokenUsage,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Preprocessing Models (P1-P3)
# ═══════════════════════════════════════════════════════════════════════════════

from models.preprocessing.package import SkillPackage
from models.preprocessing.reference import (
    FileNode,
    FileReferenceGraph,
    ScriptMetadata,
)
from models.preprocessing.roles import (
    FileRoleEntry,
    FileRoleMap,
    RoleAssignment,
)
from models.preprocessing.script import ScriptSpec

# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline Step Models
# ═══════════════════════════════════════════════════════════════════════════════

# Step 1: Structure Extraction
from models.pipeline_steps.step1 import SectionBundle, SectionItem

# Step 3: Entity and Workflow Analysis
from models.pipeline_steps.step3 import (
    ActionType,
    AlternativeFlow,
    EntityKind,
    EntitySpec,
    ExceptionFlow,
    FlowStep,
    InteractionRequirement,
    InteractionType,
    InterfaceSpec,
    StructuredSpec,
    TypeSpec,
    VarRegistry,
    VarSpec,
    WorkflowStep,
)

# Step 4: SPL Emission
from models.pipeline_steps.step4 import SPLAssembly, SPLBlock, SPLSpec

# API Models (Step 1.5, Step 4D)
from models.pipeline_steps.api import (
    APISpec,
    APISymbolTable,
    FunctionSpec,
    ToolSpec,
    UnifiedAPISpec,
)

# Review and Validation Models
from models.pipeline_steps.review import (
    NeedsReviewItem,
    ReviewSeverity,
    ValidationResult,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline Result
# ═══════════════════════════════════════════════════════════════════════════════

from models.pipeline_result import PipelineConfig, PipelineResult

# ═══════════════════════════════════════════════════════════════════════════════
# Re-export from data_models for backward compatibility (deprecated)
# These will be removed in v3.0
# ═══════════════════════════════════════════════════════════════════════════════

# Import common types from data_models that might be referenced
# This ensures existing code continues to work while warning about deprecation
import warnings

try:
    # Try to import from existing data_models as fallback
    from models.data_models import (
        FileNode as _FileNode,
        FileReferenceGraph as _FileReferenceGraph,
        FileRoleEntry as _FileRoleEntry,
        SkillPackage as _SkillPackage,
    )

    # These imports work, so data_models still exists
    # The module itself will issue deprecation warnings
    _DATA_MODELS_AVAILABLE = True
except ImportError:
    _DATA_MODELS_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Base
    "SourceRef",
    "Provenance",
    "Priority",
    "FileKind",
    "Serializable",
    "Validatable",
    "CANONICAL_SECTIONS",
    "DEFAULT_PRIORITY_THRESHOLD",
    "MAX_HEAD_LINES",
    "MAX_SCRIPT_COMMENT_LINES",
    "validate_provenance",
    "validate_priority",
    "validate_confidence",
    # Core
    "TokenUsage",
    "SessionUsage",
    "ReviewItem",
    "ReviewSeverity",
    "ReviewSummary",
    "CheckResult",
    # Preprocessing
    "FileNode",
    "FileReferenceGraph",
    "ScriptMetadata",
    "ScriptSpec",
    "FileRoleEntry",
    "FileRoleMap",
    "RoleAssignment",
    "SkillPackage",
    # Step 1
    "SectionItem",
    "SectionBundle",
    # Step 3
    "EntitySpec",
    "WorkflowStep",
    "FlowStep",
    "AlternativeFlow",
    "ExceptionFlow",
    "InteractionRequirement",
    "StructuredSpec",
    "InterfaceSpec",
    "TypeSpec",
    "VarSpec",
    "VarRegistry",
    "ActionType",
    "EntityKind",
    "InteractionType",
    # Step 4
    "SPLSpec",
    "SPLBlock",
    "SPLAssembly",
    # API
    "FunctionSpec",
    "UnifiedAPISpec",
    "APISpec",
    "ToolSpec",
    "APISymbolTable",
    # Review
    "NeedsReviewItem",
    "ValidationResult",
    # Result
    "PipelineResult",
    "PipelineConfig",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Version Info
# ═══════════════════════════════════════════════════════════════════════════════

__version__ = "2.0.0"


def check_deprecated_imports() -> None:
    """Check if deprecated imports are being used and warn."""
    # This function can be called to check for deprecated patterns
    pass


# Issue a one-time deprecation notice if models.data_models exists
if _DATA_MODELS_AVAILABLE:
    warnings.warn(
        "models.data_models is deprecated. Use 'from models import X' instead. "
        "This compatibility layer will be removed in v3.0.",
        DeprecationWarning,
        stacklevel=2,
    )
