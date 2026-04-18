# skill-to-cnlp

> Normalize heterogeneous Claude skill packages into SPL/CNL-P specifications

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Proprietary-purple.svg)](LICENSE.txt)

## Overview

**skill-to-cnlp** is a pipeline system that transforms heterogeneous skill packages into standardized **SPL (Skill Processing Language)** specifications, also known as **CNL-P (Controlled Natural Language for Prompts)**.

The pipeline leverages LLM-powered analysis to extract structured information from skill documentation and produces machine-readable, compilable SPL output that can be used by AI systems.

## What is SPL?

**SPL (Skill Processing Language)** is a structured specification language for defining AI skills with:

- **PERSONA** — Role, domain, expertise level
- **AUDIENCE** — Target users
- **CONCEPTS** — Domain-specific terminology
- **CONSTRAINTS** — Hard/Medium/Soft constraints with enforcement
- **VARIABLES** — Data types and parameters
- **FILES** — File artifacts
- **APIS** — External API definitions
- **Validation Gates** — Steps that check evidence requirements drive EXCEPTION_FLOW directly
- **WORKER_INSTRUCTION** — Workflow logic (MAIN_FLOW, ALTERNATIVE_FLOW, EXCEPTION_FLOW)

See [skills/skill-to-cnlp/references/REFERENCE.md](skills/skill-to-cnlp/references/REFERENCE.md) for the complete SPL grammar.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           skill-to-cnlp Pipeline                            │
└─────────────────────────────────────────────────────────────────────────────┘

    Skill Package                    Pipeline Stages                         Output
    ─────────────                    ───────────────                         ──────
    
    ┌─────────────┐
    │  SKILL.md   │    P1: Reference Graph     (code)     ──────────────► FileReferenceGraph
    │  *.py       │    P2: File Role Resolver  (LLM)      ──────────────► FileRoleMap
    │  *.js       │    P3: Skill Package        (code)    ──────────────► SkillPackage
    │  docs/      │    Step 1: Structure        (LLM)     ──────────────► SectionBundle
    │  scripts/   │    Step 3A: Entities        (LLM)     ──────────────► Entities
    └─────────────┘    Step 3B: Workflow        (LLM)     ──────────────► WorkflowSteps
                       Step 4: SPL Emission     (LLM)     ──────────────► SPL Spec
                             
                              Parallel Execution
                              ──────────────────
                              Line 1: 3B → S4D (APIs)
                              Line 2: S4C → S4A + S4B (Variables/Files)
                              Then:   S4E (merge) → S4F (examples)
```

## Pipeline Stages

| Stage | Type | Description |
|-------|------|-------------|
| **P1** | Code | Build reference graph from skill files |
| **P2** | LLM | Resolve file roles (documentation, code, templates) |
| **P3** | Code+LLM | Assemble skill package with merged documentation |
| **Step 1** | LLM | Extract canonical sections (INTENT, WORKFLOW, etc.) |
| **Step 3A** | LLM | Extract entities (data types, file artifacts) |
| **Step 3B** | LLM | Analyze workflow steps and capabilities |
| **Step 4** | LLM | Emit final SPL specification |

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd skill-to-cnlp

# Install dependencies
pip install -e .
```

## Requirements

- Python 3.11+
- Anthropic SDK (`anthropic>=0.40.0`)
- PyYAML (`pyyaml>=6.0`)
- Hypothesis (`hypothesis>=6.0.0`)

## Quick Start

### Running the Pipeline

```python
from pipeline.orchestrator import run_pipeline, PipelineConfig
from pipeline.llm_client import LLMConfig

# Configure the LLM
llm_config = LLMConfig(
    model='gpt-4o',
    max_tokens=16000,
)

# Configure the pipeline
config = PipelineConfig(
    skill_root='skills/pdf',
    output_dir='output/pdf',
    llm_config=llm_config,
    save_checkpoints=True,
)

# Run the pipeline
result = run_pipeline(config)

# Access the SPL output
print(result.spl_spec.spl_text)
```

### Using the CLI

```bash
skill-to-cnlp --skill pdf --output output/pdf --model gpt-4o
```

## Project Structure

```
skill-to-cnlp/
├── main.py                  # Example entry point
├── cli.py                   # Command-line interface
├── cli_async.py            # Async CLI variant
├── pyproject.toml          # Project configuration
├── AGENTS.md               # Project knowledge base
│
├── pipeline/               # Core pipeline logic (refactored)
│   ├── orchestrator.py     # Backward-compatible API entry
│   ├── orchestrator_async.py  # Async orchestrator
│   ├── llm_client.py       # LLM API wrapper with retry logic
│   ├── spl_formatter.py    # SPL formatting utilities
│   ├── orchestrator/       # NEW: Modular orchestrator components
│   │   ├── __init__.py
│   │   ├── base.py         # PipelineStep protocol
│   │   ├── builder.py      # PipelineBuilder
│   │   ├── config.py       # PipelineConfig
│   │   ├── context.py      # ExecutionContext
│   │   └── runners/        # Step runners
│   │       ├── sequential.py
│   │       └── parallel.py
│   └── llm_steps/          # Step implementations
│       ├── p2_file_role_resolve.py
│       ├── p3_summarize_file.py
│       ├── step1_structure_extraction.py
│       ├── step1_5_api_generation.py
│       ├── step3/          # Step 3: Workflow analysis
│       │   ├── __init__.py
│       │   ├── orchestrator.py
│       │   ├── t.py        # Entity extraction
│       │   └── w.py        # Workflow analysis
│       └── step4_spl_emission/  # Step 4: Parallel SPL emission
│           ├── __init__.py
│           ├── assembly.py
│           ├── orchestrator.py
│           └── substep_calls.py
│
├── pre_processing/         # Code-based preprocessing
│   ├── p1_reference_graph.py
│   ├── p2_file_role_resolver.py
│   └── p3_assembler.py
│
├── models/                 # Data models (refactored)
│   ├── __init__.py         # Backward-compatible exports
│   ├── data_models.py      # Legacy (deprecated)
│   └── pipeline/           # NEW: Pipeline-specific models
│       └── pipeline_result.py
│
├── prompts/                # LLM system prompts
│   ├── step1_system.py
│   ├── step3_system.py
│   └── step4_*.py
│
├── skills/                 # Example skill packages (20 skills)
│   ├── pdf/                # PDF processing
│   ├── docx/               # Word document processing
│   ├── pptx/               # PowerPoint manipulation
│   ├── xlsx/               # Excel operations
│   ├── skill-to-cnlp/      # The SPL emitter skill itself
│   └── ...                 # 15 other skills
│
└── test/                   # Test suite (expanded)
    ├── conftest.py         # Shared pytest fixtures
    ├── e2e/                # NEW: End-to-end tests
    │   ├── conftest.py
    │   ├── test_core_skills.py
    │   ├── test_extended_skills.py
    │   └── test_resume_functionality.py
    ├── performance/        # NEW: Performance tests
    │   ├── conftest.py
    │   ├── test_performance_core.py
    │   └── baseline.json
    ├── regression/         # NEW: Regression tests
    │   └── test_regression.py
    └── test_*.py           # Unit tests
```
skill-to-cnlp/
├── main.py                 # Example entry point
├── cli.py                  # Command-line interface
├── pyproject.toml          # Project configuration
│
├── pipeline/               # Core pipeline logic
│   ├── orchestrator.py    # Pipeline execution coordinator
│   ├── llm_client.py      # LLM API wrapper
│   └── llm_steps/         # Step 1-4 implementations
│       ├── step1_structure_extraction.py
│       ├── step3a_entity_extraction.py
│       ├── step3b_workflow_analysis.py
│       └── step4_spl_emission.py
│
├── pre_processing/         # Code-based preprocessing
│   ├── p1_reference_graph.py
│   └── p3_assembler.py
│
├── models/                 # Data models
│   └── data_models.py
│
├── prompts/               # LLM system prompts
│   ├── step1_system.py
│   ├── step3_system.py
│   └── step4_*.py
│
├── skills/                 # Example skill packages
│   ├── pdf/               # PDF processing skill
│   ├── brand-guidelines/  # Brand guidelines skill
│   ├── skill-to-cnlp/    # The SPL emitter skill itself
│   └── ...               # Other skills
│
└── test/                  # Test suite
    └── test_*.py
```

## Example Skills

The `skills/` directory contains example skill packages:

| Skill | Description |
|-------|-------------|
| [pdf](skills/pdf/) | PDF manipulation (extract, merge, split, forms) |
| [brand-guidelines](skills/brand-guidelines/) | Brand identity guidelines |
| [canvas-design](skills/canvas-design/) | HTML5 Canvas design |
| [docx](skills/docx/) | Word document processing |
| [pptx](skills/pptx/) | PowerPoint manipulation |
| [xlsx](skills/xlsx/) | Excel spreadsheet operations |
| [theme-factory](skills/theme-factory/) | Color theme generation |

## Checkpoint System

The pipeline saves intermediate results to enable reruns from any stage:

```
output/
└── pdf/
    ├── p1_graph.json
    ├── p2_file_role_map.json
    ├── p3_package.json
    ├── step1_bundle.json
    ├── step3_structured_spec.json
    └── pdf.spl              # Final output
```

Resume from a specific stage:
```python
config = PipelineConfig(
    skill_root='skills/pdf',
    resume_from='step3',  # Resume from Step 3
    ...
)
```

## Output Format

The pipeline produces SPL files like:

```spl
[DEFINE_PERSONA:]
ROLE: Comprehensive PDF manipulation toolkit for extracting text and tables
DOMAIN: PDF Processing
"""SOURCE_REF: SKILL.md:1"""
"""CONFIDENCE: 1.0"""
"""NEEDS_REVIEW: false"""
[END_PERSONA]

[DEFINE_CONSTRAINTS:]
Security: [SOFT: guidance only] Do not process sensitive documents without encryption
"""SOURCE_REF: SKILL.md:50"""
"""CONFIDENCE: 0.8"""
"""NEEDS_REVIEW: false"""
[END_CONSTRAINTS]

[DEFINE_WORKER: "PDF processing worker" pdf_worker]
[INPUTS]
REQUIRED <REF>input_file</REF>
OPTIONAL <REF>password</REF>
[END_INPUTS]
[OUTPUTS]
REQUIRED <REF>output_file</REF>
[END_OUTPUTS]
[MAIN_FLOW]
[SEQUENTIAL_BLOCK]
COMMAND-1 [CODE Open PDF file RESULT pdf_doc: document]
COMMAND-2 [CODE Extract text from pages RESULT text: text]
[END_SEQUENTIAL_BLOCK]
[END_MAIN_FLOW]
[END_WORKER]
```

## Development

### Running Tests

```bash
pytest test/
```

### Adding a New Skill

1. Create a new directory under `skills/`
2. Add `SKILL.md` with the skill documentation
3. Add supporting files (scripts, templates, examples)
4. Run the pipeline on your new skill

## License

Proprietary. See [LICENSE.txt](LICENSE.txt) for details.

## Related Documentation

- [SPL Grammar Reference](skills/skill-to-cnlp/references/REFERENCE.md)
- [SPL Emitter Skill](skills/skill-to-cnlp/SKILL.md)
- [Pipeline Design](design_docs/) (if available)