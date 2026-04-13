# Simplified Pipeline

A minimal version of the skill-to-CNL-P pipeline with reduced complexity.

## Overview

This simplified pipeline processes skill documentation and generates SPL specifications with fewer steps and simpler outputs.

## Simplifications

### Step 1: Structure Extraction
**Original (8 sections):**
- INTENT, WORKFLOW, CONSTRAINTS, TOOLS, ARTIFACTS, EVIDENCE, EXAMPLES, NOTES

**Simplified (5 sections):**
- INTENT, WORKFLOW, CONSTRAINTS, EXAMPLES, NOTES
- **Removed:** TOOLS, ARTIFACTS, EVIDENCE

### Step 3A: Entity Extraction
**Original:**
- Extracted entities with kinds: Artifact, Run, Evidence, Record
- Routed to DEFINE_VARIABLES or DEFINE_FILES

**Simplified:**
- Only extracts **variables** (no files)
- No `kind` field, simplified to just `var_id`, `type_name`, `schema_notes`
- No `is_file`, `file_path`, `from_omit_files` fields

### Step 3B: Workflow Analysis
**Original action types:**
- EXTERNAL_API, EXEC_SCRIPT, LOCAL_CODE_SNIPPET, LLM_TASK, FILE_READ, FILE_WRITE, USER_INTERACTION
- Included `tool_hint` for matching to pre-extracted tools

**Simplified action types:**
- LLM_TASK (default, most common)
- FILE_READ
- FILE_WRITE
- USER_INTERACTION
- **Removed:** EXTERNAL_API, EXEC_SCRIPT, LOCAL_CODE_SNIPPET
- **Removed:** `tool_hint` field (no pre-extracted tools)
- **Removed:** `effects` and `execution_mode` fields (replaced by `action_type`)

### Step 4: SPL Emission
**Original (6 blocks):**
- 4a: PERSONA / AUDIENCE / CONCEPTS
- 4b: CONSTRAINTS
- 4c: VARIABLES + FILES
- 4d: APIS
- 4e: WORKER
- 4f: EXAMPLES

**Simplified (4 blocks):**
- 4a: PERSONA / AUDIENCE / CONCEPTS
- 4b: CONSTRAINTS
- 4c: VARIABLES only (no FILES block)
- 4e: WORKER (no [CALL ...] commands, no external APIs)
- **Removed:** 4d (APIS) - no external API generation
- **Removed:** DEFINE_FILES from 4c

## Pipeline Flow

```
Input: merged_doc_text (merged document text)
    ↓
Step 1: Extract 5 sections → SectionBundle
    ↓
Step 3A: Extract variables → list[VariableSpec]
    ↓
Step 3B: Analyze workflow → StructuredSpec
    ↓
Step 4: Generate SPL (4 blocks) → SPLSpec
    ↓
Output: SPL text
```

## Usage

The simplified pipeline now accepts `merged_doc_text` directly as input (instead of a skill directory):

```python
from simplified_pipeline.orchestrator import run_simplified_pipeline

# Your merged document text (from pre-processing or manual input)
merged_doc_text = """
## Source: SKILL.md
# My Skill

## Intent
This skill does something useful.

## Workflow
1. Receive input
2. Process with LLM
3. Return result

## Constraints
- MUST validate input

## Examples
Example 1: Basic usage...

## Notes
Additional context here.
"""

result = run_simplified_pipeline(
    merged_doc_text=merged_doc_text,
    skill_id="my_skill",
    output_dir="output/my_skill",
    model="gpt-4o",
    api_key="your-api-key"  # or set OPENAI_API_KEY env var
)

print(result.spl_spec.spl_text)
```

Or use the lower-level API:

```python
from simplified_pipeline.orchestrator import run_pipeline, PipelineConfig
from simplified_pipeline.llm_client import LLMConfig

config = PipelineConfig(
    merged_doc_text=merged_doc_text,  # Direct text input
    skill_id="my_skill",
    output_dir="output/my_skill",
    llm_config=LLMConfig(model="gpt-4o"),
    save_checkpoints=True,
)

result = run_pipeline(config)
## File Structure

```
simplified_pipeline/
├── __init__.py           # Package exports
├── models.py             # Simplified data models
├── prompts.py            # LLM prompts (simplified versions)
├── llm_client.py         # LLM API wrapper
├── steps.py              # Step implementations (1, 3A, 3B, 4)
├── orchestrator.py       # Pipeline coordinator
├── example_usage.py      # Example script
└── README.md            # This file
```

## Key Differences from Full Pipeline

| Aspect | Full Pipeline | Simplified Pipeline |
|--------|--------------|---------------------|
| Pre-processing | P1, P2, P3 (graph, roles, assembly) | None - direct document load |
| Step 1 sections | 8 sections | 5 sections |
| Step 3A entities | 4 kinds (Artifact, Run, Evidence, Record) | Variables only |
| Step 3B actions | 7 types + tool matching | 4 types, no tools |
| Step 4 blocks | 6 blocks (4a-4f) | 4 blocks (4a, 4b, 4c, 4e) |
| API generation | Yes (4d) | No |
| File declarations | Yes (DEFINE_FILES) | No |
| Parallel execution | Yes (ThreadPoolExecutor) | Sequential |
| Checkpoint system | Full JSON checkpoints | Optional basic checkpoints |

## When to Use

Use the simplified pipeline when:
- You need a quick, lightweight SPL generation
- The skill doesn't use external APIs
- File handling is managed externally
- You want to minimize LLM calls and complexity

Use the full pipeline when:
- You need complete API integration (scripts, network APIs)
- File management is part of the skill specification
- You need maximum parallelism and checkpointing
- You need the full 8-section extraction
