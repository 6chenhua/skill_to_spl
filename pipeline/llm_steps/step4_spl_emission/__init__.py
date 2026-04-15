"""Step 4: SPL Emission - Modular implementation.

This module provides Step 4 of the skill-to-cnlp pipeline, which emits
the final normalized SPL specification through parallel sub-steps:
- S4A: Persona/Audience/Concepts generation
- S4B: Constraints generation
- S4C: Variables/Files generation
- S4D: API definitions (deprecated, moved to Step 1.5)
- S4E: Worker generation (MAIN_FLOW, ALTERNATIVE_FLOW, EXCEPTION_FLOW)
- S4F: Examples generation
"""

from __future__ import annotations

# Orchestrator entry points
from pipeline.llm_steps.step4_spl_emission.orchestrator import (
    run_step4_spl_emission,
    run_step4_spl_emission_parallel,
)

# Async sub-step calls
from pipeline.llm_steps.step4_spl_emission.substep_calls import (
    _call_4a_async,
    _call_4b_async,
    _call_4c_async,
    _call_4e_async,
    _call_4e1_async,
    _call_4e2_async,
    _call_4f_async,
    _call_s0_async,
)

# Sync sub-step calls (legacy)
from pipeline.llm_steps.step4_spl_emission.substep_calls import (
    _call_4a,
    _call_4b,
    _call_4c,
    _call_4d,
    _call_4e,
    _call_4f,
    _call_s0,
)

# Validation
from pipeline.llm_steps.step4_spl_emission.nesting_validation import (
    validate_and_fix_worker_nesting,
    validate_and_fix_worker_nesting_async,
)

# Symbol table (exposed for advanced use)
from pipeline.llm_steps.step4_spl_emission.symbol_table import (
    _extract_symbol_table,
    _format_symbol_table,
)

# Assembly (exposed for advanced use)
from pipeline.llm_steps.step4_spl_emission.assembly import _assemble_spl

# Input preparation (exposed for advanced use)
from pipeline.llm_steps.step4_spl_emission.inputs import (
    _prepare_step4_inputs_parallel,
    _prepare_step4_inputs_v2,
    _prepare_step4_inputs,  # Legacy
)

# Utilities
from pipeline.llm_steps.step4_spl_emission.utils import _build_review_summary

__all__ = [
    "run_step4_spl_emission",
    "run_step4_spl_emission_parallel",
]
