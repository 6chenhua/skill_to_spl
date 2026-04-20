"""Pipeline orchestrator module.

This module provides a flexible, extensible pipeline architecture for the
skill-to-CNL-P transformation pipeline.

Usage:
    # New architecture (recommended)
    from pipeline.orchestrator.builder import PipelineBuilder
    from pipeline.orchestrator.config import PipelineConfig
    
    builder = PipelineBuilder()
    orchestrator = (
        builder
        .with_config(config)
        .with_steps(P1ReferenceGraphStep, P2FileRolesStep, ...)
        .with_runner("parallel", max_workers=4)
        .build()
    )
    results = orchestrator.run(initial_inputs={})
    
    # Backward-compatible API (import from pipeline module directly)
    from pipeline import run_pipeline, PipelineConfig
    result = run_pipeline(config)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

# Import new architecture components
from pipeline.orchestrator.base import PipelineOrchestrator, PipelineStep
from pipeline.orchestrator.builder import PipelineBuilder
from pipeline.orchestrator.checkpoint import CheckpointManager
from pipeline.orchestrator.config import PipelineConfig as NewPipelineConfig
from pipeline.orchestrator.dependency_graph import DependencyGraph
from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.step_executor import StepExecutor, StepResult
from pipeline.orchestrator.step_registry import StepRegistry, registry

# Import backward-compatible components
from pipeline.llm_client import LLMClient, LLMConfig, SessionUsage, StepLLMConfig
from models import PipelineResult

logger = logging.getLogger(__name__)


# Backward-compatible PipelineConfig
class PipelineConfig:
    """Configuration for a pipeline run (backward-compatible)."""
    
    def __init__(
        self,
        skill_root: str,
        output_dir: str,
        llm_config: LLMConfig,
        step_llm_config: Optional[StepLLMConfig] = None,
        save_checkpoints: bool = True,
        resume_from: Optional[str] = None,
        use_new_step3: bool = False,
    ):
        self.skill_root = skill_root
        self.output_dir = output_dir
        self.llm_config = llm_config
        self.step_llm_config = step_llm_config
        self.save_checkpoints = save_checkpoints
        self.resume_from = resume_from
        self.use_new_step3 = use_new_step3
        
        # Create internal new config
        self._new_config = NewPipelineConfig(
            skill_root=skill_root,
            output_dir=output_dir,
            llm_config=llm_config,
            step_llm_config=step_llm_config,
            save_checkpoints=save_checkpoints,
            resume_from=resume_from,
            use_new_step3=use_new_step3,
        )


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Execute the full skill-to-CNL-P pipeline.
    
    Backward-compatible entry point using new architecture.
    """
    logger.info("=== skill-to-CNL-P pipeline start: %s ===", config.skill_root)
    
    # Import steps here to avoid circular imports
    from pipeline.steps import (
        P1ReferenceGraphStep,
        P2FileRolesStep,
        P3AssemblerStep,
        Step1StructureStep,
        Step1_5APIGenStep,
        Step3WorkflowStep,
        Step4SPLStep,
    )
    
    # Build and run using new architecture
    builder = PipelineBuilder()
    orchestrator = (
        builder
        .with_config(config._new_config)
        .with_steps(
            P1ReferenceGraphStep,
            P2FileRolesStep,
            P3AssemblerStep,
            Step1StructureStep,
            Step1_5APIGenStep,
            Step3WorkflowStep,
            Step4SPLStep,
        )
        # Use sequential runner: pipeline steps are strictly linear by dependency
        # graph, so ParallelRunner provides zero parallelism benefit while risking
        # nested ThreadPoolExecutor shutdown errors (cannot schedule new futures
        # after shutdown). True parallelism lives inside each step (e.g. step4
        # S4A/S4B/S0, step1_5 per-tool API calls, p3 asyncio.gather).
        .with_runner(
            runner_type="sequential",
        )
        .with_checkpointing(config.save_checkpoints)
        .build()
    )
    
    results = orchestrator.run(initial_inputs={})
    
    # Build PipelineResult from new architecture results
    return _build_pipeline_result(results, config)


def _build_pipeline_result(
    results: dict[str, Any],
    config: PipelineConfig,
) -> PipelineResult:
    """Convert new architecture results to PipelineResult."""
    from models import (
        FileNode,
        FileReferenceGraph,
        FileRoleMap,
        SectionBundle,
        SectionItem,
        SkillPackage,
        SPLSpec,
        StructuredSpec,
        WorkflowStep,
        AlternativeFlow,
        ExceptionFlow,
    )
    
    # Get outputs from each step
    p1_output = results.get("p1_reference_graph", {})
    p3_output = results.get("p3_assembler", {})
    step1_output = results.get("step1_structure", {})
    step4_output = results.get("step4_spl", {})
    
    skill_id = p1_output.get("skill_id", Path(config.skill_root).name)
    
    # Reconstruct FileNodes from dicts
    nodes: dict[str, FileNode] = {}
    for node_dict in p1_output.get("nodes", []):
        if isinstance(node_dict, dict):
            node = FileNode(**node_dict)
            nodes[node.path] = node
    
    # Build graph (edges are dict[str, list[str]])
    edges_dict: dict[str, list[str]] = p1_output.get("edges", {})
    
    graph = FileReferenceGraph(
        skill_id=skill_id,
        root_path=str(Path(config.skill_root)),
        skill_md_content="",
        frontmatter={},
        nodes=nodes,
        edges=edges_dict,
    )
    
    # Build file role map (empty for now)
    file_role_map: FileRoleMap = {}
    
    # Build skill package
    package = SkillPackage(
        skill_id=skill_id,
        root_path=str(Path(config.skill_root)),
        frontmatter={},
        merged_doc_text=p3_output.get("merged_doc_text", ""),
        file_role_map={},
        tools=[],
    )
    
    # Build section bundle
    bundle_dict = step1_output.get("section_bundle", {})
    if bundle_dict:
        section_bundle = SectionBundle(
            intent=[SectionItem(**item) if isinstance(item, dict) else item for item in bundle_dict.get("intent", [])],
            workflow=[SectionItem(**item) if isinstance(item, dict) else item for item in bundle_dict.get("workflow", [])],
            constraints=[SectionItem(**item) if isinstance(item, dict) else item for item in bundle_dict.get("constraints", [])],
            tools=[SectionItem(**item) if isinstance(item, dict) else item for item in bundle_dict.get("tools", [])],
            artifacts=[SectionItem(**item) if isinstance(item, dict) else item for item in bundle_dict.get("artifacts", [])],
            evidence=[SectionItem(**item) if isinstance(item, dict) else item for item in bundle_dict.get("evidence", [])],
            examples=[SectionItem(**item) if isinstance(item, dict) else item for item in bundle_dict.get("examples", [])],
            notes=[SectionItem(**item) if isinstance(item, dict) else item for item in bundle_dict.get("notes", [])],
        )
    else:
        section_bundle = SectionBundle()
    
    # Build structured spec
    structured_spec_dict = step4_output.get("structured_spec", {})
    workflow_steps = [
        WorkflowStep(**ws) if isinstance(ws, dict) else ws
        for ws in structured_spec_dict.get("workflow_steps", [])
    ]
    alternative_flows = [
        AlternativeFlow(**af) if isinstance(af, dict) else af
        for af in structured_spec_dict.get("alternative_flows", [])
    ]
    exception_flows = [
        ExceptionFlow(**ef) if isinstance(ef, dict) else ef
        for ef in structured_spec_dict.get("exception_flows", [])
    ]
    
    structured_spec = StructuredSpec(
        entities=[],
        workflow_steps=workflow_steps,
        alternative_flows=alternative_flows,
        exception_flows=exception_flows,
    )
    
    # Build SPL spec
    spl_spec_dict = step4_output.get("spl_spec", {})
    spl_spec = SPLSpec(
        skill_id=spl_spec_dict.get("skill_id", skill_id),
        spl_text=spl_spec_dict.get("spl_text", ""),
        review_summary=spl_spec_dict.get("review_summary", {}),
        clause_counts=spl_spec_dict.get("clause_counts", {}),
    )
    
    result = PipelineResult(
        skill_id=skill_id,
        graph=graph,
        file_role_map=file_role_map,
        package=package,
        section_bundle=section_bundle,
        structured_spec=structured_spec,
        spl_spec=spl_spec,
    )
    
    logger.info("=== skill-to-CNL-P pipeline complete ===")
    return result


__all__ = [
    # Backward-compatible API
    "PipelineConfig",
    "run_pipeline",
    # New architecture components
    "PipelineStep",
    "PipelineOrchestrator",
    "PipelineBuilder",
    "ExecutionContext",
    "StepExecutor",
    "StepResult",
    "StepRegistry",
    "registry",
    "DependencyGraph",
    "CheckpointManager",
]
