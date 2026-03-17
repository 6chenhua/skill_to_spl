# Skill-to-CNL-P Pipeline — Design Document (Actual Implementation)

---

## Overall Architecture

```
skill_root/
    │
    ├── P1 ──────────────────────────────────────────► FileReferenceGraph
    │    (pure code: rglob + frontmatter parsing + reference graph construction)
    │
    ├── P2 ──────────────────────────────────────────► FileRoleMap
    │    (LLM: infer file reading priority based on references)
    │
    ├── P3 ──────────────────────────────────────────► SkillPackage
    │    (pure code: concatenate files by priority + optional LLM summary)
    │
    ├── Step 1 ───────────────────────────────────────► SectionBundle
    │    (LLM: merged_doc_text → 8 canonical sections)
    │
    ├── Step 3A ──────────────────────────────────────► list[EntitySpec]
    │    (LLM: extract entities from ARTIFACTS + WORKFLOW + EXAMPLES)
    │
    ├── Step 3B ──────────────────────────────────────► StructuredSpec
    │    (LLM: extract workflow_steps + alternative_flows + exception_flows)
    │
    └── Step 4 ───────────────────────────────────────► SPLSpec
         (LLM×6: dependency-driven parallel execution)
         │
         ├── S4A: PERSONA / AUDIENCE / CONCEPTS
         ├── S4B: CONSTRAINTS
         ├── S4C: VARIABLES + FILES (→ symbol_table)
         ├── S4D: APIS
         ├── S4E: WORKER (MAIN_FLOW + ALTERNATIVE_FLOW + EXCEPTION_FLOW)
         └── S4F: EXAMPLES
```

**Key Differences from Old Design:**
- Step 2A/2B (clause extraction + scoring) are NOT implemented
- Step 3 is split into Step 3A (entity extraction) and Step 3B (workflow analysis)
- Step 4 has 6 sub-steps instead of 5 (S4F for EXAMPLES added)
- Dependency-driven parallel execution in Step 4

---

## Data Structure Definitions

All stage inputs/outputs are defined in [`models/data_models.py`](models/data_models.py).

```python
# ── P1 Output ───────────────────────────────────────────────────────────────
@dataclass
class FileNode:
    path: str                    # relative to skill root
    kind: str                    # "doc" | "script" | "data" | "asset"
    size_bytes: int
    head_lines: list[str]        # first 20 lines (doc) or head comment (script ≤5 lines)
    references: list[str]        # other filenames mentioned in this file

@dataclass
class FileReferenceGraph:
    skill_id: str
    root_path: str
    skill_md_content: str        # full text of SKILL.md
    frontmatter: dict[str, Any]  # parsed YAML frontmatter
    nodes: dict[str, FileNode]   # rel_path → FileNode
    edges: dict[str, list[str]]  # referencing_file → [referenced_files]
    local_scripts: list[str]     # .py/.sh files in package
    referenced_libs: list[str]  # imported library names

# ── P2 Output ───────────────────────────────────────────────────────────────
@dataclass
class FileRoleEntry:
    role: str                    # from taxonomy
    read_priority: int           # 1=must_read, 2=include_summary, 3=omit
    must_read_for_normalization: bool
    reasoning: str               # one sentence citing specific source text

# FileRoleMap = dict[str, FileRoleEntry]

# ── P3 Output ───────────────────────────────────────────────────────────────
@dataclass
class SkillPackage:
    skill_id: str
    root_path: str
    frontmatter: dict[str, Any]
    merged_doc_text: str         # concatenated content with file boundary markers
    file_role_map: dict[str, Any]  # serializable version

# ── Step 1 Output ───────────────────────────────────────────────────────────
@dataclass
class SectionItem:
    text: str           # verbatim from source
    source: str         # source filename
    multi: bool = False # True if from multiple sections

@dataclass
class SectionBundle:
    intent:      list[SectionItem]
    workflow:    list[SectionItem]
    constraints: list[SectionItem]
    tools:       list[SectionItem]
    artifacts:   list[SectionItem]
    evidence:    list[SectionItem]
    examples:    list[SectionItem]
    notes:       list[SectionItem]

# ── Step 3A Output ─────────────────────────────────────────────────────────
@dataclass
class EntitySpec:
    entity_id: str
    kind: str                   # Artifact | Run | Evidence | Record
    type_name: str
    schema_notes: str
    provenance_required: bool
    provenance: str             # EXPLICIT | ASSUMED | LOW_CONFIDENCE
    source_text: str
    is_file: bool = False       # derived from kind == "Artifact"
    file_path: str = ""         # actual path; "" → "< >" in SPL
    from_omit_files: bool = False

# ── Step 3B Output ─────────────────────────────────────────────────────────
@dataclass
class WorkflowStepSpec:
    step_id: str
    description: str
    prerequisites: list[str]    # entity_ids
    produces: list[str]         # entity_ids
    is_validation_gate: bool
    effects: list[str]          # READ | WRITE | NETWORK | EXEC | REMOTE_RUN
    execution_mode: str         # PROMPT_TO_CODE | CODE | LLM_PROMPT | USER_INPUT
    tool_hint: str
    source_text: str

@dataclass
class FlowStep:
    description: str
    execution_mode: str
    tool_hint: str
    source_text: str

@dataclass
class AlternativeFlowSpec:
    flow_id: str
    condition: str              # free-text predicate
    description: str
    steps: list[FlowStep]
    source_text: str
    provenance: str

@dataclass
class ExceptionFlowSpec:
    flow_id: str
    condition: str
    log_ref: str
    steps: list[FlowStep]
    source_text: str
    provenance: str

@dataclass
class StructuredSpec:
    entities: list[EntitySpec]
    workflow_steps: list[WorkflowStepSpec]
    alternative_flows: list[AlternativeFlowSpec]
    exception_flows: list[ExceptionFlowSpec]

# ── Step 4 Output ──────────────────────────────────────────────────────────
@dataclass
class SPLSpec:
    skill_id: str
    spl_text: str               # complete SPL specification
    review_summary: str         # human review summary
    clause_counts: dict[str, int]  # {"HARD": N, "MEDIUM": N, "SOFT": N, "NON": N}

# ── Pipeline Result ────────────────────────────────────────────────────────
@dataclass
class PipelineResult:
    skill_id: str
    graph: FileReferenceGraph
    file_role_map: dict[str, Any]
    package: SkillPackage
    section_bundle: SectionBundle
    structured_spec: StructuredSpec
    spl_spec: SPLSpec
```

---

## Stage Details

### P1 — Reference Graph Builder (Pure Code)

**File:** [`pre_processing/p1_reference_graph.py`](pre_processing/p1_reference_graph.py)

**Responsibilities:**
- Recursively enumerate all files under skill_root
- Read .md files in full; read script head comments (≤5 lines)
- Regex-scan for filename references
- Parse SKILL.md frontmatter (YAML)
- Build capability profile (local_scripts, referenced_libs)

**Input:**
```
skill_root: Path  (must contain SKILL.md)
```

**Processing Logic:**
```python
def build_reference_graph(skill_root: str) -> FileReferenceGraph:
    # 1. Enumerate files, classify by extension
    # 2. Read content: docs → full, scripts → head comment, others → skip
    # 3. Regex-scan docs for filename references
    # 4. Parse SKILL.md frontmatter
    # 5. Extract local_scripts and referenced_libs
    return FileReferenceGraph(...)
```

**Output:**
`FileReferenceGraph`

**Skip Rules:**
- Directories: `__pycache__`, `node_modules`, `.git`, `.venv`, `venv`
- Files: `.DS_Store`, `LICENSE.txt`, `LICENSE`, `COPYING`, `NOTICE`, `AUTHORS`

---

### P2 — File Role Resolver (LLM)

**File:** [`pipeline/llm_steps/`](pipeline/llm_steps/) (imported via orchestrator)

**Responsibilities:**
- Determine read_priority for each file based on references in SKILL.md
- Assign role taxonomy (core_workflow, core_script, supplementary, unknown)

**Input:**
`FileReferenceGraph` (from P1)

**LLM Prompt:**
```
You are a document analyst. Determine reading priority:
- Priority 1: essential content (MUST consult, see steps in)
- Priority 2: useful but informal references (see also)
- Priority 3: assets, generated files, unreferenced

Output JSON: {path, role, read_priority, must_read_for_normalization, reasoning}
```

**Post-processing:**
- Force SKILL.md → priority=1, role=primary
- Default missing files → priority=3

**Output:**
`FileRoleMap` (dict[path → FileRoleEntry])

---

### P3 — Skill Package Assembler (Pure Code + Optional LLM)

**File:** [`pre_processing/p3_assembler.py`](pre_processing/p3_assembler.py)

**Responsibilities:**
- Concatenate files by priority
- Add boundary markers
- Optional LLM fallback for priority-2 files with empty head_lines

**Input:**
- `FileReferenceGraph` (from P1)
- `FileRoleMap` (from P2)

**Priority Semantics:**
| Priority | Meaning | Content Included |
|----------|---------|------------------|
| 1 | must_read | Full file content |
| 2 | include_summary | head_lines (or LLM summary, or first 20 lines) |
| 3 | omit | Skip entirely |

**Boundary Markers:**
```
=== FILE: {rel_path} | role: {role} | priority: {MUST_READ|SUMMARY} ===
...content...
=== END FILE: {rel_path} ===
```

**LLM Fallback (priority-2 only):**
- If head_lines empty → read up to 4000 chars → call summarize_fn
- If no summarize_fn → use first 20 lines

**Output:**
`SkillPackage`

---

### Step 1 — Structure Extraction (LLM)

**File:** [`pipeline/llm_steps/step1_structure_extraction.py`](pipeline/llm_steps/step1_structure_extraction.py)

**Responsibilities:**
- Parse merged_doc_text into 8 canonical sections
- All text copied verbatim (no rewriting)
- Nothing is dropped

**Input:**
`SkillPackage.merged_doc_text`

**8 Canonical Sections:**
1. **INTENT** — purpose, scope, goals
2. **WORKFLOW** — step-by-step procedures
3. **CONSTRAINTS** — normative requirements (MUST/SHALL/SHOULD)
4. **TOOLS** — tools, libraries, scripts, APIs
5. **ARTIFACTS** — inputs/outputs, file formats, schemas
6. **EVIDENCE** — verification, completion criteria
7. **EXAMPLES** — sample inputs/outputs
8. **NOTES** — background, rationale, caveats

**LLM Output Format:**
```json
{
  "INTENT": [{"text": "...", "source": "file.md", "multi": false}],
  "WORKFLOW": [...],
  ...
}
```

**Output:**
`SectionBundle`

---

### Step 3A — Entity Extraction (LLM)

**File:** [`pipeline/llm_steps/step3_interface_inference.py`](pipeline/llm_steps/step3_interface_inference.py) (run_step3a_entity_extraction)

**Responsibilities:**
- Extract named data entities from ARTIFACTS + WORKFLOW + EXAMPLES
- Determine entity kind (Artifact, Run, Evidence, Record)
- is_file derived from kind (Artifact → True)

**Input:**
- `SectionBundle.to_text(["ARTIFACTS"])`
- `SectionBundle.to_text(["WORKFLOW"])`
- `SectionBundle.to_text(["EXAMPLES"])`

**Output:**
`list[EntitySpec]`

---

### Step 3B — Workflow Analysis (LLM)

**File:** [`pipeline/llm_steps/step3_interface_inference.py`](pipeline/llm_steps/step3_interface_inference.py) (run_step3b_workflow_analysis)

**Responsibilities:**
- Extract workflow steps with execution_mode
- Extract alternative_flows and exception_flows
- Use entity_ids from Step 3A as constraints

**Input:**
- `entity_ids_json` — from Step 3A
- `SectionBundle.to_text(["WORKFLOW"])`
- `SectionBundle.to_text(["TOOLS"])`
- `SectionBundle.to_text(["EVIDENCE"])`

**Output:**
`StructuredSpec` (with entities=[] — filled by caller)

**Key Changes from Old Design:**
- NO classified_clauses consumption
- NO separate InteractionRequirement — USER_INPUT steps handled in workflow
- Alternative/exception flows driven by explicit documentation, not MEDIUM clauses

---

### Step 4 — SPL Emission (LLM×6 with Dependency-Driven Parallelism)

**File:** [`pipeline/llm_steps/step4_spl_emission.py`](pipeline/llm_steps/step4_spl_emission.py)

**Responsibilities:**
- Generate SPL blocks from structured spec
- Maximize parallelism via dependency graph

**Dependency Graph:**
```
Step 3A (entities) ──┬─→ S4C ──→ symbol_table ──┬─→ S4A (persona)
                     │                          ├─→ S4B (constraints)
                     │                          └─→ S4E ←──┬── apis_spl (from S4D)
                     │                                     │
                     └─→ Step 3B ──→ workflow/flows ────────┘
                                                        │
                                                        ↓
                                                       S4F
```

**Parallel Execution Phases:**

**Phase 1:** S4C + S4D launch in parallel (independent)
- S4C: needs entities
- S4D: needs workflow_steps with NETWORK effects

**Phase 2:** When S4C completes → extract symbol_table → launch S4A + S4B
- S4A: needs symbol_table + INTENT/NOTES
- S4B: needs symbol_table + CONSTRAINTS
- S4A/S4B do NOT wait for S4D

**Phase 3:** When S4D completes → launch S4E
- S4E: needs symbol_table + apis_spl + workflow/flows

**Phase 4:** When S4E completes → launch S4F (if examples exist)
- S4F: needs worker_spl + EXAMPLES

**S4A — PERSONA/AUDIENCE/CONCEPTS:**
- Input: INTENT + NOTES sections
- Output: SPL PERSONA block with ROLE, DOMAIN, EXPERTISE, AUDIENCE, CONCEPTS

**S4B — CONSTRAINTS:**
- Input: CONSTRAINTS section + symbol_table
- Output: SPL DEFINE_CONSTRAINTS block

**S4C — VARIABLES/FILES:**
- Input: EntitySpec list
- Output: SPL DEFINE_VARIABLES + DEFINE_FILES blocks
- Extracts symbol_table for subsequent steps

**S4D — APIS:**
- Input: workflow_steps with NETWORK effects
- Output: SPL DEFINE_APIS block

**S4E — WORKER:**
- Input: workflow_steps + alternative_flows + exception_flows + symbol_table + apis_spl
- Output: SPL WORKER block with MAIN_FLOW, ALTERNATIVE_FLOW, EXCEPTION_FLOW

**S4F — EXAMPLES:**
- Input: worker_spl (from S4E) + EXAMPLES section
- Output: SPL [EXAMPLES] block (inserted before [END_WORKER])

**Output:**
`SPLSpec`

---

## Data Flow Checklist

| Stage | Required Input | Source |
|-------|---------------|--------|
| P1 | `skill_root: Path` (with SKILL.md) | Caller |
| P2 | `FileReferenceGraph` | P1 |
| P3 | `FileReferenceGraph` + `FileRoleMap` | P1 + P2 |
| Step 1 | `SkillPackage.merged_doc_text` | P3 |
| Step 3A | `SectionBundle` | Step 1 |
| Step 3B | `SectionBundle` + entity_ids | Step 1 + Step 3A |
| Step 4 | `SectionBundle` + `StructuredSpec` | Step 1 + Step 3 |

---

## Error Handling Conventions

| Error Type | Handling |
|------------|----------|
| SKILL.md missing | P1 raises `FileNotFoundError`, terminate |
| P2 LLM output invalid JSON | Default all non-SKILL.md files to priority=2 |
| Step 1 section empty | Allowed — empty text string |
| Step 3A no entities | Allowed — empty list, S4C returns "" |
| Step 4 any sub-step fails | Mark block as `"""EMISSION_FAILED: <reason>"""`, continue |

---

## Quick Reference: SPL Block Source Chains

```
DEFINE_PERSONA
  ← Step 1[INTENT] + Step 1[NOTES] → S4A

DEFINE_AUDIENCE
  ← Step 1[INTENT] (explicit user groups) → S4A

DEFINE_CONCEPTS
  ← Step 1[NOTES] (term definitions) → S4A

DEFINE_CONSTRAINTS
  ← Step 1[CONSTRAINTS] → S4B

DEFINE_VARIABLES
  ← Step 3A[entities where kind != Artifact] → S4C

DEFINE_FILES
  ← Step 3A[entities where kind == Artifact] → S4C

DEFINE_APIS
  ← Step 3B[workflow_steps where NETWORK in effects] → S4D

WORKER.MAIN_FLOW
  ← Step 3B[workflow_steps] → S4E

WORKER.ALTERNATIVE_FLOW
  ← Step 3B[alternative_flows] → S4E

WORKER.EXCEPTION_FLOW
  ← Step 3B[exception_flows] → S4E

[EXAMPLES]
  ← Step 1[EXAMPLES] → S4F → inserted in WORKER
```

---

## File Organization

```
skill_to_cnlp/
├── main.py                           # Entry point
├── cli.py                            # CLI interface
├── models/
│   └── data_models.py               # All dataclasses
├── pipeline/
│   ├── orchestrator.py              # Pipeline orchestration
│   ├── llm_client.py                # LLM client wrapper
│   └── llm_steps/
│       ├── step1_structure_extraction.py
│       ├── step3_interface_inference.py
│       │   ├── run_step3a_entity_extraction()
│       │   └── run_step3b_workflow_analysis()
│       └── step4_spl_emission.py
│           ├── run_step4_spl_emission()
│           ├── run_step4_spl_emission_parallel()
│           └── _call_4a/b/c/d/e/f()
├── pre_processing/
│   ├── p1_reference_graph.py       # P1: build reference graph
│   └── p3_assembler.py              # P3: assemble skill package
└── prompts/
    ├── templates.py                 # Prompt templates
    ├── p2_system.py                 # P2 system prompt
    ├── step1_system.py              # Step 1 system prompt
    ├── step3_system.py              # Step 3 system prompts (S3A, S3B)
    └── step4_system.py              # Step 4 system prompts (S4A-F)
```

---

## Notes

1. **No Step 2A/2B:** The clause extraction and scoring stages from the old design are not implemented. Constraints flow directly from Step 1 to Step 4.

2. **Step 3 Split:** Step 3 is split into 3A (entities) and 3B (workflow) to enable parallel execution with Step 4.

3. **Dependency-Driven Parallelism:** Step 4 uses ThreadPoolExecutor with dependency tracking to maximize parallel LLM calls.

4. **No DEFINE_GUARDRAIL:** The SPL grammar has no GUARDRAIL_INSTRUCTION. Validation gates become EXCEPTION_FLOW instead.

5. **No InteractionRequirement:** USER_INPUT steps are handled directly in workflow_steps with execution_mode="USER_INPUT".