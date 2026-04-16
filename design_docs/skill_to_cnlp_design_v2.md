# Skill-to-CNL-P Pipeline — Design Document V2 (Current Implementation)

---

## Overall Architecture

```
skill_root/
│
├── P1 ──────────────────────────────────────────► FileReferenceGraph
│   (pure code: rglob + frontmatter parsing + reference graph construction)
│
├── P2 ──────────────────────────────────────────► FileRoleMap
│   (rule-based: infer file reading priority from references)
│
├── P3 ──────────────────────────────────────────► SkillPackage
│   (pure code: concatenate files by priority + P2.5 API analysis)
│
├── Step 1 ───────────────────────────────────────► SectionBundle
│   (LLM: merged_doc_text → 8 canonical sections + network APIs)
│
├── Step 1.5 ─────────────────────────────────────► APISymbolTable
│   (LLM: generate API definitions for all tools)
│
├── Step 3 (NEW W→IO→T) ──────────────────────────► Step3FullResult
│   (LLM: unified workflow, I/O, and type analysis)
│   │
│   ├── Step 3-W ─────────────────────────────────► list[WorkflowStepRaw]
│   │   (LLM: extract workflow steps + flows)
│   │
│   ├── Step 3-IO ────────────────────────────────► Step3IOOutput
│   │   (LLM: analyze global I/O + build VarRegistry)
│   │
│   └── Step 3-T ─────────────────────────────────► Step3TOutput
│       (code: generate TYPES from registry)
│
└── Step 4 ───────────────────────────────────────► SPLSpec
    (LLM×6: dependency-driven parallel execution)
    │
    ├── S0:  DEFINE_AGENT header
    ├── S4A: PERSONA / AUDIENCE / CONCEPTS
    ├── S4B: CONSTRAINTS
    ├── S4C: VARIABLES + FILES (from Step 3 registry)
    ├── S4D: APIS (from Step 1.5)
    ├── S4E: WORKER (MAIN_FLOW + ALTERNATIVE_FLOW + EXCEPTION_FLOW)
    └── S4F: EXAMPLES
```

**Key Changes from V1:**

1. **Step 1.5 Added**: API generation moved earlier (after Step 1) for parallel execution
2. **Step 3 Completely Refactored**: Old 3A/3B split replaced with unified W→IO→T architecture
3. **New Type System**: Full TypeExpr support (simple, enum, array, struct) with GlobalVarRegistry
4. **TYPES Block**: Automatic `[DEFINE_TYPES:]` generation from complex types in registry
5. **Better Parallelism**: Step 3 outputs feed directly into Step 4 with proper dependency tracking
6. **S4C Integration**: Variables/files now generated from Step 3 registry via `s4c_from_registry.py`

---

## Data Structure Definitions

All stage inputs/outputs are defined in [`models/data_models.py`](models/data_models.py) and [`models/step3_types.py`](models/step3_types.py).

### P1-P3 (Unchanged from V1)

```python
# FileReferenceGraph, FileRoleMap, SkillPackage - unchanged
```

### Step 1 Output (Extended)

```python
@dataclass
class SectionBundle:
    intent: list[SectionItem]
    workflow: list[SectionItem]
    constraints: list[SectionItem]
    tools: list[SectionItem]
    artifacts: list[SectionItem]
    evidence: list[SectionItem]
    examples: list[SectionItem]
    notes: list[SectionItem]

# NEW: Also returns list[ToolInfo] for network APIs extracted during Step 1
```

### Step 1.5 Output (NEW)

```python
@dataclass
class APIInfo:
    name: str
    api_type: str  # "script" | "code" | "network"
    description: str
    authentication: Optional[str]
    functions: list[dict]

@dataclass
class APISymbolTable:
    apis: dict[str, APIInfo]  # name → APIInfo
```

### Step 3 New Architecture (W→IO→T)

#### Step 3-W Output

```python
@dataclass
class WorkflowStepRaw:
    step_id: str
    description: str
    action_type: str  # "LLM_TASK" | "USER_INPUT" | "CODE" | "API_CALL" | ...
    tool_hint: str
    is_validation_gate: bool
    source_text: str

@dataclass
class Step3WOutput:
    workflow_steps: list[WorkflowStepRaw]
    alternative_flows: list[AlternativeFlowSpec]
    exception_flows: list[ExceptionFlowSpec]
```

#### Step 3-IO Output

```python
@dataclass(frozen=True)
class TypeExpr:
    kind: str  # "simple" | "enum" | "array" | "struct"
    type_name: str  # For simple types: "text" | "image" | "audio" | "number" | "boolean"
    values: tuple[str, ...]  # For enum types
    element_type: TypeExpr | None  # For array types
    fields: dict[str, TypeExpr]  # For struct types

@dataclass
class VarSpec:
    var_name: str
    type_expr: TypeExpr
    is_file: bool
    description: str
    source_step: str

@dataclass
class StepIOSpec:
    step_id: str
    prerequisites: dict[str, VarSpec]  # Typed I/O (was: list[str])
    produces: dict[str, VarSpec]       # Typed I/O (was: list[str])

@dataclass
class GlobalVarRegistry:
    variables: dict[str, VarSpec]  # Non-file variables
    files: dict[str, VarSpec]      # File artifacts

@dataclass
class Step3IOOutput:
    step_io_specs: dict[str, StepIOSpec]
    global_registry: GlobalVarRegistry
```

#### Step 3-T Output

```python
@dataclass
class TypeDecl:
    declared_name: str
    type_expr: TypeExpr
    description: str

@dataclass
class Step3TOutput:
    types_spl: str  # Complete [DEFINE_TYPES:] block
    type_registry: dict[str, str]  # signature → declared_name
    declared_names: set[str]
```

#### Step 3 Full Output

```python
@dataclass
class Step3FullResult:
    workflow_steps: list[WorkflowStepRaw]
    alternative_flows: list[AlternativeFlowSpec]
    exception_flows: list[ExceptionFlowSpec]
    step_io_specs: dict[str, StepIOSpec]
    global_registry: GlobalVarRegistry
    types_spl: str
    type_registry: dict[str, str]
```

### Step 4 Output (Extended)

```python
@dataclass
class SPLSpec:
    skill_id: str
    spl_text: str
    review_summary: str
    clause_counts: dict[str, int]
    # NEW: Also includes type information
    types_count: int = 0
```

---

## Stage Details

### Step 1.5 — API Definition Generation (NEW)

**File:** [`pipeline/llm_steps/step1_5_api_generation.py`](pipeline/llm_steps/step1_5_api_generation.py)

**Responsibilities:**
- Generate API definitions for all tools extracted in P3 and Step 1
- Moved from Step 4D to enable earlier availability
- Runs in parallel for all tools

**Input:**
- `package.tools`: List of ToolInfo from P2.5 + Step 1

**Output:**
- `APISymbolTable`: Dictionary of tool name → APIInfo

**Key Functions:**
```python
async def generate_api_definitions(tools, client) -> APISymbolTable
```

---

### Step 3 — New Architecture (W→IO→T)

**Package:** [`pipeline/llm_steps/step3/`](pipeline/llm_steps/step3/)

The new Step 3 replaces the old 3A/3B split with a unified three-phase architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                     Step 3 Full                             │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   Step 3-W    │───►│  Step 3-IO    │───►│   Step 3-T    │
│               │    │               │    │               │
│ Workflow      │    │ Global I/O    │    │ Type          │
│ Structure     │    │ + Type        │    │ Declarations  │
│ Analysis      │    │ Analysis      │    │ (code)        │
│               │    │               │    │               │
│ Output:       │    │ Output:       │    │ Output:       │
│ - workflow_   │    │ - step_io_    │    │ - types_spl   │
│   steps       │    │   specs       │    │ - type_       │
│ - flows       │    │ - global_     │    │   registry    │
│               │    │   registry    │    │               │
└───────────────┘    └───────────────┘    └───────────────┘
```

#### Step 3-W: Workflow Structure Analysis

**File:** [`pipeline/llm_steps/step3/w.py`](pipeline/llm_steps/step3/w.py)

**Responsibilities:**
- Parse WORKFLOW section into structured steps
- Extract step_id, description, action_type, tool_hint
- Identify validation gates and flow branches
- Extract alternative_flows and exception_flows

**Input:**
- `workflow_section`: Text from SectionBundle.WORKFLOW
- `tools_section`: Text from SectionBundle.TOOLS
- `evidence_section`: Text from SectionBundle.EVIDENCE
- `available_tools`: List of {name, api_type} from package.tools

**LLM Output Format:**
```json
{
  "workflow_steps": [
    {
      "step_id": "step_1",
      "description": "Open the PDF file",
      "action_type": "CODE",
      "tool_hint": "PyPDF2",
      "is_validation_gate": false,
      "source_text": "..."
    }
  ],
  "alternative_flows": [...],
  "exception_flows": [...]
}
```

**Output:** `Step3WOutput`

---

#### Step 3-IO: Global I/O + Type Analysis

**File:** [`pipeline/llm_steps/step3/io.py`](pipeline/llm_steps/step3/io.py)

**Responsibilities:**
- Analyze each step's inputs (prerequisites) and outputs (produces)
- Infer TypeExpr for each variable (simple/enum/array/struct)
- Build GlobalVarRegistry with deduplication
- Handle type conflicts across steps

**Key Innovation:**
- **Typed I/O**: prerequisites/produces are `dict[str, VarSpec]` not just entity_id strings
- **Global Registry**: Single source of truth for all variables across all steps
- **Type Consistency**: All steps analyzed together → guaranteed type consistency

**Input:**
- `workflow_steps`: From Step 3-W
- `workflow_text`: Full workflow section
- `artifacts_text`: Full artifacts section

**LLM Output Format:**
```json
{
  "step_io_specs": {
    "step_1": {
      "step_id": "step_1",
      "prerequisites": {
        "input_pdf": {
          "var_name": "input_pdf",
          "type_expr": "text",
          "is_file": true,
          "description": "Input PDF file path"
        }
      },
      "produces": {
        "pdf_doc": {
          "var_name": "pdf_doc",
          "type_expr": {"pages": "number", "text": "text"},
          "is_file": false,
          "description": "PDF document object"
        }
      }
    }
  }
}
```

**Output:** `Step3IOOutput`

---

#### Step 3-T: TYPES Declaration

**File:** [`pipeline/llm_steps/step3/t.py`](pipeline/llm_steps/step3/t.py)

**Responsibilities:**
- Extract complex types from GlobalVarRegistry
- Generate TypeDecl for each unique complex type
- Build [DEFINE_TYPES:] block
- Maintain type_registry for name resolution

**Type Categories:**
- **Simple**: text, number, boolean, image, audio
- **Enum**: `["value1", "value2", ...]`
- **Array**: `List[element_type]`
- **Struct**: `{field1: type1, field2: type2, ...}`

**Input:**
- `registry`: GlobalVarRegistry from Step 3-IO

**Processing:**
```python
# 1. Collect all complex types from registry
complex_types = registry.get_all_complex_types()

# 2. Generate TypeDecl for each (pure code, no LLM)
type_decls = []
for type_expr in complex_types:
    if type_expr not in seen:
        name = generate_name(type_expr)
        type_decls.append(TypeDecl(name, type_expr))

# 3. Build SPL block
types_spl = build_types_spl(type_decls)
```

**Output:** `Step3TOutput`

**Example Output:**
```spl
[DEFINE_TYPES:]
TextList = List[text]

PageInfo = {
  page_number: number
  text: text
  has_images: boolean
}

Status = ["pending", "processing", "complete", "error"]
[END_TYPES]
```

---

#### Step 3 Combined Orchestrator

**File:** [`pipeline/llm_steps/step3/orchestrator.py`](pipeline/llm_steps/step3/orchestrator.py)

**Public API:**
```python
from pipeline.llm_steps.step3 import run_step3_full

result = await run_step3_full(
    workflow_section="...",
    tools_section="...",
    evidence_section="...",
    artifacts_section="...",
    available_tools=[...],
    client=client,
    model="gpt-4o-mini"
)

# Returns dict with:
# - workflow_steps: list[WorkflowStepRaw]
# - step_io_specs: dict[str, StepIOSpec]
# - global_registry: GlobalVarRegistry
# - types_spl: str
# - type_registry: dict[str, str]
```

---

### Step 4 — SPL Emission (Updated)

**File:** [`pipeline/llm_steps/step4_spl_emission/`](pipeline/llm_steps/step4_spl_emission/)

**Key Changes:**

1. **S4C Updated**: Now generates VARIABLES/FILES from Step 3 registry via `s4c_from_registry.py`
2. **S4D Updated**: Consumes pre-generated API table from Step 1.5
3. **TYPES Support**: S4A/S4B/S4E now receive types_spl for reference resolution

#### Updated Dependency Graph

```
Step 1.5 ──────────────────────────────────────┐
(apis)                                           │
    │                                            │
    │                                            ▼
Step 3 (W→IO→T) ──┬─→ TYPES + Global Registry ─┬─→ S4A (persona)
    │             │                              ├─→ S4B (constraints)
    │             │                              │
    │             ├─→ S4C (variables/files) ──────┘
    │             │       ↓
    │             │   symbol_table
    │             │
    └─→ workflow/flows ───────────→ S4E ←──┬── apis_spl (from S4D)
                                         │
                                         ▼
                                        S4F (examples)
```

#### New S4C: Variables/Files from Registry

**File:** [`pipeline/llm_steps/step4_spl_emission/s4c_from_registry.py`](pipeline/llm_steps/step4_spl_emission/s4c_from_registry.py)

```python
from pipeline.llm_steps.step4_spl_emission.s4c_from_registry import (
    generate_variables_files_from_registry
)

block_4c = generate_variables_files_from_registry(
    registry=step3_result["global_registry"],
    types_spl=types_spl  # For type name resolution
)
```

This replaces the old S4C LLM call when using new Step 3.

---

## Data Flow Checklist (Updated)

| Stage | Required Input | Source | Output |
|-------|---------------|--------|--------|
| P1 | `skill_root: Path` | Caller | FileReferenceGraph |
| P2 | FileReferenceGraph | P1 | FileRoleMap |
| P3 | FileReferenceGraph + FileRoleMap | P1 + P2 | SkillPackage |
| Step 1 | SkillPackage.merged_doc_text | P3 | SectionBundle + ToolInfo[] |
| Step 1.5 | package.tools | P2.5 + Step 1 | APISymbolTable |
| Step 3-W | WORKFLOW + TOOLS + EVIDENCE | Step 1 | Step3WOutput |
| Step 3-IO | workflow_steps + WORKFLOW + ARTIFACTS | Step 3-W + Step 1 | Step3IOOutput |
| Step 3-T | global_registry | Step 3-IO | Step3TOutput |
| S4C | global_registry + types_spl | Step 3 | VARIABLES/FILES block |
| S4D | APISymbolTable | Step 1.5 | APIS block |
| S4A/B/E | SectionBundle + symbol_table | Step 1 + S4C | PERSONA/CONSTRAINTS/WORKER |
| S4F | worker_spl + EXAMPLES | S4E + Step 1 | EXAMPLES block |

---

## Quick Reference: SPL Block Source Chains (Updated)

```
DEFINE_PERSONA
← Step 1[INTENT] + Step 1[NOTES] → S4A

DEFINE_AUDIENCE
← Step 1[INTENT] (explicit user groups) → S4A

DEFINE_CONCEPTS
← Step 1[NOTES] (term definitions) → S4A

DEFINE_TYPES
← Step 3-IO[global_registry] → Step 3-T

DEFINE_CONSTRAINTS
← Step 1[CONSTRAINTS] → S4B

DEFINE_VARIABLES
← Step 3-IO[global_registry.variables] → S4C

DEFINE_FILES
← Step 3-IO[global_registry.files] → S4C

DEFINE_APIS
← Step 1.5[APISymbolTable] → S4D

WORKER.MAIN_FLOW
← Step 3-W[workflow_steps] → S4E

WORKER.ALTERNATIVE_FLOW
← Step 3-W[alternative_flows] → S4E

WORKER.EXCEPTION_FLOW
← Step 3-W[exception_flows] → S4E

[EXAMPLES]
← Step 1[EXAMPLES] → S4F
```

---

## File Organization (Updated)

```
skill_to_cnlp/
├── main.py                          # Entry point
├── cli.py / cli_async.py            # CLI interfaces (sync/async)
├── pyproject.toml                   # Project configuration
├── models/
│   ├── data_models.py               # All dataclasses (V1)
│   └── step3_types.py               # NEW: Step 3 type system
├── pipeline/
│   ├── orchestrator.py              # Main sync orchestrator (NEW Step 3)
│   ├── orchestrator_async.py        # Async orchestrator
│   ├── llm_client.py                # LLM client wrapper
│   ├── llm_steps/
│   │   ├── step1_structure_extraction.py
│   │   ├── step1_5_api_generation.py    # NEW: API generation
│   │   ├── step3_interface_inference.py   # LEGACY: old Step 3A/3B
│   │   ├── step3/                       # NEW: Step 3 package
│   │   │   ├── __init__.py
│   │   │   ├── w.py                     # Step 3-W
│   │   │   ├── io.py                    # Step 3-IO
│   │   │   ├── t.py                     # Step 3-T
│   │   │   └── orchestrator.py          # Combined W→IO→T
│   │   └── step4_spl_emission/
│   │       ├── __init__.py
│   │       ├── orchestrator.py
│   │       ├── substep_calls.py
│   │       ├── s4c_from_registry.py     # NEW: S4C from registry
│   │       ├── symbol_table.py
│   │       ├── assembly.py
│   │       ├── nesting_validation.py
│   │       └── ...
│   └── spl_formatter.py
├── pre_processing/
│   ├── p1_reference_graph.py
│   ├── p2_file_roles.py             # Rule-based (replaces LLM)
│   └── p3_assembler.py              # Includes P2.5 API analysis
├── prompts/
│   ├── templates.py
│   ├── step1_system.py
│   ├── step3_system.py              # LEGACY prompts
│   ├── step3/                       # NEW: Step 3 prompts
│   │   ├── w_system.py
│   │   ├── io_system.py
│   │   └── t_system.py
│   └── step4_system.py
└── skills/
    └── ...
```

---

## Type System Reference

### TypeExpr Kinds

| Kind | Python Representation | SPL Syntax | Example |
|------|----------------------|------------|---------|
| simple | `TypeExpr.simple("text")` | `text` | `user_input: text` |
| enum | `TypeExpr.enum(["a", "b"])` | `["a", "b"]` | `status: ["ok", "error"]` |
| array | `TypeExpr.array(TypeExpr.simple("text"))` | `List[text]` | `lines: List[text]` |
| struct | `TypeExpr.struct({"a": TypeExpr.simple("text")})` | `{a: text}` | `doc: {title: text, pages: number}` |

### Type Generation Rules

1. **Simple types** (text, number, boolean, image, audio) → no TYPES declaration
2. **Complex types** (enum, array, struct) → generate TypeDecl
3. **Type deduplication** by signature (canonical string representation)
4. **Name generation** from structure (e.g., `List[text]` → `TextList`)

---

## Migration Guide: V1 → V2

### For Pipeline Users

**OLD (V1):**
```python
from pipeline.orchestrator import run_pipeline, PipelineConfig

config = PipelineConfig(skill_root="skills/pdf")
result = run_pipeline(config)  # Uses old 3A/3B
```

**NEW (V2):**
```python
from pipeline.orchestrator import run_pipeline, PipelineConfig

config = PipelineConfig(
    skill_root="skills/pdf",
    use_new_step3=True  # Enable new Step 3
)
result = run_pipeline(config)  # Uses new W→IO→T
```

### For Direct Step 3 Users

**OLD (V1):**
```python
from pipeline.llm_steps import run_step3a_entity_extraction, run_step3b_workflow_analysis

entities = run_step3a_entity_extraction(bundle=bundle, client=client)
structured_spec = run_step3b_workflow_analysis(
    bundle=bundle, entity_ids=[e.entity_id for e in entities], ...
)
```

**NEW (V2):**
```python
from pipeline.llm_steps.step3 import run_step3_full

result = await run_step3_full(
    workflow_section=bundle.to_text(["WORKFLOW"]),
    tools_section=bundle.to_text(["TOOLS"]),
    evidence_section=bundle.to_text(["EVIDENCE"]),
    artifacts_section=bundle.to_text(["ARTIFACTS"]),
    available_tools=[...],
    client=client
)

# Access results
workflow_steps = result["workflow_steps"]
step_io_specs = result["step_io_specs"]
global_registry = result["global_registry"]
types_spl = result["types_spl"]
```

---

## Notes

1. **Backward Compatibility**: Old Step 3A/3B still available via `use_new_step3=False`

2. **Async Support**: Both sync and async versions available:
   - `run_step3_full()` - async
   - `run_step3_full_sync()` - sync wrapper

3. **Type Safety**: All TypeExpr operations are pure code (no LLM), ensuring consistency

4. **Symbol Table**: New symbol_table includes "types" key for complex type resolution

5. **Testing**: 41+ tests for new Step 3:
   ```bash
   python -m pytest test/test_step3_types.py test/test_step3_full.py test/test_step3_integration.py -v
   ```

6. **Performance**: Step 3-W and Step 3-IO are LLM calls, Step 3-T is pure code

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| V1 | Original | Initial design with 3A/3B split |
| V2 | Current | New W→IO→T architecture, type system, Step 1.5 |
