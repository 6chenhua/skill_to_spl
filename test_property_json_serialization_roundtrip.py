"""
Property-based test for JSON serialization round-trip.

**Feature: integrate-updated-models-templates, Property 8: JSON serialization round-trip**
**Validates: Requirements 3.3**

This test validates that for any data model instance with new fields, serializing 
to JSON and deserializing back should preserve all field values correctly, ensuring 
checkpoint functionality works with enhanced models.
"""

import pytest
import json
from hypothesis import given, strategies as st, settings, HealthCheck
from dataclasses import asdict, fields
from typing import Any, Dict

from models.data_models import (
    FileReferenceGraph,
    RawClause, 
    ClassifiedClause,
    EntitySpec,
    WorkflowStepSpec,
    RawScores,
    Classification
)


# Strategy generators for creating valid test data
@st.composite
def file_reference_graph_strategy(draw):
    """Generate valid FileReferenceGraph instances with new fields."""
    return FileReferenceGraph(
        skill_id=draw(st.text(min_size=1, max_size=20)),
        root_path=draw(st.text(min_size=1, max_size=20)),
        skill_md_content=draw(st.text(min_size=1, max_size=100)),
        frontmatter=draw(st.dictionaries(st.text(min_size=1, max_size=10), st.text(min_size=1, max_size=10), max_size=3)),
        nodes={},
        edges={},
        local_scripts=draw(st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=3)),
        referenced_libs=draw(st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=3))
    )


@st.composite
def raw_scores_strategy(draw):
    """Generate valid RawScores instances."""
    return RawScores(
        O=draw(st.integers(min_value=0, max_value=3)),
        A=draw(st.integers(min_value=0, max_value=3)),
        F=draw(st.integers(min_value=0, max_value=3)),
        C=draw(st.integers(min_value=0, max_value=3)),
        R=draw(st.integers(min_value=0, max_value=3)),
        V=draw(st.integers(min_value=0, max_value=3))
    )


@st.composite
def raw_clause_strategy(draw):
    """Generate valid RawClause instances with new fields."""
    return RawClause(
        clause_id=draw(st.text(min_size=1, max_size=50)),
        source_section=draw(st.text(min_size=1, max_size=100)),
        source_file=draw(st.text(min_size=1, max_size=100)),
        original_text=draw(st.text(min_size=1, max_size=500)),
        is_normative=draw(st.booleans()),
        split=draw(st.booleans()),
        sub_clauses=[],  # Keep simple for testing
        scores=draw(raw_scores_strategy()),
        score_rationale=draw(st.text(min_size=1, max_size=200)),
        clause_type=draw(st.sampled_from(["rule", "step", "prerequisite", "guidance"]))
    )


@st.composite
def classified_clause_strategy(draw):
    """Generate valid ClassifiedClause instances with new fields."""
    return ClassifiedClause(
        clause_id=draw(st.text(min_size=1, max_size=50)),
        original_text=draw(st.text(min_size=1, max_size=500)),
        source_section=draw(st.text(min_size=1, max_size=100)),
        source_file=draw(st.text(min_size=1, max_size=100)),
        scores=draw(raw_scores_strategy()),
        S_det=draw(st.integers(min_value=0, max_value=3)),
        S_proc=draw(st.integers(min_value=0, max_value=3)),
        classification=draw(st.sampled_from([Classification.SOFT, Classification.MEDIUM, Classification.HARD])),
        risk_override=draw(st.booleans()),
        confidence=draw(st.floats(min_value=0.0, max_value=1.0)),
        needs_review=draw(st.booleans()),
        enforcement_backends=draw(st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=5)),
        score_rationale=draw(st.text(min_size=1, max_size=200)),
        clause_type=draw(st.sampled_from(["rule", "step", "prerequisite", "guidance"])),
        downgraded=draw(st.booleans())
    )


@st.composite
def entity_spec_strategy(draw):
    """Generate valid EntitySpec instances with new fields."""
    return EntitySpec(
        entity_id=draw(st.text(min_size=1, max_size=50)),
        kind=draw(st.sampled_from(["Artifact", "Run", "Evidence", "Record"])),
        type_name=draw(st.text(min_size=1, max_size=50)),
        schema_notes=draw(st.text(min_size=0, max_size=200)),
        provenance_required=draw(st.booleans()),
        provenance=draw(st.sampled_from(["EXPLICIT", "ASSUMED", "LOW_CONFIDENCE"])),
        source_text=draw(st.text(min_size=1, max_size=200)),
        is_file=draw(st.booleans()),
        file_path=draw(st.text(min_size=0, max_size=100)),
        from_omit_files=draw(st.booleans())
    )


@st.composite
def workflow_step_spec_strategy(draw):
    """Generate valid WorkflowStepSpec instances with new fields."""
    return WorkflowStepSpec(
        step_id=draw(st.text(min_size=1, max_size=50)),
        description=draw(st.text(min_size=1, max_size=200)),
        prerequisite