"""
step4_spl_emission.py
─────────────────────
Step 4: SPL Emission (dependency-driven parallel execution).

Changes from prior version:
  - Implemented dependency-driven task scheduling for optimal parallelism:
    * S4C generates symbol_table, which immediately triggers S4A and S4B
    * S4D runs in parallel with S4C (no mutual dependency)
    * S4E waits for both S4C (symbol_table) and S4D (apis_spl)
  - Previous round-based blocking approach removed in favor of async futures

Task dependency graph:
  Step 3A (entities) ──┬─→ S4C ──→ symbol_table ──┬─→ S4A (persona)
                       │                          ├─→ S4B (constraints)
                       │                          └─→ S4E ←──┬── apis_spl (from S4D)
                       │                                     │
                       └─→ Step 3B ──→ workflow/flows ────────┘
                                                       │
                                                       ↓
                                                      S4F
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from models.data_models import (
    AlternativeFlowSpec,
    EntitySpec,
    ExceptionFlowSpec,
    SectionBundle,
    SPLSpec,
    StructuredSpec,
    WorkflowStepSpec,
)
from pipeline.llm_client import LLMClient
from prompts import templates

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_step4_spl_emission(
    bundle: SectionBundle,
    interface_spec: StructuredSpec,
    skill_id: str,
    client: LLMClient,
) -> SPLSpec:
    """
    Step 4: Emit the final normalized SPL specification.

    Dependency-driven parallel execution:
      1. S4C (variables/files) and S4D (apis) start immediately in parallel
         - S4C depends on interface_spec.entities (Step 3A output)
         - S4D depends on interface_spec.workflow_steps (Step 3B output)
      
      2. When S4C completes → extract symbol_table → immediately start S4A + S4B
         - S4A depends on symbol_table + bundle[INTENT/NOTES]
         - S4B depends on symbol_table + bundle[CONSTRAINTS]
         - S4A/S4B do NOT wait for S4D to complete (optimization!)
      
      3. S4E starts only when BOTH symbol_table (from S4C) AND apis_spl (from S4D) are ready
         - S4E depends on: symbol_table + apis_spl + workflow/flows (from Step 3B)
      
      4. S4F starts when S4E completes
         - S4F depends on: worker_spl (from S4E) + bundle[EXAMPLES]

    This design maximizes parallelism: S4A and S4B can complete while S4D is still running.
    """
    # Prepare all inputs upfront (lightweight, no LLM calls)
    s4a_inputs, s4b_inputs, s4c_inputs, s4d_inputs, s4e_inputs, s4f_inputs = _prepare_step4_inputs_v2(
        bundle, interface_spec
    )

    with ThreadPoolExecutor(max_workers=4) as pool:
        # ── Phase 1: Launch S4C and S4D immediately (they are independent) ─────
        logger.info("[Step 4] Phase 1: Launching S4C (variables/files) and S4D (apis) in parallel")
        
        future_4c = pool.submit(_call_4c, client, s4c_inputs)
        future_4d = pool.submit(_call_4d, client, s4d_inputs)

        # ── Phase 2: When S4C completes, extract symbol table and launch S4A + S4B ──
        # Note: We don't wait for S4D here - this is the key optimization!
        logger.info("[Step 4] Phase 2: Waiting for S4C to extract symbol table...")
        block_4c = future_4c.result()
        
        symbol_table = _extract_symbol_table(block_4c)
        symbol_table_text = _format_symbol_table(symbol_table)
        logger.info("[Step 4] Symbol table extracted — variables: %d, files: %d",
                     len(symbol_table["variables"]), len(symbol_table["files"]))

        # Launch S4A and S4B immediately (they only need symbol_table, not apis_spl)
        logger.info("[Step 4] Phase 2: Launching S4A (persona) and S4B (constraints) in parallel")
        future_4a = pool.submit(_call_4a, client, s4a_inputs, symbol_table_text)
        future_4b = pool.submit(_call_4b, client, s4b_inputs, symbol_table_text)

        # ── Phase 3: Wait for S4D to complete, then launch S4E ─────────────────
        # S4E needs both symbol_table (ready) and apis_spl (from S4D)
        logger.info("[Step 4] Phase 3: Waiting for S4D to complete...")
        block_4d = future_4d.result()
        
        logger.info("[Step 4] Phase 3: Launching S4E (worker)")
        future_4e = pool.submit(_call_4e, client, s4e_inputs, symbol_table_text, block_4d)

        # ── Phase 4: Collect S4A and S4B results ───────────────────────────────
        # These may have already completed while we were waiting for S4D
        block_4a = future_4a.result()
        block_4b = future_4b.result()

        # ── Phase 5: Wait for S4E, then launch S4F ─────────────────────────────
        logger.info("[Step 4] Phase 4: Waiting for S4E to complete...")
        block_4e = future_4e.result()

        block_4f = ""
        if s4f_inputs["has_examples"]:
            logger.info("[Step 4] Phase 5: Generating S4F (examples)")
            block_4f = _call_4f(client, s4f_inputs, block_4e)

    # ── Assemble final SPL ────────────────────────────────────────────────────
    spl_text = _assemble_spl(
        skill_id, block_4a, block_4b, block_4c, block_4d, block_4e, block_4f
    )
    review_summary = _build_review_summary()
    clause_counts = {}

    logger.info("[Step 4] SPL assembled (%d chars)", len(spl_text))
    return SPLSpec(
        skill_id=skill_id,
        spl_text=spl_text,
        review_summary=review_summary,
        clause_counts=clause_counts,
    )


def run_step4_spl_emission_parallel(
    bundle: SectionBundle,
    entities: list[EntitySpec],
    workflow_steps: list[WorkflowStepSpec],
    alternative_flows: list[AlternativeFlowSpec],
    exception_flows: list[ExceptionFlowSpec],
    skill_id: str,
    client: LLMClient,
) -> SPLSpec:
    """
    Step 4: SPL Emission with maximum parallelism between 3A/3B and Step 4.
    
    Parallel execution lines:
      Line 1: S4C (needs entities) → symbol_table → (S4A || S4B)
      Line 2: S4D (needs workflow_steps with NETWORK effects)
      
    Merge point: S4E needs both symbol_table (from Line 1) and apis_spl (from Line 2)
    Final: S4F needs S4E output
    
    Args:
        bundle: SectionBundle with all sections (INTENT, NOTES, CONSTRAINTS, EXAMPLES, etc.)
        entities: From Step 3A entity extraction
        workflow_steps: From Step 3B workflow analysis
        alternative_flows: From Step 3B workflow analysis
        exception_flows: From Step 3B workflow analysis
        skill_id: The skill identifier
        client: LLM client for making calls
        
    Returns:
        SPLSpec with the complete SPL specification
    """
    # Prepare inputs for each sub-step
    s4a_inputs, s4b_inputs, s4c_inputs, s4d_inputs, s4e_inputs, s4f_inputs = _prepare_step4_inputs_parallel(
        bundle, entities, workflow_steps, alternative_flows, exception_flows
    )

    with ThreadPoolExecutor(max_workers=4) as pool:
        # ── Line 1: S4C (needs entities) ─────────────────────────────────────
        logger.info("[Step 4] Line 1: Launching S4C (variables/files)")
        future_4c = pool.submit(_call_4c, client, s4c_inputs)
        
        # ── Line 2: S4D (needs workflow_steps with NETWORK effects) ──────────
        logger.info("[Step 4] Line 2: Launching S4D (apis)")
        future_4d = pool.submit(_call_4d, client, s4d_inputs)

        # ── Line 1 continued: When S4C completes, extract symbol_table ───────
        logger.info("[Step 4] Line 1: Waiting for S4C to extract symbol table...")
        block_4c = future_4c.result()
        
        symbol_table = _extract_symbol_table(block_4c)
        symbol_table_text = _format_symbol_table(symbol_table)
        logger.info("[Step 4] Symbol table extracted — variables: %d, files: %d",
                     len(symbol_table["variables"]), len(symbol_table["files"]))

        # Launch S4A and S4B (they only need symbol_table, not apis_spl)
        logger.info("[Step 4] Line 1: Launching S4A (persona) and S4B (constraints)")
        future_4a = pool.submit(_call_4a, client, s4a_inputs, symbol_table_text)
        future_4b = pool.submit(_call_4b, client, s4b_inputs, symbol_table_text)

        # ── Merge Point: Wait for Line 2 (S4D) to complete ───────────────────
        logger.info("[Step 4] Merge point: Waiting for Line 2 (S4D) to complete...")
        block_4d = future_4d.result()
        
        # ── S4E: Needs both symbol_table (Line 1) and apis_spl (Line 2) ──────
        logger.info("[Step 4] Launching S4E (worker) - merge of Line 1 and Line 2")
        future_4e = pool.submit(_call_4e, client, s4e_inputs, symbol_table_text, block_4d)

        # Collect S4A and S4B results (may already be done)
        block_4a = future_4a.result()
        block_4b = future_4b.result()

        # ── S4F: Final step, needs S4E output ────────────────────────────────
        logger.info("[Step 4] Final: Waiting for S4E to complete...")
        block_4e = future_4e.result()

        block_4f = ""
        if s4f_inputs["has_examples"]:
            logger.info("[Step 4] Final: Generating S4F (examples)")
            block_4f = _call_4f(client, s4f_inputs, block_4e)

    # ── Assemble final SPL ────────────────────────────────────────────────────
    spl_text = _assemble_spl(
        skill_id, block_4a, block_4b, block_4c, block_4d, block_4e, block_4f
    )
    review_summary = _build_review_summary()
    clause_counts = {}

    logger.info("[Step 4] SPL assembled (%d chars)", len(spl_text))
    return SPLSpec(
        skill_id=skill_id,
        spl_text=spl_text,
        review_summary=review_summary,
        clause_counts=clause_counts,
    )


# ── Individual step call functions ────────────────────────────────────────────

def _call_4c(client: LLMClient, inputs: dict) -> str:
    """Generate DEFINE_VARIABLES + DEFINE_FILES block."""
    if not inputs["has_entities"]:
        return ""
    combined = inputs["entities_text"]
    if inputs["omit_files_text"].strip() and inputs["omit_files_text"] != "(No omit files found)":
        combined += "\n\n" + inputs["omit_files_text"]
    return client.call(
        "step4c_variables_files",
        templates.S4C_SYSTEM,
        templates.render_s4c_user(inputs["entities_text"], inputs["omit_files_text"]),
    )

def _call_4d(client: LLMClient, inputs: dict) -> str:
    """Generate DEFINE_APIS block."""
    if not inputs["has_network_steps"]:
        return ""
    return client.call(
        "step4d_apis",
        templates.S4D_SYSTEM,
        templates.render_s4d_user(
            network_steps_json=inputs["network_steps_json"],
        ),
    )

def _call_4a(client: LLMClient, inputs: dict, symbol_table_text: str) -> str:
    """Generate PERSONA / AUDIENCE / CONCEPTS block."""
    return client.call(
        "step4a_persona",
        templates.S4A_SYSTEM,
        templates.render_s4a_user(
            intent_text=inputs["intent_text"],
            notes_text=inputs["notes_text"],
            symbol_table=symbol_table_text,
        ),
    )

def _call_4b(client: LLMClient, inputs: dict, symbol_table_text: str) -> str:
    """Generate DEFINE_CONSTRAINTS block."""
    if not inputs["has_constraints"]:
        return ""
    return client.call(
        "step4b_constraints",
        templates.S4B_SYSTEM,
        templates.render_s4b_user(
            constraints_text=inputs["constraints_text"],
            symbol_table=symbol_table_text,
        ),
    )

def _call_4e(client: LLMClient, inputs: dict, symbol_table_text: str, apis_spl: str) -> str:
    """Generate WORKER block (MAIN_FLOW + ALTERNATIVE_FLOW + EXCEPTION_FLOW)."""
    s4e_system, s4e_user = templates.render_s4e_user(
        workflow_steps_json=inputs["workflow_steps_json"],
        workflow_prose=inputs["workflow_prose"],
        alternative_flows_json=inputs["alternative_flows_json"],
        exception_flows_json=inputs["exception_flows_json"],
        symbol_table=symbol_table_text,
        apis_spl=apis_spl,
    )
    return client.call(step_name="step4e_worker", system=s4e_system, user=s4e_user)

def _call_4f(client: LLMClient, inputs: dict, worker_spl: str) -> str:
    """Generate [EXAMPLES] block."""
    return client.call(
        "step4f_examples",
        templates.S4F_SYSTEM,
        templates.render_s4f_user(
            worker_spl=worker_spl,
            examples_text=inputs["examples_text"],
        ),
    )


# ── Input preparation ─────────────────────────────────────────────────────────

def _prepare_step4_inputs_parallel(
    bundle: SectionBundle,
    entities: list[EntitySpec],
    workflow_steps: list[WorkflowStepSpec],
    alternative_flows: list[AlternativeFlowSpec],
    exception_flows: list[ExceptionFlowSpec],
) -> tuple[dict, dict, dict, dict, dict, dict]:
    """
    Pre-compute all inputs for Step 4 calls with parallel execution support.
    
    Accepts decomposed inputs from Step 3A (entities) and Step 3B (workflow/flows)
    to enable maximum parallelism between Step 3 and Step 4.
    
    Returns 6 dictionaries for each S4x call.
    
    Parallel lines:
      Line 1: S4C (entities) -> symbol_table -> S4A + S4B
      Line 2: S4D (workflow_steps with NETWORK effects)
      Merge: S4E (needs symbol_table + apis_spl)
      Final: S4F (needs S4E output)
    """
    # S4A inputs - from bundle
    intent_text = bundle.to_text(["INTENT"])
    notes_text = bundle.to_text(["NOTES"])
    s4a_inputs = {
        "intent_text": intent_text,
        "notes_text": notes_text,
    }
    
    # S4B inputs - from bundle
    constraints_text = bundle.to_text(["CONSTRAINTS"])
    s4b_inputs = {
        "constraints_text": constraints_text,
        "has_constraints": bool(constraints_text.strip()),
    }
    
    # S4C inputs - from entities (Step 3A)
    entities_text = _format_entities_for_s4c(entities)
    omit_files = [e for e in entities if getattr(e, "from_omit_files", False)]
    omit_files_text = _format_omit_files_for_s4c(omit_files)
    s4c_inputs = {
        "entities_text": entities_text,
        "omit_files_text": omit_files_text,
        "has_entities": bool(entities),
    }
    
    # S4D inputs - from workflow_steps with NETWORK effects (Step 3B)
    network_steps = [s for s in workflow_steps if "NETWORK" in s.effects]
    network_steps_json = json.dumps(
        [_step_to_dict(s) for s in network_steps],
        indent=2, ensure_ascii=False,
    )
    s4d_inputs = {
        "network_steps_json": network_steps_json,
        "has_network_steps": bool(network_steps),
    }
    
    # S4E inputs - from workflow_steps, flows (Step 3B)
    workflow_steps_json = json.dumps(
        [_step_to_dict(s) for s in workflow_steps],
        indent=2, ensure_ascii=False,
    )
    workflow_prose = bundle.to_text(["WORKFLOW"])
    alternative_flows_json = json.dumps(
        [dataclasses.asdict(f) for f in alternative_flows],
        indent=2, ensure_ascii=False,
    )
    exception_flows_json = json.dumps(
        [dataclasses.asdict(f) for f in exception_flows],
        indent=2, ensure_ascii=False,
    )
    s4e_inputs = {
        "workflow_steps_json": workflow_steps_json,
        "workflow_prose": workflow_prose,
        "alternative_flows_json": alternative_flows_json,
        "exception_flows_json": exception_flows_json,
    }
    
    # S4F inputs - from bundle
    examples_text = bundle.to_text(["EXAMPLES"])
    s4f_inputs = {
        "examples_text": examples_text,
        "has_examples": bool(examples_text.strip()),
    }
    
    return s4a_inputs, s4b_inputs, s4c_inputs, s4d_inputs, s4e_inputs, s4f_inputs


def _prepare_step4_inputs_v2(
    bundle: SectionBundle,
    structured_spec: StructuredSpec,
) -> tuple[dict, dict, dict, dict, dict, dict]:
    """
    Pre-compute all inputs for the Step 4 calls.
    
    Returns 6 dictionaries, one for each S4x call, to avoid passing unnecessary
    data to each function.
    
    Dependencies:
      S4A: bundle[INTENT + NOTES]
      S4B: bundle[CONSTRAINTS]
      S4C: structured_spec.entities + omit_files
      S4D: NETWORK steps from structured_spec.workflow_steps
      S4E: ALL workflow_steps + flows + symbol_table + apis_spl
      S4F: bundle[EXAMPLES] + worker_spl
    """
    # S4A inputs
    intent_text = bundle.to_text(["INTENT"])
    notes_text = bundle.to_text(["NOTES"])
    s4a_inputs = {
        "intent_text": intent_text,
        "notes_text": notes_text,
    }
    
    # S4B inputs
    constraints_text = bundle.to_text(["CONSTRAINTS"])
    s4b_inputs = {
        "constraints_text": constraints_text,
        "has_constraints": bool(constraints_text.strip()),
    }
    
    # S4C inputs
    entities_text = _format_entities_for_s4c(structured_spec.entities)
    omit_files = [e for e in structured_spec.entities if getattr(e, "from_omit_files", False)]
    omit_files_text = _format_omit_files_for_s4c(omit_files)
    s4c_inputs = {
        "entities_text": entities_text,
        "omit_files_text": omit_files_text,
        "has_entities": bool(structured_spec.entities),
    }
    
    # S4D inputs
    network_steps = [s for s in structured_spec.workflow_steps if "NETWORK" in s.effects]
    network_steps_json = json.dumps(
        [_step_to_dict(s) for s in network_steps],
        indent=2, ensure_ascii=False,
    )
    s4d_inputs = {
        "network_steps_json": network_steps_json,
        "has_network_steps": bool(network_steps),
    }
    
    # S4E inputs
    workflow_steps_json = json.dumps(
        [_step_to_dict(s) for s in structured_spec.workflow_steps],
        indent=2, ensure_ascii=False,
    )
    workflow_prose = bundle.to_text(["WORKFLOW"])
    alternative_flows_json = json.dumps(
        [dataclasses.asdict(f) for f in structured_spec.alternative_flows],
        indent=2, ensure_ascii=False,
    )
    exception_flows_json = json.dumps(
        [dataclasses.asdict(f) for f in structured_spec.exception_flows],
        indent=2, ensure_ascii=False,
    )
    s4e_inputs = {
        "workflow_steps_json": workflow_steps_json,
        "workflow_prose": workflow_prose,
        "alternative_flows_json": alternative_flows_json,
        "exception_flows_json": exception_flows_json,
    }
    
    # S4F inputs
    examples_text = bundle.to_text(["EXAMPLES"])
    s4f_inputs = {
        "examples_text": examples_text,
        "has_examples": bool(examples_text.strip()),
    }
    
    return s4a_inputs, s4b_inputs, s4c_inputs, s4d_inputs, s4e_inputs, s4f_inputs


def _prepare_step4_inputs_parallel(
    bundle: SectionBundle,
    entities: list[EntitySpec],
    workflow_steps: list[WorkflowStepSpec],
    alternative_flows: list[AlternativeFlowSpec],
    exception_flows: list[ExceptionFlowSpec],
) -> tuple[dict, dict, dict, dict, dict, dict]:
    """
    Pre-compute all inputs for Step 4 calls with parallel execution support.
    
    Accepts decomposed inputs from Step 3A (entities) and Step 3B (workflow/flows)
    to enable maximum parallelism between Step 3 and Step 4.
    
    Returns 6 dictionaries for each S4x call.
    
    Parallel lines:
      Line 1: S4C (entities) → symbol_table → S4A + S4B
      Line 2: S4D (workflow_steps with NETWORK effects)
      Merge: S4E (needs symbol_table + apis_spl)
      Final: S4F (needs S4E output)
    """
    # S4A inputs - from bundle
    intent_text = bundle.to_text(["INTENT"])
    notes_text = bundle.to_text(["NOTES"])
    s4a_inputs = {
        "intent_text": intent_text,
        "notes_text": notes_text,
    }
    
    # S4B inputs - from bundle
    constraints_text = bundle.to_text(["CONSTRAINTS"])
    s4b_inputs = {
        "constraints_text": constraints_text,
        "has_constraints": bool(constraints_text.strip()),
    }
    
    # S4C inputs - from entities (Step 3A)
    entities_text = _format_entities_for_s4c(entities)
    omit_files = [e for e in entities if getattr(e, "from_omit_files", False)]
    omit_files_text = _format_omit_files_for_s4c(omit_files)
    s4c_inputs = {
        "entities_text": entities_text,
        "omit_files_text": omit_files_text,
        "has_entities": bool(entities),
    }
    
    # S4D inputs - from workflow_steps with NETWORK effects (Step 3B)
    network_steps = [s for s in workflow_steps if "NETWORK" in s.effects]
    network_steps_json = json.dumps(
        [_step_to_dict(s) for s in network_steps],
        indent=2, ensure_ascii=False,
    )
    s4d_inputs = {
        "network_steps_json": network_steps_json,
        "has_network_steps": bool(network_steps),
    }
    
    # S4E inputs - from workflow_steps, flows (Step 3B)
    workflow_steps_json = json.dumps(
        [_step_to_dict(s) for s in workflow_steps],
        indent=2, ensure_ascii=False,
    )
    workflow_prose = bundle.to_text(["WORKFLOW"])
    alternative_flows_json = json.dumps(
        [dataclasses.asdict(f) for f in alternative_flows],
        indent=2, ensure_ascii=False,
    )
    exception_flows_json = json.dumps(
        [dataclasses.asdict(f) for f in exception_flows],
        indent=2, ensure_ascii=False,
    )
    s4e_inputs = {
        "workflow_steps_json": workflow_steps_json,
        "workflow_prose": workflow_prose,
        "alternative_flows_json": alternative_flows_json,
        "exception_flows_json": exception_flows_json,
    }
    
    # S4F inputs - from bundle
    examples_text = bundle.to_text(["EXAMPLES"])
    s4f_inputs = {
        "examples_text": examples_text,
        "has_examples": bool(examples_text.strip()),
    }
    
    return s4a_inputs, s4b_inputs, s4c_inputs, s4d_inputs, s4e_inputs, s4f_inputs


# Legacy function kept for backward compatibility
def _prepare_step4_inputs(
    bundle: SectionBundle,
    structured_spec: StructuredSpec,
) -> dict:
    """
    Legacy input preparation function.
    Use _prepare_step4_inputs_v2 for the new dependency-driven scheduler.
    """
    s4a, s4b, s4c, s4d, s4e, s4f = _prepare_step4_inputs_v2(bundle, structured_spec)
    return {
        **s4a,
        **s4b,
        **s4c,
        **s4d,
        **s4e,
        **s4f,
    }


def _format_entities_for_s4c(entities: list[EntitySpec]) -> str:
    if not entities:
        return "(No entities found)"

    variables = [e for e in entities if e.kind != "Artifact"]
    files     = [e for e in entities if e.kind == "Artifact"]
    lines = []

    if variables:
        lines.append("VARIABLES (in-memory data structures → DEFINE_VARIABLES):")
        lines.append("")
        for e in variables:
            readonly = "[READONLY] " if e.provenance_required else ""
            lines.append(f"Variable: {readonly}{e.entity_id}")
            lines.append(f"Type:     {e.type_name}")
            lines.append(f"Kind:     {e.kind}")
            if e.schema_notes:
                lines.append(f"Schema:   {e.schema_notes}")
            lines.append(f"Provenance: {e.provenance}")
            if e.source_text:
                lines.append(f"Source:   {e.source_text[:120]}")
            lines.append("")

    if files:
        lines.append("FILES (disk artifacts → DEFINE_FILES):")
        lines.append("")
        for e in files:
            path_display = getattr(e, "file_path", "") or "< >"
            lines.append(f"File: {e.entity_id}")
            lines.append(f"Path: {path_display}")
            lines.append(f"Type: {e.type_name}")
            if e.schema_notes:
                lines.append(f"Description: {e.schema_notes}")
            lines.append(f"Provenance: {e.provenance}")
            if getattr(e, "from_omit_files", False):
                lines.append("Note: Sourced from P1 omit-files (priority=3)")
            lines.append("")

    return "\n".join(lines)


def _format_omit_files_for_s4c(omit_files: list[EntitySpec]) -> str:
    if not omit_files:
        return "(No omit files found)"
    lines = ["Additional files from skill package (P1 priority=3, not merged into main doc):"]
    lines.append("")
    for e in omit_files:
        path_display = getattr(e, "file_path", "") or "< >"
        lines.append(f"- {e.entity_id}: {path_display}")
        lines.append(f"  Type: {e.type_name}")
        lines.append(f"  Kind: {e.kind}")
        lines.append("")
    return "\n".join(lines)


def _step_to_dict(s: WorkflowStepSpec) -> dict:
    return {
        "step_id":            s.step_id,
        "description":        s.description,
        "prerequisites":      s.prerequisites,
        "produces":           s.produces,
        "is_validation_gate": s.is_validation_gate,
        "effects":            s.effects,
        "tool_hint":          s.tool_hint,
        "source_text":        s.source_text,
        "execution_mode":     getattr(s, "execution_mode", "LLM_PROMPT"),
    }


# ── Symbol table ──────────────────────────────────────────────────────────────

_VARIABLE_NAME_RE = re.compile(r'^\s{1,12}"[^"]+"\s+(?:READONLY\s+)?([a-z][a-z0-9_]+):', re.MULTILINE)
_FILE_NAME_RE     = re.compile(r'^\s{1,12}"[^"]+"\s+([a-z][a-z0-9_]+)\s+<', re.MULTILINE)


def _extract_symbol_table(block_4c: str) -> dict[str, list[str]]:
    """
    Extract FILES and VARIABLES declared in the DEFINE_VARIABLES/DEFINE_FILES
    block (4c).  APIS are NOT included — they are passed separately to S4E.
    """
    table: dict[str, list[str]] = {
        "variables": [],
        "files":     [],
    }
    if block_4c:
        parts      = block_4c.split("[END_VARIABLES]")
        var_block  = parts[0] if len(parts) > 1 else block_4c
        file_block = parts[1] if len(parts) > 1 else ""
        table["variables"] = _VARIABLE_NAME_RE.findall(var_block)
        table["files"]     = _FILE_NAME_RE.findall(file_block)
    return table


def _format_symbol_table(symbol_table: dict[str, list[str]]) -> str:
    """
    Render FILES + VARIABLES as a reference block for S4A, S4B, and S4E.
    These are the names that may appear in DESCRIPTION_WITH_REFERENCES across
    all three blocks.  APIS are injected separately into S4E.
    """
    mapping = {
        "variables": "VARIABLES (reference as <REF> var_name </REF>)",
        "files":     "FILES     (reference as <REF> file_name </REF>)",
    }
    lines = []
    for key, label in mapping.items():
        names = symbol_table.get(key, [])
        if names:
            lines.append(f"{label}:\n  {', '.join(names)}")
    return "\n\n".join(lines) if lines else "(no variables or files declared)"


# ── Assembly ──────────────────────────────────────────────────────────────────

def _assemble_spl(
    skill_id: str,
    block_4a: str,
    block_4b: str,
    block_4c: str,
    block_4d: str,
    block_4e: str,
    block_4f: str,
) -> str:
    """
    Concatenate all blocks in canonical SPL order.

    block_4f ([EXAMPLES] block) is inserted INSIDE the WORKER, before
    [END_WORKER].  If [END_WORKER] is not found, 4f is appended separately.
    """
    header = (
        f"# SPL specification — {skill_id}\n"
        f"# Generated by skill-to-cnlp pipeline\n"
    )

    # Insert S4F [EXAMPLES] block into the WORKER before [END_WORKER]
    worker_block = _strip_fences(block_4e.strip())
    if block_4f:
        examples_block = _strip_fences(block_4f.strip())
        if "[END_WORKER]" in worker_block:
            worker_block = worker_block.replace(
                "[END_WORKER]",
                examples_block + "\n[END_WORKER]",
                1,
            )
        else:
            worker_block = worker_block + "\n\n" + examples_block

    blocks = [header]
    for raw_block in (block_4a, block_4b, block_4c, block_4d):
        cleaned = _strip_fences(raw_block.strip())
        if cleaned:
            blocks.append(cleaned)
    if worker_block:
        blocks.append(worker_block)

    return "\n\n".join(blocks)


def _strip_fences(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


# ── Review summary ────────────────────────────────────────────────────────────

def _build_review_summary() -> str:
    return "## Review Summary\n"




# Legacy helper — kept for compatibility
def _split_spl_output(raw_text: str) -> tuple[str, str]:
    marker = "## Review Summary"
    idx = raw_text.find(marker)
    if idx >= 0:
        return raw_text[:idx].strip(), raw_text[idx:].strip()
    return raw_text.strip(), ""