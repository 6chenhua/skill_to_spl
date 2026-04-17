# PROJECT KNOWLEDGE BASE: skill-to-cnlp

**Language**: Python 3.11+  
**Purpose**: Normalize heterogeneous Claude skill packages into SPL/CNL-P specifications  
**Architecture**: Multi-stage LLM-powered pipeline with preprocessing, extraction, and emission phases

---

## OVERVIEW

Transforms skill packages (SKILL.md + scripts + docs) into structured SPL (Skill Processing Language) specifications. Pipeline stages: P1→P2→P3 (preprocessing) → Step 1→3A→3B→4 (LLM extraction).

---

## STRUCTURE

```
skill-to-cnlp/
├── cli.py                      # CLI entry point
├── main.py                     # Programmatic API entry
├── pyproject.toml              # Package config, entry point: skill-to-cnlp
├── pipeline/                   # Core pipeline orchestration + LLM steps
├── simplified_pipeline/        # Streamlined variant with clarification system
├── skills/                     # Example skill packages (pdf, docx, pptx, etc.)
├── pre_processing/             # P1-P3: reference graph, file roles, assembler
├── models/                     # Dataclasses: FileNode, ToolSpec, SectionBundle
├── prompts/                    # LLM system prompts (step1, step3, step4)
├── test/                       # Test suite (pytest)
└── design_docs/                # Architecture documentation
```

---

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Pipeline orchestration | `pipeline/orchestrator.py` | `run_pipeline()`, `PipelineConfig` |
| LLM client wrapper | `pipeline/llm_client.py` | `LLMClient`, token tracking |
| Step 1: Structure extraction | `pipeline/llm_steps/step1_structure_extraction.py` | 8 canonical sections |
| Step 3: Workflow analysis | `pipeline/llm_steps/step3/` | 3A entities, 3B workflow |
| Step 4: SPL emission | `pipeline/llm_steps/step4_spl_emission/` | Parallel substeps 4A-F |
| Data models | `models/data_models.py` | All dataclasses |
| Preprocessing | `pre_processing/p{1,3}_*.py` | Reference graph, assembler |
| Example skills | `skills/{pdf,docx,pptx,xlsx}/` | Reference implementations |

---

## CONVENTIONS

- **Type hints**: Required on all public functions
- **Dataclasses**: Pure data containers in `models/` — no business logic
- **Pipeline stages**: Prefix with step number (`step1_`, `step3a_`, etc.)
- **File naming**: `snake_case.py`, descriptive (e.g., `step1_structure_extraction.py`)
- **Logging**: `logger = logging.getLogger(__name__)` pattern
- **Docstrings**: Google-style with Args/Returns sections

---

## ANTI-PATTERNS

- **NEVER** mix business logic in dataclasses (keep `models/` pure)
- **NEVER** call LLM client directly from substeps — use `llm_client.py` wrapper
- **AVOID** hardcoding model names — pass via `LLMConfig`
- **NO** `print()` for debugging — use `logger.debug()`

---

## UNIQUE PATTERNS

### Pipeline Checkpoint System
Intermediate results saved to `output/{skill_name}/` as JSON checkpoints. Resume from any stage via `resume_from='step3'` in config.

### Parallel Step 4 Execution
S4A (variables) + S4B (files) run in parallel via `ThreadPoolExecutor`. S4C→S4D for APIs, then S4E merge → S4F examples.

### SPL Block Structure
All LLM outputs use SPL block syntax with metadata:
```
[DEFINE_PERSONA:]
ROLE: ...
"""SOURCE_REF: SKILL.md:1"""
"""CONFIDENCE: 0.95"""
[END_PERSONA]
```

### Skill Package Anatomy
- `SKILL.md` — canonical documentation with YAML frontmatter
- `scripts/` — implementation files
- `docs/` — supplementary documentation
- `examples/` — usage examples

---

## COMMANDS

```bash
# Install
pip install -e .

# Run CLI
skill-to-cnlp --skill pdf --output output/pdf --model gpt-4o

# Run tests
pytest test/

# Run single skill via main.py
python main.py --skill skills/pdf --output output/pdf
```

---

## NOTES

- **LLM calls are expensive** — pipeline saves checkpoints after every stage
- **Token usage tracked** — check `PipelineResult.total_usage`
- **SPL grammar** — see `skills/skill-to-cnlp/references/REFERENCE.md`
- **Large files** — `skills/docx/scripts/document.py` (1038 lines), `prompts/step3_system.py` (944 lines)
