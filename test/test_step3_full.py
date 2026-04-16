"""
TDD Tests for Step 3 Refactor
==============================

Test cases for Step 3 components.
"""

import pytest
from models.step3_types import (
    TypeExpr,
    VarSpec,
    GlobalVarRegistry,
    WorkflowStepRaw,
    StepIOSpec,
    build_types_spl,
)
from pipeline.llm_steps.step3_t import run_step3t_types_declaration_sync


class TestStep3TTypesGeneration:
    """Test Step3-T TYPES generation."""
    
    def test_empty_registry(self):
        """Test Step3-T with empty registry."""
        registry = GlobalVarRegistry()
        result = run_step3t_types_declaration_sync(registry)
        
        assert result.types_spl == ""
        assert result.declared_names == set()
    
    def test_simple_types_no_declarations(self):
        """Test that simple types don't generate TYPE declarations."""
        registry = GlobalVarRegistry()
        registry.register(VarSpec("text_var", TypeExpr.simple("text")))
        registry.register(VarSpec("num_var", TypeExpr.simple("number")))
        
        result = run_step3t_types_declaration_sync(registry)
        
        assert result.types_spl == ""
        assert len(result.declared_names) == 0
    
    def test_enum_type_declaration(self):
        """Test enum type generates TYPE declaration."""
        registry = GlobalVarRegistry()
        registry.register(VarSpec(
            "status",
            TypeExpr.enum(["pending", "running", "completed"])
        ))
        
        result = run_step3t_types_declaration_sync(registry)
        
        assert "[DEFINE_TYPES:]" in result.types_spl
        assert "[END_TYPES]" in result.types_spl
        assert len(result.declared_names) == 1  # One type declared
        assert "Enum" in list(result.declared_names)[0]  # Name contains "Enum"
        assert 'pending"' in result.types_spl or '"pending"' in result.types_spl
    
    def test_struct_type_declaration(self):
        """Test struct type generates TYPE declaration."""
        registry = GlobalVarRegistry()
        registry.register(VarSpec(
            "field_info",
            TypeExpr.struct({
                "field_id": TypeExpr.simple("text"),
                "page": TypeExpr.simple("number")
            })
        ))
        
        result = run_step3t_types_declaration_sync(registry)
        
        assert "[DEFINE_TYPES:]" in result.types_spl
        assert "FieldIdData = {" in result.types_spl or "FieldInfo" in result.types_spl
    
    def test_type_registry_mapping(self):
        """Test type_registry maps signatures to names."""
        enum_type = TypeExpr.enum(["a", "b"])
        registry = GlobalVarRegistry()
        registry.register(VarSpec("my_enum", enum_type))
        
        result = run_step3t_types_declaration_sync(registry)
        
        signature = enum_type.to_signature()
        assert signature in result.type_registry
        assert result.type_registry[signature] in result.declared_names


class TestBuildTypesSpl:
    """Test TYPES block building."""
    
    def test_build_single_enum(self):
        """Test building TYPES block with single enum."""
        from models.step3_types import TypeDecl
        
        type_decls = [
            TypeDecl("Status", TypeExpr.enum(["active", "inactive"]))
        ]
        
        spl = build_types_spl(type_decls)
        
        assert spl.startswith("[DEFINE_TYPES:]")
        assert spl.endswith("[END_TYPES]")
        assert "Status = " in spl
    
    def test_build_struct_with_fields(self):
        """Test building TYPES block with struct."""
        from models.step3_types import TypeDecl
        
        type_decls = [
            TypeDecl(
                "Person",
                TypeExpr.struct({"name": TypeExpr.simple("text")})
            )
        ]
        
        spl = build_types_spl(type_decls)
        
        assert "Person = {" in spl
        assert "name: text" in spl
    
    def test_build_empty_list(self):
        """Test building TYPES block with empty list."""
        spl = build_types_spl([])
        
        assert spl == ""


class TestStep3TypesSerialization:
    """Test type serialization."""
    
    def test_type_expr_to_spl(self):
        """Test TypeExpr.to_spl() output."""
        # Simple
        assert TypeExpr.simple("text").to_spl() == "text"
        
        # Enum
        enum = TypeExpr.enum(["x", "y"])
        assert '["x", "y"]' in enum.to_spl() or '["y", "x"]' in enum.to_spl()
        
        # Struct
        struct = TypeExpr.struct({"a": TypeExpr.simple("text")})
        assert "{a: text}" in struct.to_spl()
        
        # Array
        arr = TypeExpr.array(TypeExpr.simple("text"))
        assert arr.to_spl() == "List[text]"


class TestTypeSignatureConsistency:
    """Test that type signatures are consistent."""
    
    def test_enum_signature_sorting(self):
        """Test enum values are sorted in signature."""
        e1 = TypeExpr.enum(["z", "a", "m"])
        e2 = TypeExpr.enum(["a", "m", "z"])
        
        assert e1.to_signature() == e2.to_signature()
    
    def test_struct_signature_sorting(self):
        """Test struct fields are sorted in signature."""
        s1 = TypeExpr.struct({"z": TypeExpr.simple("text"), "a": TypeExpr.simple("number")})
        s2 = TypeExpr.struct({"a": TypeExpr.simple("number"), "z": TypeExpr.simple("text")})
        
        assert s1.to_signature() == s2.to_signature()
    
    def test_signature_as_dict_key(self):
        """Test signatures can be used as dict keys."""
        t1 = TypeExpr.enum(["a", "b"])
        t2 = TypeExpr.enum(["b", "a"])
        
        d = {t1: "value"}
        assert d[t2] == "value"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
