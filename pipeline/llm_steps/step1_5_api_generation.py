"""
step1_5_api_generation.py
────────────────────────
Step 1.5: API Definition Generation (moved from Step 4D).

Changes:
- Moved from Step 4 to Step 1.5 (after Step 1 structure extraction)
- Generates API definitions for each tool independently
- Builds APISymbolTable for later use in Step 4E
- Each tool gets its own LLM call for parallel generation

Execution:
- Called immediately after Step 1 completes
- Runs in parallel: one LLM call per tool
- Results merged into APISymbolTable
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from models.data_models import APISpec, APISymbolTable, ToolSpec, UnifiedAPISpec, FunctionSpec
from pipeline.llm_client import LLMClient
from prompts import templates

logger = logging.getLogger(__name__)


def generate_api_definitions(
    tools: list[ToolSpec],
    client: LLMClient,
    max_workers: int = 4,
    model: Optional[str] = None,
) -> APISymbolTable:
    """
    Generate DEFINE_APIS blocks for all tools.

    Called immediately after Step 1 completes.
    Each tool gets its own LLM call for independent generation.
    All calls run in parallel via ThreadPoolExecutor.

    Args:
        tools: List of ToolSpec from package.tools (merged from Step 1 + P3)
        client: LLM client for making calls
        max_workers: Max parallel workers for API generation
        model: Optional model override. If None, uses client's default model.

    Returns:
        APISymbolTable containing all generated API definitions
    """
    if not tools:
        logger.info("[Step 1.5] No tools to generate APIs for")
        return APISymbolTable(apis={})

    logger.info("[Step 1.5] Generating API definitions for %d tools...", len(tools))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        # Launch one LLM call per tool in parallel
        futures = {
            tool.name: pool.submit(_generate_single_api, client, tool, model)
            for tool in tools
        }

        # Collect results
        apis = {}
        for name, future in futures.items():
            try:
                api_spec = future.result()
                if api_spec:
                    apis[name] = api_spec
                    logger.debug("[Step 1.5] Generated API: %s", name)
            except Exception as exc:
                logger.error("[Step 1.5] Failed to generate API for %s: %s", name, exc)
                # Continue with other APIs even if one fails

    logger.info("[Step 1.5] Generated %d/%d API definitions", len(apis), len(tools))
    return APISymbolTable(apis=apis)


def _generate_single_api(
    client: LLMClient,
    tool: ToolSpec,
    model: Optional[str] = None,
) -> APISpec | None:
    """
    Generate DEFINE_API block for a single tool.

    Args:
        client: LLM client
        tool: ToolSpec with name, input_schema, output_schema, etc.
        model: Optional model override. If None, uses client's default model.

    Returns:
        APISpec with generated SPL and parsed I/O schemas
    """
    try:
        # Prepare tool info as JSON for the LLM
        tool_info = {
            "name": tool.name,
            "api_type": tool.api_type,
            "url": tool.url,
            "authentication": tool.authentication,
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
            "description": tool.description,
        }
        tool_json = json.dumps(tool_info, indent=2, ensure_ascii=False)

        # Call LLM to generate DEFINE_API block
        spl_text = client.call(
            step_name="step1_5_api_generation",
            system=templates.S1_5_API_SYSTEM,
            user=templates.render_s1_5_api_user(tool_json),
            model=model,
        )

        # Parse I/O schemas from the generated SPL
        input_params = _parse_input_schema(tool.input_schema)
        output_params = _parse_output_schema(tool.output_schema)

        return APISpec(
            name=tool.name,
            spl_text=spl_text,
            input_params=input_params,
            output_params=output_params,
            description=tool.description,
        )

    except Exception as exc:
        logger.error("[Step 1.5] Error generating API for %s: %s", tool.name, exc)
        return None


def _parse_input_schema(input_schema: dict) -> list[dict]:
    """
    Parse input schema dict into structured format.

    Args:
        input_schema: Dict of param_name -> type_annotation (str or dict)

    Returns:
        List of input parameter dicts
    """
    params = []
    for name, type_info in input_schema.items():
        # Skip self/cls for methods
        if name in ("self", "cls"):
            continue

        # Handle both string and dict type_info
        if isinstance(type_info, dict):
            # If it's a dict, extract type from it or use a default
            type_str = type_info.get("type", "text")
            description = type_info.get("description", "")
            is_required = type_info.get("required", True)
            clean_type = type_str
        elif isinstance(type_info, str):
            type_str = type_info
            # Determine if required (simplistic: no default = required)
            is_required = not type_str.startswith("Optional") and "=" not in type_str

            # Clean up type string
            clean_type = type_str.replace("Optional[", "").replace("]", "")
            clean_type = clean_type.split("=")[0].strip()
        else:
            # Unknown type, use as string
            clean_type = str(type_info)
            is_required = True

        params.append({
            "name": name,
            "type": clean_type,
            "required": is_required,
        })

    return params


def _parse_output_schema(output_schema) -> list[dict]:
    """
    Parse output schema into structured format.

    Args:
        output_schema: Return type annotation (str or dict) or "void"

    Returns:
        List of output parameter dicts (usually 1 or 0)
    """
    if not output_schema or output_schema == "void":
        return []

    # Handle dict type
    if isinstance(output_schema, dict):
        type_str = output_schema.get("type", "text")
        if type_str and type_str != "None" and type_str != "void":
            return [{"name": "result", "type": type_str}]
        return []

    # Handle string type
    if isinstance(output_schema, str):
        clean_type = output_schema.strip()
        if clean_type and clean_type != "None":
            return [{"name": "result", "type": clean_type}]

    return []


# ─────────────────────────────────────────────────────────────────────────────
# Async versions
# ─────────────────────────────────────────────────────────────────────────────

async def _generate_single_api_async(
    client: LLMClient,
    tool: ToolSpec,
    model: Optional[str] = None,
) -> APISpec | None:
    """
    Async version: Generate DEFINE_API block for a single tool.

    Args:
        client: LLM client
        tool: ToolSpec with name, input_schema, output_schema, etc.
        model: Optional model override. If None, uses client's default model.
    """
    try:
        # Prepare tool info as JSON for the LLM
        tool_info = {
            "name": tool.name,
            "api_type": tool.api_type,
            "url": tool.url,
            "authentication": tool.authentication,
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
            "description": tool.description,
        }
        tool_json = json.dumps(tool_info, indent=2, ensure_ascii=False)

        # Call LLM to generate DEFINE_API block (async)
        spl_text = await client.async_call(
            step_name="step1_5_api_generation",
            system=templates.S1_5_API_SYSTEM,
            user=templates.render_s1_5_api_user(tool_json),
            model=model,
        )

        # Parse I/O schemas from the generated SPL
        input_params = _parse_input_schema(tool.input_schema)
        output_params = _parse_output_schema(tool.output_schema)

        return APISpec(
            name=tool.name,
            spl_text=spl_text,
            input_params=input_params,
            output_params=output_params,
            description=tool.description,
        )

    except Exception as exc:
        logger.error("[Step 1.5] Error generating API for %s: %s", tool.name, exc)
        return None


def build_api_symbol_table(apis: dict[str, APISpec]) -> APISymbolTable:
    """
    Build APISymbolTable from a dict of APISpec objects.
    """
    return APISymbolTable(apis=apis)


def merge_api_spl_blocks(api_table: APISymbolTable) -> str:
    """Merge all API SPL blocks into a single DEFINE_APIS block.

    Applies post-processing to fix common LLM format errors:
    - Strips any "DEFINE_API" prefix before API declarations
    - Strips any [DEFINE_APIS:]/[END_APIS] wrappers from individual blocks
    - Validates/corrects AUTHENTICATION values to only: none, apikey, oauth

    Args:
        api_table: APISymbolTable with all generated APIs

    Returns:
        Combined DEFINE_APIS block text for S4D output
    """
    if not api_table.apis:
        return ""

    parts = ["[DEFINE_APIS:]"]
    for name, spec in api_table.apis.items():
        cleaned = _postprocess_api_spl(spec.spl_text, expected_name=name)
        if cleaned:
            parts.append(cleaned)
    parts.append("[END_APIS]")

    return "\n\n".join(parts)


# Valid SPL authentication values
_VALID_AUTH_VALUES = {"none", "apikey", "oauth"}

# Regex: match API declaration header — e.g., "PdfReading<none>" or "DEFINE_API PdfReading<none>"
_API_HEADER_RE = re.compile(
    r'^\s*'
    r'(?:DEFINE_API\s+)?'           # Optional "DEFINE_API " prefix (to strip)
    r'([A-Za-z][A-Za-z0-9_]*)'      # API name (group 1)
    r'<([^>]*)>'                     # Auth value inside <> (group 2)
)

# Regex: strip [DEFINE_APIS:] and [END_APIS] wrappers from individual blocks
_API_WRAPPER_RE = re.compile(
    r'^\s*\[DEFINE_APIS:\s*\]\s*\n?|'
    r'\n?\s*\[END_APIS\s*\]\s*$',
    re.MULTILINE
)


def _postprocess_api_spl(spl_text: str, expected_name: str) -> str:
    """Post-process a single API SPL block to fix common LLM errors.

    Fixes:
    1. Strips "DEFINE_API" prefix before API name
    2. Strips [DEFINE_APIS:]/[END_APIS] wrapper tags
    3. Validates AUTHENTICATION value — replaces invalid values with "none"
    4. Replaces literal "ApiName" with expected_name (PascalCase)

    Args:
        spl_text: Raw LLM-generated API SPL text
        expected_name: Expected PascalCase API name

    Returns:
        Cleaned API declaration text
    """
    if not spl_text or not spl_text.strip():
        return ""

    text = spl_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Strip [DEFINE_APIS:]/[END_APIS] wrappers
    text = _API_WRAPPER_RE.sub("", text).strip()

    # Fix "DEFINE_API" prefix — strip it from any line
    text = re.sub(r'^(\s*)DEFINE_API\s+', r'\1', text, flags=re.MULTILINE)

    # Fix API name and auth value in the first API declaration line
    # Match lines like: "PdfReading<none>" or "DEFINE_API PdfReading<none>"
    # or "ApiName<AdvancedPdfManipulation>"
    def _fix_header(match: re.Match) -> str:
        api_name = match.group(1)
        auth_value = match.group(2).strip()

        # Replace literal "ApiName" with expected name
        if api_name == "ApiName":
            api_name = expected_name

        # Ensure PascalCase
        if api_name and api_name[0].islower():
            api_name = api_name[0].upper() + api_name[1:]

        # Validate auth value
        if auth_value.lower() not in _VALID_AUTH_VALUES:
            logger.warning(
                "[Step 1.5] Invalid auth value <%s> for API %s, replacing with <none>",
                auth_value, api_name
            )
            auth_value = "none"
        else:
            auth_value = auth_value.lower()

        return f"{api_name}<{auth_value}>"

    text = _API_HEADER_RE.sub(_fix_header, text, count=1)

    return text


# ═══════════════════════════════════════════════════════════════════════════════
# Unified API Generation (New)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_unified_api_definitions(
    unified_apis: list[UnifiedAPISpec],
    client: LLMClient,
    max_workers: int = 4,
    model: Optional[str] = None,
) -> APISymbolTable:
    """
    Generate DEFINE_APIS blocks for UnifiedAPISpec objects.

    Args:
        unified_apis: List of UnifiedAPISpec from unified API extraction
        client: LLM client for making calls
        max_workers: Max parallel workers for API generation
        model: Optional model override. If None, uses client's default model.

    Returns:
        APISymbolTable containing all generated API definitions
    """
    if not unified_apis:
        logger.info("[Step 1.5 Unified] No unified APIs to generate")
        return APISymbolTable(apis={}, unified_apis={})

    logger.info("[Step 1.5 Unified] Generating API definitions for %d unified APIs...", len(unified_apis))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        # Launch one LLM call per unified API in parallel
        futures = {
            api.api_name: pool.submit(_generate_single_unified_api, client, api, model)
            for api in unified_apis
        }

        # Collect results
        apis = {}
        unified_apis_dict = {}
        for api_name, future in futures.items():
            try:
                api_spec = future.result()
                if api_spec:
                    apis[api_name] = api_spec
                    # Also store in unified_apis dict
                    unified_api = next((u for u in unified_apis if u.api_name == api_name), None)
                    if unified_api:
                        unified_apis_dict[api_name] = unified_api
                    logger.debug("[Step 1.5 Unified] Generated API: %s", api_name)
            except Exception as exc:
                logger.error("[Step 1.5 Unified] Failed to generate API for %s: %s", api_name, exc)
                # Continue with other APIs even if one fails

    logger.info("[Step 1.5 Unified] Generated %d/%d unified API definitions", len(apis), len(unified_apis))
    return APISymbolTable(apis=apis, unified_apis=unified_apis_dict)


def _generate_single_unified_api(
    client: LLMClient,
    unified_api: UnifiedAPISpec,
    model: Optional[str] = None,
) -> APISpec | None:
    """
    Generate DEFINE_API block for a single UnifiedAPISpec.

    Args:
        client: LLM client
        unified_api: UnifiedAPISpec with multiple functions
        model: Optional model override. If None, uses client's default model.

    Returns:
        APISpec with generated SPL containing multiple functions
    """
    try:
        # Prepare unified API info as JSON for the LLM
        functions_json = []
        for func in unified_api.functions:
            func_info = {
                "name": func.name,
                "signature": func.signature,
                "description": func.description,
                "input_schema": func.input_schema,
                "output_schema": func.output_schema,
                "url": _generate_function_url(unified_api.primary_library, func.name),
            }
            functions_json.append(func_info)

        api_info = {
            "api_name": unified_api.api_name,
            "primary_library": unified_api.primary_library,
            "all_libraries": unified_api.all_libraries,
            "language": unified_api.language,
            "functions": functions_json,
            "combined_source": unified_api.combined_source[:2000],  # Truncate for token limit
        }
        api_json = json.dumps(api_info, indent=2, ensure_ascii=False)

        # Call LLM to generate DEFINE_API block
        spl_text = client.call(
            step_name="step1_5_unified_api_generation",
            system=_UNIFIED_API_SYSTEM_PROMPT,
            user=_render_unified_api_user(api_json),
            model=model,
        )

        # Parse I/O schemas from the first function as representative
        input_params = _parse_input_schema(unified_api.functions[0].input_schema) if unified_api.functions else []
        output_params = _parse_output_schema(unified_api.functions[0].output_schema) if unified_api.functions else []

        return APISpec(
            name=unified_api.api_name,
            spl_text=spl_text,
            input_params=input_params,
            output_params=output_params,
            description=f"Unified API for {', '.join(unified_api.all_libraries)}",
        )

    except Exception as exc:
        logger.error("[Step 1.5 Unified] Error generating API for %s: %s", unified_api.api_name, exc)
        return None


def _generate_function_url(primary_library: str, function_name: str) -> str:
    """Generate URL for a function in the format library.function."""
    return f"{primary_library}.{function_name}"


_UNIFIED_API_SYSTEM_PROMPT = """You are an expert SPL (Skill Processing Language) generator.

Your task is to generate a single API_DECLARATION for a unified API that contains multiple functions from one or more libraries.

## SPL Grammar for API_DECLARATION

API_DECLARATION :=
    API_NAME "<" AUTHENTICATION ">" OPENAPI_SCHEMA API_IN_SPL

AUTHENTICATION := "none" | "apikey" | "oauth"
    - ONLY these 3 values are allowed inside < >
    - NEVER put an API name, library name, or any other text inside < >
    - SCRIPT and CODE_SNIPPET tools always use <none>
    - NETWORK_API tools use <apikey> or <oauth> as specified

API_NAME := PascalCase name derived from the api_name field in the input JSON
    - NEVER output literal "ApiName" — always use the actual API name from the input
    - Convert to PascalCase if not already (e.g., "pdf_reading" → "PdfReading")

OPENAPI_SCHEMA := "{ }" for SCRIPT/CODE_SNIPPET, or structured text for NETWORK_API

API_IN_SPL := "{" "functions:" "[" {FUNCTION} "]" "}"

FUNCTION := "{"
    "name:" STATIC_DESCRIPTION ","
    "url:" <url_string> ","
    ["description:" STATIC_DESCRIPTION ","]
    "parameters:" "{" "parameters:" "[" {PARAMETER} "]" "," "controlled-input:" BOOL "}" ","
    "return:" "{" "type:" PARAMETER_TYPE "," "controlled-output:" BOOL "}"
"}"

## Key requirements
1. Use the api_name from the input JSON as API_NAME (convert to PascalCase)
2. Each function should have a descriptive name and URL in format: library.Class.method
3. Include ALL functions from the unified API spec
4. Use controlled-input and controlled-output: false unless explicitly stated
5. AUTHENTICATION must be exactly one of: none, apikey, oauth

## CRITICAL FORMAT RULES
- Do NOT output "DEFINE_API" prefix — the declaration starts directly with API_NAME<AUTH>
- Do NOT include [DEFINE_APIS:] or [END_APIS] wrapper tags
- Do NOT use literal "ApiName" — always use the actual API name from input
- The text inside < > must ONLY be none, apikey, or oauth

Output ONLY the API declaration, no markdown, no code fences."""


def _render_unified_api_user(api_json: str) -> str:
    """Render user prompt for unified API generation."""
    return f"""Generate a single API_DECLARATION for this specification:

## Unified API Specification (JSON)

{api_json}

## Output Format

Generate a single API declaration with multiple functions.
Use the api_name field from the JSON as the PascalCase API name.

Example (for a PDF reading API):

PdfReading<none>
{{ }}
{{
functions: [
    {{
        name: "OpenPdfFile",
        url: "pypdf.PdfReader",
        description: "Open a PDF file for reading",
        parameters: {{
            parameters: [
                {{required: true, name: "file_path", type: text}}
            ],
            controlled-input: false
        }},
        return: {{
            type: "PdfReader object",
            controlled-output: false
        }}
    }},
    ... (more functions)
    ]
}}

CRITICAL RULES:
- Start with the ACTUAL API name from the input (PascalCase), NOT "ApiName"
- Authentication inside < > must be exactly: none, apikey, or oauth
- Do NOT add "DEFINE_API" prefix
- Do NOT add [DEFINE_APIS:] or [END_APIS] wrapper tags
- Output ONLY the API declaration, nothing else."""


async def _generate_single_unified_api_async(
    client: LLMClient,
    unified_api: UnifiedAPISpec,
    model: Optional[str] = None,
) -> APISpec | None:
    """
    Async version: Generate DEFINE_API block for a single UnifiedAPISpec.
    """
    try:
        # Prepare unified API info as JSON for the LLM
        functions_json = []
        for func in unified_api.functions:
            func_info = {
                "name": func.name,
                "signature": func.signature,
                "description": func.description,
                "input_schema": func.input_schema,
                "output_schema": func.output_schema,
                "url": _generate_function_url(unified_api.primary_library, func.name),
            }
            functions_json.append(func_info)

        api_info = {
            "api_name": unified_api.api_name,
            "primary_library": unified_api.primary_library,
            "all_libraries": unified_api.all_libraries,
            "language": unified_api.language,
            "functions": functions_json,
            "combined_source": unified_api.combined_source[:2000],
        }
        api_json = json.dumps(api_info, indent=2, ensure_ascii=False)

        # Call LLM to generate DEFINE_API block (async)
        spl_text = await client.async_call(
            step_name="step1_5_unified_api_generation",
            system=_UNIFIED_API_SYSTEM_PROMPT,
            user=_render_unified_api_user(api_json),
            model=model,
        )

        # Parse I/O schemas
        input_params = _parse_input_schema(unified_api.functions[0].input_schema) if unified_api.functions else []
        output_params = _parse_output_schema(unified_api.functions[0].output_schema) if unified_api.functions else []

        return APISpec(
            name=unified_api.api_name,
            spl_text=spl_text,
            input_params=input_params,
            output_params=output_params,
            description=f"Unified API for {', '.join(unified_api.all_libraries)}",
        )

    except Exception as exc:
        logger.error("[Step 1.5 Unified] Error generating API for %s: %s", unified_api.api_name, exc)
        return None
