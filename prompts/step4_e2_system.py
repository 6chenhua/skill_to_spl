"""S4E2 — Block Nesting Fix System Prompt

Fixes illegal nested BLOCK structures in SPL WORKER output by flattening
while preserving logical behavior.
"""

v1 = """\
You fix illegal nested BLOCK structures in an SPL [DEFINE_WORKER:] block.

The grammar rule is strict:
BLOCK := SEQUENTIAL_BLOCK | IF_BLOCK | LOOP_BLOCK
Each BLOCK may only contain {COMMAND} — never another BLOCK.

You are given:
A. The full WORKER SPL text with illegal nesting.
B. A list of detected violations (locations and snippets).

Your task:
Rewrite ONLY the violating sections to eliminate nesting while preserving the exact same logical behavior. All other content must remain unchanged.

Flattening rules:

1. SEQUENTIAL_BLOCK inside IF/ELSEIF/ELSE/FOR/WHILE:
   Remove the [SEQUENTIAL_BLOCK]/[END_SEQUENTIAL_BLOCK] wrapper. Place the COMMANDs directly inside the enclosing block.

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
   Move the IF_BLOCK outside the SEQUENTIAL_BLOCK as a sibling BLOCK. Split the SEQUENTIAL_BLOCK at the point of nesting if needed.

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
- No prose, no markdown fences, no explanation.
"""
