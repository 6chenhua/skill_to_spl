"""
TDD Tests for Step 3 Type System (Wave 1)
==========================================

Tests for the new type system models in models/step3_types.py
"""

import pytest
from models.step3_types import (
    TypeExpr,
    VarSpec,
    StepIOSpec,
    GlobalVarRegistry,
    WorkflowStepRaw,
    TypeDecl,
    TEXT_TYPE,
    NUMBER_TYPE,
    BOOLEAN_TYPE,
)


class TestTypeExpr:
    """Test cases for TypeExpr dataclass."""
    
    # TC-TypeExpr-4.1: Simple type serialization
    def test_simple_type_serialization(self):
        """Test simple type to_dict and from_dict."""
        # RED: Write test
        type_expr = TypeExpr.simple("text")
        
        # Assert serialization
        assert type_expr.to_dict() == "text"
        assert type_expr.is_simple() is True
        assert type_expr.is_complex() is False
        
        # Assert deserialization
        parsed = TypeExpr.from_dict("text")
        assert parsed.kind == "simple"
        assert parsed.type_name == "text"
    
    # TC-TypeExpr-4.2: Enum type serialization
    def test_enum_type_serialization(self):
        """Test enum type to_dict and from_dict."""
        type_expr = TypeExpr.enum(["red", "green", "blue"])
        
        # Assert serialization
        assert type_expr.to_dict() == ["red", "green", "blue"]
        assert type_expr.is_simple() is False
        assert type_expr.is_complex() is True
        
        # Assert deserialization
        parsed = TypeExpr.from_dict(["red", "green", "blue"])
        assert parsed.kind == "enum"
        assert parsed.values == ("red", "green", "blue")
    
    # TC-TypeExpr-4.3: Array type serialization
    def test_array_type_serialization(self):
        """Test array type to_dict and from_dict."""
        type_expr = TypeExpr.array(TypeExpr.simple("text"))
        
        # Assert serialization
        assert type_expr.to_dict() == "List[text]"
        assert type_expr.is_complex() is True
        
        # Assert deserialization
        parsed = TypeExpr.from_dict("List[text]")
        assert parsed.kind == "array"
        assert parsed.element_type.kind == "simple"
        assert parsed.element_type.type_name == "text"
    
    # TC-TypeExpr-4.4: Struct type serialization
    def test_struct_type_serialization(self):
        """Test struct type to_dict and from_dict."""
        type_expr = TypeExpr.struct({
            "name": TypeExpr.simple("text"),
            "age": TypeExpr.simple("number")
        })
        
        # Assert serialization
        result = type_expr.to_dict()
        assert isinstance(result, dict)
        assert "name" in result
        assert "age" in result
        assert result["name"] == "text"
        assert result["age"] == "number"
        
        # Assert deserialization
        parsed = TypeExpr.from_dict({"name": "text", "age": "number"})
        assert parsed.kind == "struct"
        assert "name" in parsed.fields
        assert "age" in parsed.fields
    
    # TC-TypeExpr-4.5: Nested type serialization
    def test_nested_type_serialization(self):
        """Test nested type (array of struct)."""
        type_expr = TypeExpr.array(TypeExpr.struct({
            "id": TypeExpr.simple("text"),
            "tags": TypeExpr.array(TypeExpr.simple("text"))
        }))
        
        # Assert serialization
        result = type_expr.to_dict()
        assert "List[" in str(result)
        
        # Assert type is complex
        assert type_expr.is_complex() is True
    
    # Type signature test
    def test_type_signature(self):
        """Test that type signatures are consistent."""
        # Same type should have same signature
        t1 = TypeExpr.struct({"name": TypeExpr.simple("text"), "age": TypeExpr.simple("number")})
        t2 = TypeExpr.struct({"age": TypeExpr.simple("number"), "name": TypeExpr.simple("text")})
        
        # Signatures should be equal (fields sorted)
        assert t1.to_signature() == t2.to_signature()
        
        # Can be used as dict keys
        type_map = {t1: "Person"}
        assert type_map[t2] == "Person"  # Same signature, so same key


class TestVarSpec:
    """Test cases for VarSpec dataclass."""
    
    def test_var_spec_creation(self):
        """Test VarSpec creation."""
        var = VarSpec(
            var_name="input_pdf",
            type_expr=TEXT_TYPE,
            is_file=True,
            description="Input PDF file"
        )
        
        assert var.var_name == "input_pdf"
        assert var.type_expr == TEXT_TYPE
        assert var.is_file is True
        assert var.description == "Input PDF file"
    
    def test_var_spec_default_is_file(self):
        """Test VarSpec defaults is_file to False."""
        var = VarSpec(
            var_name="result",
            type_expr=BOOLEAN_TYPE
        )
        
        assert var.is_file is False


class TestStepIOSpec:
    """Test cases for StepIOSpec dataclass."""
    
    def test_step_io_spec_creation(self):
        """Test StepIOSpec creation."""
        step_io = StepIOSpec(
            step_id="step.extract_fields",
            prerequisites={
                "input_pdf": VarSpec("input_pdf", TEXT_TYPE, is_file=True)
            },
            produces={
                "field_info": VarSpec("field_info", TypeExpr.array(TEXT_TYPE), is_file=True)
            }
        )
        
        assert step_io.step_id == "step.extract_fields"
        assert "input_pdf" in step_io.prerequisites
        assert "field_info" in step_io.produces
    
    def test_get_all_io_vars(self):
        """Test getting all I/O variable names."""
        step_io = StepIOSpec(
            step_id="step.example",
            prerequisites={"a": VarSpec("a", TEXT_TYPE)},
            produces={"b": VarSpec("b", NUMBER_TYPE)}
        )
        
        all_vars = step_io.get_all_io_vars()
        assert all_vars == {"a", "b"}


class TestGlobalVarRegistry:
    """Test cases for GlobalVarRegistry dataclass."""
    
    def test_register_variable(self):
        """Test registering a variable."""
        registry = GlobalVarRegistry()
        var = VarSpec("field_info", TEXT_TYPE, is_file=True)
        
        registry.register(var)
        
        assert "field_info" in registry.files
        assert registry.get_var("field_info") == var
    
    def test_register_same_var_ignores_duplicate(self):
        """Test registering same variable twice."""
        registry = GlobalVarRegistry()
        var1 = VarSpec("data", TEXT_TYPE, description="First")
        var2 = VarSpec("data", TEXT_TYPE, description="Second")
        
        registry.register(var1)
        registry.register(var2)  # Should not raise
        
        # Should only have one entry
        assert len(registry.variables) == 1
        # Description from first registration
        assert registry.variables["data"].description == "First"
    
    def test_register_conflict_raises_error(self):
        """Test that type conflict raises error."""
        registry = GlobalVarRegistry()
        var1 = VarSpec("data", TEXT_TYPE)
        var2 = VarSpec("data", NUMBER_TYPE)  # Different type!
        
        registry.register(var1)
        
        with pytest.raises(ValueError) as exc_info:
            registry.register(var2)
        
        assert "Type conflict" in str(exc_info.value)
    
    def test_get_all_complex_types(self):
        """Test extracting complex types from registry."""
        registry = GlobalVarRegistry()
        
        # Simple types
        registry.register(VarSpec("simple1", TEXT_TYPE))
        registry.register(VarSpec("simple2", NUMBER_TYPE))
        
        # Complex types
        enum_type = TypeExpr.enum(["a", "b"])
        struct_type = TypeExpr.struct({"x": TEXT_TYPE})
        
        registry.register(VarSpec("enum_var", enum_type))
        registry.register(VarSpec("struct_var", struct_type))
        
        complex_types = registry.get_all_complex_types()
        
        assert len(complex_types) == 2
        assert enum_type in complex_types
        assert struct_type in complex_types


class TestWorkflowStepRaw:
    """Test cases for WorkflowStepRaw dataclass."""
    
    def test_workflow_step_raw_creation(self):
        """Test WorkflowStepRaw creation."""
        step = WorkflowStepRaw(
            step_id="step.check_fillable",
            description="Check if PDF has fillable fields",
            action_type="EXEC_SCRIPT",
            tool_hint="check_fillable_fields.py",
            is_validation_gate=False,
            source_text="Run check_fillable_fields.py"
        )
        
        assert step.step_id == "step.check_fillable"
        assert step.action_type == "EXEC_SCRIPT"
        assert step.tool_hint == "check_fillable_fields.py"
        assert step.is_validation_gate is False
        assert "prerequisites" not in step.__dict__  # Should not have I/O
        assert "produces" not in step.__dict__  # Should not have I/O


class TestTypeDecl:
    """Test cases for TypeDecl dataclass."""
    
    def test_type_decl_enum(self):
        """Test TypeDecl for enum."""
        type_decl = TypeDecl(
            declared_name="Status",
            type_expr=TypeExpr.enum(["pending", "done"]),
            description="Processing status"
        )
        
        assert type_decl.declared_name == "Status"
        assert type_decl.is_enum() is True
        assert type_decl.is_struct() is False
    
    def test_type_decl_struct(self):
        """Test TypeDecl for struct."""
        type_decl = TypeDecl(
            declared_name="Person",
            type_expr=TypeExpr.struct({"name": TEXT_TYPE}),
            description="Person data"
        )
        
        assert type_decl.declared_name == "Person"
        assert type_decl.is_enum() is False
        assert type_decl.is_struct() is True


class TestTypeExprConstants:
    """Test pre-defined type constants."""
    
    def test_text_type(self):
        assert TEXT_TYPE.kind == "simple"
        assert TEXT_TYPE.type_name == "text"
    
    def test_number_type(self):
        assert NUMBER_TYPE.kind == "simple"
        assert NUMBER_TYPE.type_name == "number"
    
    def test_boolean_type(self):
        assert BOOLEAN_TYPE.kind == "simple"
        assert BOOLEAN_TYPE.type_name == "boolean"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
