"""
LLM pipeline steps module.

This module provides all the LLM-based processing steps for the skill-to-cnlp pipeline:
- P2: File role resolution
- P3: File summarization
- Step 1: Structure extraction
- Step 2A: Clause extraction and scoring
- Step 3: Interface inference (3A: entities, 3B: workflow)
- Step 4: SPL emission (including parallel version)
"""

from pipeline.llm_steps.p2_file_role_resolve import run_p2_file_role_resolver
from pipeline.llm_steps.p3_summarize_file import make_p3_summarize_fn
from pipeline.llm_steps.step1_structure_extraction import run_step1_structure_extraction
from pipeline.llm_steps.step3_interface_inference import (
    run_step3_interface_inference,
    run_step3_structured_extraction,
    run_step3a_entity_extraction,
    run_step3b_workflow_analysis,
)
from pipeline.llm_steps.step4_spl_emission import (
    run_step4_spl_emission,
    run_step4_spl_emission_parallel,
    # Async versions
    _call_4c_async,
    _call_4a_async,
    _call_4b_async,
    _call_4e_async,
    _call_4e1_async,
    _call_4e2_async,
    _call_4f_async,
    _call_s0_async,
    validate_and_fix_worker_nesting_async,
    # Legacy sync versions
    _call_4c,
    _call_4a,
    _call_4b,
    _call_4e,
    _call_4f,
    _call_s0,
    _extract_symbol_table,
    _format_symbol_table,
    _prepare_step4_inputs_parallel,
    _assemble_spl,
    _build_review_summary,
)

__all__ = [
    "run_p2_file_role_resolver",
    "make_p3_summarize_fn",
    "run_step1_structure_extraction",
    "run_step3_structured_extraction",
    "run_step3a_entity_extraction",
    "run_step3b_workflow_analysis",
    "run_step4_spl_emission",
    "run_step4_spl_emission_parallel",
]
