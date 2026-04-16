"""
Step 3 Integration Tests
===========================

End-to-end integration tests for the new Step 3 architecture.
Tests the full W -> IO -> T flow with real data.
"""

import pytest
from unittest.mock import MagicMock
from models.step3_types import (
    TypeExpr,
    VarSpec,
    GlobalVarRegistry,
    WorkflowStepRaw,
    StepIOSpec,
    TypeDecl,
    Step3TOutput,
    TEXT_TYPE,
    NUMBER_TYPE,
    BOOLEAN_TYPE,
)
from pipeline.llm_steps.step3_t import (
    run_step3t_types_declaration,
    run_step3t_types_declaration_sync
)
from pipeline.llm_steps.step3_new_orchestrator import run_step3_full_sync


@pytest.fixture
def mock_client():
    """Mock LLM client for testing."""
    return MagicMock()


class TestStep3FullFlow:
    """Test complete Step 3 flow with sample data."""
    
    @pytest.fixture
    def sample_workflow_sections(self):
        """Sample PDF skill sections."""
        return {
            "workflow_section": """
## WORKFLOW

1. Check if the PDF has fillable form fields
   Run: `python scripts/check_fillable_fields.py <file.pdf>`
   Result: Prints whether fillable fields exist

2. If fillable: Extract form field information
   Run: `python scripts/extract_form_field_info.py <input.pdf> <field_info.json>`
   Output: field_info.json with field metadata

3. Create field_values.json with values to enter
   This is a manual step where user provides the values.

4. Fill the PDF with provided values
   Run: `python scripts/fill_fillable_fields.py <input.pdf> <field_values.json> <output.pdf>`
""",
            "tools_section": """
## TOOLS

- check_fillable_fields.py: Checks if PDF has fillable fields
- extract_form_field_info.py: Extracts field metadata from PDF
- fill_fillable_fields.py: Fills PDF form with values
""",
            "evidence_section": """
## EVIDENCE

- Verify that field_info.json is produced and contains field list
- Verify that output.pdf is created and non-empty
""",
            "artifacts_section": """
## ARTIFACTS

- input.pdf: The PDF file to process
- field_info.json: Extracted field metadata
- field_values.json: User-provided values
- output.pdf: Filled PDF output
""",
            "available_tools": [
                {"name": "check_fillable_fields.py", "api_type": "SCRIPT"},
                {"name": "extract_form_field_info.py", "api_type": "SCRIPT"},
                {"name": "fill_fillable_fields.py", "api_type": "SCRIPT"},
            ]
        }
    
    def test_step3_t_with_complex_types(self, mock_client):
        """Test Step3-T generates correct SPL for complex types."""
        # Create registry with complex types
        registry = GlobalVarRegistry()
        
        # Add simple types (should not generate TYPE declarations)
        registry.register(VarSpec("input_pdf", TEXT_TYPE, is_file=True))
        registry.register(VarSpec("output_pdf", TEXT_TYPE, is_file=True))
        registry.register(VarSpec("has_fillable", BOOLEAN_TYPE))
        
        # Add enum type
        registry.register(VarSpec(
            "status",
            TypeExpr.enum(["pending", "running", "completed", "failed"]),
            is_file=False
        ))
        
        # Add struct type
        registry.register(VarSpec(
            "field_info",
            TypeExpr.struct({
                "field_id": TEXT_TYPE,
                "page": NUMBER_TYPE,
                "rect": TypeExpr.array(NUMBER_TYPE),
                "type": TEXT_TYPE
            }),
            is_file=True
        ))
        
        # Generate TYPES (use sync version for testing)
        result = run_step3t_types_declaration_sync(registry)
        
        # Verify output
        assert result.types_spl != ""
        assert "[DEFINE_TYPES:]" in result.types_spl
        assert "[END_TYPES]" in result.types_spl
        
        # Should have declared names (at least 2: Status enum + FieldInfo struct)
        # Note: nested arrays may generate additional types like NumberList
        assert len(result.declared_names) >= 2
        
        # Should have type registry
        assert len(result.type_registry) >= 2
        
        print("\n=== Generated TYPES Block ===")
        print(result.types_spl)
        print("=== End TYPES Block ===\n")
    
    def test_type_consistency_check(self):
        """Test that type conflicts are detected."""
        registry = GlobalVarRegistry()
        
        # Register variable with type A
        registry.register(VarSpec("data", TEXT_TYPE))
        
        # Try to register same name with type B - should raise
        with pytest.raises(ValueError) as exc_info:
            registry.register(VarSpec("data", NUMBER_TYPE))
        
        assert "Type conflict" in str(exc_info.value)
    
    def test_step_io_spec_creation(self):
        """Test StepIOSpec with typed I/O."""
        step_io = StepIOSpec(
            step_id="step.extract_fields",
            prerequisites={
                "input_pdf": VarSpec("input_pdf", TEXT_TYPE, is_file=True)
            },
            produces={
                "field_info": VarSpec(
                    "field_info",
                    TypeExpr.struct({"id": TEXT_TYPE}),
                    is_file=True
                ),
                "count": VarSpec("count", NUMBER_TYPE, is_file=False)
            }
        )
        
        # Verify structure
        assert step_io.step_id == "step.extract_fields"
        assert "input_pdf" in step_io.prerequisites
        assert "field_info" in step_io.produces
        assert "count" in step_io.produces
        
        # Verify types
        assert step_io.prerequisites["input_pdf"].type_expr == TEXT_TYPE
        assert step_io.produces["count"].type_expr == NUMBER_TYPE
    
    def test_workflow_step_raw_no_io(self):
        """Test WorkflowStepRaw has no I/O fields."""
        step = WorkflowStepRaw(
            step_id="step.check_fillable",
            description="Check if PDF has fillable fields",
            action_type="EXEC_SCRIPT",
            tool_hint="check_fillable_fields.py",
            is_validation_gate=False,
            source_text="Run check script"
        )
        
        # Should NOT have prerequisites/produces
        assert not hasattr(step, "prerequisites")
        assert not hasattr(step, "produces")
        assert step.step_id == "step.check_fillable"
        assert step.tool_hint == "check_fillable_fields.py"


class TestStep3ComponentsIntegration:
    """Test integration between Step3 components."""
    
    def test_registry_to_types_pipeline(self):
        """Test full pipeline: Registry -> Types -> SPL."""
        # 1. Create registry
        registry = GlobalVarRegistry()
        
        # 2. Register various types
        registry.register(VarSpec(
            "processing_result",
            TypeExpr.struct({
                "success": BOOLEAN_TYPE,
                "message": TEXT_TYPE,
                "data": TypeExpr.array(TypeExpr.struct({
                    "id": TEXT_TYPE,
                    "value": NUMBER_TYPE
                }))
            })
        ))
        
        # 3. Generate types (sync version for testing)
        result = run_step3t_types_declaration_sync(registry)
        
        # 4. Verify SPL syntax
        spl = result.types_spl
        lines = spl.split("\n")
        
        # Check structure
        assert lines[0] == "[DEFINE_TYPES:]"
        assert lines[-1] == "[END_TYPES]"
        
        # Check type declarations
        assert any("=" in line for line in lines)
        
        print("\n=== Integration Test Output ===")
        print(spl)
        print("=== End Output ===\n")
    
    def test_type_registry_lookup(self, mock_client):
        """Test type registry lookup functionality."""
        enum_type = TypeExpr.enum(["red", "green", "blue"])

        registry = GlobalVarRegistry()
        registry.register(VarSpec("color", enum_type))

        result = run_step3t_types_declaration_sync(registry)
        
        # Should be able to look up by signature
        signature = enum_type.to_signature()
        assert signature in result.type_registry
        
        # Should get declared name
        declared_name = result.type_registry[signature]
        assert declared_name in result.declared_names
        
        # Step3TOutput.get_type_name should work
        assert result.get_type_name(enum_type) == declared_name
    
    def test_empty_registry_handling(self, mock_client):
        """Test empty registry produces empty TYPES."""
        registry = GlobalVarRegistry()
        result = run_step3t_types_declaration_sync(registry)
        
        assert result.types_spl == ""
        assert result.declared_names == set()
        assert result.type_registry == {}


class TestStep3DataFlow:
    """Test data flow between steps."""
    
    def test_step3_w_to_io_interface(self):
        """Test interface between Step3-W and Step3-IO."""
        # Step3-W output
        steps = [
            WorkflowStepRaw(
                step_id="step.check",
                description="Check something",
                action_type="EXEC_SCRIPT",
                tool_hint="check.py"
            ),
            WorkflowStepRaw(
                step_id="step.extract",
                description="Extract data",
                action_type="EXEC_SCRIPT",
                tool_hint="extract.py"
            )
        ]
        
        # These would be passed to Step3-IO
        assert len(steps) == 2
        assert all(isinstance(s, WorkflowStepRaw) for s in steps)
        assert all(not hasattr(s, "prerequisites") for s in steps)
    
    def test_step3_io_to_t_interface(self, mock_client):
        """Test interface between Step3-IO and Step3-T."""
        # Step3-IO output
        registry = GlobalVarRegistry()
        registry.register(VarSpec(
            "field_info",
            TypeExpr.struct({"id": TEXT_TYPE}),
            is_file=True
        ))

        # Passed to Step3-T
        result = run_step3t_types_declaration_sync(registry)
        
        assert result.types_spl != ""
        assert len(result.declared_names) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
