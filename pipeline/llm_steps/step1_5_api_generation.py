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
from concurrent.futures import ThreadPoolExecutor

from models.data_models import APISpec, APISymbolTable, ToolSpec
from pipeline.llm_client import LLMClient
from prompts import templates

logger = logging.getLogger(__name__)


def generate_api_definitions(
    tools: list[ToolSpec],
    client: LLMClient,
    max_workers: int = 4,
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
            tool.name: pool.submit(_generate_single_api, client, tool)
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


def _generate_single_api(client: LLMClient, tool: ToolSpec) -> APISpec | None:
    """
    Generate DEFINE_API block for a single tool.

    Args:
        client: LLM client
        tool: ToolSpec with name, input_schema, output_schema, etc.

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

async def _generate_single_api_async(client: LLMClient, tool: ToolSpec) -> APISpec | None:
    """
    Async version: Generate DEFINE_API block for a single tool.
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
    """
    Merge all API SPL blocks into a single DEFINE_APIS block.

    Args:
        api_table: APISymbolTable with all generated APIs

    Returns:
        Combined DEFINE_APIS block text for S4D output
    """
    if not api_table.apis:
        return ""

    parts = ["[DEFINE_APIS:]"]
    for name, spec in api_table.apis.items():
        parts.append(spec.spl_text)
    parts.append("[END_APIS]")

    return "\n\n".join(parts)
