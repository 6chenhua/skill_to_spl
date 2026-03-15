# SPL Subset Grammar Reference

This file defines the SPL grammar subset used by the SPL Emitter skill (Step 4).
Consult this reference when constructing any SPL block.

EBNF conventions:
- `[X]` = optional
- `{X}` = zero or more repetitions
- `X | Y` = alternation
- `"..."` = literal terminal
- `<word>` etc. = terminal type (defined in §14)
- `"""..."""` = semantic note (not syntax)

---

## §1 Top-Level Structure

```
SPL_SKILL_SPEC :=
    PERSONA
    [AUDIENCE]
    [CONCEPTS]
    [CONSTRAINTS]
    [VARIABLES]
    [FILES]
    [APIS]
    [GUARDRAIL_INSTRUCTION]
    WORKER_INSTRUCTION
```

---

## §2 PERSONA

```
PERSONA          := "[DEFINE_PERSONA:]" PERSONA_ASPECTS "[END_PERSONA]"
PERSONA_ASPECTS  := ROLE_ASPECT {OPTIONAL_ASPECT}
ROLE_ASPECT      := "ROLE" ":" DESCRIPTION_WITH_REFERENCES
OPTIONAL_ASPECT  := OPTIONAL_ASPECT_NAME ":" DESCRIPTION_WITH_REFERENCES
OPTIONAL_ASPECT_NAME := <word>    """Capitalize"""
```

Common OPTIONAL_ASPECT_NAME values for PERSONA: `MODALITY`, `EXPERTISE`, `DOMAIN`, `TONE`, `LANGUAGE`

---

## §3 AUDIENCE

```
AUDIENCE         := "[DEFINE_AUDIENCE:]" AUDIENCE_ASPECTS "[END_AUDIENCE]"
AUDIENCE_ASPECTS := {OPTIONAL_ASPECT}
```

Common OPTIONAL_ASPECT_NAME values for AUDIENCE: `INTEREST`, `KNOWLEDGE`, `PREFERENCE`

---

## §4 CONCEPTS

```
CONCEPTS := "[DEFINE_CONCEPTS:]" {CONCEPT} "[END_CONCEPTS]"
CONCEPT  := OPTIONAL_ASPECT_NAME ":" STATIC_DESCRIPTION
```

"""Concepts do not need parameters or references."""

---

## §5 CONSTRAINTS

```
CONSTRAINTS   := "[DEFINE_CONSTRAINTS:]" {CONSTRAINT} "[END_CONSTRAINTS]"
CONSTRAINT    := [OPTIONAL_ASPECT_NAME ":"] DESCRIPTION_WITH_REFERENCES [LOG_VIOLATION]
LOG_VIOLATION := "LOG" DESCRIPTION_WITH_REFERENCES
```

"""One ASPECT_NAME may have multiple CONSTRAINT entries (1:M cardinality)."""

Constraint tier prefixes (normalization convention, not SPL syntax):
- HARD clauses: no prefix — direct statement + LOG_VIOLATION
- MEDIUM clauses: prefix body with `[MEDIUM: requires review/evidence before proceeding]`
- SOFT clauses: prefix body with `[SOFT: guidance only — no enforcement gate]`

---

## §6 VARIABLES

```
VARIABLES            := "[DEFINE_VARIABLES:]" {VARIABLE_DECLARATION} "[END_VARIABLES]"
VARIABLE_DECLARATION := ["\"" DESCRIPTION_WITH_REFERENCES "\""]
                        ["READONLY"]
                        VAR_NAME ":" DATA_TYPE
                        ["=" DEFAULT_VALUE]
VAR_NAME             := <word>
DEFAULT_VALUE        := VALUE
```

"""APPLY_GUARDRAILS, APPLY_CONSTRAINTS, REFERENCE_VECTOR_STORE omitted from this subset."""

---

## §7 FILES

```
FILES                  := "[DEFINE_FILES:]" {FILE_DECLARATION} "[END_FILES]"
FILE_DECLARATION       := LEAF_FILE_DECLARATION
LEAF_FILE_DECLARATION  := ["\"" STATIC_DESCRIPTION "\""]
                          FILE_NAME FILE_PATH ":" DATA_TYPE
FILE_NAME              := <word>
FILE_PATH              := <filepath> | "< >"
```

"""< > = file path not known at compile time; must be provided at runtime."""
"""FOLDER_DECLARATION, DATABASE_DECLARATION, and all modifier decorators omitted from this subset."""

---

## §8 APIS

```
APIS           := "[DEFINE_APIS:]" {API_DECLARATION} "[END_APIS]"
API_DECLARATION := ["\"" STATIC_DESCRIPTION "\""]
                   API_NAME "<" AUTHENTICATION ">"
                   ["RETRY" <number>]
                   OPENAPI_SCHEMA
                   API_IN_SPL

AUTHENTICATION := <none> | <apikey> | <oauth>
OPENAPI_SCHEMA := STRUCTURED_TEXT

API_IN_SPL := "{" FUNCTIONS "}"
FUNCTIONS  := "functions:" "[" {FUNCTION} "]"
FUNCTION   := "{"
                  "name:"        STATIC_DESCRIPTION ","
                  URL            ","
                  ["description:" STATIC_DESCRIPTION ","]
                  PARAMETERS     ","
                  RETURN
              "}"
PARAMETERS := "{"
                  "parameters:"    "[" {PARAMETER} "]" ","
                  "controlled-input:" BOOL_VALUE
              "}"
PARAMETER  := "{"
                  "required:" BOOL_VALUE ","
                  "name:"     STATIC_DESCRIPTION ","
                  "type:"     PARAMETER_TYPE
                  ["," "description:" STATIC_DESCRIPTION]
              "}"
RETURN     := "{"
                  "type:"             PARAMETER_TYPE ","
                  "controlled-output:" BOOL_VALUE
                  ["," "description:" STATIC_DESCRIPTION]
              "}"
BOOL_VALUE     := "true" | "false"
PARAMETER_TYPE := TYPE_NAME | "List [" TYPE_NAME "]"
```

"""LOG, guardrails on PARAMETER/RETURN omitted from this subset."""
"""controlled-input and controlled-output default to false."""

---

## §9 GUARDRAIL_INSTRUCTION

```
GUARDRAIL_INSTRUCTION :=
    "[DEFINE_GUARDRAIL:" ["\"" STATIC_DESCRIPTION "\""] GUARDRAIL_NAME "]"
    [INPUTS]
    [OUTPUTS]
    MAIN_FLOW
    {ALTERNATIVE_FLOW}
    {EXCEPTION_FLOW}
    "[END_GUARDRAIL]"

GUARDRAIL_NAME := <word>
```

"""THROW_EXCEPTIONS, EXAMPLES, SCENARIOS omitted from this subset."""
"""Only emit when source doc explicitly describes parseable validation output (stdout/exit code)."""

---

## §10 WORKER_INSTRUCTION

```
WORKER_INSTRUCTION :=
    "[DEFINE_WORKER:" ["\"" STATIC_DESCRIPTION "\""] WORKER_NAME "]"
    [INPUTS]
    [OUTPUTS]
    MAIN_FLOW
    {ALTERNATIVE_FLOW}
    {EXCEPTION_FLOW}
    [EXAMPLES]
    "[END_WORKER]"

WORKER_NAME := <word>
```

"""SCENARIOS omitted. EXAMPLES contains only EXPECTED_WORKER_BEHAVIOR (no DEFECT_WORKER_BEHAVIOR)."""

### §10.1 INPUTS / OUTPUTS

```
INPUTS  := "[INPUTS]"  {["REQUIRED" | "OPTIONAL"] REFERENCE_DATA} "[END_INPUTS]"
OUTPUTS := "[OUTPUTS]" {["REQUIRED" | "OPTIONAL"] REFERENCE_DATA} "[END_OUTPUTS]"

REFERENCE_DATA := "<REF>" DATA_NAME "</REF>"
DATA_NAME      := VAR_NAME | FILE_NAME
```

"""APPLY_GUARDRAILS, APPLY_CONSTRAINTS, CONTROLLED_INPUTS/CONTROLLED_OUTPUTS omitted."""
"""REFERENCE_DATA must refer to names declared in VARIABLES or FILES."""

### §10.2 MAIN_FLOW

```
MAIN_FLOW := "[MAIN_FLOW]" {BLOCK} "[END_MAIN_FLOW]"
```

### §10.3 ALTERNATIVE_FLOW

```
ALTERNATIVE_FLOW :=
    "[ALTERNATIVE_FLOW:" CONDITION "]"
        {BLOCK}
    "[END_ALTERNATIVE_FLOW]"
CONDITION := DESCRIPTION_WITH_REFERENCES
```

Use for COMPILABLE_MEDIUM clauses that require review or evidence gates.

### §10.4 EXCEPTION_FLOW

```
EXCEPTION_FLOW :=
    "[EXCEPTION_FLOW:" CONDITION "]"
        ["LOG" DESCRIPTION_WITH_REFERENCES]
        {BLOCK}
    "[END_EXCEPTION_FLOW]"
```

Use for NON_COMPILABLE clauses. Preserve original prose via DISPLAY_MESSAGE (lossless rule).

### §10.5 EXAMPLES

```
EXAMPLES := "[EXAMPLES]" {EXPECTED_WORKER_BEHAVIOR} "[END_EXAMPLES]"

EXPECTED_WORKER_BEHAVIOR :=
    "<EXPECTED-WORKER-BEHAVIOR>"
        "{"
            INPUT_EXAMPLE ","
            EXPECTED_OUTPUT_EXAMPLE ","
            EXECUTION_PATH
        "}"
    "</EXPECTED-WORKER-BEHAVIOR>"

INPUT_EXAMPLE           := "inputs:"          "{" VAR_VALUE_PAIRS "}"
EXPECTED_OUTPUT_EXAMPLE := "expected-outputs:" "{" VAR_VALUE_PAIRS "}"
EXECUTION_PATH          := "execution-path:"  COMMAND_DECISION_INDEX {"," COMMAND_DECISION_INDEX}
VAR_VALUE_PAIRS         := VAR_NAME ":" VALUE {"," VAR_VALUE_PAIRS}
COMMAND_DECISION_INDEX  := COMMAND_INDEX | DECISION_INDEX
```

---

## §11 BLOCK Structures

```
BLOCK := SEQUENTIAL_BLOCK | IF_BLOCK | LOOP_BLOCK
```

"""FORK_BLOCK omitted from this subset."""

### §11.1 SEQUENTIAL_BLOCK

```
SEQUENTIAL_BLOCK := "[SEQUENTIAL_BLOCK]" {COMMAND} "[END_SEQUENTIAL_BLOCK]"
```

### §11.2 IF_BLOCK

```
IF_BLOCK :=
    DECISION_INDEX "[IF" CONDITION "]"
        {COMMAND}
    {"[ELSEIF" CONDITION "]"
        {COMMAND}}
    ["[ELSE]"
        {COMMAND}]
    "[END_IF]"
DECISION_INDEX := "DECISION-" <number>
```

### §11.3 LOOP_BLOCK

```
LOOP_BLOCK  := WHILE_BLOCK | FOR_BLOCK
WHILE_BLOCK := DECISION_INDEX "[WHILE" CONDITION "]" {COMMAND} "[END_WHILE]"
FOR_BLOCK   := DECISION_INDEX "[FOR"   CONDITION "]" {COMMAND} "[END_FOR]"
```

---

## §12 COMMAND

```
COMMAND       := COMMAND_INDEX COMMAND_BODY
COMMAND_INDEX := "COMMAND-" <number>
COMMAND_BODY  :=   GENERAL_COMMAND
                 | CALL_API
                 | INVOKE_INSTRUCTION
                 | REQUEST_INPUT
                 | DISPLAY_MESSAGE
                 | THROW
```

"""AGENT_INSTANTIATION, OPERATE_DATA, EXEC_SPL_PROMPT, EXEC_COMMAND omitted."""

### §12.1 GENERAL_COMMAND

```
GENERAL_COMMAND :=
    "[COMMAND"
        ["PROMPT_TO_CODE" | "CODE"]
        ["THINK_ALOUD"]
        DESCRIPTION_WITH_REFERENCES
        ["STOP" DESCRIPTION_WITH_REFERENCES]
        ["RESULT" COMMAND_RESULT ["SET" | "APPEND"]]
    "]"
COMMAND_RESULT := VAR_NAME ":" DATA_TYPE | REFERENCE
```

"""A command without PROMPT_TO_CODE or CODE modifier is a regular natural-language prompt."""
"""THINK_ALOUD: use when source doc explicitly requires reasoning steps to be visible."""

### §12.2 CALL_API

```
CALL_API :=
    "[CALL" API_NAME
        ["WITH" ARGUMENT_LIST]
        ["RESPONSE" COMMAND_RESULT ["SET" | "APPEND"]]
    "]"
ARGUMENT_LIST := STRUCTURED_TEXT
```

Only call APIs declared in the APIS block.

### §12.3 INVOKE_INSTRUCTION

```
INVOKE_INSTRUCTION :=
    "[INVOKE" INSTRUCTION_NAME
        ["WITH" ARGUMENT_LIST]
        ["RESPONSE" COMMAND_RESULT ["SET" | "APPEND"]]
    "]"
INSTRUCTION_NAME := WORKER_NAME | GUARDRAIL_NAME
```

### §12.4 REQUEST_INPUT

```
REQUEST_INPUT :=
    "[INPUT"
        ["DISPLAY"] DESCRIPTION_WITH_REFERENCES
        "VALUE" COMMAND_RESULT ["SET" | "APPEND"]
    "]"
```

"""With DISPLAY: DESCRIPTION is shown as a prompt to the user."""
"""Without DISPLAY: DESCRIPTION is an internal elicitation prompt."""
Use for needs_review_items from InterfaceSpec.

### §12.5 DISPLAY_MESSAGE

```
DISPLAY_MESSAGE := "[DISPLAY" DESCRIPTION_WITH_REFERENCES "]"
```

Primary use: preserve NON_COMPILABLE original prose in EXCEPTION_FLOW.

### §12.6 THROW

```
THROW := "[THROW" EXCEPTION_NAME "\"" DESCRIPTION_WITH_REFERENCES "\"" "]"
EXCEPTION_NAME := <word>
```

Use only for COMPILABLE_HARD violations inside MAIN_FLOW.
Naming convention: `<aspect>_violation` (e.g., `prereq_violation`, `security_violation`).

---

## §13 Type System

### §13.1 DATA_TYPE

```
DATA_TYPE            := ARRAY_DATA_TYPE | STRUCTURED_DATA_TYPE | ENUM_TYPE | TYPE_NAME
TYPE_NAME            := SIMPLE_TYPE_NAME | DECLARED_TYPE_NAME
SIMPLE_TYPE_NAME     := "text" | "image" | "audio" | "number" | "boolean"
DECLARED_TYPE_NAME   := <word>
ENUM_TYPE            := "[" <word> {"," <word>} "]"
ARRAY_DATA_TYPE      := "List [" DATA_TYPE "]"
STRUCTURED_DATA_TYPE := "{" STRUCTURED_TYPE_BODY "}" | "{ }"
STRUCTURED_TYPE_BODY := TYPE_ELEMENT | TYPE_ELEMENT "," STRUCTURED_TYPE_BODY
TYPE_ELEMENT         := ["OPTIONAL"] ELEMENT_NAME ":" DATA_TYPE
ELEMENT_NAME         := <word>
```

"""APPLY_GUARDRAILS, APPLY_CONSTRAINTS, REFERENCE_VECTOR_STORE, description strings
   omitted from TYPE_ELEMENT in this subset."""

### §13.2 DESCRIPTION_WITH_REFERENCES

```
DESCRIPTION_WITH_REFERENCES :=
      STATIC_DESCRIPTION {DESCRIPTION_WITH_REFERENCES}
    | REFERENCE {DESCRIPTION_WITH_REFERENCES}
STATIC_DESCRIPTION := <word> | <word> <space> STATIC_DESCRIPTION
REFERENCE          := "<REF>" ["*"] NAME "</REF>"
NAME               := SIMPLE_NAME | QUALIFIED_NAME | ARRAY_ACCESS | DICT_ACCESS
SIMPLE_NAME        := <word>
QUALIFIED_NAME     := NAME "." SIMPLE_NAME | NAME "." ARRAY_ACCESS | NAME "." DICT_ACCESS
ARRAY_ACCESS       := NAME "[" [<number>] "]"
DICT_ACCESS        := NAME "[" SIMPLE_NAME "]"
```

"""Prefer explicit <REF>NAME</REF> form for all declared variable/file references."""

### §13.3 STRUCTURED_TEXT

```
STRUCTURED_TEXT      := "{" STRUCTURED_TEXT_BODY "}" | "{ }"
STRUCTURED_TEXT_BODY := FORMAT_ELEMENT | FORMAT_ELEMENT "," STRUCTURED_TEXT_BODY
FORMAT_ELEMENT       := KEY ":" VALUE | VALUE
KEY                  := <word>
VALUE                := DESCRIPTION_WITH_REFERENCES | ARRAY | STRUCTURED_TEXT
ARRAY                := "[" ARRAY_ELEMENTS "]" | "[ ]"
ARRAY_ELEMENTS       := VALUE | VALUE "," ARRAY_ELEMENTS
```

Used in APIS (OPENAPI_SCHEMA, ARGUMENT_LIST).

---

## §14 Terminal Symbols

```
<word>     — sequence of characters/digits/symbols, no spaces
<space>    — whitespace or tab
<number>   — integer or float
<filepath> — canonical file path, relative to skill root
<none>     — empty authentication
<apikey>   — API key string
<oauth>    — OAuth configuration string
```

---

## §15 Annotation Convention (normalization-specific)

Annotations are SPL triple-quoted comments. They carry pipeline metadata and are
stripped by the SPL parser before compilation.

```
"""SOURCE_REF: <source_file>:<clause_id_or_anchor>"""
"""CONFIDENCE: <float 0.0–1.0>"""
"""NEEDS_REVIEW: true | false"""
"""ASSUMED: <reason>"""
"""LOW_CONFIDENCE: <reason>"""
"""RISK_OVERRIDE: R=3 — upgraded from SOFT"""
"""NOTE: <free text for content that cannot be mapped>"""
```

Rules:
- Every CONSTRAINT, VARIABLE, FILE declaration, and every COMMAND carries SOURCE_REF + CONFIDENCE + NEEDS_REVIEW.
- ASSUMED/LOW_CONFIDENCE appear only on items whose InterfaceSpec provenance is not EXPLICIT.
- RISK_OVERRIDE appears when Step 2B set risk_override=true.
- NOTE is the fallback for any SectionBundle content that cannot be mapped to a typed construct.

---

## §16 Quick Mapping Reference

| Pipeline concept            | SPL construct                                        |
|-----------------------------|------------------------------------------------------|
| INTENT (skill purpose)      | `PERSONA.ROLE` + `PERSONA.DOMAIN`                    |
| Audience description        | `AUDIENCE`                                           |
| Domain terms                | `CONCEPTS`                                           |
| COMPILABLE_HARD clause      | `CONSTRAINT` + `LOG_VIOLATION` + `THROW` in MAIN_FLOW|
| COMPILABLE_MEDIUM clause    | `CONSTRAINT [MEDIUM]` + `ALTERNATIVE_FLOW`           |
| COMPILABLE_SOFT clause      | `CONSTRAINT [SOFT]` (no LOG, no THROW)               |
| NON_COMPILABLE clause       | `EXCEPTION_FLOW` + `DISPLAY_MESSAGE` (lossless)      |
| Non-file data entity        | `VARIABLES`                                          |
| File / artifact entity      | `FILES` → `LEAF_FILE_DECLARATION`                    |
| External API (explicit)     | `APIS`                                               |
| Explicit validation logic   | `GUARDRAIL_INSTRUCTION`                              |
| Workflow steps              | `WORKER_INSTRUCTION` → `MAIN_FLOW` → `SEQUENTIAL_BLOCK` |
| Conditional branch          | `IF_BLOCK`                                           |
| Iteration                   | `FOR_BLOCK` / `WHILE_BLOCK`                          |
| Sub-procedure call          | `INVOKE_INSTRUCTION`                                 |
| User confirmation prompt    | `REQUEST_INPUT`                                      |
| Positive examples           | `EXAMPLES` → `EXPECTED_WORKER_BEHAVIOR`              |
| Pipeline annotations        | `"""SOURCE_REF / CONFIDENCE / NEEDS_REVIEW / ..."""` |