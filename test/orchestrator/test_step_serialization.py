"""Test suite for Step serialization/deserialization.

These tests ensure that all pipeline steps can properly serialize their outputs
to JSON (for checkpointing) and deserialize them back.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from pipeline.orchestrator.checkpoint import DataclassEncoder, _default_serializer
from pipeline.orchestrator.config import PipelineConfig
from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.llm_client import LLMClient, LLMConfig, SessionUsage


class MockContext:
    """Mock execution context for testing."""
    
    def __init__(self):
        self.config = PipelineConfig(
            skill_root="/test/skill",
            output_dir="/test/output",
            llm_config=LLMConfig(),
        )
        self.client = LLMClient(self.config.llm_config, SessionUsage())
        self.logger = __import__('logging').getLogger("test")


class TestP1ReferenceGraphStep:
    """Test P1 step output serialization."""
    
    def test_p1_output_is_json_serializable(self):
        """Test P1 output can be serialized to JSON."""
        from pipeline.steps import P1ReferenceGraphStep
        
        # Create expected output structure
        output = {
            "skill_id": "test-skill",
            "nodes": [
                {
                    "path": "SKILL.md",
                    "kind": "doc",
                    "size_bytes": 1000,
                    "head_lines": ["# Test"],
                    "references": [],
                },
            ],
            "edges": {
                "SKILL.md": ["script.py"],
            },
        }
        
        # Should not raise
        result = _default_serializer(output)
        parsed = json.loads(result)
        
        assert parsed["skill_id"] == "test-skill"
        assert len(parsed["nodes"]) == 1
        assert parsed["edges"]["SKILL.md"] == ["script.py"]


class TestP2FileRolesStep:
    """Test P2 step output serialization."""
    
    def test_p2_output_is_json_serializable(self):
        """Test P2 file role map can be serialized."""
        output = {
            "SKILL.md": {
                "role": "doc",
                "read_priority": 1,
                "must_read_for_normalization": True,
                "reasoning": "Main documentation",
            },
            "script.py": {
                "role": "script",
                "read_priority": 2,
                "must_read_for_normalization": True,
                "reasoning": "Implementation",
            },
        }
        
        # Should not raise
        result = _default_serializer(output)
        parsed = json.loads(result)
        
        assert parsed["SKILL.md"]["role"] == "doc"
        assert parsed["script.py"]["read_priority"] == 2


class TestP3AssemblerStep:
    """Test P3 step output serialization."""
    
    def test_p3_output_is_json_serializable(self):
        """Test P3 package output can be serialized."""
        from models import ToolSpec
        
        output = {
            "skill_id": "test-skill",
            "merged_doc_text": "# Documentation",
            "tools": [
                asdict(ToolSpec(
                    name="test_tool",
                    api_type="SCRIPT",
                    description="Test tool",
                )),
            ],
            "unified_apis": [],
        }
        
        # Should not raise
        result = _default_serializer(output)
        parsed = json.loads(result)
        
        assert parsed["skill_id"] == "test-skill"
        assert len(parsed["tools"]) == 1


class TestStep1StructureStep:
    """Test Step 1 output serialization."""
    
    def test_step1_output_is_json_serializable(self):
        """Test Step 1 section bundle output can be serialized."""
        from models import SectionItem, SectionBundle
        
        bundle = SectionBundle(
            intent=[SectionItem(text="Test intent", source="INTENT")],
            workflow=[SectionItem(text="Step 1", source="WORKFLOW")],
        )
        
        output = {
            "section_bundle": asdict(bundle),
            "network_apis": [],
        }
        
        # Should not raise
        result = _default_serializer(output)
        parsed = json.loads(result)
        
        assert len(parsed["section_bundle"]["intent"]) == 1


class TestStep3WorkflowStep:
    """Test Step 3 output serialization."""
    
    def test_step3_output_with_set_field(self):
        """Test Step 3 output with declared_names set."""
        from models.step3_types import Step3TOutput
        
        output = Step3TOutput(
            types_spl="TYPES: test",
            type_registry={},
            declared_names={"var1", "var2", "var3"},
        )
        
        # This was the failing case - set in declared_names
        result = json.dumps(asdict(output), cls=DataclassEncoder)
        parsed = json.loads(result)
        
        assert parsed["types_spl"] == "TYPES: test"
        assert sorted(parsed["declared_names"]) == ["var1", "var2", "var3"]
    
    def test_step3_full_output_is_serializable(self):
        """Test complete Step 3 output structure."""
        from models import WorkflowStep, AlternativeFlow, ExceptionFlow
        from models.step3_types import (
            GlobalVarRegistry,
            StepIOSpec,
            Step3TOutput,
            VarSpec,
        )
        
        # Simulate the structure returned by run_step3_full_sync
        output = {
            "workflow_steps": [
                asdict(WorkflowStep(
                    step_id="step1",
                    description="Test step",
                    prerequisites=[],
                    produces=[],
                )),
            ],
            "alternative_flows": [],
            "exception_flows": [],
            "step_io_specs": [
                asdict(StepIOSpec(
                    step_id="step1",
                    prerequisites={},
                    produces={"result": VarSpec(
                        var_name="result",
                        type_expr="str",
                        is_file=False,
                    )},
                )),
            ],
            "global_registry": asdict(GlobalVarRegistry(
                variables={},
                files={},
            )),
            "type_registry": {},
            "types_spl": "",
            "declared_names": {"type1", "type2"},  # Set field
        }
        
        # Should not raise - this is the main test
        result = _default_serializer(output)
        parsed = json.loads(result)
        
        assert len(parsed["workflow_steps"]) == 1
        assert sorted(parsed["declared_names"]) == ["type1", "type2"]


class TestStep4SPLStep:
    """Test Step 4 output serialization."""
    
    def test_step4_output_is_json_serializable(self):
        """Test Step 4 SPL output can be serialized."""
        from models import SPLSpec
        
        output = {
            "spl_spec": asdict(SPLSpec(
                skill_id="test-skill",
                spl_text="DEFINE_AGENT...",
            )),
        }
        
        # Should not raise
        result = _default_serializer(output)
        parsed = json.loads(result)
        
        assert parsed["spl_spec"]["skill_id"] == "test-skill"


class TestRoundTripSerialization:
    """Test round-trip serialization for all step outputs."""
    
    def _roundtrip(self, data: Any) -> Any:
        """Serialize and deserialize data."""
        serialized = _default_serializer(data)
        return json.loads(serialized)
    
    def test_complex_nested_structure(self):
        """Test complex nested structure roundtrip."""
        from models.step3_types import GlobalVarRegistry, VarSpec
        
        data = {
            "workflow_analysis": {
                "steps": [
                    {"id": "step1", "name": "First"},
                    {"id": "step2", "name": "Second"},
                ],
                "dependencies": {"step1", "step2"},  # Set
            },
            "registry": asdict(GlobalVarRegistry(
                variables={
                    "var1": VarSpec(
                        var_name="var1",
                        type_expr="str",
                        is_file=False,
                        description="Test var",
                        source_step="step1",
                    ),
                },
                files={},
            )),
            "metadata": {
                "tags": {"tag1", "tag2"},  # Set
                "coordinates": (1.0, 2.0),  # Tuple
            },
        }
        
        result = self._roundtrip(data)
        
        assert len(result["workflow_analysis"]["steps"]) == 2
        assert "step1" in result["workflow_analysis"]["dependencies"]
        assert result["metadata"]["coordinates"] == [1.0, 2.0]


class TestCheckpointScenarios:
    """Test real-world checkpoint scenarios."""
    
    def test_step3_result_from_checkpoint(self, tmp_path):
        """Test loading Step 3 result from checkpoint."""
        from pipeline.orchestrator.checkpoint import CheckpointManager
        
        manager = CheckpointManager()
        
        # Simulate a Step 3 result that would be checkpointed
        step3_result = {
            "workflow_steps": [{"step_id": "s1", "description": "Step 1"}],
            "alternative_flows": [],
            "exception_flows": [],
            "step_io_specs": [],
            "global_registry": {"variables": {}, "files": {}},
            "type_registry": {},
            "types_spl": "",
            "declared_names": {"type1", "type2"},  # This set caused issues
        }
        
        # Save and load
        manager.save("step3_workflow", step3_result, tmp_path)
        loaded = manager.load("step3_workflow", tmp_path)
        
        # Verify
        assert loaded["declared_names"] == ["type1", "type2"]  # Set becomes sorted list
        assert len(loaded["workflow_steps"]) == 1
    
    def test_resume_from_checkpoint(self, tmp_path):
        """Test resuming pipeline from a checkpoint."""
        from pipeline.orchestrator.checkpoint import CheckpointManager
        
        manager = CheckpointManager()
        
        # Simulate step1 result checkpoint
        step1_output = {
            "section_bundle": {
                "intent": [{"text": "Test", "source": "INTENT"}],
                "workflow": [{"text": "Step 1", "source": "WORKFLOW"}],
                "constraints": [],
                "tools": [],
                "artifacts": [],
                "evidence": [],
                "examples": [],
                "notes": [],
            },
            "network_apis": [],
        }
        
        manager.save("step1_structure", step1_output, tmp_path)
        
        # Simulate resuming - load checkpoint
        loaded = manager.load("step1_structure", tmp_path)
        
        # This is what Step 3 would receive
        assert "section_bundle" in loaded
        assert len(loaded["section_bundle"]["intent"]) == 1


class TestSerializationErrors:
    """Test handling of serialization edge cases."""
    
    def test_custom_object_without_dataclass(self):
        """Test custom object not marked as dataclass."""
        class CustomObject:
            def __init__(self, value):
                self.value = value
        
        data = {"obj": CustomObject(42)}
        
        # Should use __dict__ fallback
        result = json.dumps(data, cls=DataclassEncoder)
        parsed = json.loads(result)
        
        assert parsed["obj"]["value"] == 42
    
    def test_bytes_encoding(self):
        """Test bytes are base64 encoded."""
        data = {"content": b"hello world"}
        result = json.dumps(data, cls=DataclassEncoder)
        parsed = json.loads(result)
        
        assert isinstance(parsed["content"], str)
        # Should be base64
        import base64
        decoded = base64.b64decode(parsed["content"])
        assert decoded == b"hello world"
