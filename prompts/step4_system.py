s4_a_v2 = """\
Emit the opening identity blocks of an SPL specification.
Emit exactly the blocks listed below and nothing else.
 
## Complete grammar
 
SPL_PROMPT := PERSONA [AUDIENCE] [CONCEPTS] ...
 
PERSONA := "[DEFINE_PERSONA:]" PERSONA_ASPECTS "[END_PERSONA]"
PERSONA_ASPECTS := ROLE_ASPECT {OPTIONAL_ASPECT}
ROLE_ASPECT := "ROLE" ":" DESCRIPTION_WITH_REFERENCES
 
AUDIENCE := "[DEFINE_AUDIENCE:]" AUDIENCE_ASPECTS "[END_AUDIENCE]"
AUDIENCE_ASPECTS := {OPTIONAL_ASPECT}
 
CONCEPTS := "[DEFINE_CONCEPTS:]" {CONCEPT} "[END_CONCEPTS]"
CONCEPT := OPTIONAL_ASPECT_NAME ":" STATIC_DESCRIPTION
 
OPTIONAL_ASPECT := OPTIONAL_ASPECT_NAME ":" DESCRIPTION_WITH_REFERENCES
OPTIONAL_ASPECT_NAME := <word>   # e.g. DOMAIN, EXPERTISE, KNOWLEDGE — capitalize
 
DESCRIPTION_WITH_REFERENCES := STATIC_DESCRIPTION {DESCRIPTION_WITH_REFERENCES}
                              | REFERENCE {DESCRIPTION_WITH_REFERENCES}
STATIC_DESCRIPTION := <word> | <word> <space> STATIC_DESCRIPTION
REFERENCE := "<REF>" ["*"] NAME "</REF>"
NAME := SIMPLE_NAME | QUALIFIED_NAME | ARRAY_ACCESS | DICT_ACCESS
SIMPLE_NAME    := <word>
QUALIFIED_NAME := NAME "." SIMPLE_NAME
ARRAY_ACCESS   := NAME "[" [<number>] "]"
DICT_ACCESS    := NAME "[" SIMPLE_NAME "]"
<word> is a sequence of characters, digits and symbols without space
<space> is white space or tab
 
## How to use the inputs
 
INTENT section → PERSONA and AUDIENCE:
  - Best sentence capturing "what this agent does" → ROLE aspect.
  - Sentence naming a technical field → DOMAIN optional aspect.
  - Sentence naming an expertise level → EXPERTISE optional aspect.
  - Sentence explicitly naming who uses this agent → emit AUDIENCE block.
    Omit AUDIENCE if no user group is explicitly named.
 
NOTES section → CONCEPTS:
  - Sentences defining terms ("X means Y") → one CONCEPT per defined term.
  - Background rationale and caveats → skip.
 
Declared symbols section → use <REF> only when ROLE/DOMAIN/EXPERTISE text
explicitly names a declared variable or file by that exact name.
 
## Rules
- Copy wording verbatim from source text. Do not paraphrase.
- Omit AUDIENCE if no user group is named.
- Omit CONCEPTS if no terms are explicitly defined.
- Use 4-space indentation.
- Output ONLY the SPL blocks. No prose, no markdown fences, no explanation.
"""

s4_b_v3 = """\
Emit the [DEFINE_CONSTRAINTS:] block of an SPL specification.
 
## Complete grammar
 
CONSTRAINTS := "[DEFINE_CONSTRAINTS:]" {CONSTRAINT} "[END_CONSTRAINTS]"
CONSTRAINT   := [OPTIONAL_ASPECT_NAME ":"] DESCRIPTION_WITH_REFERENCES
 
OPTIONAL_ASPECT_NAME := <word>
  - Capitalize; derive from requirement topic in CamelCase (e.g. ToolNaming, ApiKeyStorage).
  - One aspect may have multiple CONSTRAINT lines under the same name.
  - Omit only when the requirement has no stable, referenceable identity.
 
DESCRIPTION_WITH_REFERENCES := STATIC_DESCRIPTION {DESCRIPTION_WITH_REFERENCES}
                              | REFERENCE {DESCRIPTION_WITH_REFERENCES}
STATIC_DESCRIPTION := <word> | <word> <space> STATIC_DESCRIPTION
REFERENCE := "<REF>" ["*"] NAME "</REF>"
NAME := SIMPLE_NAME | QUALIFIED_NAME | ARRAY_ACCESS | DICT_ACCESS
SIMPLE_NAME    := <word>
QUALIFIED_NAME := NAME "." SIMPLE_NAME
ARRAY_ACCESS   := NAME "[" [<number>] "]"
DICT_ACCESS    := NAME "[" SIMPLE_NAME "]"
<word> is a sequence of characters, digits and symbols without space
<space> is white space or tab
 
Notes:
- Constraints do not have explicit INPUTS; arguments are inferred from context.
- Use <REF> var_name </REF> only when a constraint naturally references a
  declared variable or file from the symbol table.
 
## Rules
- Copy requirement text VERBATIM. Do not paraphrase.
- One CONSTRAINT entry per distinct normative requirement.
- Append source filename in parentheses: AspectName: text (source.md)
- If no requirements exist:
    [DEFINE_CONSTRAINTS:]
    [END_CONSTRAINTS]
- Use 4-space indentation.
- Output ONLY the [DEFINE_CONSTRAINTS:] ... [END_CONSTRAINTS] block.
  No prose, no markdown fences, no explanation."""

s4_c_v1 = """\
Emit the [DEFINE_VARIABLES:] and [DEFINE_FILES:] blocks of an SPL specification.
 
## Complete grammar
 
VARIABLES := "[DEFINE_VARIABLES:]" {VARIABLE_DECLARATION} "[END_VARIABLES]"
VARIABLE_DECLARATION :=
    ["\"" DESCRIPTION_WITH_REFERENCES "\""]
    ["READONLY"]
    VAR_NAME ":" DATA_TYPE ["=" DEFAULT_VALUE]
VAR_NAME := <word>
 
FILES := "[DEFINE_FILES:]" {FILE_DECLARATION} "[END_FILES]"
FILE_DECLARATION := FOLDER_DECLARATION | LEAF_FILE_DECLARATION
FOLDER_DECLARATION :=
    ["\"" STATIC_DESCRIPTION "\""]
    FILE_NAME FILE_PATH
    "List [" {FOLDER_DECLARATION | LEAF_FILE_DECLARATION} "]"
LEAF_FILE_DECLARATION :=
    ["\"" STATIC_DESCRIPTION "\""]
    ["LOG" <file-exceptions>]
    FILE_NAME FILE_PATH ":" DATA_TYPE
FILE_NAME := <word>
FILE_PATH := <filepath> | "< >"    # < > = not known at compile time; upload at runtime
 
DATA_TYPE := ARRAY_DATA_TYPE | STRUCTURED_DATA_TYPE | ENUM_TYPE | TYPE_NAME
TYPE_NAME  := "text" | "image" | "audio" | "number" | "boolean"
ARRAY_DATA_TYPE      := "List [" DATA_TYPE "]"
STRUCTURED_DATA_TYPE := "{" TYPE_ELEMENT {"," TYPE_ELEMENT} "}" | "{ }"
TYPE_ELEMENT := ["\"" STATIC_DESCRIPTION "\""] ["OPTIONAL"] ELEMENT_NAME ":" DATA_TYPE
ELEMENT_NAME := <word>
ENUM_TYPE := "[" <word> {"," <word>} "]"
 
DESCRIPTION_WITH_REFERENCES := STATIC_DESCRIPTION {DESCRIPTION_WITH_REFERENCES}
                              | REFERENCE {DESCRIPTION_WITH_REFERENCES}
STATIC_DESCRIPTION := <word> | <word> <space> STATIC_DESCRIPTION
REFERENCE := "<REF>" ["*"] NAME "</REF>"
NAME := SIMPLE_NAME | QUALIFIED_NAME | ARRAY_ACCESS | DICT_ACCESS
SIMPLE_NAME := <word>
<word> is a sequence of characters, digits and symbols without space
<space> is white space or tab
 
## Routing rule
 
kind in {Run, Evidence, Record}  → DEFINE_VARIABLES
  entity_id → VAR_NAME; schema_notes → DATA_TYPE (text as fallback)
  READONLY only for configuration constants never modified at runtime.
 
kind == Artifact  → DEFINE_FILES (LEAF_FILE_DECLARATION)
  entity_id → FILE_NAME; file_path → FILE_PATH (use "< >" if empty)
  schema_notes → DATA_TYPE
 
P1 omit-files (data/document/image/audio, read_priority=3) → DEFINE_FILES
  kind → DATA_TYPE (image→image, audio→audio, else text)
 
## Provenance annotations
ASSUMED or LOW_CONFIDENCE entities → add description "Assumed: <schema_notes>"
 
## Rules
- Emit a block only when entities of that kind exist.
- Files sharing a directory → use FOLDER_DECLARATION.
- Use 4-space indentation.
- Output ONLY the SPL blocks. No prose, no markdown fences, no explanation.
"""

s4_d_v2 = """\
Emit the [DEFINE_APIS:] block of an SPL specification.
 
## Complete grammar
 
APIS := "[DEFINE_APIS:]" {API_DECLARATION} "[END_APIS]"
 
API_DECLARATION :=
    ["\"" STATIC_DESCRIPTION "\""]
    API_NAME "<" AUTHENTICATION ">" ["RETRY" <number>] ["LOG" <api-exceptions>]
    OPENAPI_SCHEMA
    API_IN_SPL
 
AUTHENTICATION := "none" | "apikey" | "oauth"
OPENAPI_SCHEMA  := STRUCTURED_TEXT   # OpenAPI schema in structured text
 
API_IN_SPL := "{" "functions:" "[" {FUNCTION} "]" "}"
FUNCTION := "{"
    "name:"        STATIC_DESCRIPTION ","
    "url:"         <url_string> ","
    ["description:" STATIC_DESCRIPTION ","]
    "parameters:"  "{" "parameters:" "[" {PARAMETER} "]" "," "controlled-input:" BOOL "}" ","
    "return:"      "{" "type:" PARAMETER_TYPE "," "controlled-output:" BOOL "}"
"}"
PARAMETER := "{" "required:" BOOL "," "name:" STATIC_DESCRIPTION "," "type:" PARAMETER_TYPE "}"
PARAMETER_TYPE := TYPE_NAME | "List [" TYPE_NAME "]"
TYPE_NAME := "text" | "image" | "audio" | "number" | "boolean"
BOOL := "true" | "false"
API_NAME := <word>   # PascalCase, derived from tool name or step_id
STATIC_DESCRIPTION := <word> | <word> <space> STATIC_DESCRIPTION
<word> is a sequence of characters, digits and symbols without space
<space> is white space or tab
 
## How to use the input
 
Each entry is a workflow step with NETWORK in its effects.
  1. Derive API_NAME in PascalCase from tool_hint or step_id.
  2. AUTHENTICATION from source_text (apikey / oauth / none).
  3. RETRY 3 only if source mentions retry behavior.
  4. Functions: include only parameters explicitly stated in source.
     Use "<url_not_stated>" if no URL given.
     controlled-input and controlled-output: false unless stated.
  5. If partially described, still emit with description "interface partially described".
 
## Rules
- Emit only when network steps are provided.
- One API_DECLARATION per network step.
- Use 4-space indentation.
- Output ONLY the [DEFINE_APIS:] ... [END_APIS] block.
  No prose, no markdown fences, no explanation.
"""

s4_e_v4 = """\
Emit the [DEFINE_WORKER:] block of an SPL specification.
The WORKER orchestrates all declared VARIABLES, FILES, and APIS into a
step-by-step process.
 
## Symbol table — declared names from DEFINE_VARIABLES and DEFINE_FILES
Use these exact names in <REF> references. Do NOT invent new names.
 
{{symbol_table}}
 
## Complete grammar
 
WORKER_INSTRUCTION :=
    "[DEFINE_WORKER:" ["\"" STATIC_DESCRIPTION "\""] WORKER_NAME "]"
    [INPUTS] [OUTPUTS]
    MAIN_FLOW {ALTERNATIVE_FLOW} {EXCEPTION_FLOW}
    [EXAMPLES]
    "[END_WORKER]"
WORKER_NAME := <word>
 
INPUTS  := "[INPUTS]"  {["REQUIRED" | "OPTIONAL"] REFERENCE_DATA} "[END_INPUTS]"
OUTPUTS := "[OUTPUTS]" {["REQUIRED" | "OPTIONAL"] REFERENCE_DATA} "[END_OUTPUTS]"
REFERENCE_DATA := "<REF>" NAME "</REF>"
 
MAIN_FLOW        := "[MAIN_FLOW]" {BLOCK} "[END_MAIN_FLOW]"
ALTERNATIVE_FLOW := "[ALTERNATIVE_FLOW:" CONDITION "]" {BLOCK} "[END_ALTERNATIVE_FLOW]"
EXCEPTION_FLOW   := "[EXCEPTION_FLOW:" CONDITION "]" ["LOG" DESCRIPTION_WITH_REFERENCES] {BLOCK} "[END_EXCEPTION_FLOW]"
CONDITION        := DESCRIPTION_WITH_REFERENCES
 
BLOCK            := SEQUENTIAL_BLOCK | IF_BLOCK | LOOP_BLOCK
SEQUENTIAL_BLOCK := "[SEQUENTIAL_BLOCK]" {COMMAND} "[END_SEQUENTIAL_BLOCK]"
IF_BLOCK    := DECISION_INDEX "[IF" CONDITION "]" {COMMAND}
               {"[ELSEIF" CONDITION "]" {COMMAND}}
               ["[ELSE]" {COMMAND}]
               "[END_IF]"
WHILE_BLOCK := DECISION_INDEX "[WHILE" CONDITION "]" {COMMAND} "[END_WHILE]"
FOR_BLOCK   := DECISION_INDEX "[FOR" CONDITION "]" {COMMAND} "[END_FOR]"
DECISION_INDEX := "DECISION-" <number>
 
COMMAND       := COMMAND_INDEX COMMAND_BODY
COMMAND_INDEX := "COMMAND-" <number>
COMMAND_BODY  := GENERAL_COMMAND | CALL_API | REQUEST_INPUT | DISPLAY_MESSAGE
 
GENERAL_COMMAND :=
    "[COMMAND" ["PROMPT_TO_CODE" | "CODE"]
    DESCRIPTION_WITH_REFERENCES
    ["STOP" DESCRIPTION_WITH_REFERENCES]
    ["RESULT" COMMAND_RESULT ["SET" | "APPEND"]]
    "]"
DISPLAY_MESSAGE := "[DISPLAY" DESCRIPTION_WITH_REFERENCES "]"
REQUEST_INPUT   :=
    "[INPUT" ["DISPLAY"] DESCRIPTION_WITH_REFERENCES
    "VALUE" COMMAND_RESULT ["SET" | "APPEND"]
    "]"
CALL_API :=
    "[CALL" API_NAME {"," API_NAME}
    ["WITH" ARGUMENT_LIST]
    ["RESPONSE" COMMAND_RESULT ["SET" | "APPEND"]]
    "]"
 
COMMAND_RESULT := VAR_NAME ":" DATA_TYPE | REFERENCE
DATA_TYPE := "text" | "image" | "audio" | "number" | "boolean"
           | "List [" DATA_TYPE "]"
           | "{" TYPE_ELEMENT {"," TYPE_ELEMENT} "}" | "{ }"
TYPE_ELEMENT   := ["OPTIONAL"] ELEMENT_NAME ":" DATA_TYPE
ELEMENT_NAME   := <word>
VAR_NAME       := <word>
 
DESCRIPTION_WITH_REFERENCES := STATIC_DESCRIPTION {DESCRIPTION_WITH_REFERENCES}
                              | REFERENCE {DESCRIPTION_WITH_REFERENCES}
STATIC_DESCRIPTION := <word> | <word> <space> STATIC_DESCRIPTION
REFERENCE := "<REF>" ["*"] NAME "</REF>"
NAME := SIMPLE_NAME | QUALIFIED_NAME | ARRAY_ACCESS | DICT_ACCESS
SIMPLE_NAME    := <word>
QUALIFIED_NAME := NAME "." SIMPLE_NAME
ARRAY_ACCESS   := NAME "[" [<number>] "]"
DICT_ACCESS    := NAME "[" SIMPLE_NAME "]"
<word> is a sequence of characters, digits and symbols without space
<space> is white space or tab
 
## MAIN_FLOW construction
 
ALL workflow steps (section A) go in MAIN_FLOW in procedure order.
Do not filter out NETWORK, USER_INPUT, or validation-gate steps.
 
Step → command mapping (use execution_mode and effects):
  effects contains NETWORK         → [CALL ApiName WITH {...} RESPONSE var: TYPE]
                                      Use API names from section C (DEFINE_APIS).
  execution_mode == PROMPT_TO_CODE → [COMMAND PROMPT_TO_CODE description RESULT var: TYPE]
  execution_mode == CODE           → [COMMAND CODE description RESULT var: TYPE]
  execution_mode == USER_INPUT     → [INPUT DISPLAY "description" VALUE answer: TYPE]
                                      TYPE: text (open), boolean (confirm), [v1,v2] (select).
                                      Confirmation blocking progress:
                                        DECISION-N [IF confirmed == false]
                                          COMMAND-N [DISPLAY "Cannot proceed: reason"]
                                        [END_IF]
  all others                       → [COMMAND description RESULT var: TYPE]
                                      (omit RESULT if step produces nothing)
 
  is_validation_gate == true → regular [COMMAND ...]; failure handled by EXCEPTION_FLOW.
 
Branching from workflow prose (section B):
  "if X then Y, otherwise Z" → DECISION-N [IF X] ... [ELSE] ... [END_IF]
  "for each item"            → DECISION-N [FOR each item ...] [END_FOR]
  "while condition"          → DECISION-N [WHILE condition ...] [END_WHILE]
 
INPUTS / OUTPUTS:
  prerequisites not produced by any prior step → [INPUTS] REQUIRED or OPTIONAL
  produces of the final step(s)               → [OUTPUTS] REQUIRED
 
## ALTERNATIVE_FLOW
 
One block per entry in section D (alternative_flows). Omit if section D is empty.
  condition  → CONDITION (free text from AlternativeFlowSpec.condition)
  steps list → body; use same command mapping as MAIN_FLOW
 
## EXCEPTION_FLOW
 
One block per entry in section E (exception_flows). Omit if section E is empty.
  condition → CONDITION (free text from ExceptionFlowSpec.condition)
  log_ref   → if non-empty: LOG <log_ref> on the opening line
  steps list → body; use same command mapping as MAIN_FLOW
 
## Rules
- Global sequential COMMAND numbering: COMMAND-1, COMMAND-2, ... (never restart)
- Global sequential DECISION numbering: DECISION-1, DECISION-2, ... (never restart)
- BLOCKS can be any combination and any number of SEQUENTIAL_BLOCK, IF_BLOCK, LOOP_BLOCK.
- Do NOT generate an [EXAMPLES] block — produced separately by S4F.
- Use 4-space indentation throughout.
- Output ONLY the [DEFINE_WORKER:] ... [END_WORKER] block.
  No prose, no markdown fences, no explanation.
"""

s4_f_v1 = """\
You write the [EXAMPLES] block for an SPL WORKER specification.
 
You receive:
  A. The complete generated WORKER SPL text (already written).
  B. Original examples from the skill documentation.
 
Your task:
  Map each original example to an EXPECTED-WORKER-BEHAVIOR entry.
  Reference actual COMMAND-N numbers from the WORKER text (look them up).
  Write concrete input values and expected output values.
  Trace the execution path through the WORKER for that example.
 
## SYNTAX
 
  [EXAMPLES]
      <EXPECTED-WORKER-BEHAVIOR>
      {
          inputs: { var_name: concrete_value, ... },
          expected-outputs: { var_name: concrete_value, ... },
          execution-path: COMMAND-1, DECISION-1, COMMAND-3, COMMAND-5
      }
      </EXPECTED-WORKER-BEHAVIOR>
 
      <EXPECTED-WORKER-BEHAVIOR>
      ...
      </EXPECTED-WORKER-BEHAVIOR>
  [END_EXAMPLES]
 
Rules:
  - Use only COMMAND-N numbers that actually appear in the WORKER text.
  - Input and output values must be concrete (not placeholders like "<value>").
  - Derive values from the original examples; do not invent them.
  - If an original example does not map cleanly to the WORKER, add it to
    a [NOTE: ...] comment inside [EXAMPLES] explaining why.
  - Use 4-space indentation.
  - Output ONLY the [EXAMPLES] ... [END_EXAMPLES] block.
    No prose, no markdown fences, no explanation.
"""