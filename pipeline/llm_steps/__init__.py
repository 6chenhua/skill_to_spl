"""
LLM pipeline steps module.

This module provides all the LLM-based processing steps for the skill-to-cnlp pipeline:
- P2: File role resolution
- P3: File summarization
- Step 1: Structure extraction
- Step 2A: Clause extraction and scoring
- Step 3: New architecture (W -> IO -> T)
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
from pipeline.llm_steps.step3 import (
    run_step3_full,
    run_step3_full_sync,
)
# Step 4 is now a package - imports remain backward compatible
from pipeline.llm_steps.step4_spl_emission import (
    run_step4_spl_emission,
    run_step4_spl_emission_parallel,
)

__all__ = [
    "run_p2_file_role_resolver",
    "make_p3_summarize_fn",
    "run_step1_structure_extraction",
    "run_step3_structured_extraction",
    "run_step3a_entity_extraction",
    "run_step3b_workflow_analysis",
    "run_step3_full",
    "run_step3_full_sync",
    "run_step4_spl_emission",
    "run_step4_spl_emission_parallel",
]
