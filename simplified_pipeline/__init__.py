"""
Simplified Pipeline for skill-to-CNL-P

A minimal version of the pipeline that:
- Step1: Extracts only 5 sections (INTENT, WORKFLOW, CONSTRAINTS, EXAMPLES, NOTES)
- Step3A: Extracts only variables (no files)
- Step3B: Simplified action types (no API-related types)
- Step4: Generates SPL without DEFINE_APIS and DEFINE_FILES
"""

from .orchestrator import run_pipeline, PipelineConfig
from .llm_client import LLMConfig

__all__ = ["run_pipeline", "PipelineConfig", "LLMConfig"]
