"""
Step 3-T: TYPES Declaration
===========================

Generate SPL [DEFINE_TYPES:] block from GlobalVarRegistry.

Input:
- GlobalVarRegistry from Step 3-IO

Output:
- Step3TOutput with types_spl (SPL text) and type_registry

Includes both async and sync versions.
"""

import logging
from typing import TYPE_CHECKING, Optional

from models.step3_types import (
    Step3TOutput,
    TypeDecl,
    GlobalVarRegistry,
    TypeExpr,
    build_types_spl
)

if TYPE_CHECKING:
    from pipeline.llm_client import LLMClient

logger = logging.getLogger(__name__)


def run_step3t_types_declaration_sync(
    registry: GlobalVarRegistry
) -> Step3TOutput:
    """
    Generate TYPES declarations from registry (synchronous version).

    Filters for complex types, generates PascalCase names,
    builds [DEFINE_TYPES:] block.

    Args:
        registry: Global variable registry

    Returns:
        Step3TOutput with types_spl and type_registry
    """
    logger.info("Starting Step 3-T: TYPES Declaration")

    # Get all complex types
    complex_types = registry.get_all_complex_types()
    logger.debug(f"Found {len(complex_types)} complex types")

    if not complex_types:
        logger.info("No complex types found, returning empty TYPES")
        return Step3TOutput(
            types_spl="",
            type_registry={},
            declared_names=set()
        )

    # Generate TypeDecls with PascalCase names
    type_decls = []
    type_registry = {}
    declared_names = set()
    used_names = set()

    for type_expr in complex_types:
        # Generate name
        declared_name = _generate_type_name(type_expr, used_names)
        used_names.add(declared_name)
        declared_names.add(declared_name)

        # Create description
        description = _generate_description(type_expr)

        # Create TypeDecl
        type_decl = TypeDecl(
            declared_name=declared_name,
            type_expr=type_expr,
            description=description
        )
        type_decls.append(type_decl)

        # Add to registry
        signature = type_expr.to_signature()
        type_registry[signature] = declared_name

        logger.debug(f"Registered type: {declared_name} -> {signature}")

    # Build SPL block
    types_spl = build_types_spl(type_decls)

    logger.info(
        f"Step 3-T complete: {len(type_decls)} type declarations"
    )

    return Step3TOutput(
        types_spl=types_spl,
        type_registry=type_registry,
        declared_names=declared_names
    )


async def run_step3t_types_declaration(
    registry: GlobalVarRegistry,
    client: Optional["LLMClient"]=None,
    model: str = "gpt-4o-mini"
) -> Step3TOutput:
    """
    Generate TYPES declarations from registry (async version).

    Filters for complex types, generates PascalCase names,
    builds [DEFINE_TYPES:] block.

    This step is computationally driven (no LLM call needed) but follows
    the async signature convention for pipeline consistency.

    Args:
        registry: Global variable registry
        client: LLM client (unused, for signature compatibility)
        model: Model name (unused, for signature compatibility)

    Returns:
        Step3TOutput with types_spl and type_registry
    """
    # Delegate to sync version - this step doesn't require LLM
    return run_step3t_types_declaration_sync(registry)


# =============================================================================
# Helper Functions
# =============================================================================

def _generate_type_name(type_expr: TypeExpr, used_names: set[str]) -> str:
    """Generate PascalCase type name from type expression."""
    if type_expr.kind == "enum":
        base = _enum_to_name(type_expr.values)
    elif type_expr.kind == "struct":
        base = _struct_to_name(type_expr.fields)
    elif type_expr.kind == "array":
        base = _array_to_name(type_expr.element_type)
    else:
        base = "Type"

    # Ensure unique
    name = base
    counter = 1
    while name in used_names:
        name = f"{base}{counter}"
        counter += 1

    return name


def _enum_to_name(values: tuple[str, ...]) -> str:
    """Generate name from enum values."""
    if not values:
        return "Enum"
    # Use first value as base
    return _to_pascal_case(values[0]) + "Enum"


def _struct_to_name(fields: dict[str, TypeExpr]) -> str:
    """Generate name from struct fields."""
    if not fields:
        return "Struct"
    # Use first field name
    first_field = list(fields.keys())[0]
    return _to_pascal_case(first_field) + "Data"


def _array_to_name(element_type: TypeExpr | None) -> str:
    """Generate name from array element type."""
    if element_type and element_type.kind == "simple":
        return _to_pascal_case(element_type.type_name) + "List"
    elif element_type and element_type.kind == "struct":
        # Get name from struct
        struct_name = _struct_to_name(element_type.fields)
        return struct_name + "List"
    return "List"


def _to_pascal_case(snake_str: str) -> str:
    """Convert snake_case to PascalCase."""
    components = snake_str.split("_")
    return "".join(x.capitalize() for x in components if x)


def _generate_description(type_expr: TypeExpr) -> str:
    """Generate description for type."""
    if type_expr.kind == "enum":
        return f"Enumeration with values: {', '.join(type_expr.values)}"
    elif type_expr.kind == "struct":
        fields = ', '.join(type_expr.fields.keys())
        return f"Structured data with fields: {fields}"
    elif type_expr.kind == "array":
        return "List of elements"
    return "Data type"