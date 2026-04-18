# Models Package

This package contains all data models for the skill-to-CNL-P normalization pipeline.

## Structure

```
models/
├── __init__.py          # Unified exports
├── base.py              # Base types and protocols
├── core.py              # Core shared types (TokenUsage, ReviewItem, etc.)
├── pipeline_result.py   # PipelineResult and PipelineConfig
├── deprecated.py        # Backward compatibility layer (to be removed in v3.0)
├── data_models.py       # Forward compatibility (to be removed in v3.0)
├── preprocessing/       # P1-P3 stage models
│   ├── __init__.py
│   ├── reference.py     # FileNode, FileReferenceGraph
│   ├── roles.py         # FileRoleEntry, RoleAssignment
│   ├── package.py       # SkillPackage
│   └── script.py        # ScriptSpec
└── pipeline_steps/      # Step 1-4 stage models
    ├── __init__.py
    ├── step1.py         # SectionBundle, SectionItem
    ├── api.py           # APISpec, ToolSpec, UnifiedAPISpec, etc.
    ├── step4.py         # SPLSpec, SPLBlock, SPLAssembly
    ├── review.py        # NeedsReviewItem, ValidationResult
    └── step3/           # Step 3 models
        ├── __init__.py
        └── models.py    # EntitySpec, WorkflowStep, Flows, etc.
```

## Quick Start

```python
# Import from the unified models package (recommended)
from models import (
    FileNode,
    FileReferenceGraph,
    SkillPackage,
    SectionBundle,
    SectionItem,
    EntitySpec,
    WorkflowStep,
    SPLSpec,
    PipelineResult,
)

# Create a file node
node = FileNode(
    path="docs/guide.md",
    kind="doc",
    size_bytes=1024,
    head_lines=["# Guide"],
    references=["script.py"],
)

# Create a section bundle
bundle = SectionBundle()
bundle.intent.append(SectionItem(text="Process PDF files", source="SKILL.md"))
```

## Migration Guide

### From old imports (deprecated)

```python
# OLD (deprecated, will be removed in v3.0)
from models.data_models import FileNode, SectionBundle
```

### To new imports (recommended)

```python
# NEW (recommended)
from models import FileNode, SectionBundle
```

## Module Details

### base.py

Base types and protocols used across all modules:

- `SourceRef` - Source code reference with file, line, column
- `Serializable` / `Validatable` - Protocols
- Type aliases: `Provenance`, `Priority`, `FileKind`
- Constants: `CANONICAL_SECTIONS`, `MAX_HEAD_LINES`, etc.

### core.py

Core types used across the pipeline:

- `TokenUsage` / `SessionUsage` - LLM token tracking
- `ReviewItem` / `ReviewSeverity` - Review annotations
- `CheckResult` - Validation results

### preprocessing/

Models for preprocessing stages (P1-P3):

- **reference.py**: `FileNode`, `FileReferenceGraph`
- **roles.py**: `FileRoleEntry`, `FileRoleMap`, `RoleAssignment`
- **package.py**: `SkillPackage`
- **script.py**: `ScriptSpec`

### pipeline_steps/

Models for pipeline stages (Step 1-4):

- **step1.py**: `SectionItem`, `SectionBundle`
- **api.py**: `APISpec`, `ToolSpec`, `UnifiedAPISpec`, `FunctionSpec`, `APISymbolTable`
- **step3/models.py**: `EntitySpec`, `WorkflowStep`, `AlternativeFlow`, `ExceptionFlow`, `VarRegistry`
- **step4.py**: `SPLSpec`, `SPLBlock`, `SPLAssembly`
- **review.py**: `NeedsReviewItem`, `ValidationResult`

### pipeline_result.py

- `PipelineResult` - Complete pipeline output
- `PipelineConfig` - Pipeline configuration

## Testing

Run tests:

```bash
# Run all model tests
pytest test/models/ -v

# Run specific test file
pytest test/models/test_base.py -v
pytest test/models/test_core.py -v
pytest test/models/test_preprocessing.py -v
```

## Design Principles

1. **Pure Data Containers**: All dataclasses have no business logic
2. **Type Safety**: Full type hints with Python 3.11+ features
3. **Immutability**: Where appropriate (frozen dataclasses)
4. **Documentation**: Docstrings with Args/Returns/Examples
5. **Backward Compatibility**: Compatibility layer for migration (v2.x)

## Deprecation Timeline

| Version | Status |
|---------|--------|
| v2.x (current) | New structure with backward compatibility |
| v3.0 (planned) | Remove compatibility layer, only new imports |

## License

See project LICENSE.txt
