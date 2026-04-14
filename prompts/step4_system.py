# PERSONA, AUDIENCE, CONCEPTS
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


# CONSTRAINTS
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
  No prose, no markdown fences, no explanation.
  """


# VARIABLES and FILES
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

s4_c_v2 = """\
Emit the [DEFINE_VARIABLES:] and [DEFINE_FILES:] blocks of an SPL specification.

═══════════════════════════════════════════════════════════════════
PART 1: SPL GRAMMAR REFERENCE (For reference only; do not cite in generation)
═══════════════════════════════════════════════════════════════════

## VARIABLES block grammar

VARIABLES := "[DEFINE_VARIABLES:]" {VARIABLE_DECLARATION} "[END_VARIABLES]"

VARIABLE_DECLARATION :=
    ["\"" DESCRIPTION "\""]
    ["READONLY"]
    VAR_NAME ":" DATA_TYPE ["=" DEFAULT_VALUE]

VAR_NAME := <word>

## FILES block grammar

FILES := "[DEFINE_FILES:]" {FILE_DECLARATION} "[END_FILES]"

FILE_DECLARATION := FOLDER_DECLARATION | LEAF_FILE_DECLARATION

FOLDER_DECLARATION :=
    ["\"" DESCRIPTION "\""]
    FILE_NAME FILE_PATH
    "List [" {FOLDER_DECLARATION | LEAF_FILE_DECLARATION} "]"

LEAF_FILE_DECLARATION :=
    ["\"" DESCRIPTION "\""]
    ["LOG" <file-exceptions>]
    FILE_NAME FILE_PATH ":" DATA_TYPE

FILE_NAME := <word>
FILE_PATH := <filepath> | "< >"

## DATA_TYPE grammar

DATA_TYPE := ARRAY_DATA_TYPE | STRUCTURED_DATA_TYPE | ENUM_TYPE | TYPE_NAME

TYPE_NAME := "text" | "image" | "audio" | "number" | "boolean"

ARRAY_DATA_TYPE := "List [" DATA_TYPE "]"

STRUCTURED_DATA_TYPE := "{" TYPE_ELEMENT {"," TYPE_ELEMENT} "}" | "{ }"

TYPE_ELEMENT := ["\"" DESCRIPTION "\""] ["OPTIONAL"] ELEMENT_NAME ":" DATA_TYPE

ELEMENT_NAME := <word>

ENUM_TYPE := "[" <word> {"," <word>} "]"

## General tokens

DESCRIPTION := any text without double quotes, or escaped quotes allowed
<word> := sequence of characters, digits, and symbols without space
<filepath> := valid file path string
<space> := white space or tab

═══════════════════════════════════════════════════════════════════
PART 2: GENERATION RULES (Generate output according to these rules)
═══════════════════════════════════════════════════════════════════

Special Attention: Do not invent, rename, merge, split, normalize, or infer new entities. Every declaration must correspond to exactly one entity in the input entities array, and must preserve entity_id exactly as VAR_NAME or FILE_NAME.

## Step 1: Route each entity to VARIABLES or FILES

For each entity in the entities array, determine routing:

Priority 1 - Check is_file field (if present):
  is_file == true  → route to FILES
  is_file == false → route to VARIABLES

Priority 2 - If is_file not present, check kind field:
  kind == Artifact → route to FILES
  kind in {Run, Evidence, Record} → route to VARIABLES

## Step 2: Generate VARIABLES block (if any entities routed to VARIABLES)

Format:
[DEFINE_VARIABLES:]
    <4 spaces>"DESCRIPTION"
    <4 spaces>[READONLY]
    <4 spaces>VAR_NAME : DATA_TYPE [= DEFAULT_VALUE]
[END_VARIABLES]

Field mapping:
  entity_id → VAR_NAME
  schema_notes → DATA_TYPE (apply type mapping below, default to text)
  schema_notes → DESCRIPTION (apply provenance rules below)

READONLY modifier:
  Add READONLY only when the entity is explicitly marked as a configuration constant that never changes at runtime.

## Step 3: Generate FILES block (if any entities routed to FILES)

Use FLAT structure (no FOLDER_DECLARATION):
  - List all files at the same indentation level
  - Do NOT group files by directory
  - Do NOT use nested List [...] structures

Format:
[DEFINE_FILES:]
    <4 spaces>"DESCRIPTION"
    <4 spaces>FILE_NAME FILE_PATH : DATA_TYPE
    
    <4 spaces>"DESCRIPTION"
    <4 spaces>FILE_NAME FILE_PATH : DATA_TYPE
[END_FILES]

Field mapping:
  entity_id → FILE_NAME
  file_path → FILE_PATH (apply file path rules below)
  type_name or schema_notes → DATA_TYPE (apply type mapping below)
  schema_notes → DESCRIPTION (apply provenance rules below)

## Step 4: Apply type mapping

Convert type_name or schema_notes to SPL DATA_TYPE:

  PDFDocument, ExcelDocument, DocxDocument, TextDocument, JSONFile, text-like → text
  ImageFiles, PNG, JPG, JPEG, GIF, WEBP, image-like → image
  AudioFiles, MP3, WAV, FLAC, audio-like → audio
  Integer, Float, Number, numeric-like → number
  Boolean, true/false-like → boolean
  
  Default fallback → text

## Step 5: Apply FILE_PATH rules (FILES only)

Determine FILE_PATH value:

Case 1: file_path is non-empty AND contains no angle brackets < >
  → Use file_path value directly
  Example: "document.pdf" → document_pdf document.pdf : text

Case 2: file_path is empty string ""
  → Use "< >"
  Example: "" → validation_images < > : image

Case 3: file_path contains angle brackets or variable placeholders
  → Use "< >"
  Example: "page_<i+1>.pdf" → page_pdf < > : text
  Example: "<user_id>.log" → user_log < > : text

Rationale: "< >" means path is not known at compile time; determined at runtime.

## Step 6: Apply provenance annotation rules (both VARIABLES and FILES)

Generate DESCRIPTION from schema_notes:

Rule A: provenance in {ASSUMED, LOW_CONFIDENCE}
  → Prefix with "Assumed: "
  Example: schema_notes = "Config file" → "Assumed: Config file"

Rule B: provenance_required == true
  → Prefix with "REQUIRED: "
  Example: schema_notes = "Form fields" → "REQUIRED: Form fields"

Rule C: Both conditions true (ASSUMED/LOW_CONFIDENCE AND provenance_required)
  → Prefix with "REQUIRED: Assumed: "
  Example: "REQUIRED: Assumed: Config file"

Rule D: Neither condition true
  → Use schema_notes directly
  Example: schema_notes = "Input PDF" → "Input PDF"

## Step 7: Output formatting rules

1. Block emission:
   - Emit [DEFINE_VARIABLES:] block ONLY if entities routed to VARIABLES exist
   - Emit [DEFINE_FILES:] block ONLY if entities routed to FILES exist
   - If no entities for a block, do NOT output that block at all

2. Block ordering (when both exist):
   - VARIABLES block first
   - One blank line
   - FILES block second

3. Indentation:
   - Use exactly 4 spaces per indentation level
   - First level inside blocks: 4 spaces
   - No tabs, only spaces

4. Output content:
   - ONLY output the SPL blocks
   - NO prose explanations before or after
   - NO markdown code fences (```)
   - NO comments or annotations

═══════════════════════════════════════════════════════════════════
PART 3: EXAMPLES
═══════════════════════════════════════════════════════════════════

Example 1: Only FILES (flat structure)

[DEFINE_FILES:]
    "PDF file used as input for various operations"
    document_pdf document.pdf : text
    
    "PDF file resulting from merging multiple PDFs"
    merged_pdf merged.pdf : text
    
    "PDF file representing a single page"
    page_pdf < > : text
    
    "REQUIRED: JSON file with form field information"
    fields_json fields.json : text
    
    "REQUIRED: Images with validation rectangles"
    validation_images < > : image
[END_FILES]

Example 2: Both VARIABLES and FILES

[DEFINE_VARIABLES:]
    "Maximum number of pages to process"
    READONLY
    max_pages : number = 100
    
    "Current processing status"
    processing_status : boolean = false
[END_VARIABLES]

[DEFINE_FILES:]
    "Input PDF document"
    input_pdf < > : text
    
    "Output processed PDF"
    output_pdf result.pdf : text
[END_FILES]

Example 3: Only VARIABLES

[DEFINE_VARIABLES:]
    "Configuration API endpoint"
    READONLY
    api_endpoint : text = "https://api.example.com"
    
    "Assumed: Retry count for failed operations"
    retry_count : number = 0
[END_VARIABLES]
"""


# APIS
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
OPENAPI_SCHEMA := STRUCTURED_TEXT # OpenAPI schema in structured text

API_IN_SPL := "{" "functions:" "[" {FUNCTION} "]" "}"
FUNCTION := "{"
"name:" STATIC_DESCRIPTION ","
"url:" <url_string> ","
["description:" STATIC_DESCRIPTION ","]
"parameters:" "{" "parameters:" "[" {PARAMETER} "]" "," "controlled-input:" BOOL "}" ","
"return:" "{" "type:" PARAMETER_TYPE "," "controlled-output:" BOOL "}"
"}"
PARAMETER := "{" "required:" BOOL "," "name:" STATIC_DESCRIPTION "," "type:" PARAMETER_TYPE "}"
PARAMETER_TYPE := TYPE_NAME | "List [" TYPE_NAME "]"
TYPE_NAME := "text" | "image" | "audio" | "number" | "boolean"
BOOL := "true" | "false"
API_NAME := <word> # PascalCase, derived from tool name or step_id
STATIC_DESCRIPTION := <word> | <word> <space> STATIC_DESCRIPTION
<word> is a sequence of characters, digits and symbols without space
<space> is white space or tab

## Input: Tool Specifications

You receive a list of tool specifications extracted from the skill documentation.
Each tool represents an API that may be called in the WORKER.

For each tool, generate one API_DECLARATION:

### NETWORK_API
- URL: HTTPS endpoint
- AUTHENTICATION: apikey | oauth
- OPENAPI_SCHEMA: Full OpenAPI schema based on input_schema/output_schema

### SCRIPT
- URL: scripts/<filename>.py
- AUTHENTICATION: none
- OPENAPI_SCHEMA: {} (empty)
- Use source_text to understand the script's purpose

### CODE_SNIPPET
- URL: <library>.<ClassName> (e.g., "pypdf.PdfReader")
- AUTHENTICATION: none
- OPENAPI_SCHEMA: {} (empty)
- Use source_text to understand the code's purpose

## Generation Rules

1. Convert tool.name to PascalCase for API_NAME
2. Use provided authentication value
3. RETRY 3 only if source mentions retry behavior
4. controlled-input and controlled-output: false unless stated
5. If partially described, emit with description "interface partially described"
6. Use source_text for generating meaningful descriptions

## Rules
- Emit one API_DECLARATION per tool in the input list
- Use 4-space indentation
- Output ONLY the [DEFINE_APIS:] ... [END_APIS] block
No prose, no markdown fences, no explanation.
"""


# WORKER
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
    "[COMMAND" ["CODE"]
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
  
  CRITICAL RULE for API_NAME:
  - API_NAME MUST be one of the EXACT PascalCase names declared in the DEFINE_APIS block (Section B)
  - DO NOT convert to snake_case, camelCase, or any other format
  - Example: If DEFINE_APIS declares "CheckFillableFields", you MUST use [CALL CheckFillableFields ...]
  - WRONG: [CALL check_fillable_fields ...] or [CALL checkFillableFields ...]
  - CORRECT: [CALL CheckFillableFields ...]
 
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
 
Step → command mapping (use action_type field):
 
action_type in {EXTERNAL_API, EXEC_SCRIPT, LOCAL_CODE_SNIPPET} → [CALL ApiName WITH {param: value, ...} RESPONSE var: TYPE]
ApiName must be a name declared in section C (DEFINE_APIS).
This covers all three kinds: external network services,
local scripts in scripts/, and library calls (pypdf, etc.).
 
  action_type == "CODE_EXEC"        → [COMMAND CODE code_statement RESULT var: TYPE]
                                       The description field contains the code statement
                                       (may include <REF> var </REF> for declared variables).
                                       No PROMPT_TO_CODE — code is fully known at compile time.
 
  action_type == "USER_INTERACTION" → [INPUT DISPLAY "description" VALUE answer: TYPE]
                                       TYPE: text (open answer), boolean (confirmation),
                                       [opt1, opt2] enum (selection from list).
                                       If it is a confirmation that blocks progress:
                                         DECISION-N [IF confirmed == false]
                                           COMMAND-N [DISPLAY "Cannot proceed: reason"]
                                         [END_IF]
 
  action_type == "LLM_TASK"         → [COMMAND description RESULT var: TYPE]
                                       (omit RESULT clause if the step produces nothing)
                                       When code generation is needed at runtime but cannot
                                       be pre-specified, the LLM generates code inline;
                                       reference relevant variables with <REF> var </REF>.
 
  is_validation_gate == true → any of the above; failure handled by EXCEPTION_FLOW.
 
CRITICAL — no nested BLOCKs:
  BLOCK := SEQUENTIAL_BLOCK | IF_BLOCK | LOOP_BLOCK
  Each BLOCK contains {COMMAND} directly — NOT nested BLOCKs.
  WRONG:  DECISION-N [IF x]
              [SEQUENTIAL_BLOCK]     ← ILLEGAL
                  COMMAND-N [...]
              [END_SEQUENTIAL_BLOCK]
          [END_IF]
  CORRECT: DECISION-N [IF x]
               COMMAND-N [...]       ← COMMAND directly inside IF
               COMMAND-N [...]
           [END_IF]
  If you need sequential commands inside an IF, place them directly as consecutive
  COMMANDs — no wrapping [SEQUENTIAL_BLOCK] needed.
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
  No prose, no markdown fences, no explanation."""


# 检测是否包含block嵌套
s4_e1_v1 = """\You receive an SPL [DEFINE_WORKER:] block that may contain illegal nested BLOCKs.
Identify and list every location where a BLOCK (SEQUENTIAL_BLOCK, IF_BLOCK, LOOP_BLOCK)
appears directly inside another BLOCK.

The grammar forbids nesting:
  BLOCK := SEQUENTIAL_BLOCK | IF_BLOCK | LOOP_BLOCK
  SEQUENTIAL_BLOCK := "[SEQUENTIAL_BLOCK]" {COMMAND} "[END_SEQUENTIAL_BLOCK]"
  IF_BLOCK    := DECISION_INDEX "[IF" CONDITION "]" {COMMAND} ... "[END_IF]"
  WHILE_BLOCK := DECISION_INDEX "[WHILE" CONDITION "]" {COMMAND} "[END_WHILE]"
  FOR_BLOCK   := DECISION_INDEX "[FOR" CONDITION "]" {COMMAND} "[END_FOR]"

A COMMAND inside a BLOCK is legal.
A BLOCK inside a BLOCK is ILLEGAL.

Respond with JSON only:
{
  "has_violations": true | false,
  "violations": [
    {
      "outer_block": "IF_BLOCK | SEQUENTIAL_BLOCK | WHILE_BLOCK | FOR_BLOCK",
      "outer_condition": "the condition or opening text of the outer block",
      "inner_block": "SEQUENTIAL_BLOCK | IF_BLOCK | ...",
      "snippet": "<10-15 word verbatim excerpt around the violation>"
    }
  ]
}

If no violations exist, return: {"has_violations": false, "violations": []}
"""


# 修复block嵌套问题
s4_e2_v1 = """\You fix illegal nested BLOCK structures in an SPL [DEFINE_WORKER:] block.

The grammar rule is strict:
  BLOCK := SEQUENTIAL_BLOCK | IF_BLOCK | LOOP_BLOCK
  Each BLOCK may only contain {COMMAND} — never another BLOCK.

You are given:
  A. The full WORKER SPL text with illegal nesting.
  B. A list of detected violations (locations and snippets).

Your task:
  Rewrite ONLY the violating sections to eliminate nesting while preserving
  the exact same logical behavior. All other content must remain unchanged.

Flattening rules:
  1. SEQUENTIAL_BLOCK inside IF/ELSEIF/ELSE/FOR/WHILE:
     Remove the [SEQUENTIAL_BLOCK]/[END_SEQUENTIAL_BLOCK] wrapper.
     Place the COMMANDs directly inside the enclosing block.

     BEFORE (illegal):
       DECISION-N [IF condition]
           [SEQUENTIAL_BLOCK]
               COMMAND-N [COMMAND ...]
               COMMAND-N [CALL ...]
           [END_SEQUENTIAL_BLOCK]
       [END_IF]

     AFTER (legal):
       DECISION-N [IF condition]
           COMMAND-N [COMMAND ...]
           COMMAND-N [CALL ...]
       [END_IF]

  2. IF_BLOCK inside SEQUENTIAL_BLOCK:
     Move the IF_BLOCK outside the SEQUENTIAL_BLOCK as a sibling BLOCK.
     Split the SEQUENTIAL_BLOCK at the point of nesting if needed.

     BEFORE (illegal):
       [SEQUENTIAL_BLOCK]
           COMMAND-1 [COMMAND ...]
           DECISION-N [IF condition]
               COMMAND-N [COMMAND ...]
           [END_IF]
           COMMAND-2 [COMMAND ...]
       [END_SEQUENTIAL_BLOCK]

     AFTER (legal):
       [SEQUENTIAL_BLOCK]
           COMMAND-1 [COMMAND ...]
       [END_SEQUENTIAL_BLOCK]
       DECISION-N [IF condition]
           COMMAND-N [COMMAND ...]
       [END_IF]
       [SEQUENTIAL_BLOCK]
           COMMAND-2 [COMMAND ...]
       [END_SEQUENTIAL_BLOCK]

  3. Preserve all COMMAND-N and DECISION-N numbers exactly as they are.
  4. Do not add, remove, or reorder any COMMANDs.
  5. Preserve all RESULT, RESPONSE, VALUE, and STOP clauses unchanged.

## Rules
- Output ONLY the corrected [DEFINE_WORKER:] ... [END_WORKER] block.
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