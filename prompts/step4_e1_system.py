"""S4E1 — Block Nesting Detection System Prompt

Detects illegal nested BLOCK structures in SPL WORKER output.
BLOCKs (SEQUENTIAL_BLOCK, IF_BLOCK, LOOP_BLOCK) may only contain COMMANDs,
never other BLOCKs.
"""

v1 = """\
You receive an SPL [DEFINE_WORKER:] block that may contain illegal nested BLOCKs. Identify and list every location where a BLOCK (SEQUENTIAL_BLOCK, IF_BLOCK, LOOP_BLOCK) appears directly inside another BLOCK.

The grammar forbids nesting:

BLOCK := SEQUENTIAL_BLOCK | IF_BLOCK | LOOP_BLOCK

SEQUENTIAL_BLOCK := "[SEQUENTIAL_BLOCK]" {COMMAND} "[END_SEQUENTIAL_BLOCK]"

IF_BLOCK := DECISION_INDEX "[IF" CONDITION "]" {COMMAND} ... "[END_IF]"

WHILE_BLOCK := DECISION_INDEX "[WHILE" CONDITION "]" {COMMAND} "[END_WHILE]"

FOR_BLOCK := DECISION_INDEX "[FOR" CONDITION "]" {COMMAND} "[END_FOR]"

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

If no violations exist, return:

{"has_violations": false, "violations": []}
"""
