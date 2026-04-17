# PROJECT KNOWLEDGE BASE: simplified_pipeline

**Language**: Python 3.11+
**Purpose**: Streamlined alternative to the full skill-to-CNL-P pipeline with HITL clarification support
**Architecture**: Sequential pipeline (Step 0→1→3A→3B→4) with optional human-in-the-loop clarification

---

## OVERVIEW

A minimal version of the skill-to-CNL-P pipeline that reduces complexity by extracting only 5 sections (vs 8), handling only variables (no files), and using simplified action types. Includes a human-in-the-loop (HITL) clarification system for resolving ambiguous requirements through interactive questioning.

---

## STRUCTURE

```
simplified_pipeline/
├── __init__.py              # Package exports: run_pipeline, PipelineConfig, LLMConfig
├── models.py                # Core data models (SectionBundle, VariableSpec, etc.)
├── prompts.py               # LLM prompts for all pipeline steps (Step 1, 3A, 3B, 4)
├── llm_client.py            # LLM API wrapper with token tracking
├── steps.py                 # Step implementations (1, 3A, 3B, 4)
├── orchestrator.py          # Pipeline coordinator with HITL integration
├── example_usage.py         # Example usage script
├── README.md                # Detailed documentation
└── clarification/           # HITL clarification module
    ├── __init__.py          # Module exports and conditional imports
    ├── models.py            # Data models (AmbiguityMarker, ClarificationQuestion, etc.)
    ├── detector.py          # Hybrid ambiguity detection (rule-based + LLM)
    ├── questions.py         # Question generation from ambiguity markers
    ├── manager.py           # Clarification workflow orchestration
    ├── ui.py                # UI interfaces (console, mock, abstract)
    ├── prompts.py           # LLM prompts for question generation
    ├── structural_models.py # Step 0 structural clarification models
    ├── structural_ui.py     # Step 0 structural clarification UI
    ├── step0_orchestrator.py # Step 0 orchestration logic
    └── README.md            # Clarification module documentation
```

---

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Pipeline entry point | `orchestrator.py` | `run_pipeline()`, `run_simplified_pipeline()` |
| Pipeline configuration | `orchestrator.py` | `PipelineConfig` class with HITL options |
| Core data models | `models.py` | `SectionBundle`, `VariableSpec`, `WorkflowStepSpec`, `SPLSpec` |
| LLM client wrapper | `llm_client.py` | `LLMClient`, `LLMConfig`, `SessionUsage` |
| Step 1: Structure extraction | `steps.py` | `run_step1_structure_extraction()` - 5 sections |
| Step 3A: Variable extraction | `steps.py` | `run_step3a_variable_extraction()` - variables only |
| Step 3B: Workflow analysis | `steps.py` | `run_step3b_workflow_analysis()` - simplified action types |
| Step 4: SPL emission | `steps.py` | `run_step4_spl_emission()` - 4 blocks (no APIs/files) |
| LLM prompts | `prompts.py` | `STEP1_SYSTEM`, `STEP3A_SYSTEM`, etc. |
| Ambiguity detection | `clarification/detector.py` | `AmbiguityDetector`, `RuleBasedDetector`, `LLMBasedDetector` |
| Question generation | `clarification/questions.py` | `QuestionGenerator`, templates, translation rules |
| Clarification orchestration | `clarification/manager.py` | `ClarificationManager`, `run_hitl_clarification()` |
| UI interfaces | `clarification/ui.py` | `ClarificationUI`, `ConsoleClarificationUI`, `MockClarificationUI` |
| Clarification models | `clarification/models.py` | `AmbiguityMarker`, `ClarificationQuestion`, `ClarificationContext` |
| Step 0: Structural clarification | `clarification/step0_orchestrator.py` | Pre-Step 1 section assignment clarification |

---

## CONVENTIONS

- **Type hints**: Required on all public functions
- **Dataclasses**: Pure data containers in `models.py` and `clarification/models.py`
- **Pipeline stages**: Sequential execution (no parallel steps like full pipeline)
- **File naming**: `snake_case.py`, descriptive
- **Logging**: `logger = logging.getLogger(__name__)` pattern
- **Docstrings**: Google-style with Args/Returns sections
- **SPL terminology hidden**: Users never see SPL jargon in clarification questions
- **Question templates**: Business-domain language, multiple choice with "Other" option

---

## ANTI-PATTERNS

- **NEVER** expose SPL jargon to users in clarification questions (no `[DEFINE_]`, `<REF>`, `var_id`, etc.)
- **NEVER** call LLM client directly from substeps, use `llm_client.py` wrapper
- **NEVER** invent new variable IDs in Step 3B, only use IDs from provided list
- **NEVER** generate nested BLOCKs in SPL emission (flat structure only)
- **AVOID** hardcoding model names, pass via `LLMConfig`
- **NO** `print()` for debugging, use `logger.debug()`
- **NO** external API declarations in simplified pipeline (skip Step 4D)
- **NO** file declarations in simplified pipeline (skip DEFINE_FILES)

---

## UNIQUE PATTERNS

### Simplified Pipeline Differences

| Aspect | Full Pipeline | Simplified Pipeline |
|--------|---------------|---------------------|
| Pre-processing | P1, P2, P3 | None - direct document input |
| Step 1 sections | 8 sections | 5 sections (no TOOLS, ARTIFACTS, EVIDENCE) |
| Step 3A entities | 4 kinds (Artifact, Run, Evidence, Record) | Variables only |
| Step 3B actions | 7 types + tool matching | 4 types (LLM_TASK, FILE_READ, FILE_WRITE, USER_INTERACTION) |
| Step 4 blocks | 6 blocks (4a-4f) | 4 blocks (4a, 4b, 4c, 4e) - no APIs, no files |
| Parallel execution | Yes (ThreadPoolExecutor) | Sequential |

### Clarification System Architecture

```
Input: merged_doc_text
↓
Step 0: Structural Clarification (optional)
  - Detect ambiguous section assignments
  - Ask user for section guidance
  - Produce SectionGuidance
↓
Step 1: Structure Extraction (with guidance)
  - Apply section overrides from Step 0
  - Extract 5 sections → SectionBundle
↓
[If enable_clarification]
  Ambiguity Detection → Question Generation → User Interaction
  - detector.py: Hybrid detection (rule + LLM)
  - questions.py: Template/LLM question generation
  - ui.py: Console or custom UI
  - manager.py: Orchestration
↓
Step 3A: Variable Extraction
Step 3B: Workflow Analysis
Step 4: SPL Emission
```

### Ambiguity Detection Types

| Type | Description | Example |
|------|-------------|---------|
| `LEXICAL` | Word with multiple meanings | "bank", "green", "light" |
| `SYNTACTIC` | Multiple parse interpretations | "The Tibetan history teacher" |
| `SEMANTIC` | Scope/quantifier ambiguity | "All users need a license" |
| `PRAGMATIC` | Vague context-dependent terms | "fast", "sufficient", "appropriate" |
| `QUANTIFIER` | Vague quantity words | "many", "few", "some", "most" |
| `OPTIONALITY` | Uncertain requirement strength | "may", "might", "optionally" |
| `WEAK_WORD` | Subjective criteria | "appropriate", "suitable", "adequate" |
| `REFERENCE` | Unclear pronoun antecedents | "it", "they", "this" |
| `NEGATION` | Double/unclear negation | "not uncommon", "not impossible" |

### Sensitivity Levels

| Level | Defect Density | Confidence | Use Case |
|-------|---------------|------------|----------|
| `low` | 0.25 | 0.5 | Fewer interruptions, high-confidence only |
| `medium` | 0.15 | 0.7 | Balanced detection (recommended) |
| `high` | 0.10 | 0.8 | Thorough, catches subtle ambiguities |

---

## COMMANDS

```python
# Run simplified pipeline
from simplified_pipeline import run_simplified_pipeline

result = run_simplified_pipeline(
    merged_doc_text="Your skill documentation...",
    skill_id="my_skill",
    enable_clarification=True,  # Enable HITL
    clarification_sensitivity="medium",
)

# Access results
print(result.spl_spec.spl_text)

# Run with full configuration
from simplified_pipeline.orchestrator import run_pipeline, PipelineConfig
from simplified_pipeline.llm_client import LLMConfig

config = PipelineConfig(
    merged_doc_text="...",
    skill_id="my_skill",
    llm_config=LLMConfig(model="gpt-4o"),
    enable_clarification=True,
    clarification_sensitivity="medium",
    clarification_max_iterations=5,
)
result = run_pipeline(config)
```

---

## NOTES

- **Direct document input**: Unlike the full pipeline, simplified_pipeline accepts `merged_doc_text` directly (no skill directory)
- **HITL disabled by default**: Set `enable_clarification=True` to activate
- **One question at a time**: Questions presented sequentially, not in bulk
- **Bounded iterations**: Max 5 clarification rounds by default (configurable 1-10)
- **Checkpoint support**: Clarification state can be saved/resumed via `ClarificationCheckpoint`
- **Business language**: All user-facing questions use business terms, never SPL jargon
- **Graceful degradation**: If clarification fails or is disabled, pipeline continues normally
