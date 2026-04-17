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

from models import FileReferenceGraph, SkillPackage, ToolSpec, UnifiedAPISpec
from pre_processing.unified_api_extractor import extract_unified_apis_with_retry

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
    tools: list,
    script_results: dict,
    priority2_tasks: list,
) -> None:
    """统一处理LLM任务结果。

    Args:
        task_type: 任务类型 ("unified_api" | "script")
        rel_path: 相对文件路径
        result: LLM返回结果或异常
        unified_apis: 统一的API列表（会被修改）
        tools: 工具列表（会被修改）
        script_results: 脚本结果字典（会被修改）
        priority2_tasks: 优先级2任务列表（用于查找node）
    """
    if isinstance(result, Exception):
        logger.warning("[P3/P2.5] Task failed for %s: %s", rel_path, result)
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
                "[P3/P2.5] Extracted %d unified APIs from %s",
                len(result),
                rel_path,
            )
    elif task_type == "script":
        if isinstance(result, ToolSpec) or result is None:
            tool = result
            for rp, role, fp, node in priority2_tasks:
                if rp == rel_path:
                    script_results[rel_path] = (tool, role, rel_path, node)
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
    tools: list[ToolSpec] = []
    unified_apis: list[UnifiedAPISpec] = []
    script_results: dict[str, tuple[Optional[ToolSpec], str, str, Any]] = {}
    results: list[Any] = []

    if llm_tasks or unified_api_tasks:
        logger.info("[P3/P2.5] Launching %d parallel LLM tasks (%d unified API)", 
                    len(llm_tasks), len(unified_api_tasks))
        
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
            tools=tools,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
        )

    # Process script results - only add to tools, NOT to merged_doc_text
    # API specs are for Step 3B/4D, not for Step 1 structure extraction
    for rel_path, (tool, role, _, node) in script_results.items():
        if tool:
            tools.append(tool)
            # NOTE: We do NOT add script API specs to merged_doc_text
            # merged_doc_text is for Step 1 structure extraction (doc content only)
            # Script API specs are stored in package.tools for Step 3B/4D
            logger.info("[P3/P2.5] Analyzed script: %s", rel_path)
        else:
            logger.warning("[P3/P2.5] Script analysis failed for %s", rel_path)

    merged_doc_text = "\n\n".join(sections)

    logger.info(
        "[P3] Assembled %d sections, %d tools, %d unified APIs",
        len(sections),
        len(tools),
        len(unified_apis),
    )

    return SkillPackage(
        skill_id=graph.skill_id,
        root_path=graph.root_path,
        frontmatter=graph.frontmatter,
        merged_doc_text=merged_doc_text,
        file_role_map=file_role_map,
        scripts=[], # Deprecated: use tools instead
        tools=tools, # Unified API specs from P2.5 (legacy)
        unified_apis=unified_apis, # NEW: Unified API extraction
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
) -> Optional[ToolSpec]:
    """
    Async version: Analyze a script file using AST + LLM.
    Supports multiple languages, with AST analysis for Python and LLM fallback for others.
    """
    try:
        source_code = file_path.read_text(encoding="utf-8")
        language = _detect_language_from_extension(file_path)

        # Only use AST analysis for Python files
        if language == 'python':
            return await _analyze_python_script(source_code, file_path, rel_path, client)
        else:
            # For non-Python files, use LLM-based analysis
            return await _analyze_generic_script(source_code, file_path, rel_path, client, language)

    except Exception as e:
        logger.warning("[P3/P2.5] Failed to analyze script %s: %s", rel_path, e)
        return None


async def _analyze_python_script(
    source_code: str, file_path: Path, rel_path: str, client
) -> Optional[ToolSpec]:
    """Analyze a Python script using AST + LLM."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        logger.warning("[P3/P2.5] Syntax error in %s: %s", rel_path, e)
        return None

    # Find main function
    main_func = None
    for item in tree.body:
        if isinstance(item, ast.FunctionDef):
            if item.name in ["main", "run", "execute"]:
                main_func = item
                break
        elif main_func is None and isinstance(item, ast.FunctionDef):
            main_func = item

    if not main_func:
        # No function found - generate a simple spec
        return ToolSpec(
            name=file_path.stem,
            api_type="SCRIPT",
            url=rel_path,
            authentication="none",
            input_schema={},
            output_schema="void",
            description=f"Script: {file_path.name}",
            source_text=source_code[:5000],
        )

    # Extract input parameters
    input_schema = {}
    for arg in main_func.args.args:
        arg_name = arg.arg
        arg_type = _infer_type_from_annotation(arg.annotation)
        input_schema[arg_name] = arg_type

    # Extract return type
    output_schema = _infer_type_from_annotation(main_func.returns)

    # Use LLM for description (async)
    description = await _get_script_description_async(source_code[:3000], client, 'python')

    return ToolSpec(
        name=main_func.name,
        api_type="SCRIPT",
        url=rel_path,
        authentication="none",
        input_schema=input_schema,
        output_schema=output_schema,
        description=description,
        source_text=source_code[:5000],
    )


async def _analyze_generic_script(
    source_code: str, file_path: Path, rel_path: str, client, language: str
) -> Optional[ToolSpec]:
    """Analyze a non-Python script using LLM."""
    try:
        prompt = f"""Analyze this {language} script and extract the API specification.

Script ({language}):
```{language}
{source_code[:3000]}
```

Extract:
1. Main function name (or generate a descriptive name)
2. Input parameters and their types (if applicable)
3. Output/return type (if applicable)
4. Short description of what it does

Respond in this exact JSON format:
{{
    "name": "function_or_script_name",
    "input_schema": {{"param1": "type1", "param2": "type2"}},
    "output_schema": "return_type",
    "description": "Short functional description"
}}

Types should be: text, number, boolean, {{ }}, List [ ], or any.
Use empty objects {{}} for input_schema if the script takes no arguments.
"""
        response = await client.async_call_json("analyze_script", "", prompt)

        if isinstance(response, dict):
            name = response.get("name", file_path.stem)
            return ToolSpec(
                name=name,
                api_type="SCRIPT",
                url=rel_path,
                authentication="none",
                input_schema=response.get("input_schema", {}),
                output_schema=response.get("output_schema", "void"),
                description=response.get("description", f"{language} script: {name}"),
                source_text=source_code[:5000],
            )
    except Exception as e:
        logger.warning("[P3/P2.5] LLM analysis failed for %s: %s", rel_path, e)

    # Fallback: return basic spec
    return ToolSpec(
        name=file_path.stem,
        api_type="SCRIPT",
        url=rel_path,
        authentication="none",
        input_schema={},
        output_schema="void",
        description=f"{language.capitalize()} script: {file_path.name}",
        source_text=source_code[:5000],
    )


async def _get_script_description_async(source_code: str, client, language: str = 'python') -> str:
    """Async version: Use LLM to generate a description for the script."""
    try:
        prompt = f"""Analyze this {language} script and provide a one-line description of its main functionality.

Script:
```{language}
{source_code[:2000]}
```

Respond with just the description, no JSON, no markdown.
"""
        response = await client.async_call("describe_script", "", prompt)
        if isinstance(response, str):
            return response.strip()[:200]
    except Exception:
        pass
    return f"{language.capitalize()} script"


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions (sync, no I/O)
# ═══════════════════════════════════════════════════════════════════════════════


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
