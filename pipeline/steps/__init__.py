"""Pipeline steps module.

Contains PipelineStep implementations for each stage of the skill-to-CNL-P pipeline.

Steps:
    P1ReferenceGraphStep: Build reference graph from skill files
    P2FileRolesStep: Resolve file roles (documentation, code, templates)
    P3AssemblerStep: Assemble skill package with merged documentation
    Step1StructureStep: Extract 8 canonical sections from SKILL.md
    Step1_5APIGenStep: Generate API definitions
    Step3WorkflowStep: Analyze workflow and extract entities
    Step4SPLStep: Emit final SPL specification
"""

from __future__ import annotations

from pipeline.steps.p1_reference_graph import P1ReferenceGraphStep
from pipeline.steps.p2_file_roles import P2FileRolesStep
from pipeline.steps.p3_assembler import P3AssemblerStep
from pipeline.steps.step1_structure import Step1StructureStep
from pipeline.steps.step1_5_api import Step1_5APIGenStep
from pipeline.steps.step3_workflow import Step3WorkflowStep
from pipeline.steps.step4_spl import Step4SPLStep

__all__ = [
    "P1ReferenceGraphStep",
    "P2FileRolesStep",
    "P3AssemblerStep",
    "Step1StructureStep",
    "Step1_5APIGenStep",
    "Step3WorkflowStep",
    "Step4SPLStep",
]
