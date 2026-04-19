"""
P3 — Skill Package Assembler (merged with P2.5 API analysis, async version).

Responsibilities:
- Consume FileReferenceGraph + FileRoleMap (P2 output)
- Priority 1 (doc files): Read full content + extract code snippets (async parallel)
- Priority 2 (script files): Analyze with AST + LLM to generate ToolSpec (async parallel)
- Priority 3 (data/asset): Skip entirely
- Concatenate into merged_doc_text with clear file boundary markers
- Output: SkillPackage (ready for Step 1 LLM input)

Merged P2.5 functionality:
- Code snippet extraction from doc files (priority=1 branch, parallel)
- Script API analysis (priority=2 branch, parallel)
"""
from __future__ import annotations

import asyncio
import ast
import logging
import re
from pathlib import Path
from typing import Any, Optional

from models.data_models import FileReferenceGraph, SkillPackage, ToolSpec, UnifiedAPISpec
from pre_processing.unified_api_extractor import extract_unified_apis_with_retry, FunctionSpec
import uuid

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Language Support Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# Comprehensive set of supported programming languages (markdown code block identifiers)
SUPPORTED_LANGUAGES = {
    # Python ecosystem
    'python', 'py',
    # JavaScript/TypeScript ecosystem
    'javascript', 'js', 'typescript', 'ts', 'jsx', 'tsx',
    # Web markup/styles
    'html', 'htm', 'css', 'scss', 'sass', 'less', 'svg',
    # JVM languages
    'java', 'kotlin', 'kt', 'scala', 'sc', 'groovy',
    'csharp', 'cs', 'vb', 'fsharp', 'fs',
    # Systems/C-family
    'c', 'cpp', 'cxx', 'cc', 'h', 'hpp', 'hxx',
    'rust', 'rs', 'go', 'golang',
    'swift', 'objectivec', 'objc', 'm',
    # Scripting languages
    'bash', 'sh', 'zsh', 'fish', 'shell',
    'powershell', 'ps1', 'psm1', 'pwsh',
    'perl', 'pl', 'pm',
    'php', 'ruby', 'rb', 'lua',
    # Functional languages
    'haskell', 'hs', 'erlang', 'erl', 'elixir', 'ex', 'exs',
    'clojure', 'clj', 'cljs', 'lisp', 'scheme', 'racket', 'rkt',
    'ocaml', 'ml', 'fsharp', 'fs',
    # Data/config languages
    'sql', 'mysql', 'postgresql', 'postgres', 'sqlite',
    'yaml', 'yml', 'json', 'toml', 'xml', 'csv', 'tsv',
    'r', 'matlab', 'octave', 'm', 'sas',
    # Other modern languages
    'dart', 'flutter', 'julia', 'nim', 'crystal', 'v', 'zig',
    'solidity', 'vyper', 'move', 'cairo',
    'wolfram', 'mathematica', 'wl',
    # Documentation/markup
    'markdown', 'md', 'rst', 'asciidoc', 'adoc',
    'dockerfile', 'docker', 'makefile', 'make', 'cmake',
    'graphql', 'gql', 'regex', 'diff', 'ini', 'cfg',
}


def _boundary(rel_path: str, role: str, priority_label: str) -> str:
    """Generate a file boundary marker for merged_doc_text."""
    return f"=== FILE: {rel_path} | role: {role} | priority: {priority_label} ==="


def _process_task_result(
    task_type: str,
    rel_path: str,
    result: Any,
    unified_apis: list,
    script_unified_apis: list,
    script_results: dict,
    priority2_tasks: list,
) -> None:
    """统一处理LLM任务结果。

    Args:
        task_type: 任务类型 ("unified_api" | "script")
        rel_path: 相对文件路径
        result: LLM返回结果或异常
        unified_apis: 来自文档的统一API列表（会被修改）
        script_unified_apis: 来自脚本的统一API列表（会被修改）
        script_results: 脚本结果字典（会被修改）
        priority2_tasks: 优先级2任务列表（用于查找node）
    """
    if isinstance(result, Exception):
        logger.warning("[P3] Task failed for %s: %s", rel_path, result)
        if task_type == "script":
            for rp, role, fp, node in priority2_tasks:
                if rp == rel_path:
                    script_results[rel_path] = (None, role, rel_path, node)
                    break
        return

    if task_type == "unified_api":
        if isinstance(result, list) and len(result) > 0:
            unified_apis.extend(result)
            logger.info(
                "[P3] Extracted %d unified APIs from doc %s",
                len(result),
                rel_path,
            )
    elif task_type == "script":
        # Script analysis now returns UnifiedAPISpec
        if isinstance(result, UnifiedAPISpec):
            for rp, role, fp, node in priority2_tasks:
                if rp == rel_path:
                    script_results[rel_path] = (result, role, rel_path, node)
                    break
            logger.info("[P3] Extracted UnifiedAPI from script %s", rel_path)
        elif result is None:
            for rp, role, fp, node in priority2_tasks:
                if rp == rel_path:
                    script_results[rel_path] = (None, role, rel_path, node)
                    break


def assemble_skill_package(
    graph: FileReferenceGraph,
    file_role_map: dict[str, Any],
    client=None,  # LLM client for API analysis
) -> SkillPackage:
    """
    P3: Assemble the merged document text for Step 1, merging P2.5 analysis.

    This is a synchronous wrapper around the async implementation.
    All LLM calls are executed in parallel for better performance.

    Priority semantics (new):
    1 = doc files -> read full content + extract code snippets (P2.5, parallel)
    2 = script files -> analyze with AST + LLM, generate ToolSpec (P2.5, parallel)
    3 = data/asset -> skip entirely
    """
    return asyncio.run(_assemble_skill_package_async(graph, file_role_map, client))


async def _assemble_skill_package_async(
    graph: FileReferenceGraph,
    file_role_map: dict[str, Any],
    client=None,
) -> SkillPackage:
    """
    Async implementation: All LLM calls are executed in parallel.
    """
    root = Path(graph.root_path)
    sections: list[str] = []

    # Sort by read_priority ascending (1 before 2), then by path for determinism
    ordered = sorted(
        file_role_map.items(),
        key=lambda kv: (kv[1].get("read_priority", 3), kv[0]),
    )

    # Separate tasks by priority
    priority1_tasks: list[tuple[str, str, Path, Any]] = []  # (rel_path, role, file_path, node)
    priority2_tasks: list[tuple[str, str, Path, Any]] = []  # (rel_path, role, file_path, node)

    for rel_path, role_entry in ordered:
        priority: int = role_entry.get("read_priority", 3)
        if priority == 3:
            continue

        node = graph.nodes.get(rel_path)
        if node is None:
            continue

        role = role_entry.get("role", "unknown")
        file_path = root / rel_path

        if priority == 1:
            priority1_tasks.append((rel_path, role, file_path, node))
        elif priority == 2:
            priority2_tasks.append((rel_path, role, file_path, node))

    # Process priority 1: Read all content first (I/O bound, fast)
    doc_contents: dict[str, str] = {}
    for rel_path, role, file_path, node in priority1_tasks:
        content = _read_file_content(file_path)
        header = _boundary(rel_path, role, "MUST_READ")
        sections.append(f"{header}\n{content}")
        doc_contents[rel_path] = content

# Phase 1: Launch all LLM tasks in parallel
    llm_tasks = []
    unified_api_tasks = []

    # Create tasks for unified API extraction (NEW - replaces legacy snippet extraction)
    if client and priority1_tasks:
        for rel_path, content in doc_contents.items():
            task = extract_unified_apis_with_retry(content, rel_path, client, max_retries=3)
            unified_api_tasks.append(("unified_api", rel_path, task))

    # Create tasks for script analysis
    if client and priority2_tasks:
        for rel_path, role, file_path, node in priority2_tasks:
            task = _analyze_script_file_async(file_path, rel_path, node, client)
            llm_tasks.append(("script", rel_path, task))

    # Execute all LLM tasks in parallel
    # Note: script analysis now returns UnifiedAPISpec, not ToolSpec
    script_unified_apis: list[UnifiedAPISpec] = []
    unified_apis: list[UnifiedAPISpec] = [] # From doc files
    script_results: dict[str, tuple[Optional[UnifiedAPISpec], str, str, Any]] = {}
    results: list[Any] = []

    if llm_tasks or unified_api_tasks:
        logger.info("[P3] Launching %d parallel LLM tasks (%d doc API, %d script)",
                    len(llm_tasks), len(unified_api_tasks), len(llm_tasks))

    # Gather all tasks including unified API extraction
    all_tasks = [task for _, _, task in llm_tasks + unified_api_tasks]
    results = await asyncio.gather(
        *all_tasks,
        return_exceptions=True,
    )

    # Process results using unified handler
    for i, (task_type, rel_path, _) in enumerate(llm_tasks + unified_api_tasks):
        _process_task_result(
            task_type=task_type,
            rel_path=rel_path,
            result=results[i],
            unified_apis=unified_apis,
            script_unified_apis=script_unified_apis,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
            )

    # Process script results - now returns UnifiedAPISpec
    for rel_path, (script_api, role, _, node) in script_results.items():
        if script_api:
            script_unified_apis.append(script_api)
            logger.info("[P3] Analyzed script: %s (%d functions)", 
                        rel_path, len(script_api.functions))
        else:
            logger.warning("[P3] Script analysis failed for %s", rel_path)

    # Merge all unified_apis: doc files + scripts
    all_unified_apis = unified_apis + script_unified_apis

    merged_doc_text = "\n\n".join(sections)

    logger.info(
        "[P3] Assembled %d sections, %d unified APIs (doc: %d, scripts: %d)",
        len(sections),
        len(all_unified_apis),
        len(unified_apis),
        len(script_unified_apis),
    )

    return SkillPackage(
        skill_id=graph.skill_id,
        root_path=graph.root_path,
        frontmatter=graph.frontmatter,
        merged_doc_text=merged_doc_text,
        file_role_map=file_role_map,
        scripts=[], # Deprecated
        tools=[], # Deprecated: now all in unified_apis
        unified_apis=all_unified_apis, # Combined: doc APIs + script APIs
    )


def _read_file_content(file_path: Path) -> str:
    """Read file content with error handling."""
    try:
        return file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"[ERROR: could not read file — {exc}]"


# ═══════════════════════════════════════════════════════════════════════════════
# Async P2.5 Functions
# ═══════════════════════════════════════════════════════════════════════════════


async def _extract_snippets_from_doc_async(
    content: str, source_file: str, client
) -> list[ToolSpec]:
    """
    Async version: Extract code snippets from a doc file's content.
    All snippets are processed in parallel.
    """
    tools = []
    pattern = r'```(\w+)?\n(.*?)```'
    matches = list(re.finditer(pattern, content, re.DOTALL))

    # Filter valid code snippets (any supported language)
    snippet_tasks = []
    for i, match in enumerate(matches):
        language = (match.group(1) or "python").lower()
        code_text = match.group(2).strip()

        if language in SUPPORTED_LANGUAGES and len(code_text) > 50:
            task = _analyze_code_snippet_async(code_text, i, source_file, client, language)
            snippet_tasks.append(task)

    if snippet_tasks:
        # Execute all snippet analysis in parallel
        results = await asyncio.gather(*snippet_tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, ToolSpec):
                tools.append(result)
            elif isinstance(result, Exception):
                logger.warning("[P3/P2.5] Snippet analysis failed: %s", result)

    return tools


async def _analyze_code_snippet_async(
    code_text: str, index: int, source_file: str, client, language: str = 'python'
) -> Optional[ToolSpec]:
    """Async version: Use LLM to analyze a code snippet in any supported language."""
    try:
        prompt = f"""Analyze this {language} code snippet and extract the API specification.

Code:
```{language}
{code_text[:3000]}
```

Extract:
1. Function or class name (or generate a descriptive name if no explicit name)
2. Input parameters and their types
3. Output/return type
4. Short description of what it does

Respond in this exact JSON format:
{{
  "name": "{language}:function_or_class_name",
  "input_schema": {{"param1": "type1", "param2": "type2"}},
  "output_schema": "return_type",
  "description": "Short functional description"
}}

Types should be: text, number, boolean, {{ }}, List [ ], or any.
If no function/class found, generate a descriptive name like "process_data" or "parse_response".
"""
        response = await client.async_call_json("analyze_snippet", "", prompt)

        if isinstance(response, dict):
            name = response.get("name", f"snippet_{index}")
            library = _detect_library(code_text)
            url = f"{library}.{name}" if library else f"code.{name}"

            return ToolSpec(
                name=name,
                api_type="CODE_SNIPPET",
                url=url,
                authentication="none",
                input_schema=response.get("input_schema", {}),
                output_schema=response.get("output_schema", "void"),
                description=response.get("description", f"Code snippet: {name}"),
                source_text=code_text[:3000],
            )
    except Exception as e:
        logger.warning("[P3/P2.5] Failed to analyze snippet %d from %s: %s", index, source_file, e)

    return None


def _detect_language_from_extension(file_path: Path) -> str:
    """Detect programming language from file extension."""
    ext = file_path.suffix.lower()
    ext_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.jsx': 'javascript',
        '.sh': 'bash',
        '.bash': 'bash',
        '.zsh': 'zsh',
        '.ps1': 'powershell',
        '.rb': 'ruby',
        '.pl': 'perl',
        '.php': 'php',
        '.lua': 'lua',
        '.rs': 'rust',
        '.go': 'go',
        '.java': 'java',
        '.kt': 'kotlin',
        '.scala': 'scala',
        '.clj': 'clojure',
        '.hs': 'haskell',
        '.ex': 'elixir',
        '.exs': 'elixir',
        '.swift': 'swift',
        '.c': 'c',
        '.cpp': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
        '.cs': 'csharp',
        '.fs': 'fsharp',
        '.r': 'r',
        '.m': 'matlab',
        '.jl': 'julia',
        '.nim': 'nim',
        '.cr': 'crystal',
        '.dart': 'dart',
        '.v': 'v',
        '.zig': 'zig',
        '.sol': 'solidity',
        '.vy': 'vyper',
    }
    return ext_map.get(ext, 'python')  # Default to python if unknown


async def _analyze_script_file_async(
    file_path: Path, rel_path: str, node: Any, client
) -> Optional[UnifiedAPISpec]:
    """
    Analyze a script file using LLM.
    
    Unified approach for all languages:
    - Uses LLM to intelligently detect main function
    - Extracts detailed IO schema for main function (if exists)
    - Extracts all functions (if no main function)
    - Returns UnifiedAPISpec for consistent downstream processing
    
    Args:
        file_path: Path to the script file
        rel_path: Relative path from skill root
        node: FileNode from reference graph
        client: LLM client
        
    Returns:
        UnifiedAPISpec representing the script's API
    """
    try:
        source_code = file_path.read_text(encoding="utf-8")
        language = _detect_language_from_extension(file_path)
        
        # Unified LLM-based analysis for all languages
        return await _analyze_script_with_llm(
            source_code, file_path, rel_path, client, language
        )

    except Exception as e:
        logger.warning("[P3] Failed to analyze script %s: %s", rel_path, e)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# New LLM-based Script Analysis (Replaces AST-based approach)
# ═══════════════════════════════════════════════════════════════════════════════

_SCRIPT_ANALYSIS_SYSTEM_PROMPT = """You are an expert code analyzer specializing in extracting API specifications from scripts.

Your task is to:
1. Detect if the script has a "main function" (a primary entry point that other functions serve)
2. Extract appropriate API specifications based on the script structure

Key concepts:
- Main function: The primary callable entry point, often called from `if __name__ == "__main__":` or handling command-line arguments
- Helper functions: Functions that support the main function's operation
- Independent functions: Functions that can be called standalone (no main function scenario)

Be precise and thorough in your analysis."""

_SCRIPT_ANALYSIS_USER_PROMPT_TEMPLATE = """Analyze this {language} script and extract its API specification.

Script file: {file_name}

Source code:
```{language}
{source_code}
```

Analysis Instructions:

1. **Detect Main Function**: 
   - Check if there's a function in `if __name__ == "__main__":` block or handling `sys.argv`
   - Determine if other functions serve this function (called by it, prepare data for it)
   - Main function is the "primary workflow" that other functions support

2. **Extraction Strategy**:
   
   **IF main function EXISTS** (other functions serve it):
   - Extract detailed IO schema for the main function only
   - Map `sys.argv` indices to main function parameters
   - List helper function names (no detailed IO needed for helpers)
   - Describe the main function's purpose
   
   **IF NO main function** (all functions are independent tools):
   - Extract detailed IO schema for ALL functions
   - Each function is a standalone callable
   - Describe what the script provides as a toolkit

3. **IO Schema Extraction**:
   - Parameter name, type (text, number, boolean, List[type], {{ }}, any, file_path, stream)
   - Whether required (true if no default, false if has default)
   - Default value if applicable
   - Parameter description
   - Return/output type

4. **Command-line mapping**:
   - If script uses `sys.argv[N]`, map to corresponding function parameter
   - Document usage pattern: `python script.py arg1 arg2`

Output JSON format:
```json
{{
  "has_main_function": true/false,
  "main_function": {{
    "name": "function_name or null",
    "description": "What this function does (one sentence)",
    "input_schema": {{
      "param_name": {{
        "type": "text|number|boolean|List[type]|{{}}|any|file_path|stream",
        "required": true/false,
        "default": "default value or null",
        "description": "What this parameter is for"
      }}
    }},
    "output_schema": "return type description",
    "is_entry_point": true/false,
    "command_line_params": ["param1", "param2"] // maps to sys.argv[1], sys.argv[2]
  }},
  "all_functions": [
    {{
      "name": "function_name",
      "description": "What this function does",
      "input_schema": {{...}},
      "output_schema": "return type",
      "is_entry_point": true/false,  // callable from outside
      "serves_main": true/false  // supports main function
    }}
  ],
  "auxiliary_functions": ["helper1", "helper2"],  // only when has_main_function=true
  "command_line_usage": "python script.py [args]",
  "imported_libraries": ["os", "json", "sys"],
  "script_description": "Overall what this script does"
}}
"""


async def _analyze_script_with_llm(
    source_code: str,
    file_path: Path,
    rel_path: str,
    client,
    language: str
) -> Optional[UnifiedAPISpec]:
    """
    Analyze script using LLM to extract unified API specification.
    
    Intelligently detects main function vs independent functions,
    extracts appropriate IO schemas.
    """
    import uuid
    
    try:
        # Build prompt
        prompt = _SCRIPT_ANALYSIS_USER_PROMPT_TEMPLATE.format(
            language=language,
            file_name=file_path.name,
            source_code=source_code[:5000]  # Limit to avoid token overflow
        )
        
        # Call LLM
        response = await client.async_call_json(
            step_name="script_analysis",
            system=_SCRIPT_ANALYSIS_SYSTEM_PROMPT,
            user=prompt
        )
        
        if not isinstance(response, dict):
            logger.warning("[P3] Invalid LLM response type for %s: %s", rel_path, type(response))
            return _create_fallback_unified_api(source_code, file_path, rel_path, language)
        
        return _parse_script_llm_response(response, source_code, file_path, rel_path, language)
        
    except Exception as e:
        logger.warning("[P3] LLM analysis failed for %s: %s", rel_path, e)
        return _create_fallback_unified_api(source_code, file_path, rel_path, language)


def _parse_script_llm_response(
    response: dict,
    source_code: str,
    file_path: Path,
    rel_path: str,
    language: str
) -> UnifiedAPISpec:
    """Parse LLM response and build UnifiedAPISpec."""
    
    has_main = response.get("has_main_function", False)
    imported_libs = response.get("imported_libraries", [])
    script_desc = response.get("script_description", f"{language} script: {file_path.name}")
    
    # Build FunctionSpec list
    functions = []
    
    if has_main:
        # Has main function: detailed main + simplified helpers
        main_func_data = response.get("main_function", {})
        if main_func_data and main_func_data.get("name"):
            # Main function with detailed IO
            func_spec = _build_function_spec_from_data(main_func_data, is_main=True)
            functions.append(func_spec)
        
        # Add all functions from all_functions list
        all_funcs_data = response.get("all_functions", [])
        for func_data in all_funcs_data:
            func_name = func_data.get("name", "")
            # Skip if already added as main
            if func_name and func_name != main_func_data.get("name"):
                is_helper = func_data.get("serves_main", True)
                if is_helper:
                    # Helper function: simplified
                    func_spec = FunctionSpec(
                        name=func_name,
                        signature=f"def {func_name}(...)",
                        description=func_data.get("description", f"Helper function"),
                        input_schema={},
                        output_schema="void"
                    )
                else:
                    # Not a helper: detailed
                    func_spec = _build_function_spec_from_data(func_data, is_main=False)
                functions.append(func_spec)
        
        # Also add auxiliary function names if provided
        aux_names = response.get("auxiliary_functions", [])
        for aux_name in aux_names:
            # Check if not already in functions
            if not any(f.name == aux_name for f in functions):
                functions.append(FunctionSpec(
                    name=aux_name,
                    signature=f"def {aux_name}(...)",
                    description=f"Helper function for {main_func_data.get('name', 'main')}",
                    input_schema={},
                    output_schema="void"
                ))
    else:
        # No main function: all functions are independent tools
        all_funcs_data = response.get("all_functions", [])
        for func_data in all_funcs_data:
            func_spec = _build_function_spec_from_data(func_data, is_main=False)
            functions.append(func_spec)
    
    # Build UnifiedAPISpec
    api_id = f"{file_path.stem}_{uuid.uuid4().hex[:8]}"
    api_name = _to_pascal_case(file_path.stem)
    
    return UnifiedAPISpec(
        api_id=api_id,
        api_name=api_name,
        primary_library="scripts",
        all_libraries=imported_libs if imported_libs else ["scripts"],
        language=language,
        functions=functions,
        combined_source=source_code[:5000],
        source_file=rel_path
    )


def _build_function_spec_from_data(func_data: dict, is_main: bool) -> FunctionSpec:
    """Build FunctionSpec from LLM response data."""
    input_schema_raw = func_data.get("input_schema", {})
    
    # Convert detailed input schema to simple dict
    input_schema = {}
    for param_name, param_info in input_schema_raw.items():
        if isinstance(param_info, dict):
            input_schema[param_name] = param_info.get("type", "text")
        else:
            input_schema[param_name] = str(param_info)
    
    # Build signature string
    param_list = ", ".join([
        f"{k}: {v}" if isinstance(v, str) else f"{k}"
        for k, v in input_schema_raw.items()
    ])
    signature = f"def {func_data.get('name', 'function')}({param_list})"
    
    return FunctionSpec(
        name=func_data.get("name", "function"),
        signature=signature,
        description=func_data.get("description", ""),
        input_schema=input_schema,
        output_schema=func_data.get("output_schema", "void")
    )


def _create_fallback_unified_api(
    source_code: str,
    file_path: Path,
    rel_path: str,
    language: str
) -> UnifiedAPISpec:
    """Create a fallback UnifiedAPISpec when LLM analysis fails."""
    import uuid
    
    api_id = f"{file_path.stem}_{uuid.uuid4().hex[:8]}"
    api_name = _to_pascal_case(file_path.stem)
    
    return UnifiedAPISpec(
        api_id=api_id,
        api_name=api_name,
        primary_library="scripts",
        all_libraries=["scripts"],
        language=language,
        functions=[
            FunctionSpec(
                name=file_path.stem,
                signature=f"def {file_path.stem}(...)",
                description=f"{language.capitalize()} script: {file_path.name}",
                input_schema={},
                output_schema="void"
            )
        ],
        combined_source=source_code[:5000],
        source_file=rel_path
    )


def _to_pascal_case(snake_str: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in snake_str.split("_"))


# ═══════════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions (sync, no I/O)
# ═══════════════════════════════════════════════════════════════════════════════

# Note: The following legacy functions have been removed as part of Phase 6 cleanup:
# - _analyze_python_script (replaced by _analyze_script_with_llm)
# - _analyze_generic_script (replaced by _analyze_script_with_llm)
# - _get_script_description_async (no longer needed with new LLM-based approach)
#
# The new LLM-based approach (_analyze_script_with_llm) handles all languages
# uniformly and intelligently detects main functions vs independent functions.

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
        return annotation.value

    return "text"


def _detect_library(code_text: str) -> Optional[str]:
    """Detect the primary library being used in code."""
    library_patterns = [
        (r'import\s+([a-zA-Z_][a-zA-Z0-9_]*)', 1),
        (r'from\s+([a-zA-Z_][a-zA-Z0-9_]*)', 1),
    ]

    imports = []
    for pattern, group in library_patterns:
        matches = re.findall(pattern, code_text)
        imports.extend(matches)

    stdlib = {'os', 'sys', 'json', 're', 'pathlib', 'typing', 'datetime', 'collections'}
    external = [imp for imp in imports if imp not in stdlib]

    if external:
        return external[0]
    elif imports:
        return imports[0]

    return None


def _format_tool_spec_as_content(tool: ToolSpec) -> str:
    """Format a ToolSpec as readable content for merged_doc_text."""
    lines = [
        f"[API Spec: {tool.name}]",
        f"Type: {tool.api_type}",
        f"URL: {tool.url}",
        f"Authentication: {tool.authentication}",
        "",
        "Input Schema:",
    ]
    for param, ptype in tool.input_schema.items():
        lines.append(f"  - {param}: {ptype}")

    lines.extend([
        "",
        f"Output: {tool.output_schema}",
        "",
        f"Description: {tool.description}",
    ])
    return "\n".join(lines)
