"""P2.5: API Analyzer - Extract I/O Schema from scripts and code snippets.Uses LLM for code analysis to extract input/output schemas and descriptions."""
from __future__ import annotations

import asyncio
import ast
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from models.data_models import FileReferenceGraph, ToolSpec

logger = logging.getLogger(__name__)


def analyze_skill_apis(graph: FileReferenceGraph, client) -> list[ToolSpec]:
    """
    P2.5: Analyze all callable APIs (scripts + code snippets).

    Returns:
    List[ToolSpec] - Contains SCRIPT and CODE_SNIPPET types
    """
    apis = []

    # 1. Analyze scripts/ directory
    apis.extend(_analyze_scripts(graph))

    # 2. Analyze code snippets in SKILL.md
    apis.extend(_analyze_code_snippets(graph, client))

    logger.info("[P2.5] Extracted %d APIs (%d scripts, %d code snippets)",
                len(apis),
                len([a for a in apis if a.api_type == "SCRIPT"]),
                len([a for a in apis if a.api_type == "CODE_SNIPPET"]))

    return apis


async def analyze_skill_apis_async(graph: FileReferenceGraph, client) -> list[ToolSpec]:
    """
    Async version: P2.5 Analyze all callable APIs (scripts + code snippets).
    Code snippets are processed in parallel using asyncio.gather().

    Returns:
    List[ToolSpec] - Contains SCRIPT and CODE_SNIPPET types
    """
    apis = []

    # 1. Analyze scripts/ directory (synchronous - CPU only)
    apis.extend(_analyze_scripts(graph))

    # 2. Analyze code snippets in SKILL.md (async parallel)
    snippet_tools = await _analyze_code_snippets_async(graph, client)
    apis.extend(snippet_tools)

    logger.info("[P2.5] Extracted %d APIs (%d scripts, %d code snippets) [async mode]",
                len(apis),
                len([a for a in apis if a.api_type == "SCRIPT"]),
                len([a for a in apis if a.api_type == "CODE_SNIPPET"]))

    return apis


def _analyze_scripts(graph: FileReferenceGraph) -> list[ToolSpec]:
    """Analyze Python scripts in scripts/ directory."""
    tools = []
    root_path = Path(graph.root_path)
    
    for node in graph.nodes.values():
        if node.kind == "script" and node.path.startswith("scripts/"):
            tool = _extract_script_spec(root_path / node.path, node.path)
            if tool:
                tools.append(tool)
    
    return tools


def _extract_script_spec(file_path: Path, rel_path: str) -> Optional[ToolSpec]:
    """Extract ToolSpec from a single script file."""
    try:
        if not file_path.exists():
            logger.warning(f"Script file not found: {file_path}")
            return None
            
        source_code = file_path.read_text(encoding='utf-8')
        
        # AST analysis to extract function signature
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return None
        
        # Find main function or first function
        main_func = None
        for item in tree.body:
            if isinstance(item, ast.FunctionDef):
                if item.name in ["main", "run", "execute"]:
                    main_func = item
                    break
                elif main_func is None:
                    main_func = item
        
        if not main_func:
            # No function found - might be a script with top-level code
            # Generate a simple spec
            return ToolSpec(
                name=file_path.stem,
                api_type="SCRIPT",
                url=f"scripts/{rel_path}",
                authentication="none",
                input_schema={},
                output_schema="void",
                description=f"Script: {file_path.name}",
                source_text=source_code[:5000]  # First 5000 chars
            )
        
        # Extract input parameters
        input_schema = {}
        for arg in main_func.args.args:
            arg_name = arg.arg
            arg_type = _infer_type_from_annotation(arg.annotation)
            input_schema[arg_name] = arg_type
        
        # Handle *args and **kwargs
        if main_func.args.vararg:
            input_schema["*args"] = "List [any]"
        if main_func.args.kwarg:
            input_schema["**kwargs"] = "{ }"
        
        # Extract return type
        output_schema = _infer_type_from_annotation(main_func.returns)
        
        # Extract description from docstring
        description = ""
        if (main_func.body and 
            isinstance(main_func.body[0], ast.Expr) and 
            isinstance(main_func.body[0].value, ast.Constant) and
            isinstance(main_func.body[0].value.value, str)):
            docstring = main_func.body[0].value.value.strip()
            description = docstring.split('\n')[0][:200]  # First line, max 200 chars
        
        # Fallback to file head comment
        if not description:
            description = _extract_head_comment(source_code) or f"Script: {file_path.name}"
        
        return ToolSpec(
            name=main_func.name,
            api_type="SCRIPT",
            url=f"scripts/{rel_path}",
            authentication="none",
            input_schema=input_schema,
            output_schema=output_schema,
            description=description,
            source_text=source_code[:5000]  # First 5000 chars for context
        )
        
    except Exception as e:
        logger.warning(f"Failed to extract script spec from {file_path}: {e}")
        return None


def _extract_head_comment(source_code: str) -> Optional[str]:
    """Extract head comment from script."""
    lines = source_code.split('\n')
    comments = []
    in_comment = False
    
    for line in lines[:20]:  # Check first 20 lines
        stripped = line.strip()
        if stripped.startswith('#'):
            comment = stripped.lstrip('#').strip()
            if comment:
                comments.append(comment)
        elif stripped.startswith('"""') or stripped.startswith("'''"):
            break  # Docstring starts, stop here
        elif stripped and not stripped.startswith('#'):
            break  # Code starts
    
    if comments:
        return ' '.join(comments[:3])  # First 3 comment lines
    return None


def _infer_type_from_annotation(annotation) -> str:
    """Infer type from AST annotation."""
    if annotation is None:
        return "text"
    
    if isinstance(annotation, ast.Name):
        type_map = {
            'str': 'text',
            'int': 'number',
            'float': 'number',
            'bool': 'boolean',
            'dict': '{ }',
            'list': 'List [ ]',
            'Dict': '{ }',
            'List': 'List [ ]',
            'Any': 'any',
            'Optional': 'any',
            'Union': 'any',
        }
        return type_map.get(annotation.id, 'text')
    
    if isinstance(annotation, ast.Subscript):
        if isinstance(annotation.value, ast.Name):
            if annotation.value.id in ['List', 'list']:
                return 'List [ ]'
            elif annotation.value.id in ['Dict', 'dict']:
                return '{ }'
            elif annotation.value.id == 'Optional':
                return _infer_type_from_annotation(annotation.slice)
    
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        # Handle string annotations like "Dict[str, Any]"
        return annotation.value
    
    return "text"


def _analyze_code_snippets(graph: FileReferenceGraph, client) -> list[ToolSpec]:
    """Analyze code snippets in all .md files using LLM."""
    tools = []
    pattern = r'```(\w+)?\n(.*?)```'
    snippet_index = 0

    # Extract code blocks from all .md files (not just SKILL.md)
    for doc_path, content in graph.docs_content.items():
        matches = re.finditer(pattern, content, re.DOTALL)

        for match in matches:
            language = (match.group(1) or "python").lower()
            code_text = match.group(2).strip()

            if language in ['python', 'py'] and len(code_text) > 50:
                # Use LLM to analyze the code snippet
                tool = _extract_snippet_spec_with_llm(code_text, snippet_index, client, doc_path)
                if tool:
                    tools.append(tool)
                snippet_index += 1

    return tools


async def _analyze_code_snippets_async(graph: FileReferenceGraph, client) -> list[ToolSpec]:
    """Async version: Analyze code snippets in all .md files using LLM in parallel."""
    pattern = r'```(\w+)?\n(.*?)```'
    valid_snippets = []
    snippet_index = 0

    # Extract code blocks from all .md files (not just SKILL.md)
    for doc_path, content in graph.docs_content.items():
        matches = re.finditer(pattern, content, re.DOTALL)

        for match in matches:
            language = (match.group(1) or "python").lower()
            code_text = match.group(2).strip()

            if language in ['python', 'py'] and len(code_text) > 50:
                valid_snippets.append((snippet_index, code_text, doc_path))
                snippet_index += 1

    if not valid_snippets:
        return []

    # Create async tasks for parallel processing
    tasks = [
        _extract_snippet_spec_with_llm_async(code_text, index, client, doc_path)
        for index, code_text, doc_path in valid_snippets
    ]

    # Execute all tasks in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter successful results
    tools = []
    for result in results:
        if result is not None and not isinstance(result, Exception):
            tools.append(result)

    return tools


def _extract_snippet_spec_with_llm(code_text: str, index: int, client, doc_path: str = "") -> Optional[ToolSpec]:
    """Use LLM to analyze a code snippet and extract API spec."""
    try:
        prompt = f"""Analyze this Python code snippet and extract the API specification.

Code:
```python
{code_text[:3000]}
```

Extract:
1. Function or class name (or generate a descriptive name if no explicit name)
2. Input parameters and their types
3. Output/return type
4. Short description of what it does

Respond in this exact JSON format:
{{
    "name": "function_or_class_name",
    "input_schema": {{"param1": "type1", "param2": "type2"}},
    "output_schema": {{"return_value1": "type1", "return_value2": "type2"}},
    "description": "Short functional description"
}}

Types should be: text, number, boolean, {{ }}, List [ ], or any.
If no function/class found, generate a descriptive name like "process_data" or "parse_response".
"""

        # Call LLM
        response = client.call_json("analyze_snippet", "", prompt)

        # Parse JSON response
        try:
            data = response

            # Generate a library-qualified name if possible
            library = _detect_library(code_text)
            name = data.get("name", f"snippet_{index}")
            url = f"{library}.{name}" if library else f"code.{name}"

            return ToolSpec(
                name=name,
                api_type="CODE_SNIPPET",
                url=url,
                authentication="none",
                input_schema=data.get("input_schema", {}),
                output_schema=data.get("output_schema", "void"),
                description=data.get("description", f"Code snippet: {name}"),
                source_text=code_text[:3000]
            )
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response for snippet {index}")
            return None

    except Exception as e:
        logger.warning(f"Failed to extract snippet spec: {e}")
        return None


async def _extract_snippet_spec_with_llm_async(code_text: str, index: int, client, doc_path: str = "") -> Optional[ToolSpec]:
    """Async version: Use LLM to analyze a code snippet and extract API spec."""
    try:
        prompt = f"""Analyze this Python code snippet and extract the API specification.

Code:
```python
{code_text[:3000]}
```

Extract:
1. Function or class name (or generate a descriptive name if no explicit name)
2. Input parameters and their types
3. Output/return type
4. Short description of what it does

Respond in this exact JSON format:
{{
    "name": "function_or_class_name",
    "input_schema": {{"param1": "type1", "param2": "type2"}},
    "output_schema": "return_type",
    "description": "Short functional description"
}}

Types should be: text, number, boolean, {{ }}, List [ ], or any.
If no function/class found, generate a descriptive name like "process_data" or "parse_response".
"""

        # Async call to LLM
        response = await client.async_call_json("analyze_snippet", "", prompt)

        # Parse JSON response
        try:
            data = response

            # Generate a library-qualified name if possible
            library = _detect_library(code_text)
            name = data.get("name", f"snippet_{index}")
            url = f"{library}.{name}" if library else f"code.{name}"

            return ToolSpec(
                name=name,
                api_type="CODE_SNIPPET",
                url=url,
                authentication="none",
                input_schema=data.get("input_schema", {}),
                output_schema=data.get("output_schema", "void"),
                description=data.get("description", f"Code snippet: {name}"),
                source_text=code_text[:3000]
            )
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response for snippet {index}")
            return None

    except Exception as e:
        logger.warning(f"Failed to extract snippet spec: {e}")
        return None


def _detect_library(code_text: str) -> Optional[str]:
    """Detect the primary library being used in code."""
    # Common library patterns
    library_patterns = [
        (r'import\s+([a-zA-Z_][a-zA-Z0-9_]*)', 1),
        (r'from\s+([a-zA-Z_][a-zA-Z0-9_]*)', 1),
    ]
    
    imports = []
    for pattern, group in library_patterns:
        matches = re.findall(pattern, code_text)
        imports.extend(matches)
    
    # Filter out common stdlib modules
    stdlib = {'os', 'sys', 'json', 're', 'pathlib', 'typing', 'datetime', 'collections'}
    external = [imp for imp in imports if imp not in stdlib]
    
    if external:
        return external[0]  # Return first external library
    elif imports:
        return imports[0]  # Fall back to any import
    
    return None
