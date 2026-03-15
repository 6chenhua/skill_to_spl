"""
step3_interface_inference.py
────────────────────────────
Step 3: Structured Entity and Step Extraction.

Two sequential LLM calls:

  Step 3A — Entity Extraction
    Input:  ARTIFACTS + WORKFLOW + EXAMPLES sections
    Output: list[EntitySpec]
    Note:   is_file is derived from kind by code, not output by the LLM.
            from_omit_files defaults to False; P3 assembler overwrites it.

  Step 3B — Workflow Analysis
    Input:  WORKFLOW + TOOLS + EVIDENCE sections
            + entity_ids from Step 3A (as prerequisite/produces constraint)
    Output: workflow_steps, alternative_flows, exception_flows

    Steps requiring user input are WorkflowStepSpec entries with
    execution_mode="USER_INPUT". No separate InteractionRequirement object.

    classified_clauses is no longer consumed by Step 3.
"""

from __future__ import annotations

import json
import logging

from models.data_models import (
    AlternativeFlowSpec,
    ClassifiedClause,
    EntitySpec,
    ExceptionFlowSpec,
    FlowStep,
    SectionBundle,
    StructuredSpec,
    WorkflowStepSpec,
)
from pipeline.llm_client import LLMClient
from prompts import templates

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────────────────

def run_step3a_entity_extraction(
    bundle: SectionBundle,
    client: LLMClient,
) -> list[EntitySpec]:
    """
    Step 3A: Extract named data entities.

    Reads ARTIFACTS + WORKFLOW + EXAMPLES so entities mentioned only in
    workflow context (e.g., "produces evaluation_suite") are not missed.

    Field ownership:
      LLM sets:   entity_id, kind, type_name, schema_notes,
                  provenance_required, file_path, provenance, source_text
      Code sets:  is_file = (kind == "Artifact")   — derived here
                  from_omit_files = False           — P3 assembler overwrites
    """
    user_prompt = templates.render_step3a_user(
        artifacts_section=bundle.to_text(["ARTIFACTS"]),
        workflow_section=bundle.to_text(["WORKFLOW"]),
        examples_section=bundle.to_text(["EXAMPLES"]),
    )

    raw = client.call_json(
        step_name="step3a_entity_extraction",
        system=templates.STEP3A_SYSTEM,
        user=user_prompt,
    )

    entities = _parse_entities(raw.get("entities", []))
    logger.info("[Step 3A] extracted %d entities", len(entities))
    return entities


def run_step3b_workflow_analysis(
    bundle: SectionBundle,
    entity_ids: list[str],
    client: LLMClient,
) -> StructuredSpec:
    """
    Step 3B: Extract workflow steps, alternative/exception flows.

    entity_ids from Step 3A constrain prerequisites/produces so the LLM
    cannot invent entity names.

    Steps requiring user input have execution_mode="USER_INPUT".
    Returns a StructuredSpec with entities=[] (filled by the caller).
    """
    user_prompt = templates.render_step3b_user(
        entity_ids_json=json.dumps(entity_ids, indent=2, ensure_ascii=False),
        workflow_section=bundle.to_text(["WORKFLOW"]),
        tools_section=bundle.to_text(["TOOLS"]),
        evidence_section=bundle.to_text(["EVIDENCE"]),
    )

    raw = client.call_json(
        step_name="step3b_workflow_analysis",
        system=templates.STEP3B_SYSTEM,
        user=user_prompt,
    )

    spec = _parse_step3b_result(raw)
    val_gates = sum(1 for s in spec.workflow_steps if s.is_validation_gate)
    user_inputs = sum(
        1 for s in spec.workflow_steps if s.execution_mode == "USER_INPUT"
    )
    logger.info(
        "[Step 3B] %d steps (%d validation gates, %d user-input), "
        "%d alt-flows, %d exc-flows",
        len(spec.workflow_steps), val_gates, user_inputs,
        len(spec.alternative_flows), len(spec.exception_flows)
    )
    return spec


def run_step3_structured_extraction(
    bundle: SectionBundle,
    classified_clauses: list[ClassifiedClause],  # unused; kept for orchestrator compat
    client: LLMClient,
) -> StructuredSpec:
    """
    Combined Step 3A + 3B. This is the function the orchestrator calls.
    classified_clauses is accepted but not used (see module docstring).
    """
    entities = run_step3a_entity_extraction(bundle, client)

    partial = run_step3b_workflow_analysis(
        bundle=bundle,
        entity_ids=[e.entity_id for e in entities],
        client=client,
    )

    return StructuredSpec(
        entities=entities,
        workflow_steps=partial.workflow_steps,
        alternative_flows=partial.alternative_flows,
        exception_flows=partial.exception_flows,
    )


# Backward-compatible alias
def run_step3_interface_inference(
    bundle: SectionBundle,
    classified_clauses: list[ClassifiedClause],
    client: LLMClient,
) -> StructuredSpec:
    return run_step3_structured_extraction(bundle, classified_clauses, client)


# ─────────────────────────────────────────────────────────────────────────────
# Parse helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_entities(items: list) -> list[EntitySpec]:
    """is_file derived from kind; from_omit_files defaults False."""
    parsed = []
    for item in items:
        kind = item.get("kind", "Artifact")
        parsed.append(EntitySpec(
            entity_id=item.get("entity_id", ""),
            kind=kind,
            type_name=item.get("type_name", ""),
            schema_notes=item.get("schema_notes", ""),
            provenance_required=bool(item.get("provenance_required", False)),
            is_file=(kind == "Artifact"),
            file_path=item.get("file_path", ""),
            from_omit_files=False,
            provenance=item.get("provenance", "LOW_CONFIDENCE"),
            source_text=item.get("source_text", ""),
        ))
    return parsed


def _parse_workflow_steps(items: list) -> list[WorkflowStepSpec]:
    return [
        WorkflowStepSpec(
            step_id=item.get("step_id", ""),
            description=item.get("description", ""),
            prerequisites=item.get("prerequisites", []),
            produces=item.get("produces", []),
            is_validation_gate=bool(item.get("is_validation_gate", False)),
            effects=item.get("effects", []),
            execution_mode=item.get("execution_mode", "LLM_PROMPT"),
            tool_hint=item.get("tool_hint", ""),
            source_text=item.get("source_text", ""),
        )
        for item in items
    ]


def _parse_flow_step(item: dict) -> FlowStep:
    return FlowStep(
        description=item.get("description", ""),
        execution_mode=item.get("execution_mode", "LLM_PROMPT"),
        tool_hint=item.get("tool_hint", ""),
        source_text=item.get("source_text", ""),
    )


def _parse_alternative_flows(items: list) -> list[AlternativeFlowSpec]:
    return [
        AlternativeFlowSpec(
            flow_id=item.get("flow_id", f"alt-{i:03d}"),
            condition=item.get("condition", ""),
            description=item.get("description", ""),
            steps=[_parse_flow_step(s) for s in item.get("steps", [])],
            source_text=item.get("source_text", ""),
            provenance=item.get("provenance", "EXPLICIT"),
        )
        for i, item in enumerate(items)
    ]


def _parse_exception_flows(items: list) -> list[ExceptionFlowSpec]:
    return [
        ExceptionFlowSpec(
            flow_id=item.get("flow_id", f"exc-{i:03d}"),
            condition=item.get("condition", ""),
            log_ref=item.get("log_ref", ""),
            steps=[_parse_flow_step(s) for s in item.get("steps", [])],
            source_text=item.get("source_text", ""),
            provenance=item.get("provenance", "EXPLICIT"),
        )
        for i, item in enumerate(items)
    ]


def _parse_step3b_result(raw: dict) -> StructuredSpec:
    """Parse Step 3B JSON into a StructuredSpec with entities=[]."""
    return StructuredSpec(
        entities=[],
        workflow_steps=_parse_workflow_steps(raw.get("workflow_steps", [])),
        alternative_flows=_parse_alternative_flows(
            raw.get("alternative_flows", [])),
        exception_flows=_parse_exception_flows(
            raw.get("exception_flows", [])),
    )


_parse_interface_spec = _parse_step3b_result

