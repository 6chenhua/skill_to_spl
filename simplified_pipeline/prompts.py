"""
Simplified prompts for the minimal pipeline.
"""

from __future__ import annotations


# ═════════════════════════════════════════════════════════════════════════════
# STEP 1: Structure Extraction (5 sections only)
# ═════════════════════════════════════════════════════════════════════════════

STEP1_SYSTEM = """\
You are a precise document organizer. Your only task is to read technical
documents and distribute their content into labeled categories — without
paraphrasing, summarizing, or drawing conclusions. Copy content verbatim.

## Categories

INTENT
The purpose, scope, and goals of the document set.
Found in opening paragraphs, introductions, or headings like "Intent".
Extract sentences describing what this system/agent does and its purpose.

WORKFLOW
Ordered procedures, step sequences, branching logic, conditional paths.
Includes: numbered/bulleted steps, "if X then Y" patterns,
phase descriptions, failure-handling procedures, and alternative procedures.

Granularity rule — each array element must represent exactly ONE of:
(a) A single executable action or named phase
(b) A complete conditional block including condition AND all sub-steps
(c) A complete alternative procedure block introduced by a condition
(d) A prerequisite statement that gates a specific action

Do NOT split conditional blocks across multiple elements.
Do NOT merge unrelated actions into one element.

CONSTRAINTS
Rules, restrictions, requirements, prohibitions, normative statements.
Keywords: MUST, MUST NOT, SHALL, SHOULD, always, never, required,
forbidden, blocked, only if, not allowed, prohibited.
Also include implicit normative statements.

EXAMPLES
ONLY complete workflow execution paths — NOT code examples or tool demos.
Extract: end-to-end test cases, scenario walkthroughs, full execution sequences.
Format: "Given X input, the worker should Y, producing Z output"
- Include: Multi-step scenarios showing complete workflow from start to finish
- Exclude: Individual function calls, code samples

NOTES
Everything that does not fit the above: rationale, background, caveats, tips,
warnings that are not normative, references to external documentation.

## Rules

1. Copy text VERBATIM — never paraphrase or summarize.
2. If a sentence belongs to more than one category, copy it into each and set
   "multi": true on every copy.
3. Record the source filename for every item (use "SKILL.md" if not specified).
4. Preserve original formatting (bullets, numbering, indentation).
5. NOTHING may be dropped. If unsure, put it in NOTES.

## Output Format

Return a JSON object. Keys are the category names above (uppercase).
Each value is an array of items:
{ "text": "<verbatim original>", "source": "<filename>", "multi": false }

Example:
{
  "INTENT": [
    {"text": "你是一个智能体调度系统", "source": "SKILL.md", "multi": false}
  ],
  "WORKFLOW": [
    {"text": "1. 接收用户输入", "source": "SKILL.md", "multi": false},
    {"text": "2. 判断调用哪个智能体", "source": "SKILL.md", "multi": false}
  ],
  "CONSTRAINTS": [
    {"text": "当type == 视频时不能选择智能体A", "source": "SKILL.md", "multi": false}
  ],
  "EXAMPLES": [
    {"text": "用户提交图文稿件 -> 智能体A处理", "source": "SKILL.md", "multi": false}
  ],
  "NOTES": [
    {"text": "处理时间取决于输入复杂度", "source": "SKILL.md", "multi": false}
  ]
}
"""

STEP1_USER = """\
## Document Package

{merged_doc_text}
"""


def render_step1_user(merged_doc_text: str) -> str:
    return STEP1_USER.format(merged_doc_text=merged_doc_text)


# ═════════════════════════════════════════════════════════════════════════════
# STEP 3A: Variable Extraction (No files)
# ═════════════════════════════════════════════════════════════════════════════

STEP3A_SYSTEM = """\
You extract named data variables from skill documentation.

Extract ONLY in-memory data structures (variables), NOT files.

## Fields

var_id — snake_case stable identifier (e.g., max_retries, output_format)
type_name — short PascalCase label (e.g., "ConfigSettings", "ProcessResult")
schema_notes — describe the data structure and fields
provenance_required — true only when source explicitly says this must be validated
provenance — "EXPLICIT" if named in source, "ASSUMED" if implied, "LOW_CONFIDENCE" if unclear
source_text — verbatim quote describing this variable

## Rules

- Only extract variables that are explicitly mentioned or strongly implied.
- Do NOT invent variables not grounded in the source text.
- This is for IN-MEMORY data only - no file paths or disk artifacts.
- If no variables found, return {"variables": []}.

## Output Format

Return exactly:
{
  "variables": [
    {
      "var_id": "snake_case_name",
      "type_name": "PascalCaseName",
      "schema_notes": "description of fields/structure",
      "provenance_required": true | false,
      "provenance": "EXPLICIT" | "ASSUMED" | "LOW_CONFIDENCE",
      "source_text": "<verbatim quote>"
    }
  ]
}
"""

STEP3A_USER = """\
## Workflow Context

Look for variables mentioned in the workflow steps (inputs, outputs, config).

{workflow_section}

## Examples Section

Use concrete examples to understand variable structures.

{examples_section}
"""


def render_step3a_user(workflow_section: str, examples_section: str) -> str:
    return STEP3A_USER.format(
        workflow_section=workflow_section,
        examples_section=examples_section
    )


# ═════════════════════════════════════════════════════════════════════════════
# STEP 3B: Workflow Analysis (Simplified action types)
# ═════════════════════════════════════════════════════════════════════════════

STEP3B_SYSTEM = """\
You extract structured workflow information from skill documentation.

Your output describes the skill's procedure - steps, branches, and failure paths.

## Simplified Action Types

Each step must have exactly one action_type from:

- "LLM_TASK" — Pure LLM reasoning/judgment (default, most common)
- "FILE_READ" — Step reads from a file
- "FILE_WRITE" — Step writes to a file  
- "USER_INTERACTION" — Step requires user input before proceeding

NO EXTERNAL APIs, NO SCRIPTS, NO CODE SNIPPETS - this is a simplified pipeline.

## Workflow Step Fields

step_id — "step.<action_name>" in snake_case (e.g., "step.validate_input")
description — concise description using abstract action verbs
prerequisites — var_ids (from provided list) that must exist before this step
produces — var_ids this step creates or updates
is_validation_gate — true ONLY when: (a) from EVIDENCE requirement AND (b) clear pass/fail
action_type — one of: LLM_TASK | FILE_READ | FILE_WRITE | USER_INTERACTION
source_text — verbatim quote from WORKFLOW

## Flow Classification

MAIN_FLOW — default execution path steps. Steps proceed sequentially unless branched.

DECISION_BLOCK — fork-and-merge branch inside MAIN_FLOW:
- Use when: "if X then Y, otherwise Z" or "根据...判断"
- Both branches execute within MAIN_FLOW context and converge to same outputs
- Example: "根据type判断调用哪个智能体" → DECISION with IF/ELSEIF/ELSE

ALTERNATIVE_FLOW — complete substitute procedure when precondition not met:
- Use when: entire main flow cannot run under a condition
- Example: "If the API is unavailable, use fallback instead"

EXCEPTION_FLOW — recovery when a specific step fails:
- Use when source explicitly describes what to do on failure
- Must have failure handling described (not just validation)

## Dispatch Rule Analysis

For agent dispatch systems (智能体调度), convert rules to workflow_steps:

1. Dispatch rules become steps with conditions:
   - step_id: "step.dispatch_<number>" (e.g., "step.dispatch_1")
   - description: What triggers this dispatch
   - prerequisites: Variables needed for condition evaluation
   - produces: ["dispatch_result"] or specific output
   - action_type: "LLM_TASK" (decision is LLM reasoning)
   - condition: The dispatch condition string

2. Pattern recognition:
   - "X → **N**" or "X → 智能体N" → dispatch step producing agent_id
   - "当 condition 时不能选择" → Constraint (not workflow step)
   - "{var} ≠ none 且 {var} = value" → condition for dispatch

3. Priority ordering (优先匹配):
   - Extract the order from "按上列顺序优先匹配" text
   - List dispatch conditions in that priority order for IF/ELSEIF generation

## Output Format

Return exactly:
{
  "workflow_steps": [
    {
      "step_id": "step.action_name",
      "description": "Concise description",
      "prerequisites": ["var_id"],
      "produces": ["var_id"],
      "is_validation_gate": false,
      "action_type": "LLM_TASK",
      "source_text": "<verbatim quote>"
    }
  ],
  "alternative_flows": [
    {
      "flow_id": "alt-001",
      "condition": "when this alternative triggers",
      "description": "what this path accomplishes",
      "steps": [
        {"description": "step action", "action_type": "LLM_TASK", "source_text": "..."}
      ],
      "source_text": "<verbatim quote>",
      "provenance": "EXPLICIT"
    }
  ],
  "exception_flows": [
    {
      "flow_id": "exc-001",
      "condition": "failure description",
      "log_ref": "",
      "steps": [
        {"description": "recovery action", "action_type": "LLM_TASK", "source_text": "..."}
      ],
      "source_text": "<verbatim quote>",
      "provenance": "EXPLICIT"
    }
  ]
}
"""

STEP3B_USER = """\
## Available Variables

Use ONLY these var_ids in prerequisites and produces. Do NOT invent new ones.

{var_ids_json}

## Workflow Procedure

{workflow_section}

## Constraints (for validation gates)

{constraints_section}
"""


def render_step3b_user(
    var_ids_json: str,
    workflow_section: str,
    constraints_section: str
) -> str:
    return STEP3B_USER.format(
        var_ids_json=var_ids_json,
        workflow_section=workflow_section,
        constraints_section=constraints_section
    )


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4A: PERSONA / AUDIENCE / CONCEPTS
# ═════════════════════════════════════════════════════════════════════════════

STEP4A_SYSTEM = """\
Emit the opening identity blocks of an SPL specification.

## Complete Grammar

SPL_PROMPT := PERSONA [AUDIENCE] [CONCEPTS] ...

PERSONA := "[DEFINE_PERSONA:]" PERSONA_ASPECTS "[END_PERSONA]"
PERSONA_ASPECTS := ROLE_ASPECT {OPTIONAL_ASPECT}
ROLE_ASPECT := "ROLE" ":" DESCRIPTION_WITH_REFERENCES
OPTIONAL_ASPECT := OPTIONAL_ASPECT_NAME ":" DESCRIPTION_WITH_REFERENCES
OPTIONAL_ASPECT_NAME := <word>  # e.g., DOMAIN, EXPERTISE — capitalize

AUDIENCE := "[DEFINE_AUDIENCE:]" AUDIENCE_ASPECTS "[END_AUDIENCE]"

CONCEPTS := "[DEFINE_CONCEPTS:]" {CONCEPT} "[END_CONCEPTS]"
CONCEPT := OPTIONAL_ASPECT_NAME ":" STATIC_DESCRIPTION

## How to Extract PERSONA

From INTENT section:
1. Best sentence capturing "what this agent does" → ROLE aspect
   - Look for: "你是一个..." pattern in Chinese → Extract role after this phrase
   - Remove markdown formatting (**，*, etc.) from extracted text
   - Example: "你是一个智能体调度系统，负责..." → Extract: "智能体调度系统，负责根据当前流程判断调用哪个子智能体"

2. Sentence naming a technical field → DOMAIN optional aspect (e.g., "MCN", "AI", "Natural Language Processing")

3. Sentence naming an expertise level → EXPERTISE optional aspect (e.g., "Intermediate", "Senior")

4. Sentence explicitly naming who uses this agent → emit AUDIENCE block
   Omit AUDIENCE if no user group is explicitly named.

## How to Extract CONCEPTS

From NOTES section AND agent definitions:
1. Sentences defining terms ("X means Y") → one CONCEPT per defined term
2. Agent definitions (智能体A, 智能体B, etc.) → Extract as CONCEPT:
   - Format: AgentName: "Role description + Core responsibilities"
   - Example: "AgentA: MCN brand execution specialist responsible for image-text collaboration projects"
3. Background rationale and caveats → skip

## Rules

- Copy wording VERBATIM from source text. Do not paraphrase.
- Omit AUDIENCE if no user group is named.
- Omit CONCEPTS if no terms are explicitly defined.
- Use 4-space indentation.
- Output ONLY the SPL blocks. No prose, no markdown fences, no explanation.
"""

STEP4A_USER = """\
## INTENT Section

{intent_text}

## NOTES Section

{notes_text}

## Declared Variables

{variables_list}
"""


def render_step4a_user(
    intent_text: str,
    notes_text: str,
    variables_list: str
) -> str:
    return STEP4A_USER.format(
        intent_text=intent_text,
        notes_text=notes_text,
        variables_list=variables_list
    )


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4B: CONSTRAINTS
# ═════════════════════════════════════════════════════════════════════════════

STEP4B_SYSTEM = """\
Emit the [DEFINE_CONSTRAINTS:] block of an SPL specification.

## Complete Grammar

CONSTRAINTS := "[DEFINE_CONSTRAINTS:]" {CONSTRAINT} "[END_CONSTRAINTS]"
CONSTRAINT := [OPTIONAL_ASPECT_NAME ":"] DESCRIPTION_WITH_REFERENCES
OPTIONAL_ASPECT_NAME := <word>
- Capitalize; derive from requirement topic in CamelCase
- One aspect may have multiple CONSTRAINT lines under the same name
- Omit only when the requirement has no stable, referenceable identity

DESCRIPTION_WITH_REFERENCES := STATIC_DESCRIPTION {DESCRIPTION_WITH_REFERENCES}
| REFERENCE {DESCRIPTION_WITH_REFERENCES}
REFERENCE := "<REF>" ["*"] NAME "</REF>"
NAME := SIMPLE_NAME | QUALIFIED_NAME
SIMPLE_NAME := <word>
QUALIFIED_NAME := NAME "." SIMPLE_NAME

## Aspect Naming Rules

1. Derive AspectName from constraint content using CamelCase:
   - "当 type == 视频 时不能选择智能体A" → AgentSelectionConstraint
   - "仅输出一个数字" → OutputFormatConstraint
   - "按上列顺序优先匹配" → PriorityMatchingRule

2. Group related constraints under the same AspectName:
   - All format-related constraints → OutputFormatConstraint
   - All agent selection constraints → AgentSelectionConstraint

3. When constraints reference variables, use <REF> tags:
   - "当 type == 视频时" → "AgentSelectionConstraint: 当 <REF>type</REF> == 视频时不能选择"
   - "{manuscript_link} ≠ none" → "<REF>manuscript_link</REF> != 'none'"

## Rules

- Copy requirement text VERBATIM. Do not paraphrase.
- One CONSTRAINT entry per distinct requirement.
- Append source filename in parentheses: AspectName: text (source.md)
- If no requirements exist:
  [DEFINE_CONSTRAINTS:]
  [END_CONSTRAINTS]
- Use 4-space indentation.
- Output ONLY the [DEFINE_CONSTRAINTS:] ... [END_CONSTRAINTS] block.
No prose, no markdown fences, no explanation.
"""

STEP4B_USER = """\
## CONSTRAINTS Section

{constraints_text}

## Declared Variables

Reference these by name when constraints mention them:

{variables_list}
"""


def render_step4b_user(constraints_text: str, variables_list: str) -> str:
    return STEP4B_USER.format(
        constraints_text=constraints_text,
        variables_list=variables_list
    )


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4C: VARIABLES (Simplified - no FILES block)
# ═════════════════════════════════════════════════════════════════════════════

STEP4C_SYSTEM = """\
Emit the [DEFINE_VARIABLES:] block of an SPL specification.

## Grammar

[DEFINE_VARIABLES:]
    "Description"
    [READONLY]
    var_name : data_type [= default_value]
[END_VARIABLES]

data_type: text | number | boolean | List[data_type] | {field: type, ...}

## Rules

- Generate one declaration per variable in the input list.
- READONLY only for configuration constants that never change at runtime.
- Use schema_notes for the description.
- Convert type_name to SPL data_type (text, number, boolean, etc.).
- Use 4-space indentation.
- Output ONLY the SPL block.
"""

STEP4C_USER = """\
## Variables to Declare

{variables_json}
"""


def render_step4c_user(variables_json: str) -> str:
    return STEP4C_USER.format(variables_json=variables_json)


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4E: WORKER (Simplified - no APIs, no files)
# ═════════════════════════════════════════════════════════════════════════════

STEP4E_SYSTEM = """\
Emit the [DEFINE_WORKER:] block of an SPL specification.

## Complete Grammar

WORKER_INSTRUCTION :=
"[DEFINE_WORKER:" ["\"" STATIC_DESCRIPTION "\""] WORKER_NAME "]"
[INPUTS] [OUTPUTS]
MAIN_FLOW {ALTERNATIVE_FLOW} {EXCEPTION_FLOW}
"[END_WORKER]"

INPUTS := "[INPUTS]" {["REQUIRED" | "OPTIONAL"] REFERENCE_DATA} "[END_INPUTS]"
OUTPUTS := "[OUTPUTS]" {["REQUIRED" | "OPTIONAL"] REFERENCE_DATA} "[END_INPUTS]"
REFERENCE_DATA := "<REF>" NAME "</REF>"

MAIN_FLOW := "[MAIN_FLOW]" {BLOCK} "[END_MAIN_FLOW]"
ALTERNATIVE_FLOW := "[ALTERNATIVE_FLOW:" CONDITION "]" {BLOCK} "[END_ALTERNATIVE_FLOW]"
EXCEPTION_FLOW := "[EXCEPTION_FLOW:" CONDITION "]" ["LOG" DESCRIPTION_WITH_REFERENCES] {BLOCK} "[END_EXCEPTION_FLOW]"

BLOCK := SEQUENTIAL_BLOCK | IF_BLOCK | LOOP_BLOCK
SEQUENTIAL_BLOCK := "[SEQUENTIAL_BLOCK]" {COMMAND} "[END_SEQUENTIAL_BLOCK]"
IF_BLOCK := DECISION_INDEX "[IF" CONDITION "]" {COMMAND}
{"[ELSEIF" CONDITION "]" {COMMAND}}
["[ELSE]" {COMMAND}]
"[END_IF]"
WHILE_BLOCK := DECISION_INDEX "[WHILE" CONDITION "]" {COMMAND} "[END_WHILE]"
FOR_BLOCK := DECISION_INDEX "[FOR" CONDITION "]" {COMMAND} "[END_FOR]"

DECISION_INDEX := "DECISION-" <number>
COMMAND := COMMAND_INDEX COMMAND_BODY
COMMAND_INDEX := "COMMAND-" <number>
COMMAND_BODY :=
"[COMMAND" ["CODE"] DESCRIPTION_WITH_REFERENCES
["STOP" DESCRIPTION_WITH_REFERENCES]
["RESULT" COMMAND_RESULT ["SET" | "APPEND"]]
"]"
| "[DISPLAY" DESCRIPTION_WITH_REFERENCES "]"
| "[INPUT" ["DISPLAY"] DESCRIPTION_WITH_REFERENCES "VALUE" COMMAND_RESULT ["SET" | "APPEND"] "]"

COMMAND_RESULT := VAR_NAME ":" DATA_TYPE | REFERENCE
DATA_TYPE := "text" | "number" | "boolean" | "List [" DATA_TYPE "]" | "{" TYPE_ELEMENT {"," TYPE_ELEMENT} "}"
TYPE_ELEMENT := ["OPTIONAL"] ELEMENT_NAME ":" DATA_TYPE

## Action Type Mapping

LLM_TASK → [COMMAND description RESULT var: type]
FILE_READ → [COMMAND description RESULT var: type]
FILE_WRITE → [COMMAND description]
USER_INTERACTION → [INPUT DISPLAY "prompt" VALUE var: type]

## INPUTS/OUTPUTS Generation

Prerequisites not produced by any prior step → [INPUTS] REQUIRED or OPTIONAL
Produces of the final step(s) → [OUTPUTS] REQUIRED

## MAIN_FLOW Construction

CRITICAL — no nested BLOCKs:
- Each BLOCK may only contain {COMMAND} — never another BLOCK
- IF/ELSEIF/ELSE contain COMMANDs directly, no wrapping SEQUENTIAL_BLOCK

All workflow_steps go in MAIN_FLOW in procedure order.

Step → command mapping (use action_type field):
- action_type == "USER_INTERACTION" → [INPUT DISPLAY "description" VALUE answer: TYPE]
- action_type == "LLM_TASK" → [COMMAND description RESULT var: TYPE]
- action_type == "FILE_READ" → [COMMAND description RESULT var: TYPE]
- action_type == "FILE_WRITE" → [COMMAND description]

## IF_BLOCK Generation for Dispatch Logic

When workflow_steps have conditions (e.g., dispatch rules), generate IF blocks:

Single condition:
DECISION-1 [IF <REF>type</REF> == "图文" AND <REF>manuscript_link</REF> != "none"]
COMMAND-1 [COMMAND Dispatch to Agent A RESULT agent_id: number]
[END_IF]

Multiple mutually exclusive conditions (use IF/ELSEIF/ELSE):
DECISION-1 [IF <REF>type</REF> == "图文" AND <REF>manuscript_link</REF> != "none"]
COMMAND-1 [COMMAND Dispatch to Agent 3 RESULT agent_id: number]
[ELSEIF <REF>type</REF> == "视频" AND <REF>preview_link</REF> != "none"]
COMMAND-2 [COMMAND Dispatch to Agent 4 RESULT agent_id: number]
[ELSEIF <REF>type</REF> == "图文"]
COMMAND-3 [COMMAND Dispatch to Agent 1 RESULT agent_id: number]
[ELSE]
COMMAND-4 [COMMAND Unable to determine agent RESULT error: text]
[END_IF]

Condition translation:
- "{var} ≠ none" → <REF>var</REF> != "none"
- "{var} = value" → <REF>var</REF> == "value"
- "且" → AND
- "或" → OR

## Rules

- Global sequential COMMAND numbering: COMMAND-1, COMMAND-2, ... (never restart)
- Global sequential DECISION numbering: DECISION-1, DECISION-2, ... (never restart)
- Generate ALTERNATIVE_FLOW blocks from alternative_flows list.
- Generate EXCEPTION_FLOW blocks from exception_flows list.
- Use declared variable names in <REF> references.
- Use 4-space indentation.
- Output ONLY the [DEFINE_WORKER:] ... [END_WORKER] block.
No prose, no markdown fences, no explanation.
"""

STEP4E_USER = """\
## A. Workflow Steps

{workflow_steps_json}

## B. Alternative Flows

{alternative_flows_json}

## C. Exception Flows

{exception_flows_json}

## D. Declared Variables

Use these exact names in references:

{variables_list}
"""


def render_step4e_user(
    workflow_steps_json: str,
    alternative_flows_json: str,
    exception_flows_json: str,
    variables_list: str
) -> str:
    return STEP4E_USER.format(
        workflow_steps_json=workflow_steps_json,
        alternative_flows_json=alternative_flows_json,
        exception_flows_json=exception_flows_json,
        variables_list=variables_list
    )
