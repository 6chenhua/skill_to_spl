"""
Step 3 Refactor - Type System Models
=====================================

New data models for the refactored Step 3 architecture.
Supports:
- TypeExpr: Type expressions (simple, enum, array, struct)
- VarSpec: Variable specifications with typed I/O
- StepIOSpec: Per-step input/output analysis
- GlobalVarRegistry: Deduplicated global variables
- WorkflowStepRaw: Step structure without I/O
- TypeDecl: TYPE declarations for complex types
- Step3TOutput: Contains SPL TYPES block text

Created: 2026-04-15
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# Type Expressions
# =============================================================================

@dataclass(frozen=True)
class TypeExpr:
    """
    Type expression representing a data type in the SPL type system.
    """
    kind: str  # "simple" | "enum" | "array" | "struct"
    type_name: str = ""  # For simple types
    values: tuple[str, ...] = field(default_factory=tuple)  # For enum types
    element_type: TypeExpr | None = None  # For array types
    fields: dict[str, TypeExpr] = field(default_factory=dict)  # For struct types
    
    @classmethod
    def simple(cls, type_name: str) -> TypeExpr:
        """Create a simple type."""
        assert type_name in ("text", "image", "audio", "number", "boolean"), \
            f"Invalid simple type: {type_name}"
        return cls(kind="simple", type_name=type_name)
    
    @classmethod
    def enum(cls, values: list[str]) -> TypeExpr:
        """Create an enum type."""
        return cls(kind="enum", values=tuple(values))
    
    @classmethod
    def array(cls, element_type: TypeExpr) -> TypeExpr:
        """Create an array type."""
        return cls(kind="array", element_type=element_type)
    
    @classmethod
    def struct(cls, fields: dict[str, TypeExpr]) -> TypeExpr:
        """Create a struct type."""
        return cls(kind="struct", fields=dict(fields))
    
    def is_simple(self) -> bool:
        """Check if this is a simple type."""
        return self.kind == "simple"
    
    def is_complex(self) -> bool:
        """Check if this is a complex type (not simple)."""
        return self.kind != "simple"
    
    def to_signature(self) -> str:
        """Convert to a canonical signature string for deduplication."""
        if self.kind == "simple":
            return self.type_name
        elif self.kind == "enum":
            return str(sorted(self.values))
        elif self.kind == "array":
            if self.element_type:
                return f"List[{self.element_type.to_signature()}]"
            return "List[any]"
        elif self.kind == "struct":
            field_strs = [f"{k}: {v.to_signature()}" for k, v in sorted(self.fields.items())]
            return "{" + ", ".join(field_strs) + "}"
        else:
            raise ValueError(f"Unknown kind: {self.kind}")
    
    def to_dict(self) -> Any:
        """Serialize to dictionary for JSON output."""
        if self.kind == "simple":
            return self.type_name
        elif self.kind == "enum":
            return list(self.values) if self.values else []
        elif self.kind == "array":
            if self.element_type:
                return f"List[{self.element_type.to_dict()}]"
            return "List[any]"
        elif self.kind == "struct":
            if not self.fields:
                return {}
            return {k: v.to_dict() for k, v in self.fields.items()}
        else:
            raise ValueError(f"Unknown kind: {self.kind}")
    
    def to_spl(self) -> str:
        """Convert to SPL syntax."""
        result = self.to_dict()
        if isinstance(result, str):
            return result
        elif self.kind == "enum" and isinstance(result, list):
            values = ", ".join(f'"{v}"' for v in result)
            return f"[{values}]"
        elif self.kind == "struct" and isinstance(result, dict):
            if not result:
                return "{}"
            fields = ", ".join(f"{k}: {v}" for k, v in result.items())
            return f"{{{fields}}}"
        return str(result)
    
    @classmethod
    def from_dict(cls, data: Any) -> TypeExpr:
        """Parse from dictionary (LLM JSON output)."""
        if isinstance(data, str):
            if data in ("text", "image", "audio", "number", "boolean"):
                return cls.simple(data)
            elif data.startswith("List[") and data.endswith("]"):
                inner = data[5:-1]
                if inner == "any":
                    return cls.array(cls.simple("text"))
                return cls.array(cls.from_dict(inner))
            else:
                raise ValueError(f"Cannot parse type string: {data}")
        elif isinstance(data, list):
            return cls.enum(data)
        elif isinstance(data, dict):
            if not data:
                return cls.struct({})
            fields = {k: cls.from_dict(v) for k, v in data.items()}
            return cls.struct(fields)
        else:
            raise ValueError(f"Cannot parse type data: {data}")
    
    def __hash__(self) -> int:
        """Hash based on signature for use in sets/dicts."""
        return hash(self.to_signature())
    
    def __eq__(self, other: object) -> bool:
        """Equality based on signature."""
        if not isinstance(other, TypeExpr):
            return False
        return self.to_signature() == other.to_signature()


# =============================================================================
# Variable Specifications
# =============================================================================

@dataclass
class VarSpec:
    """Variable specification - describes an input or output variable."""
    var_name: str
    type_expr: TypeExpr
    is_file: bool = False
    description: str = ""
    source_step: str = ""


# =============================================================================
# Step I/O Specifications
# =============================================================================

@dataclass
class StepIOSpec:
    """Input/output specification for a single workflow step."""
    step_id: str
    prerequisites: dict[str, VarSpec] = field(default_factory=dict)
    produces: dict[str, VarSpec] = field(default_factory=dict)
    
    def get_all_io_vars(self) -> set[str]:
        """Get all variable names used by this step."""
        return set(self.prerequisites.keys()) | set(self.produces.keys())


# =============================================================================
# Global Variable Registry
# =============================================================================

@dataclass
class GlobalVarRegistry:
    """Deduplicated registry of all variables across all steps."""
    variables: dict[str, VarSpec] = field(default_factory=dict)
    files: dict[str, VarSpec] = field(default_factory=dict)
    
    def register(self, var_spec: VarSpec) -> None:
        """Register a variable, merging with existing if same name."""
        registry = self.files if var_spec.is_file else self.variables
        
        if var_spec.var_name in registry:
            existing = registry[var_spec.var_name]
            if existing.type_expr != var_spec.type_expr:
                raise ValueError(
                    f"Type conflict for variable '{var_spec.var_name}': "
                    f"existing={existing.type_expr.to_signature()}, "
                    f"new={var_spec.type_expr.to_signature()}"
                )
            if var_spec.description and not existing.description:
                existing.description = var_spec.description
        else:
            registry[var_spec.var_name] = var_spec
    
    def get_var(self, var_name: str) -> VarSpec | None:
        """Get a variable by name (searches both variables and files)."""
        if var_name in self.variables:
            return self.variables[var_name]
        if var_name in self.files:
            return self.files[var_name]
        return None
    
    def get_all_complex_types(self) -> set[TypeExpr]:
        """Get all complex types (non-simple) used in the registry."""
        complex_types: set[TypeExpr] = set()
        
        def collect_types(type_expr: TypeExpr) -> None:
            if type_expr.is_complex():
                complex_types.add(type_expr)
            if type_expr.kind == "array" and type_expr.element_type:
                collect_types(type_expr.element_type)
            elif type_expr.kind == "struct":
                for field_type in type_expr.fields.values():
                    collect_types(field_type)
        
        for var_spec in list(self.variables.values()) + list(self.files.values()):
            collect_types(var_spec.type_expr)
        
        return complex_types


# =============================================================================
# Workflow Step (Raw - without I/O)
# =============================================================================

@dataclass
class WorkflowStepRaw:
    """Raw workflow step structure without I/O information."""
    step_id: str
    description: str
    action_type: str = "LLM_TASK"
    tool_hint: str = ""
    is_validation_gate: bool = False
    source_text: str = ""


# =============================================================================
# Type Declarations
# =============================================================================

@dataclass
class TypeDecl:
    """TYPE declaration for a complex type."""
    declared_name: str
    type_expr: TypeExpr
    description: str = ""
    
    def is_enum(self) -> bool:
        return self.type_expr.kind == "enum"
    
    def is_struct(self) -> bool:
        return self.type_expr.kind == "struct"
    
    def to_spl(self) -> str:
        """
        Convert to SPL TYPE declaration syntax.
        
        Format:
            "description" (optional)
            DeclaredName = <type_expr>
        """
        lines = []
        if self.description:
            lines.append(f'"{self.description}"')
        
        if self.type_expr.kind == "enum":
            values = ", ".join(f'"{v}"' for v in self.type_expr.values)
            lines.append(f"{self.declared_name} = [{values}]")
        elif self.type_expr.kind == "struct":
            if not self.type_expr.fields:
                lines.append(f"{self.declared_name} = {{}}")
            else:
                field_lines = []
                for field_name, field_type in self.type_expr.fields.items():
                    field_type_str = field_type.to_spl()
                    field_lines.append(f"    {field_name}: {field_type_str}")
                lines.append(f"{self.declared_name} = {{")
                lines.extend(field_lines)
                lines.append("}")
        elif self.type_expr.kind == "array":
            if self.type_expr.element_type:
                element_str = self.type_expr.element_type.to_spl()
                lines.append(f"{self.declared_name} = List[{element_str}]")
            else:
                lines.append(f"{self.declared_name} = List[text]")
        
        return "\n".join(lines)


# =============================================================================
# Step 3 Outputs
# =============================================================================

@dataclass
class Step3WOutput:
    """Output of Step3-W: Workflow Structure Analysis."""
    workflow_steps: list[WorkflowStepRaw] = field(default_factory=list)
    alternative_flows: list[Any] = field(default_factory=list)
    exception_flows: list[Any] = field(default_factory=list)


@dataclass
class Step3IOOutput:
    """Output of Step3-IO: Global I/O + Type Analysis."""
    step_io_specs: dict[str, StepIOSpec] = field(default_factory=dict)
    global_registry: GlobalVarRegistry = field(default_factory=GlobalVarRegistry)


@dataclass
class Step3TOutput:
    """
    Output of Step3-T: TYPES Declaration.
    
    Contains SPL TYPES block that is inserted into final SPL specification.
    """
    types_spl: str = ""
    type_registry: dict[str, str] = field(default_factory=dict)
    declared_names: set[str] = field(default_factory=set)
    
    def get_type_name(self, type_expr: TypeExpr) -> str:
        """Get the declared name for a type expression, or inline SPL if not declared."""
        signature = type_expr.to_signature()
        return self.type_registry.get(signature, type_expr.to_spl())
    
    def is_declared(self, type_name: str) -> bool:
        """Check if a type name is declared in this TYPES block."""
        return type_name in self.declared_names


# =============================================================================
# TYPES Block Builder
# =============================================================================

def build_types_spl(type_decls: list[TypeDecl]) -> str:
    """
    Build the complete [DEFINE_TYPES:] block from TypeDecl list.
    
    Args:
        type_decls: List of TypeDecl objects
        
    Returns:
        Complete SPL TYPES block text
    """
    if not type_decls:
        return ""
    
    lines = ["[DEFINE_TYPES:]"]
    
    for i, type_decl in enumerate(type_decls):
        if i > 0:
            lines.append("")
        lines.append(type_decl.to_spl())
    
    lines.append("[END_TYPES]")
    
    return "\n".join(lines)


# =============================================================================
# Constants
# =============================================================================

TEXT_TYPE = TypeExpr.simple("text")
NUMBER_TYPE = TypeExpr.simple("number")
BOOLEAN_TYPE = TypeExpr.simple("boolean")
IMAGE_TYPE = TypeExpr.simple("image")
AUDIO_TYPE = TypeExpr.simple("audio")
