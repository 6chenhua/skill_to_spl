"""
Generate [DEFINE_VARIABLES:] and [DEFINE_FILES:] from Step 3 registry.
"""

from __future__ import annotations

from models.step3_types import GlobalVarRegistry, TypeExpr


def generate_variables_files_from_registry(
    registry: GlobalVarRegistry,
    types_spl: str = ""
) -> str:
    """
    Generate [DEFINE_VARIABLES:] and [DEFINE_FILES:] blocks from registry.
    
    Args:
        registry: GlobalVarRegistry from Step 3
        types_spl: TYPES block (optional, for type references)
        
    Returns:
        Complete [DEFINE_VARIABLES:] ... [DEFINE_FILES:] ... block
    """
    lines = []
    
    # Add TYPES if present
    if types_spl:
        lines.append(types_spl)
        lines.append("")
    
    # Generate VARIABLES block
    if registry.variables:
        lines.append("[DEFINE_VARIABLES:]")
        lines.append("")
        
        for var_name, var_spec in sorted(registry.variables.items()):
            # Get type string
            if var_spec.type_expr.is_simple():
                type_str = var_spec.type_expr.type_name
            else:
                type_str = var_spec.type_expr.to_spl()
            
            # Format: "description"
            # variable_name : type
            if var_spec.description:
                lines.append(f'"{var_spec.description}"')
            lines.append(f"{var_name} : {type_str}")
            lines.append("")
        
        lines.append("[END_VARIABLES]")
        lines.append("")
    
    # Generate FILES block
    if registry.files:
        lines.append("[DEFINE_FILES:]")
        lines.append("")
        
        for var_name, var_spec in sorted(registry.files.items()):
            # Get type string
            if var_spec.type_expr.is_simple():
                type_str = var_spec.type_expr.type_name
            else:
                type_str = var_spec.type_expr.to_spl()
            
            # Format: "description"
            # file_name <path> : type
            if var_spec.description:
                lines.append(f'"{var_spec.description}"')
            lines.append(f"{var_name} < > : {type_str}")
            lines.append("")
        
        lines.append("[END_FILES]")
        lines.append("")
    
    return "\n".join(lines)
