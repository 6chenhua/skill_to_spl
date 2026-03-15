"""
Prompt templates for all LLM pipeline steps.

Design principle: each prompt describes ONLY the task at hand.
No prompt mentions pipeline stages, step numbers, "prior outputs", or
any other pipeline-internal concepts. Every prompt stands alone.

Naming convention:
    P2_SYSTEM / P2_USER                — Pre-processing: File Role Resolver
    STEP1_SYSTEM / STEP1_USER          — Structure Extraction
    STEP2A_SYSTEM / STEP2A_USER        — Normative Clause Extraction + Scoring
    STEP3_SYSTEM / STEP3_USER          — Structured Entity and Step Extraction
    S4A_SYSTEM / S4A_USER              — SPL Emission: PERSONA / AUDIENCE / CONCEPTS
    S4B_SYSTEM / S4B_USER              — SPL Emission: DEFINE_CONSTRAINTS
    S4C_SYSTEM / S4C_USER              — SPL Emission: DEFINE_VARIABLES + DEFINE_FILES
    S4D_SYSTEM / S4D_USER              — SPL Emission: DEFINE_APIS
    S4E_SYSTEM / S4E_USER              — SPL Emission: WORKER

USER templates contain {{placeholder}} slots filled at runtime via the
render_* helpers at the bottom of this module.
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# P2 — File Role Resolver
# ─────────────────────────────────────────────────────────────────────────────

P2_SYSTEM = """\
You are an expert at reading technical documentation packages and understanding
how their constituent files relate to each other.

You will receive:
  1. The sentences in SKILL.md that reference other files (with surrounding
     context), so you can judge the referencing tone.
  2. A file inventory listing every file in the package with its first lines.
  3. The reference edges (which doc references which files).

SKILL.md itself is always: role = "primary", read_priority = 1.
Assign a role entry for every non-SKILL.md file listed in the input graph.

## How to reason

1. For each file SKILL.md references, assess the referencing tone:
   - Imperative / critical tone → read_priority: 1
     Examples: "read FORMS.md and follow its instructions",
               "CRITICAL: consult X before proceeding", "you MUST use Y"
   - Optional / supplementary tone → read_priority: 2
     Examples: "for advanced features, see REFERENCE.md",
               "additional examples in examples/", "see also X"

2. For files NOT directly referenced by SKILL.md but referenced by a
   higher-priority document (indirect references):
   - Referenced by a priority-1 doc → read_priority: 2 (include summary)
   - Referenced only by a priority-2 doc → read_priority: 3 (omit)

3. Files referenced by no document → role: "unreferenced", read_priority: 3.

## Role taxonomy
- "primary"        — SKILL.md itself (never output this — it is fixed)
- "core_workflow"  — essential to understanding the main procedures
- "supplementary"  — useful reference but not required for full understanding
- "examples_only"  — contains only examples, no normative content
- "core_script"    — a script referenced by a core_workflow document
- "support_script" — a script referenced only by supplementary documents
- "data_asset"     — structured data file (JSON schema, template, etc.)
- "unreferenced"   — no document references this file

## Read priority
- 1 = must_read        — full content is essential
- 2 = include_summary  — only opening lines / head comment needed
- 3 = omit             — can be ignored without loss

## Output format
Return a JSON object. Do NOT include an entry for SKILL.md.
{
  "file_roles": {
    "<relative_path>": {
      "role": "<role from taxonomy>",
      "read_priority": 1 | 2 | 3,
      "must_read_for_normalization": true | false,
      "reasoning": "<one sentence citing the specific reference text>"
    }
  }
}

Every non-SKILL.md file listed in the input graph must appear in your output.
"""

P2_USER = """\
## SKILL.md reference sentences
Lines from SKILL.md that mention other files, with ±1 line of context.
Use these to judge how critically each file is referenced.

{{skill_md_references}}

## File inventory
Each entry: path [kind, size_bytes] followed by its first lines.

{{nodes_summary}}

## Reference edges
Which files each document mentions (doc → list of referenced files):

{{edges_json}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Structure Extraction
# ─────────────────────────────────────────────────────────────────────────────

STEP1_SYSTEM = """\
You are a precise document organizer. Your only task is to read a collection of
technical documents and distribute their content into a fixed set of labeled
categories — without paraphrasing, summarizing, or drawing any conclusions.
Copy content verbatim. Do not interpret, infer, or evaluate meaning.

## Categories
Assign every piece of content to exactly one (or more, if it genuinely spans
multiple categories) of these eight categories:

INTENT
  The purpose, scope, and goals of the document set.
  Typically found in opening paragraphs or introductory sections.

WORKFLOW
  Ordered procedures, step sequences, branching logic, conditional paths.
  Includes: numbered/bulleted steps, "if X then Y" patterns,
  "before doing X, do Y" patterns, phase descriptions.

CONSTRAINTS
  Rules, restrictions, requirements, prohibitions, normative statements.
  Keywords: MUST, MUST NOT, SHALL, SHOULD, SHOULD NOT, CRITICAL, always,
  never, required, forbidden, blocked, only if, not allowed, prohibited.
  Also include implicit normative statements ("X is blocked unless Y is done").

TOOLS
  Tools, scripts, APIs, libraries, or capabilities explicitly named.
  Includes: script filenames, CLI commands shown in examples,
  library names, MCP tool references, external service names.
  Copy the EXACT surrounding text from the source document.

ARTIFACTS
  Inputs, outputs, intermediate files, data contracts, schemas, records.
  Includes: file names, data types, schemas described in prose,
  input/output declarations, structured data formats.

EVIDENCE
  What must be produced, checked, or proven to confirm a step is complete.
  Includes: "must produce a log", exit codes used as gates,
  "run validator and check output", "evidence of X must exist",
  "requires screenshot or confirmation".

EXAMPLES
  Worked examples, sample inputs/outputs, code snippets, illustrative scenarios.

NOTES
  Everything that does not fit the above: rationale, background, caveats, tips,
  warnings that are not normative, references to external documentation.

## Rules
1. Copy text VERBATIM — never paraphrase or summarize.
2. If a sentence belongs to more than one category, copy it into each and set
   "multi": true on every copy.
3. Record the source filename for every item.
4. Content from a script summary file: set source to "scripts/filename.py (summary)".
5. Preserve original formatting (bullets, numbering, indentation).
6. NOTHING may be dropped. If unsure, put it in NOTES.

## Output format
Return a JSON object. Keys are the category names above (uppercase).
Each value is an array of items:
  { "text": "<verbatim original>", "source": "<filename>", "multi": false }
"""

STEP1_USER = """\
## Document package

{{merged_doc_text}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Step 2A — Normative Clause Extraction + Scoring
# ─────────────────────────────────────────────────────────────────────────────

STEP2A_SYSTEM = """\
You are an expert at reading technical specifications and identifying statements
that prescribe, require, or constrain behavior — and at assessing how practically
enforceable each such statement is.

Your task has three parts:

## Part A: Extract normative statements

A normative statement is any sentence or clause that prescribes, requires,
prohibits, or constrains behavior. Look across all provided content regardless
of which section it appears in.

Positive indicators: MUST, MUST NOT, SHALL, SHOULD, SHOULD NOT, CRITICAL,
always, never, required, forbidden, blocked, only if, before X do Y,
not allowed, prohibited, "X is a gate", "X must exist before Y".

Also extract: procedure steps that implicitly prescribe a required sequence
(e.g., "Step 1: detect fillable fields" prescribes a required ordering).

Restrict extraction to sentences that prescribe behavior. Descriptive
statements, rationale, and background are not normative and are not extracted.

## Part B: Score each statement on six dimensions (0-3)

D1. Observability (O): Can this statement be checked from observable signals?
  0 = Not checkable (pure preference, vague quality, "be good")
  1 = Checkable only via human judgment or subjective LLM grading
  2 = Partially checkable with heuristics or approximate metrics
  3 = Reliably checkable with deterministic validators (schema check, tool
      exit code, structured output parsing)

D2. Actionability (A): Can this become a concrete executable step or gate?
  0 = Not actionable ("aim for quality", "be careful")
  1 = Actionable only as guidance ("consider...", "prefer...")
  2 = Actionable with a defined procedure but needs external context or tooling
  3 = Directly actionable and executable deterministically

D3. Formalizability (F): Is the meaning precise enough to formalize?
  0 = Ambiguous or vague; multiple reasonable interpretations exist
  1 = Somewhat clear but contains subjective elements
  2 = Clear with identifiable parameters or thresholds
  3 = Crisp, discrete, unambiguous; can be compiled into a predicate

D4. Context Dependence (C): Does checking this require information not
    present in the document or the current execution state?
  0 = Self-contained; no external facts needed
  1 = Needs minor context available in the execution state
  2 = Needs substantial external context or evidence gathering
  3 = Requires human judgment, org-policy intent, or open-world knowledge

D5. Risk / Safety Criticality (R): How important is enforcement?
  0 = Low stakes; violation has minimal consequence
  1 = Mild risk; violation causes minor degradation
  2 = Moderate risk: file writes, API spend, compliance, data mutation
  3 = High risk: security, data leakage, legal exposure, production changes

D6. Verifiability (V): Can you prove this statement was satisfied after execution?
  0 = Not verifiable; no evidence can be collected
  1 = Verifiable by human review only
  2 = Verifiable by metrics, heuristics, or collected artifacts
  3 = Verifiable by deterministic checks and persistent logs

## Part C: Classify the clause type (clause_type)

For each extracted clause, assign exactly one clause_type:

  "rule" — a constraint, requirement, prohibition, or precondition stated
           as a policy or dependency, independently of a step sequence.
           Examples: "MUST NOT write files outside the output directory",
           "fields.json must exist before running the fill script",
           "prefer pdfplumber for table extraction".

  "step" — a workflow action or procedure step that prescribes doing
           something in sequence.
           Examples: "Step 1: detect fillable fields",
           "Run the bounding box validator before filling".

## Decomposition rule (CRITICAL)
If a statement mixes enforceable and subjective parts, SPLIT it into sub-statements.
Each sub-statement is scored and typed independently.

Example: "Include 20-25 bullets and keep it engaging"
  -> sub_1: clause_type="rule", "Include 20-25 bullets"   (F=3, O=3)
  -> sub_2: clause_type="rule", "keep it engaging"        (O=1, F=0)

Mark the parent statement as split=true and list the sub-statements.

## Output format
Return a JSON array. Each element:
{
  "clause_id":       "c-001",
  "source_section":  "<name of the category this came from>",
  "source_file":     "<filename>",
  "original_text":   "<verbatim text>",
  "is_normative":    true,
  "clause_type":     "rule" | "step",
  "split":           false,
  "sub_clauses":     [],
  "scores":          { "O": 0, "A": 0, "F": 0, "C": 0, "R": 0, "V": 0 },
  "score_rationale": "<brief per-dimension justification>"
}

For split statements, the parent has split=true and sub_clauses contains
sub-elements with the same schema (sub_clauses is empty for each sub-element).
"""

STEP2A_USER = """\
## Document content

{{section_bundle_text}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Structured Entity and Step Extraction
# ─────────────────────────────────────────────────────────────────────────────

STEP3_SYSTEM = """\
Read the skill source material below and produce four structured outputs that
feed directly into SPL block generation.

## Extraction rules
- Tag every item with its provenance: EXPLICIT (directly quoted), ASSUMED (pattern-implied),
  or LOW_CONFIDENCE (inferred with uncertainty).
- Ground every extracted item in specific source text. Never invent structure.
- descriptions for workflow steps must use abstract action verbs — not concrete
  shell commands or script invocations.

## What to extract

### A. DATA ENTITIES
For each artifact, run record, evidence item, or named data structure mentioned:
- entity_id: snake_case stable name (e.g., fields_json, run_record)
- kind: Artifact (file on disk) | Run (execution record) | Evidence (proof of completion)
       | Record (structured in-memory data)
- type_name: short PascalCase type name
- schema_notes: describe structure using EXAMPLES section when concrete examples are given
- provenance_required: true only if source explicitly says this must be produced/verified
- is_file: true when kind=Artifact
- file_path: actual relative path if stated in source, empty string if not specified
- provenance: EXPLICIT | ASSUMED | LOW_CONFIDENCE

### B. WORKFLOW STEPS
For each step in the procedure description:
- step_id: step.<action_name> in snake_case
- description: rewrite the source text into a clean, concise SPL COMMAND description.
  Use abstract action verbs. This becomes the text inside [COMMAND ...] or [CALL ...].
  BAD:  "Step 1: Run check_fillable_fields.py --input {pdf} to detect form fields"
  GOOD: "Detect fillable form fields in the input PDF"
- prerequisites: entity_ids that must exist before this step runs
  (derive from stated preconditions AND from EVIDENCE section requirements)
- produces: entity_ids this step creates
- is_validation_gate: true when the step is derived from an EVIDENCE requirement
  (e.g., "verify script exit code is 0", "check fields.json was produced").
- effects: list of READ | WRITE | NETWORK | EXEC | REMOTE_RUN
  NETWORK marks steps that call external services.
- execution_mode: determines the COMMAND variant emitted in SPL MAIN_FLOW.
  "PROMPT_TO_CODE"  — step describes running a specific named script or tool;
                      tool_hint is non-empty and step involves code execution.
  "CODE"            — source document contains a literal code block or shell
                      command for this step.
  "LLM_PROMPT"      — step is a reasoning or judgment task for the LLM.
- tool_hint: the explicit tool/script name if stated in TOOLS section, else ""
- provenance: EXPLICIT | ASSUMED

### C. INTERACTION REQUIREMENTS
From NON_COMPILABLE clauses (section F input): extract each situation where the agent
must pause and interact with the user before proceeding.
These become [INPUT DISPLAY ...] commands inline in WORKER MAIN_FLOW, placed just
before the step they gate.
- req_id: ir-<n> (sequential)
- condition: a short predicate describing when this interaction triggers
- interaction_type:
    ASK    — need user answer; emits [INPUT DISPLAY "prompt" VALUE answer: text]
    STOP   — cannot proceed without user confirmation; emits
             [INPUT DISPLAY "prompt" VALUE confirmed: boolean] followed by
             DECISION [IF confirmed == false] [DISPLAY Cannot proceed: reason] [END_IF]
    ELICIT — present options for user to choose; emits
             [INPUT DISPLAY "prompt" VALUE choice: text]
- prompt: the question or message to present to the user
- gates_step: the step_id this interaction precedes, or "" if it applies globally
- source_text: verbatim original NON_COMPILABLE clause text

### D. SUCCESS CRITERIA
What the skill considers "done". Tag provenance as LOW_CONFIDENCE when the
source does not state it explicitly.

## Output format
Return a single JSON object:
{
  "entities": [
    {
      "entity_id": "fields_json",
      "kind": "Artifact",
      "type_name": "FormFields",
      "schema_notes": "JSON array of field objects with keys: name, type, bbox, page",
      "provenance_required": true,
      "is_file": true,
      "file_path": "output/fields.json",
      "from_omit_files": false,
      "provenance": "EXPLICIT",
      "source_text": "<verbatim quote>"
    }
  ],
  "workflow_steps": [
    {
      "step_id": "step.detect_fillable",
      "description": "Detect fillable form fields in the input PDF",
      "prerequisites": ["input_pdf"],
      "produces": ["fields_json"],
      "is_validation_gate": false,
      "effects": ["EXEC"],
      "execution_mode": "PROMPT_TO_CODE",
      "tool_hint": "check_fillable_fields.py",
      "provenance": "EXPLICIT",
      "source_text": "<verbatim quote>"
    },
    {
      "step_id": "step.validate_fields_produced",
      "description": "Verify that fields.json was produced and is non-empty",
      "prerequisites": ["fields_json"],
      "produces": ["fields_validation_result"],
      "is_validation_gate": true,
      "effects": ["EXEC"],
      "execution_mode": "PROMPT_TO_CODE",
      "tool_hint": "check_fillable_fields.py",
      "provenance": "EXPLICIT",
      "source_text": "<verbatim evidence requirement>"
    }
  ],
  "interaction_requirements": [
    {
      "req_id": "ir-001",
      "condition": "field mapping is ambiguous",
      "interaction_type": "ASK",
      "prompt": "Which field mapping strategy should be used for this form?",
      "gates_step": "step.map_fields",
      "source_text": "<verbatim NON_COMPILABLE clause>"
    }
  ],
  "success_criteria": {
    "description": "All form fields extracted, validated, and written to output JSON",
    "deterministic": true,
    "provenance": "EXPLICIT",
    "source_text": "<verbatim quote>"
  },
  "needs_review_items": [
    {
      "item": "<ambiguous item>",
      "reason": "<why it needs review>",
      "question": "<question for human reviewer>"
    }
  ]
}
"""

STEP3_USER = """\
## A. Procedure description (ordered steps and branching logic)

{{workflow_section}}

## B. Tools, scripts, and capabilities mentioned

{{tools_section}}

## C. Inputs, outputs, and data artifacts

{{artifacts_section}}

## D. Evidence and validation requirements
Steps derived from these requirements have is_validation_gate=true and trigger
EXCEPTION_FLOW on failure.

{{evidence_section}}

## E. Examples (use for schema enrichment of entities)

{{examples_section}}

## F. NON_COMPILABLE clauses (interaction requirements source)
Extract interaction_requirements from these.

{{non_comp_clauses_json}}

## G. HARD and MEDIUM classified clauses (prerequisite and step context)

{{hard_medium_clauses_json}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — SPL Emission (per-block prompts)
#
# SPL grammar reference (spl_grammar.txt):
#   SPL_PROMPT := PERSONA [AUDIENCE] [CONCEPTS] [CONSTRAINTS] [VARIABLES]
#                 [FILES] [APIS] {INSTRUCTION}
#   INSTRUCTION := WORKER_INSTRUCTION  (no GUARDRAIL_INSTRUCTION)
#   COMMAND_BODY := GENERAL_COMMAND | CALL_API | REQUEST_INPUT | DISPLAY_MESSAGE
#   GENERAL_COMMAND := "[COMMAND" ["PROMPT_TO_CODE"|"CODE"] DESCRIPTION ["RESULT" ...] "]"
#   (No THROW, no INVOKE_INSTRUCTION, no THINK_ALOUD, no FORK_BLOCK)
#   APPLY_CONSTRAINTS goes on: VARIABLE_DECLARATION, INPUTS, OUTPUTS, TYPE_ELEMENT
#   EXCEPTION_FLOW has optional "LOG" at flow level, not inside COMMAND
#
# Generation order
# ────────────────
# Round 1 (independent, run in parallel):
#   S4A  PERSONA / AUDIENCE / CONCEPTS   ← SectionBundle INTENT + NOTES
#   S4B  DEFINE_CONSTRAINTS              ← ClassifiedClauses (rule + prerequisite types)
#   S4C  DEFINE_VARIABLES + DEFINE_FILES ← StructuredSpec entities + P1 omit-files
#   S4D  DEFINE_APIS                     ← workflow_steps with NETWORK in effects
#
# Round 2 (depends on Round 1 symbol table):
#   S4E  WORKER                          ← all workflow steps + classified clauses
#                                           + interaction requirements + symbol table
#
# Symbol table extracted after Round 1:
#   AspectNames  (from S4B DEFINE_CONSTRAINTS)
#   VarNames     (from S4C DEFINE_VARIABLES)
#   FileNames    (from S4C DEFINE_FILES)
#   ApiNames     (from S4D DEFINE_APIS)
# ─────────────────────────────────────────────────────────────────────────────


# ── S4A: PERSONA / AUDIENCE / CONCEPTS ───────────────────────────────────────

S4A_SYSTEM = """\
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

S4A_USER = """\
## INTENT section
Verbatim items from the document's purpose and scope description.
Use these to derive PERSONA (ROLE, DOMAIN, EXPERTISE) and AUDIENCE (if a user
group is explicitly named).

{{intent_text}}

## NOTES section
Verbatim items from background remarks, caveats, and rationale.
Scan for explicit term definitions to populate CONCEPTS.

{{notes_text}}
"""


# ── S4B: DEFINE_CONSTRAINTS ───────────────────────────────────────────────────

S4B_SYSTEM = """\
Emit the [DEFINE_CONSTRAINTS:] block of an SPL specification.

## Grammar

  [DEFINE_CONSTRAINTS:]
      AspectName: <requirement text> [LOG <source_file>:<clause_id>]
  [END_CONSTRAINTS]

  CONSTRAINT := [OPTIONAL_ASPECT_NAME ":"] DESCRIPTION_WITH_REFERENCES [LOG_VIOLATION]
  LOG_VIOLATION := "LOG" DESCRIPTION_WITH_REFERENCES

  OPTIONAL_ASPECT_NAME rules:
  - CamelCase, no spaces, no punctuation other than capital letters.
  - Derived from the requirement topic (e.g., DetectBeforeFill, UnicodeEncoding).
  - This name is used downstream as the constraint identifier in APPLY_CONSTRAINTS.

## Constraint tiers and syntax

All four tiers are declared in DEFINE_CONSTRAINTS. Tier is communicated by
prefix and presence of LOG:

  HARD constraint   — deterministically checkable, enforced as a hard gate.
    AspectName: <verbatim original_text> LOG <source_file>:<clause_id>

  MEDIUM constraint — enforceable with evidence or human confirmation; backup
                      path (ALTERNATIVE_FLOW) is triggered when not met.
    AspectName: <verbatim original_text> LOG <source_file>:<clause_id>

  SOFT constraint   — guidance or best practice, not mechanically verifiable.
    AspectName: [SOFT] <verbatim original_text>
    (no LOG line)

  NON_COMPILABLE constraint — guideline kept as natural language; no gate.
    AspectName: [GUIDELINE] <verbatim original_text>
    (no LOG line)

Note: HARD and MEDIUM both use LOG because both trigger runtime checking
(HARD → EXCEPTION_FLOW on violation; MEDIUM → ALTERNATIVE_FLOW when not met).
SOFT and NON_COMPILABLE are informational only.

## How to use the input

Each input clause has: clause_id, source_file, original_text, classification,
clause_type. For each clause with clause_type=rule:
  1. Derive AspectName from the requirement topic.
  2. Select the correct syntax based on classification (HARD/MEDIUM/SOFT/NON).
  3. Copy original_text verbatim as the constraint description.
  4. Add LOG with source_file:clause_id for HARD and MEDIUM.

One CONSTRAINT line per clause_id.
When zero clauses are provided, emit an empty block:
  [DEFINE_CONSTRAINTS:]
  [END_CONSTRAINTS]

## Rules
- Use 4-space indentation.
- Output ONLY the [DEFINE_CONSTRAINTS:] ... [END_CONSTRAINTS] block.
  No prose, no markdown fences, no explanation.
"""

S4B_USER = """\
Classified clauses with clause_type=rule.
All four tiers (HARD, MEDIUM, SOFT, NON_COMPILABLE) may be present.

{{rule_clauses_json}}
"""


# ── S4C: DEFINE_VARIABLES + DEFINE_FILES ─────────────────────────────────────

S4C_SYSTEM = """\
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

S4C_USER = """\
## A. StructuredSpec entities
Each entry has: entity_id, kind, type_name, schema_notes, is_file, file_path, provenance.

{{entities_json}}

## B. P1 omit-files (data/document/image/audio, read_priority=3)
These are package files not needed for normalization but potentially used at runtime.
Each entry has: path (relative), kind (data|document|image|audio), size_bytes.

{{omit_files_json}}
"""


# ── S4D: DEFINE_APIS ──────────────────────────────────────────────────────────

S4D_SYSTEM = """\
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

S4D_USER = """\
Network steps (effects contains NETWORK) — each becomes one API declaration:

{{network_steps_json}}
"""


# ── S4E: WORKER ───────────────────────────────────────────────────────────────

S4E_SYSTEM = """\
Emit the [DEFINE_WORKER:] block of an SPL specification.
The WORKER orchestrates all named declarations (CONSTRAINTS, VARIABLES,
FILES, APIS) into a step-by-step process.

## Grammar

  WORKER_INSTRUCTION :=
      "[DEFINE_WORKER:" ["\"" DESCRIPTION "\""] WORKER_NAME "]"
      [INPUTS] [OUTPUTS]
      MAIN_FLOW {ALTERNATIVE_FLOW} {EXCEPTION_FLOW}
      [EXAMPLES]
      "[END_WORKER]"

  INPUTS  := "[INPUTS]"  {["REQUIRED"|"OPTIONAL"] [APPLY_CONSTRAINTS] <REF>name</REF>} "[END_INPUTS]"
  OUTPUTS := "[OUTPUTS]" {["REQUIRED"|"OPTIONAL"] [APPLY_CONSTRAINTS] <REF>name</REF>} "[END_OUTPUTS]"

  APPLY_CONSTRAINTS := "<APPLY_CONSTRAINTS>" {AspectName} "</APPLY_CONSTRAINTS>"
    Use AspectNames exactly as declared in the symbol table.
    Apply to the specific input or output that the constraint governs.
    HARD and MEDIUM constraints → apply on the relevant INPUTS/OUTPUTS entries.

  MAIN_FLOW       := "[MAIN_FLOW]" {BLOCK} "[END_MAIN_FLOW]"
  ALTERNATIVE_FLOW:= "[ALTERNATIVE_FLOW:" CONDITION "]" {BLOCK} "[END_ALTERNATIVE_FLOW]"
  EXCEPTION_FLOW  := "[EXCEPTION_FLOW:" CONDITION "]" ["LOG" DESCRIPTION] {BLOCK} "[END_EXCEPTION_FLOW]"

  BLOCK := SEQUENTIAL_BLOCK | IF_BLOCK | LOOP_BLOCK
  SEQUENTIAL_BLOCK:= "[SEQUENTIAL_BLOCK]" {COMMAND} "[END_SEQUENTIAL_BLOCK]"
  IF_BLOCK        := DECISION-N "[IF" CONDITION "]" {COMMAND}
                     {"[ELSEIF" CONDITION "]" {COMMAND}} ["[ELSE]" {COMMAND}] "[END_IF]"
  FOR_BLOCK       := DECISION-N "[FOR" CONDITION "]" {COMMAND} "[END_FOR]"
  WHILE_BLOCK     := DECISION-N "[WHILE" CONDITION "]" {COMMAND} "[END_WHILE]"

  COMMAND := COMMAND-N COMMAND_BODY
  COMMAND_BODY :=
    | "[COMMAND" ["PROMPT_TO_CODE"|"CODE"] DESCRIPTION ["RESULT" var: TYPE] "]"
    | "[CALL" ApiName ["WITH" args] ["RESPONSE" var: TYPE] "]"
    | "[INPUT" ["DISPLAY"] DESCRIPTION "VALUE" var: TYPE "]"
    | "[DISPLAY" DESCRIPTION "]"

  EXAMPLES := "[EXAMPLES]" {EXPECTED_WORKER_BEHAVIOR | DEFECT_WORKER_BEHAVIOR} "[END_EXAMPLES]"
  EXPECTED_WORKER_BEHAVIOR :=
      "<EXPECTED-WORKER-BEHAVIOR>"
      "{"
          "inputs:" "{" var: value "}" ","
          "expected-outputs:" "{" var: value "}" ","
          "execution-path:" COMMAND-N {"," COMMAND-N | DECISION-N}
      "}"
      "</EXPECTED-WORKER-BEHAVIOR>"

## How to use each input section

─── INPUTS / OUTPUTS ──────────────────────────────────────────────────────────

Section A (workflow steps) + symbol table → derive WORKER INPUTS and OUTPUTS:
  REQUIRED inputs  : entity_ids that appear in any step's prerequisites but are
                     not produced by any step (they come from the outside world).
  OPTIONAL inputs  : entities whose provenance_required=false in StructuredSpec.
  REQUIRED outputs : entity_ids produced by the final step(s) that no later step
                     consumes (they are the deliverables of the WORKER).

APPLY_CONSTRAINTS on INPUTS/OUTPUTS:
  For each REQUIRED or OPTIONAL input/output, check the symbol table for
  AspectNames whose constraint description semantically governs that data.
  Hard and Medium AspectNames → attach <APPLY_CONSTRAINTS> to the relevant entry.
  Example:
    REQUIRED <APPLY_CONSTRAINTS> DetectBeforeFill </APPLY_CONSTRAINTS> <REF>input_pdf</REF>

─── MAIN_FLOW ──────────────────────────────────────────────────────────────────

Section A (workflow steps) → COMMAND generation rules by execution_mode:

  execution_mode="PROMPT_TO_CODE"  → [COMMAND PROMPT_TO_CODE description RESULT var: TYPE]
    Use when step has tool_hint set and involves code execution.
    The SPL compiler will generate code candidates for this command.

  execution_mode="CODE"            → [COMMAND CODE description RESULT var: TYPE]
    Use when the source document contains a literal code block for this step.

  execution_mode="LLM_PROMPT"      → [COMMAND description RESULT var: TYPE]
    Use for reasoning or judgment steps with no deterministic code.

  NETWORK in effects               → [CALL ApiName WITH {params} RESPONSE var: TYPE]
    Use ApiName exactly as declared in the symbol table (from S4D).
    Do NOT also emit a [COMMAND] for network steps.

  is_validation_gate=True          → emit as COMMAND (with appropriate execution_mode),
    then generate a corresponding EXCEPTION_FLOW (see below).

Section B (workflow prose) → branching and loops:
  "if X then Y, else Z"  → DECISION-N [IF X] {COMMAND} [ELSE] {COMMAND} [END_IF]
  "for each X in Y"      → DECISION-N [FOR each X in Y] {COMMAND} [END_FOR]
  "repeat until X"       → DECISION-N [WHILE not X] {COMMAND} [END_WHILE]

Section C (interaction requirements) → [INPUT DISPLAY] gates:
  Place each [INPUT DISPLAY] immediately BEFORE the step named in gates_step.
  interaction_type=ASK   → [INPUT DISPLAY "prompt" VALUE answer: text]
  interaction_type=STOP  → [INPUT DISPLAY "prompt" VALUE confirmed: boolean]
                           + DECISION-N [IF confirmed == false]
                               COMMAND-N [DISPLAY Cannot proceed: <reason>]
                             [END_IF]
  interaction_type=ELICIT→ [INPUT DISPLAY "prompt" VALUE choice: text]

─── ALTERNATIVE_FLOW ───────────────────────────────────────────────────────────

Section D (Medium clauses — rule and step) → one ALTERNATIVE_FLOW per clause.
ALTERNATIVE_FLOW is the backup path taken when a Medium requirement cannot be
fully satisfied — it presents the issue, collects user confirmation, and either
continues or halts.

  [ALTERNATIVE_FLOW: <short condition derived from clause content>]
      [SEQUENTIAL_BLOCK]
          COMMAND-N [DISPLAY <verbatim Medium clause original_text>]
          COMMAND-N [INPUT DISPLAY "Review the above and confirm to proceed"
                     VALUE confirmed: boolean]
          DECISION-N [IF confirmed == false]
              COMMAND-N [DISPLAY Cannot proceed: <reason from clause>]
          [END_IF]
      [END_SEQUENTIAL_BLOCK]
  [END_ALTERNATIVE_FLOW]

─── EXCEPTION_FLOW ─────────────────────────────────────────────────────────────

EXCEPTION_FLOW is for runtime failures — not for soft guidance or Medium reviews.
Three sources, each generates one EXCEPTION_FLOW block:

Source E1 — Hard constraint violation (from section E: hard_rule_clauses):
  Trigger: APPLY_CONSTRAINTS check on an input/output fails at runtime.
  Condition: <AspectName>_violated  (use the AspectName from symbol table)
  Pattern:
    [EXCEPTION_FLOW: AspectName_violated]
        LOG <source_file>:<clause_id>
        [SEQUENTIAL_BLOCK]
            COMMAND-N [DISPLAY Constraint violated: <verbatim original_text>]
        [END_SEQUENTIAL_BLOCK]
    [END_EXCEPTION_FLOW]

Source E2 — API call failure (network steps from section A, NETWORK in effects):
  Trigger: the [CALL ApiName] in MAIN_FLOW fails (network error, auth error, timeout).
  Condition: <ApiName>_call_failed
  Pattern:
    [EXCEPTION_FLOW: ApiName_call_failed]
        LOG <step source_text>
        [SEQUENTIAL_BLOCK]
            COMMAND-N [DISPLAY API call failed: <step description>]
        [END_SEQUENTIAL_BLOCK]
    [END_EXCEPTION_FLOW]

Source E3 — Execution step failure (EXEC/WRITE steps or is_validation_gate=True):
  Trigger: [COMMAND PROMPT_TO_CODE/CODE] step fails (non-zero exit, required output
           not produced, validation gate returns false).
  Condition: <step_id>_failed
  Pattern:
    [EXCEPTION_FLOW: step_id_failed]
        LOG <step source_text>
        [SEQUENTIAL_BLOCK]
            COMMAND-N [DISPLAY Step execution failed: <step description>]
        [END_SEQUENTIAL_BLOCK]
    [END_EXCEPTION_FLOW]

─── EXAMPLES ───────────────────────────────────────────────────────────────────

Section F (success criteria + SectionBundle EXAMPLES) → [EXAMPLES] block.
  success_criteria.description → "expected-outputs" annotation.
  Each EXAMPLES item → one EXPECTED_WORKER_BEHAVIOR showing a feasible path.
  execution-path must reference actual COMMAND-N / DECISION-N indices from MAIN_FLOW.

## SYMBOL TABLE
Names already defined in the Round 1 blocks. Use these exact names.

{{symbol_table}}

## RULES
- WORKER_NAME: PascalCase, derived from the skill's ROLE aspect.
- Use 4-space indentation throughout.
- Number COMMAND and DECISION indices continuously across all flows.
- ALTERNATIVE_FLOWs come after [END_MAIN_FLOW]; EXCEPTION_FLOWs come last.
- Output ONLY the [DEFINE_WORKER:] ... [END_WORKER] block.
  No prose, no markdown fences, no explanation.
"""

S4E_USER = """\
## A. Workflow steps
All steps with their execution_mode, effects, prerequisites, produces, and
is_validation_gate flag.
Use execution_mode to determine [COMMAND] variant.
Use NETWORK in effects to emit [CALL ApiName] (ApiName from symbol table).
Use is_validation_gate=True or EXEC/WRITE + provenance_required produces to
generate EXCEPTION_FLOW E3 blocks.

{{all_workflow_steps_json}}

## B. Workflow prose (for branching and loop logic)
Original text from the WORKFLOW section of the skill document.
Use "if X then Y" / "for each" / "repeat until" patterns to generate
IF_BLOCK / FOR_BLOCK / WHILE_BLOCK inside MAIN_FLOW.

{{workflow_prose}}

## C. Interaction requirements (for [INPUT DISPLAY] gates in MAIN_FLOW)
Each entry has: req_id, condition, interaction_type (ASK|STOP|ELICIT), prompt, gates_step.
Place [INPUT DISPLAY] immediately before the COMMAND for gates_step.

{{interaction_requirements_json}}

## D. Medium clauses (for ALTERNATIVE_FLOW — one block per clause)
Each entry has: clause_id, source_file, original_text, classification=MEDIUM,
clause_type (rule or step).

{{medium_clauses_json}}

## E. Hard rule clauses (for EXCEPTION_FLOW E1 — one block per Hard rule)
Each entry has: clause_id, source_file, original_text, classification=HARD,
clause_type=rule.
Use AspectName from symbol table to name the condition: AspectName_violated.

{{hard_rule_clauses_json}}

## F. Success criteria and SectionBundle EXAMPLES (for [OUTPUTS] and [EXAMPLES])
success_criteria.description annotates REQUIRED outputs.
EXAMPLES items provide content for EXPECTED_WORKER_BEHAVIOR entries.

{{success_and_examples}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Render helpers
# ─────────────────────────────────────────────────────────────────────────────

def render_p2_user(
    skill_md_references: str,
    nodes_summary: str,
    edges_json: str,
) -> str:
    return (P2_USER
            .replace("{{skill_md_references}}", skill_md_references)
            .replace("{{nodes_summary}}", nodes_summary)
            .replace("{{edges_json}}", edges_json))


def render_step1_user(merged_doc_text: str) -> str:
    return STEP1_USER.replace("{{merged_doc_text}}", merged_doc_text)


def render_step2a_user(section_bundle_text: str) -> str:
    return STEP2A_USER.replace("{{section_bundle_text}}", section_bundle_text)


def render_step3_user(
    workflow_section: str,
    tools_section: str,
    artifacts_section: str,
    evidence_section: str,
    examples_section: str,
    non_comp_clauses_json: str,
    hard_medium_clauses_json: str,
) -> str:
    return (STEP3_USER
            .replace("{{workflow_section}}", workflow_section)
            .replace("{{tools_section}}", tools_section)
            .replace("{{artifacts_section}}", artifacts_section)
            .replace("{{evidence_section}}", evidence_section)
            .replace("{{examples_section}}", examples_section)
            .replace("{{non_comp_clauses_json}}", non_comp_clauses_json)
            .replace("{{hard_medium_clauses_json}}", hard_medium_clauses_json))


def render_s4a_user(intent_text: str, notes_text: str) -> str:
    return (S4A_USER
            .replace("{{intent_text}}", intent_text)
            .replace("{{notes_text}}", notes_text))


def render_s4b_user(rule_clauses_json: str) -> str:
    return S4B_USER.replace("{{rule_clauses_json}}", rule_clauses_json)


def render_s4c_user(entities_json: str, omit_files_json: str) -> str:
    return (S4C_USER
            .replace("{{entities_json}}", entities_json)
            .replace("{{omit_files_json}}", omit_files_json))


def render_s4d_user(network_steps_json: str) -> str:
    return S4D_USER.replace("{{network_steps_json}}", network_steps_json)


def render_s4e_user(
    all_workflow_steps_json: str,
    workflow_prose: str,
    interaction_requirements_json: str,
    medium_clauses_json: str,
    hard_rule_clauses_json: str,
    success_and_examples: str,
    symbol_table: str,
) -> tuple[str, str]:
    system = S4E_SYSTEM.replace("{{symbol_table}}", symbol_table)
    user = (S4E_USER
            .replace("{{all_workflow_steps_json}}", all_workflow_steps_json)
            .replace("{{workflow_prose}}", workflow_prose)
            .replace("{{interaction_requirements_json}}", interaction_requirements_json)
            .replace("{{medium_clauses_json}}", medium_clauses_json)
            .replace("{{hard_rule_clauses_json}}", hard_rule_clauses_json)
            .replace("{{success_and_examples}}", success_and_examples))
    return system, user
