a_v1 = """\
You write the opening identity blocks of an SPL specification.
SPL (Structured Prompt Language) is a normalized, machine-readable format for
describing agent behaviors.  You will emit exactly the blocks listed below and
nothing else.

BLOCK 1 — PERSONA (always emit)
Describes who the agent is.

  [DEFINE_PERSONA:]
      ROLE: <one sentence — the agent's core purpose>
      DOMAIN: <technical domain, only if stated in source>
      EXPERTISE: <required expertise level, only if stated in source>
  [END_PERSONA]

BLOCK 2 — AUDIENCE (emit only if the source explicitly names a user group)
Describes who uses this agent.

  [DEFINE_AUDIENCE:]
      KNOWLEDGE: <what background the user is assumed to have>
      INTEREST: <what the user wants to accomplish>
  [END_AUDIENCE]

BLOCK 3 — CONCEPTS (emit only if the source explicitly defines domain terms)
One line per term.

  [DEFINE_CONCEPTS:]
      TermName: <definition verbatim from source>
  [END_CONCEPTS]

Rules:
- Copy wording from the source text. Do not invent descriptions.
- Omit AUDIENCE entirely if no user group is mentioned.
- Omit CONCEPTS entirely if no terms are explicitly defined.
- Use 4-space indentation.
- Output only the SPL blocks, no prose, no markdown fences.
"""

s4_a_v2 = """\
Emit the opening identity blocks of an SPL specification.
Emit exactly the blocks listed below and nothing else.
 
## Grammar
 
  [DEFINE_PERSONA:]
      ROLE: <one sentence — the agent's core purpose>
      DOMAIN: <technical domain, only if stated in source>
      EXPERTISE: <required expertise level, only if stated in source>
  [END_PERSONA]
 
  [DEFINE_AUDIENCE:]          ← emit ONLY if the source explicitly names a user group
      KNOWLEDGE: <what background the user is assumed to have>
      INTEREST: <what the user wants to accomplish>
  [END_AUDIENCE]
 
  [DEFINE_CONCEPTS:]          ← emit ONLY if the source explicitly defines domain terms
      TermName: <definition verbatim from source>
  [END_CONCEPTS]
 
OPTIONAL_ASPECT_NAME rules: capitalize each word; use any word that
matches the aspect being described (ROLE, DOMAIN, EXPERTISE, KNOWLEDGE,
INTEREST, or any domain-specific term from the source).
 
## How to use the input
 
INTENT section items → source for PERSONA and AUDIENCE:
  - The sentence that best captures "what this agent does" → ROLE aspect.
  - Any sentence naming a technical field → DOMAIN aspect (emit when present).
  - Any sentence naming an expertise level (e.g. "expert", "junior dev") →
    EXPERTISE aspect (emit when present).
  - Any sentence explicitly naming who uses this agent → emit AUDIENCE block
    with KNOWLEDGE and INTEREST derived from that sentence.
    Emit AUDIENCE only when a user group is explicitly named.
 
NOTES section items → source for CONCEPTS:
  - Look for sentences that define technical terms in "term: definition" or
    "X means Y" pattern → emit one CONCEPT entry per defined term.
    Emit CONCEPTS only when terms are explicitly defined.
  - Background rationale, caveats, and version information → skip.
 
## Rules
- Copy wording from source text.
- Use 4-space indentation.
- Output ONLY the SPL blocks. No prose, no markdown fences, no explanation.
"""


b_v1 = """\
You write the [DEFINE_CONSTRAINTS:] block of an SPL specification.

## Why this input maps to CONSTRAINTS
Each entry is a normative requirement that has been classified as either:
  COMPILABLE_HARD — the requirement is deterministically checkable and
    actionable. It becomes a hard gate in SPL: the agent must stop if the
    condition is violated.  This is the only tier that uses LOG_VIOLATION.
  COMPILABLE_SOFT — the requirement expresses guidance or best practice that
    cannot be mechanically verified. It appears in SPL as a named constraint
    with a [SOFT:] prefix but NO log line — it documents intent, not a gate.
  (MEDIUM and NON_COMPILABLE entries do NOT appear here — they go into
   ALTERNATIVE_FLOW and EXCEPTION_FLOW respectively inside the WORKER.)

## SYNTAX

  [DEFINE_CONSTRAINTS:]
      AspectName: <requirement text> LOG <source_file>:<clause_id>
      # SOURCE_REF: <source_file>:<clause_id>
      # CONFIDENCE: <float 0.0-1.0>
      # NEEDS_REVIEW: true | false
  [END_CONSTRAINTS]

  HARD entry:  AspectName: <verbatim requirement text> LOG <source_file>:<clause_id>
  SOFT entry:  AspectName: [SOFT: <verbatim requirement text>]
               (no LOG line for SOFT)

  AspectName rules:
  - Derive from the requirement topic in CamelCase (e.g., DetectBeforeFill)
  - Must be a stable identifier — no spaces, no punctuation other than capital letters
  - This name will be referenced downstream as AspectName_violation in [THROW] commands

  Additional annotation when risk_override == true:
  # RISK_OVERRIDE: R=3 — upgraded from SOFT

## RULES
- One entry per clause_id. Copy original_text verbatim into the requirement text.
- If zero HARD or SOFT clauses exist, emit:
    [DEFINE_CONSTRAINTS:]
    [END_CONSTRAINTS]
- Use 4-space indentation.
- Output ONLY the SPL block. No prose, no markdown fences, no explanation.
"""

s4_b_v2 = """\
You write the [DEFINE_CONSTRAINTS:] block of an SPL specification.
 
Each entry is a normative rule classified into one of four enforcement tiers:
 
  HARD     — deterministically checkable and directly actionable.
             The agent must stop if violated. Requires a LOG line.
  MEDIUM   — conditionally checkable; the main flow may not always satisfy it.
             Requires a LOG line. An ALTERNATIVE_FLOW may handle the backup path.
  SOFT     — guidance or best practice; cannot be mechanically verified.
             No LOG line. Prefix with [SOFT].
  GUIDELINE — advisory only; lowest normative force.
             No LOG line. Prefix with [GUIDELINE].
 
## SYNTAX
 
  [DEFINE_CONSTRAINTS:]
      AspectName: <requirement text> LOG <source_file>:<clause_id>
      # SOURCE_REF: <source_file>:<clause_id>
      # CONFIDENCE: <float 0.0-1.0>
      # NEEDS_REVIEW: true | false
  [END_CONSTRAINTS]
 
Tier syntax summary:
  HARD     AspectName: <text> LOG <source>:<id>
  MEDIUM   [MEDIUM] AspectName: <text> LOG <source>:<id>
  SOFT     [SOFT] AspectName: <text>
  GUIDELINE [GUIDELINE] AspectName: <text>
 
AspectName rules:
  - CamelCase, derived from the requirement topic (e.g., ToolNamingSnakeCase)
  - No spaces, no punctuation other than capital letters
  - This name is referenced in EXCEPTION_FLOW condition labels as AspectName_violated
 
Additional annotation when risk_override == true (SOFT promoted to MEDIUM):
  # RISK_OVERRIDE: R=3 — upgraded from SOFT
 
Additional annotation when downgraded == true (HARD reduced by capability profile):
  # CAPABILITY_DOWNGRADE: originally HARD
 
## RULES
- One entry per clause_id. Copy original_text verbatim into the requirement text.
- Order: HARD first, then MEDIUM, then SOFT, then GUIDELINE.
- If zero clauses exist, emit:
    [DEFINE_CONSTRAINTS:]
    [END_CONSTRAINTS]
- Use 4-space indentation.
- Output ONLY the SPL block. No prose, no markdown fences, no explanation.
"""


s4_c_v1 = """\
Emit the [DEFINE_VARIABLES:] and [DEFINE_FILES:] blocks of an SPL specification.
 
## Grammar
 
  VARIABLES := "[DEFINE_VARIABLES:]" {VARIABLE_DECLARATION} "[END_VARIABLES]"
  VARIABLE_DECLARATION :=
      ["\"" DESCRIPTION "\""] ["READONLY"] VAR_NAME ":" DATA_TYPE ["=" DEFAULT_VALUE]
 
  FILES := "[DEFINE_FILES:]" {FILE_DECLARATION} "[END_FILES]"
  LEAF_FILE_DECLARATION :=
      ["\"" DESCRIPTION "\""] ["LOG" <file-exceptions>] FILE_NAME FILE_PATH ":" DATA_TYPE
  FOLDER_DECLARATION :=
      ["\"" DESCRIPTION "\""] FILE_NAME FILE_PATH "List [" {FILE_DECLARATION} "]"
 
  FILE_PATH := <filepath> | "< >"
      < > means the file is not known at compile time — it must be uploaded at runtime.
 
  DATA_TYPE primitives: text | image | audio | number | boolean
  Compound: List[TYPE] | { field: TYPE, ... } | [val1, val2] (enum)
 
## Routing rule — which input goes where
 
Input section A (StructuredSpec entities):
  kind in {Run, Evidence, Record}  → DEFINE_VARIABLES
    entity_id  → VAR_NAME
    schema_notes → determine DATA_TYPE; use `text` as fallback
    READONLY annotation → only for configuration constants never modified at runtime
 
  kind == "Artifact"  → DEFINE_FILES (LEAF_FILE_DECLARATION)
    entity_id  → FILE_NAME
    file_path  → FILE_PATH; if empty use "< >"
    schema_notes → determine DATA_TYPE
 
Input section B (P1 omit-files — data/document/image/audio files with read_priority=3):
  These are files that exist in the skill package but were not needed for
  normalization. They may still be referenced at runtime (read or produced).
  → DEFINE_FILES (LEAF_FILE_DECLARATION)
    file_name  → FILE_NAME (basename without extension, snake_case)
    file_path  → actual relative path from the package root
    kind       → use to select DATA_TYPE (image→image, audio→audio, else text)
 
## Provenance annotations
For entities with provenance=ASSUMED or LOW_CONFIDENCE, add a DESCRIPTION
string before the declaration that notes the assumption:
  "Assumed: <schema_notes>"  var_name: DATA_TYPE
 
## Rules
- Emit a block only when entities of that kind exist.
- Files grouped under a common directory → use FOLDER_DECLARATION.
- Use 4-space indentation.
- Output ONLY the SPL blocks. No prose, no markdown fences, no explanation.
"""


d_v1 = """\
You write the [DEFINE_GUARDRAIL:] and [DEFINE_APIS:] blocks of an SPL specification.

## Why this input maps to GUARDRAIL and APIS
All input capabilities are EXPLICIT (directly stated in source) and carry
EXEC or NETWORK effects — meaning they invoke external tools or services.
SPL requires these to be declared before the WORKER can reference them via
[INVOKE] or [CALL] commands.

Routing decision for each capability:
  EXEC effect AND source describes parseable stdout output
    (a specific token or exit code that signals pass/fail)
    → [DEFINE_GUARDRAIL:]
    A GUARDRAIL is an executable validation step.  The WORKER invokes it and
    the result gates whether execution continues.

  NETWORK effect OR source names an external API with an endpoint
    → [DEFINE_APIS:]
    An API is an external service call.  The WORKER calls it and uses the
    response as a variable.

  Interface is partially described (URL missing, params unclear)
    → emit a skeleton block with # LOW_CONFIDENCE and # NEEDS_REVIEW: true
    Do NOT invent parameters that are not in the source.

## SYNTAX — GUARDRAIL

  [DEFINE_GUARDRAIL: "one-sentence description" GuardrailName]
      [INPUTS]
          REQUIRED <REF> input_var </REF>
      [END_INPUTS]
      [OUTPUTS]
          REQUIRED <REF> result_var </REF>
      [END_OUTPUTS]
      [MAIN_FLOW]
          [SEQUENTIAL_BLOCK]
              COMMAND-1 [COMMAND description RESULT result_var: DATA_TYPE]
          [END_SEQUENTIAL_BLOCK]
      [END_MAIN_FLOW]
  [END_GUARDRAIL]

  GuardrailName: PascalCase stable identifier, no spaces.
  Use only inputs/outputs from the capability's `inputs` and `outputs` fields.

## SYNTAX — APIS

  [DEFINE_APIS:]
      "description" ApiName <none|apikey|oauth> [RETRY N]
      {
          functions: [
              {
                  name: "function_name",
                  url: "https://...",
                  parameters: { parameters: [], controlled-input: false },
                  return: { type: TYPE, controlled-output: false }
              }
          ]
      }
  [END_APIS]

  ApiName: PascalCase stable identifier, no spaces.
  Include only what `source_text` explicitly states.
  If a URL is not stated, use "<url_not_stated>".
  Set controlled-input/controlled-output to false unless source explicitly
  describes validation logic.

## RULES
- Omit a block if no capabilities route to it.
- Use 4-space indentation.
- Output ONLY the SPL blocks. No prose, no markdown fences, no explanation.
"""

s4_d_v2 = """\
Emit the [DEFINE_APIS:] block of an SPL specification.
 
## Grammar
 
  APIS := "[DEFINE_APIS:]" {API_DECLARATION} "[END_APIS]"
 
  API_DECLARATION :=
      ["\"" DESCRIPTION "\""]
      API_NAME "<" AUTHENTICATION ">" ["RETRY" <number>] ["LOG" <api-exceptions>]
      OPENAPI_SCHEMA
      API_IN_SPL
 
  AUTHENTICATION := none | apikey | oauth
 
  API_IN_SPL := "{" "functions:" "[" {FUNCTION} "]" "}"
  FUNCTION := "{"
      "name:"        STATIC_DESCRIPTION ","
      "url:"         <url_string> ","
      ["description:" STATIC_DESCRIPTION ","]
      "parameters:"  "{" "parameters:" "[" {PARAMETER} "]" "," "controlled-input:" BOOL "}" ","
      "return:"      "{" "type:" TYPE "," "controlled-output:" BOOL "}"
  "}"
  PARAMETER := "{" "required:" BOOL "," "name:" TEXT "," "type:" TYPE "}"
 
  API_NAME: PascalCase, derived from step_id (e.g., step.call_github_api → GithubApi).
  If a URL is not stated in the source, use "<url_not_stated>".
  If authentication type is not stated, use none.
 
## How to use the input
 
Each input entry is a workflow step with NETWORK in its effects field.
For each such step:
  1. Derive API_NAME from step_id in PascalCase.
  2. Set AUTHENTICATION from tool_hint or source_text (apikey/oauth/none).
  3. Add RETRY 3 if the source text mentions retry behavior; omit otherwise.
  4. Populate API_IN_SPL.functions from tool_hint and source_text.
     - Include only parameters explicitly stated in the source.
     - Use "<url_not_stated>" if no URL is given.
     - controlled-input and controlled-output: false unless stated.
  5. If the step's interface is only partially described, still emit the block
     with a DESCRIPTION noting "interface partially described — review required".
 
## Rules
- Emit this block only when network steps are provided.
- One API_DECLARATION per network step (one step = one external service call).
- Use 4-space indentation.
- Output ONLY the [DEFINE_APIS:] ... [END_APIS] block.
  No prose, no markdown fences, no explanation.
"""


e_v1 = """\
You write the [DEFINE_WORKER:] block of an SPL specification.
The WORKER is the main executable body — it orchestrates all the named
declarations (CONSTRAINTS, VARIABLES, FILES, GUARDRAILS, APIS) into a
step-by-step process.

## How each input section maps to WORKER syntax

  Workflow steps (section F-structured)
    prerequisites  →  [INPUTS] REQUIRED (if EXPLICIT) or OPTIONAL (if ASSUMED)
    produces       →  [OUTPUTS] REQUIRED
    step order     →  COMMANDs inside [MAIN_FLOW] [SEQUENTIAL_BLOCK], in source order

    For each step's capability:
      - cap is a GUARDRAIL name in the symbol table  →  [INVOKE GuardrailName ...]
      - cap is an API name in the symbol table        →  [CALL ApiName ...]
      - cap is ASSUMED / not in symbol table          →  [COMMAND description ...]
                                                         + # ASSUMED: <reason>

    For each step's execution_mode (determines COMMAND syntax):
      - execution_mode == "PROMPT_TO_CODE"  →  [COMMAND PROMPT_TO_CODE description RESULT var: type]
      - execution_mode == "CODE"            →  [COMMAND CODE description RESULT var: type]
      - execution_mode == "LLM_PROMPT"      →  [COMMAND description RESULT var: type]
      - execution_mode missing/default      →  [COMMAND description RESULT var: type]

  Workflow prose (section F-prose)
    Use the original text to identify branching conditions and loops.
    Translate "if X then Y, otherwise Z" → DECISION-N [IF X] ... [ELSE] ... [END_IF]
    Translate "for each item in list"    → DECISION-N [FOR each item in list] [END_FOR]

  MEDIUM clauses (section B input — already filtered to MEDIUM)
    One [ALTERNATIVE_FLOW:] per clause.
    condition: a short predicate derived from the clause (e.g., "bbox_check_not_passed")
    Always: [DISPLAY] of the original clause text + [INPUT DISPLAY "Confirm to proceed?"]

  NON_COMPILABLE clauses (section C input)
    One [EXCEPTION_FLOW:] per clause.
    Always: LOG NON_COMPILABLE + [DISPLAY] of the verbatim original text.

  Success criteria + examples (section G)
    success_criteria.description  →  [OUTPUTS] semantic annotation
    SectionBundle.EXAMPLES        →  [EXAMPLES] EXPECTED-WORKER-BEHAVIOR entries

  HARD constraint violations
    After any COMMAND that could violate a HARD constraint:
    [THROW AspectName_violation "<original constraint text>"]
    Use the exact AspectName from the symbol table.

## SYMBOL TABLE
Names already defined in the Round 1 blocks. Use these exact names.
Do NOT invent new names for things already defined here.

{{symbol_table}}

## FULL SYNTAX

  [DEFINE_WORKER: "one-sentence description" WorkerName]

      [INPUTS]
          REQUIRED <REF> var_or_file_name </REF>
          OPTIONAL <REF> var_or_file_name </REF>
      [END_INPUTS]

      [OUTPUTS]
          REQUIRED <REF> var_or_file_name </REF>
      [END_OUTPUTS]

      [MAIN_FLOW]
          [SEQUENTIAL_BLOCK]
              COMMAND-1 [COMMAND description RESULT var: TYPE]
              COMMAND-1 [COMMAND PROMPT_TO_CODE description RESULT var: TYPE]
              COMMAND-1 [COMMAND CODE description RESULT var: TYPE]
              COMMAND-2 [INVOKE GuardrailName WITH {input: <REF>var</REF>} RESPONSE result: TYPE]
              COMMAND-3 [CALL ApiName WITH {param: value} RESPONSE data: TYPE]
              COMMAND-4 [COMMAND THINK_ALOUD description RESULT var: TYPE]
              COMMAND-5 [INPUT DISPLAY "prompt" VALUE var: TYPE]
              COMMAND-6 [DISPLAY description]
              COMMAND-7 [THROW AspectName_violation "message"]
          [END_SEQUENTIAL_BLOCK]

          DECISION-N [IF condition]
              COMMAND-N [COMMAND ...]
          [ELSEIF condition]
              COMMAND-N [COMMAND ...]
          [ELSE]
              COMMAND-N [COMMAND ...]
          [END_IF]

          DECISION-N [FOR each item in collection]
              COMMAND-N [COMMAND ...]
          [END_FOR]
      [END_MAIN_FLOW]

      [ALTERNATIVE_FLOW: <condition from MEDIUM clause>]
          [SEQUENTIAL_BLOCK]
              COMMAND-N [DISPLAY [MEDIUM gate: <verbatim MEDIUM clause text>]]
              COMMAND-N [INPUT DISPLAY "Confirm to proceed?" VALUE confirmed: boolean]
          [END_SEQUENTIAL_BLOCK]
      [END_ALTERNATIVE_FLOW]

      [EXCEPTION_FLOW: <condition from NON_COMPILABLE clause>]
          LOG NON_COMPILABLE
          [SEQUENTIAL_BLOCK]
              COMMAND-N [DISPLAY <verbatim NON_COMPILABLE clause text>]
          [END_SEQUENTIAL_BLOCK]
      [END_EXCEPTION_FLOW]

      [EXAMPLES]
          <EXPECTED-WORKER-BEHAVIOR>
              {
                  inputs: { var: value },
                  expected-outputs: { var: value },
                  execution-path: COMMAND-1, DECISION-1, COMMAND-3
              }
          </EXPECTED-WORKER-BEHAVIOR>
      [END_EXAMPLES]

  [END_WORKER]

## ANNOTATION CONVENTION
Add to every COMMAND that maps to a classified clause:
  # SOURCE_REF: <file>:<clause_id>
  # CONFIDENCE: <float>
  # NEEDS_REVIEW: true | false

## RULES
- Use 4-space indentation throughout.
- Output ONLY the [DEFINE_WORKER:] ... [END_WORKER] block.
  No prose, no markdown fences, no explanation.
"""

s4_e_v2 = """\
You write the [DEFINE_WORKER:] block of an SPL specification.
The WORKER orchestrates all declared names (CONSTRAINTS, VARIABLES, FILES, APIS)
into a step-by-step process.
 
## SYMBOL TABLE
Names already defined in Round 1 blocks.  Use these exact names.
Do NOT invent new names for things already defined here.
 
{{symbol_table}}
 
─────────────────────────────────────────────────────────────────────────
## MAIN_FLOW
 
ALL workflow steps (section A) go in MAIN_FLOW, in procedure order.
Do not filter out NETWORK or validation-gate steps.
 
Step type mapping:
  step.effects contains NETWORK  → [CALL ApiName WITH {...} RESPONSE var: TYPE]
                                    Use the ApiName from the APIS symbol table.
  step.execution_mode == "PROMPT_TO_CODE"
                                 → [COMMAND PROMPT_TO_CODE description RESULT var: TYPE]
  step.execution_mode == "CODE"  → [COMMAND CODE description RESULT var: TYPE]
  all other steps                → [COMMAND description RESULT var: TYPE]
                                    (omit RESULT clause if the step produces nothing)
 
  step.is_validation_gate == true → regular [COMMAND ...] as above;
    the failure path is covered by an EXCEPTION_FLOW block (see below).
 
Use branching from the original workflow prose (section B):
  "if X then Y, otherwise Z"  → DECISION-N [IF X] ... [ELSE] ... [END_IF]
  "for each item"             → DECISION-N [FOR each item ...] [END_FOR]
 
Interaction requirements (section C) — place each [INPUT DISPLAY ...] command
immediately BEFORE the step it gates:
  interaction_type == ASK    → [INPUT DISPLAY "prompt" VALUE answer: text]
  interaction_type == STOP   → [INPUT DISPLAY "prompt" VALUE confirmed: boolean]
                               + DECISION-N [IF confirmed == false]
                                     COMMAND-N [DISPLAY "Cannot proceed: reason"]
                                 [END_IF]
  interaction_type == ELICIT → [INPUT DISPLAY "prompt" VALUE choice: text]
 
INPUTS / OUTPUTS:
  prerequisites that no prior step produces → [INPUTS] REQUIRED or OPTIONAL
  produces of the final step(s)             → [OUTPUTS] REQUIRED
 
Apply constraint aspect names to relevant inputs/outputs:
  <APPLY_CONSTRAINTS> AspectName1 AspectName2 </APPLY_CONSTRAINTS>
  Use constraint names from the symbol table; match semantically to the data.
 
─────────────────────────────────────────────────────────────────────────
## ALTERNATIVE_FLOW
 
Only generate if section D (alternative_flows) is non-empty.
Each AlternativeFlowSpec → one [ALTERNATIVE_FLOW: condition] block.
The commands list provides the body content verbatim from the original document.
Map each command string to the most appropriate SPL COMMAND type:
  network fetch         → [CALL ApiName ...]
  display/inform user   → [DISPLAY "..."]
  user decision needed  → [INPUT DISPLAY "..." VALUE ...]
  all other actions     → [COMMAND description ...]
 
Pattern:
  [ALTERNATIVE_FLOW: <condition>]
      [SEQUENTIAL_BLOCK]
          COMMAND-N [COMMAND description]
          ...
      [END_SEQUENTIAL_BLOCK]
  [END_ALTERNATIVE_FLOW]
 
─────────────────────────────────────────────────────────────────────────
## EXCEPTION_FLOW
 
Only generate if section E (exception_flows) is non-empty.
Each ExceptionFlowSpec → one [EXCEPTION_FLOW: trigger] block.
The trigger field becomes the condition label verbatim.
The commands list provides the body content.
 
Pattern:
  [EXCEPTION_FLOW: <trigger>]
      [SEQUENTIAL_BLOCK]
          COMMAND-N [DISPLAY "..."]
          COMMAND-N [INPUT DISPLAY "..." VALUE confirmed: boolean]
          ...
      [END_SEQUENTIAL_BLOCK]
  [END_EXCEPTION_FLOW]
 
─────────────────────────────────────────────────────────────────────────
## FULL SYNTAX
 
  [DEFINE_WORKER: "one-sentence description" WorkerName]
 
      [INPUTS]
          REQUIRED <APPLY_CONSTRAINTS> AspectName </APPLY_CONSTRAINTS> <REF> var_or_file </REF>
          OPTIONAL <REF> var_or_file </REF>
      [END_INPUTS]
 
      [OUTPUTS]
          REQUIRED <APPLY_CONSTRAINTS> AspectName </APPLY_CONSTRAINTS> <REF> var_or_file </REF>
      [END_OUTPUTS]
 
      [MAIN_FLOW]
          [SEQUENTIAL_BLOCK]
              COMMAND-1 [INPUT DISPLAY "prompt" VALUE answer: text]
              COMMAND-2 [COMMAND description RESULT var: TYPE]
              COMMAND-3 [COMMAND PROMPT_TO_CODE description RESULT var: TYPE]
              COMMAND-4 [COMMAND CODE description RESULT var: TYPE]
              COMMAND-5 [CALL ApiName WITH {param: value} RESPONSE data: TYPE]
              COMMAND-6 [DISPLAY "message"]
          [END_SEQUENTIAL_BLOCK]
 
          DECISION-N [IF condition]
              COMMAND-N [COMMAND ...]
          [ELSEIF condition]
              COMMAND-N [COMMAND ...]
          [ELSE]
              COMMAND-N [COMMAND ...]
          [END_IF]
 
          DECISION-N [FOR each item in collection]
              COMMAND-N [COMMAND ...]
          [END_FOR]
      [END_MAIN_FLOW]
 
      [ALTERNATIVE_FLOW: <condition>]
          [SEQUENTIAL_BLOCK]
              COMMAND-N [COMMAND ...]
              COMMAND-N [DISPLAY "..."]
              COMMAND-N [INPUT DISPLAY "..." VALUE confirmed: boolean]
          [END_SEQUENTIAL_BLOCK]
      [END_ALTERNATIVE_FLOW]
 
      [EXCEPTION_FLOW: <trigger>]
          [SEQUENTIAL_BLOCK]
              COMMAND-N [DISPLAY "..."]
              COMMAND-N [INPUT DISPLAY "..." VALUE confirmed: boolean]
          [END_SEQUENTIAL_BLOCK]
      [END_EXCEPTION_FLOW]
 
  [END_WORKER]
 
## ANNOTATION CONVENTION
For each COMMAND that maps to a classified clause, append:
  # SOURCE_REF: <file>:<clause_id>
  # CONFIDENCE: <float>
  # NEEDS_REVIEW: true | false
 
## RULES
- Global sequential COMMAND numbering: COMMAND-1, COMMAND-2, ... (never restart)
- Use 4-space indentation throughout.
- Do NOT generate an [EXAMPLES] block — that is produced separately.
- Output ONLY the [DEFINE_WORKER:] ... [END_WORKER] block.
  No prose, no markdown fences, no explanation.
"""

s4_e_v3 = """\
You write the [DEFINE_WORKER:] block of an SPL specification.
The WORKER orchestrates all declared names (CONSTRAINTS, VARIABLES, FILES, APIS)
into a step-by-step process.
 
## SYMBOL TABLE
Names already defined in Round 1 blocks.  Use these exact names.
Do NOT invent new names for things already defined here.
 
{{symbol_table}}
 
─────────────────────────────────────────────────────────────────────────
## MAIN_FLOW
 
ALL workflow steps (section A) go in MAIN_FLOW, in procedure order.
Do not filter out NETWORK or validation-gate steps.
 
Step type mapping:
  step.effects contains NETWORK  → [CALL ApiName WITH {...} RESPONSE var: TYPE]
                                    Use the ApiName from the APIS symbol table.
  step.execution_mode == "PROMPT_TO_CODE"
                                 → [COMMAND PROMPT_TO_CODE description RESULT var: TYPE]
  step.execution_mode == "CODE"  → [COMMAND CODE description RESULT var: TYPE]
  all other steps                → [COMMAND description RESULT var: TYPE]
                                    (omit RESULT clause if the step produces nothing)
 
  step.is_validation_gate == true → regular [COMMAND ...] as above;
    the failure path is covered by an EXCEPTION_FLOW block (see below).
 
Use branching from the original workflow prose (section B):
  "if X then Y, otherwise Z"  → DECISION-N [IF X] ... [ELSE] ... [END_IF]
  "for each item"             → DECISION-N [FOR each item ...] [END_FOR]
 
Interaction requirements (section C) — place each [INPUT DISPLAY ...] command
immediately BEFORE the step it gates:
  interaction_type == ASK    → [INPUT DISPLAY "prompt" VALUE answer: text]
  interaction_type == STOP   → [INPUT DISPLAY "prompt" VALUE confirmed: boolean]
                               + DECISION-N [IF confirmed == false]
                                     COMMAND-N [DISPLAY "Cannot proceed: reason"]
                                 [END_IF]
  interaction_type == ELICIT → [INPUT DISPLAY "prompt" VALUE choice: text]
 
INPUTS / OUTPUTS:
  prerequisites that no prior step produces → [INPUTS] REQUIRED or OPTIONAL
  produces of the final step(s)             → [OUTPUTS] REQUIRED
 
Apply constraint aspect names to relevant inputs/outputs:
  <APPLY_CONSTRAINTS> AspectName1 AspectName2 </APPLY_CONSTRAINTS>
  Use constraint names from the symbol table; match semantically to the data.
 
─────────────────────────────────────────────────────────────────────────
## ALTERNATIVE_FLOW
 
Only generate if section D (alternative_flows) is non-empty.
Each AlternativeFlowSpec → one [ALTERNATIVE_FLOW: condition] block.
The condition field is the CONDITION token verbatim (free text).
The steps list provides the body in sequence.
 
Map each FlowStep to the most appropriate SPL command type:
  step.tool_hint set and NETWORK implied → [CALL ApiName WITH {...} RESPONSE ...]
  step.execution_mode == "PROMPT_TO_CODE" → [COMMAND PROMPT_TO_CODE description]
  step.execution_mode == "CODE"           → [COMMAND CODE description]
  needs user confirmation                 → [INPUT DISPLAY "..." VALUE confirmed: boolean]
  display-only                            → [DISPLAY "..."]
  all others                              → [COMMAND description]
 
Pattern:
  [ALTERNATIVE_FLOW: <condition text>]
      [SEQUENTIAL_BLOCK]
          COMMAND-N [COMMAND description]
          ...
      [END_SEQUENTIAL_BLOCK]
  [END_ALTERNATIVE_FLOW]
 
─────────────────────────────────────────────────────────────────────────
## EXCEPTION_FLOW
 
Only generate if section E (exception_flows) is non-empty.
Each ExceptionFlowSpec → one [EXCEPTION_FLOW: condition] block.
The condition field is the CONDITION token verbatim (free text).
If log_ref is non-empty, append: LOG <log_ref> on the same line as the condition.
The steps list provides the body in sequence.
 
Pattern (no LOG):
  [EXCEPTION_FLOW: <condition text>]
      [SEQUENTIAL_BLOCK]
          COMMAND-N [DISPLAY "..."]
          COMMAND-N [INPUT DISPLAY "..." VALUE confirmed: boolean]
          ...
      [END_SEQUENTIAL_BLOCK]
  [END_EXCEPTION_FLOW]
 
Pattern (with LOG):
  [EXCEPTION_FLOW: <condition text>] LOG <log_ref>
      [SEQUENTIAL_BLOCK]
          COMMAND-N [DISPLAY "..."]
          ...
      [END_SEQUENTIAL_BLOCK]
  [END_EXCEPTION_FLOW]
 
─────────────────────────────────────────────────────────────────────────
## FULL SYNTAX
 
  [DEFINE_WORKER: "one-sentence description" WorkerName]
 
      [INPUTS]
          REQUIRED <APPLY_CONSTRAINTS> AspectName </APPLY_CONSTRAINTS> <REF> var_or_file </REF>
          OPTIONAL <REF> var_or_file </REF>
      [END_INPUTS]
 
      [OUTPUTS]
          REQUIRED <APPLY_CONSTRAINTS> AspectName </APPLY_CONSTRAINTS> <REF> var_or_file </REF>
      [END_OUTPUTS]
 
      [MAIN_FLOW]
          [SEQUENTIAL_BLOCK]
              COMMAND-1 [INPUT DISPLAY "prompt" VALUE answer: text]
              COMMAND-2 [COMMAND description RESULT var: TYPE]
              COMMAND-3 [COMMAND PROMPT_TO_CODE description RESULT var: TYPE]
              COMMAND-4 [COMMAND CODE description RESULT var: TYPE]
              COMMAND-5 [CALL ApiName WITH {param: value} RESPONSE data: TYPE]
              COMMAND-6 [DISPLAY "message"]
          [END_SEQUENTIAL_BLOCK]
 
          DECISION-N [IF condition]
              COMMAND-N [COMMAND ...]
          [ELSEIF condition]
              COMMAND-N [COMMAND ...]
          [ELSE]
              COMMAND-N [COMMAND ...]
          [END_IF]
 
          DECISION-N [FOR each item in collection]
              COMMAND-N [COMMAND ...]
          [END_FOR]
      [END_MAIN_FLOW]
 
      [ALTERNATIVE_FLOW: <condition — free text from AlternativeFlowSpec.condition>]
          [SEQUENTIAL_BLOCK]
              COMMAND-N [COMMAND ...]
              COMMAND-N [DISPLAY "..."]
              COMMAND-N [INPUT DISPLAY "..." VALUE confirmed: boolean]
          [END_SEQUENTIAL_BLOCK]
      [END_ALTERNATIVE_FLOW]
 
      [EXCEPTION_FLOW: <condition — free text from ExceptionFlowSpec.condition>] LOG <log_ref if non-empty>
          [SEQUENTIAL_BLOCK]
              COMMAND-N [DISPLAY "..."]
              COMMAND-N [INPUT DISPLAY "..." VALUE confirmed: boolean]
          [END_SEQUENTIAL_BLOCK]
      [END_EXCEPTION_FLOW]
 
  [END_WORKER]
 
## ANNOTATION CONVENTION
For each COMMAND that maps to a classified clause, append:
  # SOURCE_REF: <file>:<clause_id>
  # CONFIDENCE: <float>
  # NEEDS_REVIEW: true | false
 
## RULES
- Global sequential COMMAND numbering: COMMAND-1, COMMAND-2, ... (never restart)
- Use 4-space indentation throughout.
- Do NOT generate an [EXAMPLES] block — that is produced separately.
- Output ONLY the [DEFINE_WORKER:] ... [END_WORKER] block.
  No prose, no markdown fences, no explanation.
"""

s4_e_v4 = """\
You write the [DEFINE_WORKER:] block of an SPL specification.
The WORKER orchestrates all declared names (CONSTRAINTS, VARIABLES, FILES, APIS)
into a step-by-step process.
 
## SYMBOL TABLE
Names already defined in Round 1 blocks.  Use these exact names.
Do NOT invent new names for things already defined here.
 
{{symbol_table}}
 
─────────────────────────────────────────────────────────────────────────
## MAIN_FLOW
 
ALL workflow steps (section A) go in MAIN_FLOW, in procedure order.
Do not filter out NETWORK or validation-gate steps.
 
Step type mapping (use execution_mode and effects to choose the command form):
  step.effects contains NETWORK        → [CALL ApiName WITH {...} RESPONSE var: TYPE]
                                          Use the ApiName from the APIS symbol table.
  step.execution_mode == "PROMPT_TO_CODE"
                                       → [COMMAND PROMPT_TO_CODE description RESULT var: TYPE]
  step.execution_mode == "CODE"        → [COMMAND CODE description RESULT var: TYPE]
  step.execution_mode == "USER_INPUT"  → [INPUT DISPLAY "description" VALUE answer: TYPE]
                                          TYPE is text for open answers, boolean for
                                          confirmations, or a list enum for selections.
                                          If it is a confirmation that blocks progress:
                                          add DECISION-N [IF confirmed == false]
                                                COMMAND-N [DISPLAY "Cannot proceed: reason"]
                                              [END_IF]
  all other steps                      → [COMMAND description RESULT var: TYPE]
                                          (omit RESULT clause if the step produces nothing)
 
  step.is_validation_gate == true → regular [COMMAND ...] as above;
    the failure path is covered by an EXCEPTION_FLOW block (see below).
 
Use branching from the original workflow prose (section B):
  "if X then Y, otherwise Z"  → DECISION-N [IF X] ... [ELSE] ... [END_IF]
  "for each item"             → DECISION-N [FOR each item ...] [END_FOR]
 
INPUTS / OUTPUTS:
  prerequisites that no prior step produces → [INPUTS] REQUIRED or OPTIONAL
  produces of the final step(s)             → [OUTPUTS] REQUIRED
 
Apply constraint aspect names to relevant inputs/outputs:
  <APPLY_CONSTRAINTS> AspectName1 AspectName2 </APPLY_CONSTRAINTS>
  Use constraint names from the symbol table; match semantically to the data.
 
─────────────────────────────────────────────────────────────────────────
## ALTERNATIVE_FLOW
 
Only generate if section D (alternative_flows) is non-empty.
Each AlternativeFlowSpec → one [ALTERNATIVE_FLOW: condition] block.
The condition field is the CONDITION token verbatim (free text).
The steps list provides the body in sequence.
 
Map each FlowStep to the most appropriate SPL command type:
  step.tool_hint set and NETWORK implied → [CALL ApiName WITH {...} RESPONSE ...]
  step.execution_mode == "PROMPT_TO_CODE" → [COMMAND PROMPT_TO_CODE description]
  step.execution_mode == "CODE"           → [COMMAND CODE description]
  needs user confirmation                 → [INPUT DISPLAY "..." VALUE confirmed: boolean]
  display-only                            → [DISPLAY "..."]
  all others                              → [COMMAND description]
 
Pattern:
  [ALTERNATIVE_FLOW: <condition text>]
      [SEQUENTIAL_BLOCK]
          COMMAND-N [COMMAND description]
          ...
      [END_SEQUENTIAL_BLOCK]
  [END_ALTERNATIVE_FLOW]
 
─────────────────────────────────────────────────────────────────────────
## EXCEPTION_FLOW
 
Only generate if section E (exception_flows) is non-empty.
Each ExceptionFlowSpec → one [EXCEPTION_FLOW: condition] block.
The condition field is the CONDITION token verbatim (free text).
If log_ref is non-empty, append: LOG <log_ref> on the same line as the condition.
The steps list provides the body in sequence.
 
Pattern (no LOG):
  [EXCEPTION_FLOW: <condition text>]
      [SEQUENTIAL_BLOCK]
          COMMAND-N [DISPLAY "..."]
          COMMAND-N [INPUT DISPLAY "..." VALUE confirmed: boolean]
          ...
      [END_SEQUENTIAL_BLOCK]
  [END_EXCEPTION_FLOW]
 
Pattern (with LOG):
  [EXCEPTION_FLOW: <condition text>] LOG <log_ref>
      [SEQUENTIAL_BLOCK]
          COMMAND-N [DISPLAY "..."]
          ...
      [END_SEQUENTIAL_BLOCK]
  [END_EXCEPTION_FLOW]
 
─────────────────────────────────────────────────────────────────────────
## FULL SYNTAX
 
  [DEFINE_WORKER: "one-sentence description" WorkerName]
 
      [INPUTS]
          REQUIRED <APPLY_CONSTRAINTS> AspectName </APPLY_CONSTRAINTS> <REF> var_or_file </REF>
          OPTIONAL <REF> var_or_file </REF>
      [END_INPUTS]
 
      [OUTPUTS]
          REQUIRED <APPLY_CONSTRAINTS> AspectName </APPLY_CONSTRAINTS> <REF> var_or_file </REF>
      [END_OUTPUTS]
 
      [MAIN_FLOW]
          [SEQUENTIAL_BLOCK]
              COMMAND-1 [INPUT DISPLAY "prompt" VALUE answer: text]   # execution_mode=USER_INPUT
              COMMAND-2 [COMMAND description RESULT var: TYPE]
              COMMAND-3 [COMMAND PROMPT_TO_CODE description RESULT var: TYPE]
              COMMAND-4 [COMMAND CODE description RESULT var: TYPE]
              COMMAND-5 [CALL ApiName WITH {param: value} RESPONSE data: TYPE]
              COMMAND-6 [DISPLAY "message"]
          [END_SEQUENTIAL_BLOCK]
 
          DECISION-N [IF condition]
              COMMAND-N [COMMAND ...]
          [ELSEIF condition]
              COMMAND-N [COMMAND ...]
          [ELSE]
              COMMAND-N [COMMAND ...]
          [END_IF]
 
          DECISION-N [FOR each item in collection]
              COMMAND-N [COMMAND ...]
          [END_FOR]
      [END_MAIN_FLOW]
 
      [ALTERNATIVE_FLOW: <condition — free text from AlternativeFlowSpec.condition>]
          [SEQUENTIAL_BLOCK]
              COMMAND-N [COMMAND ...]
              COMMAND-N [DISPLAY "..."]
              COMMAND-N [INPUT DISPLAY "..." VALUE confirmed: boolean]
          [END_SEQUENTIAL_BLOCK]
      [END_ALTERNATIVE_FLOW]
 
      [EXCEPTION_FLOW: <condition — free text from ExceptionFlowSpec.condition>] LOG <log_ref if non-empty>
          [SEQUENTIAL_BLOCK]
              COMMAND-N [DISPLAY "..."]
              COMMAND-N [INPUT DISPLAY "..." VALUE confirmed: boolean]
          [END_SEQUENTIAL_BLOCK]
      [END_EXCEPTION_FLOW]
 
  [END_WORKER]
 
## ANNOTATION CONVENTION
For each COMMAND that maps to a classified clause, append:
  # SOURCE_REF: <file>:<clause_id>
  # CONFIDENCE: <float>
  # NEEDS_REVIEW: true | false
 
## RULES
- Global sequential COMMAND numbering: COMMAND-1, COMMAND-2, ... (never restart)
- Use 4-space indentation throughout.
- Do NOT generate an [EXAMPLES] block — that is produced separately.
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