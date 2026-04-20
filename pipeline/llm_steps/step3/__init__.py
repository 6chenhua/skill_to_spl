"""
Step 3: Interface Inference Package
====================================

New Step 3 architecture with three sub-steps:
- Step 3-W: Workflow Structure Analysis
- Step 3-IO: Global I/O + Type Analysis
- Step 3-T: TYPES Declaration

Usage:
    from pipeline.llm_steps.step3 import (
        run_step3w_workflow_analysis,
        run_step3io_global_analysis,
        run_step3t_types_declaration,
        run_step3_full,
    )
"""

from pipeline.llm_steps.step3.w import (
    run_step3w_workflow_analysis,
)
from pipeline.llm_steps.step3.io import (
    run_step3io_global_analysis,
    run_step3io_global_analysis_sync,
)
from pipeline.llm_steps.step3.t import (
    run_step3t_types_declaration,
    run_step3t_types_declaration_sync,
)
from pipeline.llm_steps.step3.orchestrator import (
    run_step3_full,
    run_step3_full_sync,
)

__all__ = [
    # Step 3-W
    "run_step3w_workflow_analysis",
    # Step 3-IO
    "run_step3io_global_analysis",
    "run_step3io_global_analysis_sync",
    # Step 3-T
    "run_step3t_types_declaration",
    "run_step3t_types_declaration_sync",
    # Combined orchestrator
    "run_step3_full",
    "run_step3_full_sync",
]
