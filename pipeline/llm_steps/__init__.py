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

from pipeline.llm_steps.step1_structure_extraction import run_step1_structure_extraction
# Step 3: New architecture (W -> IO -> T)
from pipeline.llm_steps.step3 import (
    run_step3_full,
    run_step3_full_sync,
)

__all__ = [
    "run_step1_structure_extraction",
    "run_step3_full",           # New: W -> IO -> T orchestrator
    "run_step3_full_sync",      # New: Sync version of W -> IO -> T
]
