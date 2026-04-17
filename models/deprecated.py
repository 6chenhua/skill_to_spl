"""Backward compatibility module for deprecated imports.

This module provides compatibility for old import paths from models.data_models.
It forwards all imports to the new models package and issues deprecation warnings.

WARNING: This module will be removed in v3.0. Migrate to use:
    from models import X  # New way
    # Instead of:
    from models.data_models import X  # Old way (deprecated)
"""

from __future__ import annotations

from typing import Any

import warnings

# Issue deprecation warning when this module is imported
warnings.warn(
    "models.data_models is deprecated and will be removed in v3.0. "
    "Use 'from models import X' instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Import all public symbols from the new models package
from models import (
    # Base types
    CANONICAL_SECTIONS,
    DEFAULT_PRIORITY_THRESHOLD,
    MAX_HEAD_LINES,
    MAX_SCRIPT_COMMENT_LINES,
    FileKind,
    Priority,
    Provenance,
    Serializable,
    SourceRef,
    Validatable,
    # Core types
    CheckResult,
    ReviewItem,
    ReviewSeverity,
    SessionUsage,
    TokenUsage,
    # Preprocessing
    FileNode,
    FileReferenceGraph,
    FileRoleEntry,
    FileRoleMap,
    RoleAssignment,
    ScriptMetadata,
    ScriptSpec,
    SkillPackage,
    # Step 1
    SectionBundle,
    SectionItem,
    # Step 3
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
    # Step 4
    SPLAssembly,
    SPLBlock,
    SPLSpec,
    # Review
    NeedsReviewItem,
    ValidationResult,
    # API
    APISpec,
    APISymbolTable,
    FunctionSpec,
    ToolSpec,
    UnifiedAPISpec,
    # Results
    PipelineConfig,
    PipelineResult,
    # Validation functions
    validate_confidence,
    validate_priority,
    validate_provenance,
)

# Backward compatibility aliases
# These provide compatibility for code that uses the old names

# Old interface name (deprecated)
InterfaceSpec = StructuredSpec

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
    "InteractionType",
    "StructuredSpec",
    "InterfaceSpec",  # Backward compatibility alias
    "TypeSpec",
    "VarSpec",
    "VarRegistry",
    "ActionType",
    "EntityKind",
    # Review
    "NeedsReviewItem",
    "ValidationResult",
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
    # Results
    "PipelineResult",
    "PipelineConfig",
]


# Mark all re-exported symbols as deprecated
def _deprecate_symbol(name: str) -> None:
    """Mark a symbol as deprecated."""
    if name.startswith("_"):
        return
    warnings.warn(
        f"{name} from models.data_models is deprecated. "
        f"Use 'from models import {name}' instead.",
        DeprecationWarning,
        stacklevel=3,
    )


# Helper function for migration checking
def check_migration_status() -> dict[str, Any]:
    """Check if codebase has migrated from old imports.

    Returns:
        Dictionary with migration status
    """
    return {
        "migrated": False,
        "message": "Code is still using deprecated models.data_models imports",
        "action": "Update imports to use 'from models import X'",
    }
