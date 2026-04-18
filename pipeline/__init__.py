"""Pipeline package - Backward-compatible API re-exports.

Usage:
    from pipeline import run_pipeline, PipelineConfig
    result = run_pipeline(config)
"""
from __future__ import annotations

# Re-export backward-compatible API from pipeline.orchestrator module
from pipeline.orchestrator import run_pipeline, PipelineConfig

__all__ = [
    "run_pipeline",
    "PipelineConfig",
]
