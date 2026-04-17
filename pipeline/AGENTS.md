# PIPELINE KNOWLEDGE BASE: skill-to-cnlp

**Language**: Python 3.11+
**Purpose**: Multi-stage LLM-powered pipeline for transforming skill packages into SPL/CNL-P specifications

---

## OVERVIEW

The pipeline module orchestrates the core transformation logic, coordinating preprocessing stages (P1-P3) and LLM extraction steps (Step 1, 3A, 3B, 4) to convert skill packages into structured SPL specifications. It handles checkpoint management, parallel execution, and token tracking throughout the process.

---

## STRUCTURE

```
pipeline/
├── orchestrator.py              # Pipeline execution coordinator
├── orchestrator_async.py        # Async variant of orchestrator
├── llm_client.py                # LLM API wrapper with token tracking
├── spl_formatter.py             # SPL formatting utilities
├── step2b_classifier.py         # Step 2B classification logic
├── steps.py.bak                 # Backup of legacy steps
├── llm_steps/                   # Step implementations
│   ├── __init__.py
│   ├── p2_file_role_resolve.py  # P2: File role resolution
│   ├── p3_summarize_file.py     # P3: File summarization
│   ├── step1_structure_extraction.py      # Step 1: Extract 8 canonical sections
│   ├── step1_5_api_generation.py        # Step 1.5: API generation
│   ├── step4_adapter.py         # Step 4 adapter utilities
│   ├── step3/                   # Step 3: Workflow analysis
│   │   ├── __init__.py
│   │   ├── io.py                # Step 3 I/O utilities
│   │   ├── orchestrator.py      # Step 3 orchestration
│   │   ├── t.py                 # Step 3A: Entity extraction
│   │   └── w.py                 # Step 3B: Workflow analysis
│   └── step4_spl_emission/      # Step 4: SPL emission (parallel substeps)
│       ├── __init__.py
│       ├── assembly.py          # SPL assembly logic
│       ├── inputs.py            # Input handling
│       ├── inputs_v2.py         # Input handling v2
│       ├── nesting_validation.py # Nesting validation
│       ├── orchestrator.py      # Step 4 orchestration
│       ├── s4c_from_registry.py # S4C from registry
│       ├── substep_calls.py     # Substep call management
│       ├── symbol_table.py      # Symbol table management
│       └── utils.py             # Step 4 utilities
```

---

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Pipeline orchestration | `orchestrator.py` | `run_pipeline()`, `PipelineConfig`, checkpoint management |
| Async orchestration | `orchestrator_async.py` | Async variant with concurrent execution |
| LLM client wrapper | `llm_client.py` | `LLMClient`, token tracking, retry logic |
| SPL formatting | `spl_formatter.py` | SPL block formatting utilities |
| Step 1: Structure extraction | `llm_steps/step1_structure_extraction.py` | Extracts 8 canonical sections from SKILL.md |
| Step 1.5: API generation | `llm_steps/step1_5_api_generation.py` | API specification generation |
| Step 3 orchestration | `llm_steps/step3/orchestrator.py` | Coordinates 3A and 3B |
| Step 3A: Entities | `llm_steps/step3/t.py` | Tool and entity extraction |
| Step 3B: Workflow | `llm_steps/step3/w.py` | Workflow and control flow analysis |
| Step 3 I/O | `llm_steps/step3/io.py` | Input/output handling for step 3 |
| Step 4 orchestration | `llm_steps/step4_spl_emission/orchestrator.py` | Coordinates parallel substeps 4A-F |
| Step 4 assembly | `llm_steps/step4_spl_emission/assembly.py` | SPL block assembly |
| Step 4 inputs | `llm_steps/step4_spl_emission/inputs.py` | Input preparation |
| Step 4 symbol table | `llm_steps/step4_spl_emission/symbol_table.py` | Symbol resolution |
| Step 4 substep calls | `llm_steps/step4_spl_emission/substep_calls.py` | LLM substep invocation |
| Step 4 validation | `llm_steps/step4_spl_emission/nesting_validation.py` | SPL nesting validation |
| Step 4 utilities | `llm_steps/step4_spl_emission/utils.py` | Helper functions |
| P2: File roles | `llm_steps/p2_file_role_resolve.py` | File role classification |
| P3: Summarization | `llm_steps/p3_summarize_file.py` | File content summarization |

---

## CONVENTIONS

- **All LLM calls go through `llm_client.py`** - Never call LLM APIs directly from substeps
- **Steps prefixed with step number** - `step1_`, `step3a_`, `step3b_`, `step4_`, etc.
- **Use templates from `prompts/` directory** - System prompts loaded from sibling `prompts/` folder
- **Checkpoint after every stage** - Results saved to `output/{skill_name}/` as JSON
- **Token tracking** - All LLM calls report usage via `PipelineResult.total_usage`
- **Parallel execution** - Step 4 substeps run in parallel via `ThreadPoolExecutor`
- **SPL block syntax** - All outputs use `[DEFINE_X:]` ... `[END_X]` format with metadata

---

## ANTI-PATTERNS

- **NEVER call LLM APIs directly** - Always use `llm_client.py` wrapper for retries and tracking
- **NEVER skip checkpoint saves** - Every stage must persist results for resume capability
- **NEVER hardcode model names** - Pass via `LLMConfig` from orchestrator
- **NEVER block the event loop** - Use async patterns in `orchestrator_async.py`
- **NO direct file I/O in substeps** - Use orchestrator-provided paths
- **NO print() debugging** - Use `logger.debug()` from `logging.getLogger(__name__)`
- **NEVER modify checkpoint files manually** - Use resume_from config option
- **NO tight coupling to step implementations** - Substeps should be swappable

---

## PIPELINE FLOW

```
Input: Skill Package (SKILL.md + scripts/ + docs/)
    |
    v
[P1] Reference Graph -----> [P2] File Roles -----> [P3] Summarize
    |                           |                       |
    v                           v                       v
[Step 1] Structure Extraction (8 canonical sections)
    |
    v
[Step 3A] Entity Extraction -----> [Step 3B] Workflow Analysis
    |                                       |
    v                                       v
[Step 4A] Variables -----> [Step 4B] Files (parallel)
    |                                       |
    v                                       v
[Step 4C] APIs -------------------------> [Step 4D] Merge
    |                                       |
    v                                       v
[Step 4E] Final Assembly -----> [Step 4F] Examples
    |
    v
Output: SPL Specification (.spl)
```

---

## CHECKPOINT FILES

Each stage saves to `output/{skill_name}/`:

- `step1_structure.json` - Extracted 8 sections
- `step3_entities.json` - Tool and entity definitions
- `step3_workflow.json` - Workflow and control flow
- `step4_spl.json` - Final SPL specification
- `pipeline_result.json` - Complete result with token usage

Resume from any stage via `resume_from='step3'` in `PipelineConfig`.
