"""
Script Analyzer — Extract I/O schemas from Python scripts.

Responsibilities:
- Parse Python scripts in the scripts/ directory
- Extract function signatures with type hints
- Identify main callable functions (by name patterns or __main__ block)
- Generate ScriptSpec with input_schema, output_schema, and description

Used by P3 to populate SkillPackage.scripts for DEFINE_APIS generation.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

from models.data_models import ScriptSpec


# ─── Type annotation helpers ────────────────────────────────────────────────────

def _unparse_annotation(node: ast.AST | None) -> str:
    """Convert an AST annotation node to a string representation."""
    if node is None:
        return "Any"
    
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Constant):
        return repr(node.value)
    elif isinstance(node, ast.Subscript):
        # Handle generic types like List[str], Dict[str, Any]
        value = _unparse_annotation(node.value)
        slice_val = _unparse_annotation(node.slice)
        return f"{value}[{slice_val}]"
    elif isinstance(node, ast.Attribute):
        # Handle module.Attribute like typing.List
        return f"{_unparse_annotation(node.value)}.{node.attr}"
    elif isinstance(node, ast.Tuple):
        elements = ", ".join(_unparse_annotation(e) for e in node.elts)
        return f"({elements})"
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        # Handle Union types with | syntax (Python 3.10+)
        left = _unparse_annotation(node.left)
        right = _unparse_annotation(node.right)
        return f"{left} | {right}"
    else:
        return "Any"


def _extract_docstring(func_node: ast.FunctionDef) -> str:
    """Extract the first line of a function's docstring, or empty string."""
    if not func_node.body:
        return ""
    first_stmt = func_node.body[0]
    if isinstance(first_stmt, ast.Expr) and isinstance(first_stmt.value, ast.Constant):
        docstring = first_stmt.value.value
        if isinstance(docstring, str):
            # Return first line, stripped
            first_line = docstring.strip().split("\n")[0]
            return first_line[:200] if len(first_line) > 200 else first_line
    return ""


# ─── Function extraction ────────────────────────────────────────────────────────

def _extract_main_function(tree: ast.Module) -> Optional[ast.FunctionDef]:
    """
    Find the primary callable function in a script.
    
    Strategy:
    1. Look for functions named 'main' or matching the script filename
    2. Otherwise, return the first top-level function with arguments
    3. Skip private functions (starting with _)
    """
    candidates: list[ast.FunctionDef] = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Skip private functions
            if node.name.startswith("_"):
                continue
            # Skip functions inside classes (methods)
            if isinstance(node.parent, ast.ClassDef):  # type: ignore[attr-defined]
                continue
            candidates.append(node)
    
    if not candidates:
        return None
    
    # Priority 1: function named 'main'
    for func in candidates:
        if func.name == "main":
            return func
    
    # Priority 2: function matching the script's purpose (common patterns)
    action_verbs = ["get_", "extract_", "fill_", "create_", "convert_", "check_", "validate_"]
    for func in candidates:
        for verb in action_verbs:
            if func.name.startswith(verb):
                return func
    
    # Priority 3: first function with arguments (likely the main entry point)
    for func in candidates:
        if func.args.args:
            return func
    
    return candidates[0] if candidates else None


def _analyze_script(script_path: Path) -> Optional[ScriptSpec]:
    """
    Analyze a single Python script and extract its API specification.
    
    Returns:
        ScriptSpec with function signature, I/O schema, and description.
        None if the script cannot be parsed or has no callable functions.
    """
    try:
        source = script_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    
    # Add parent references for filtering methods
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent  # type: ignore[attr-defined]
    
    main_func = _extract_main_function(tree)
    if main_func is None:
        return None
    
    # Extract input schema (parameter names and types)
    input_schema: dict[str, str] = {}
    for arg in main_func.args.args:
        param_name = arg.arg
        param_type = _unparse_annotation(arg.annotation)
        input_schema[param_name] = param_type
    
    # Extract output schema (return type)
    return_annotation = main_func.returns
    output_schema = _unparse_annotation(return_annotation) if return_annotation else "None"
    
    # Extract description from docstring
    description = _extract_docstring(main_func)
    if not description:
        # Fallback: use function name as description
        description = f"Execute {main_func.name.replace('_', ' ')}"
    
    return ScriptSpec(
        name=script_path.name,
        path=str(script_path.relative_to(script_path.parent.parent)),  # relative to skill root
        input_schema=input_schema,
        output_schema=output_schema,
        description=description,
        main_function=main_func.name,
    )


# ─── Batch analysis ─────────────────────────────────────────────────────────────

def analyze_scripts_directory(scripts_dir: Path) -> list[ScriptSpec]:
    """
    Analyze all Python scripts in the scripts/ directory.
    
    Args:
        scripts_dir: Path to the scripts/ directory under the skill root.
    
    Returns:
        List of ScriptSpec for each successfully analyzed script.
    """
    if not scripts_dir.exists() or not scripts_dir.is_dir():
        return []
    
    specs: list[ScriptSpec] = []
    
    for script_path in sorted(scripts_dir.glob("*.py")):
        # Skip test files
        if "_test" in script_path.name or script_path.name.startswith("test_"):
            continue
        
        spec = _analyze_script(script_path)
        if spec:
            specs.append(spec)
    
    return specs


def analyze_skill_scripts(skill_root: str) -> list[ScriptSpec]:
    """
    Entry point for script analysis from P3.
    
    Args:
        skill_root: Path to the skill directory.
    
    Returns:
        List of ScriptSpec for all analyzable scripts.
    """
    root = Path(skill_root)
    scripts_dir = root / "scripts"
    return analyze_scripts_directory(scripts_dir)
