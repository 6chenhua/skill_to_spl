"""
Step 1: Structure Extraction

Parse the assembled skill package into 8 canonical sections.
All text is copied verbatim from source. Nothing is dropped.

Also extracts network APIs from TOOLS section and converts them to ToolSpec objects.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from models.data_models import SectionBundle, SectionItem, SkillPackage, ToolSpec
from pipeline.llm_client import LLMClient
from prompts import templates

logger = logging.getLogger(__name__)

_SECTION_KEYS = ["INTENT", "WORKFLOW", "CONSTRAINTS", "TOOLS",
"ARTIFACTS", "EVIDENCE", "EXAMPLES", "NOTES"]


def run_step1_structure_extraction(
    package: SkillPackage,
    client: LLMClient,
) -> tuple[SectionBundle, list[ToolSpec]]:
    """
    Step 1: Parse the assembled skill package into 8 canonical sections.
    All text is copied verbatim from source. Nothing is dropped.

    Also extracts network APIs from TOOLS section and converts them to ToolSpec objects.

    Returns:
    Tuple of (SectionBundle with verbatim items per section, list of ToolSpec from network APIs).
    """
    user_prompt = templates.render_step1_user(
        merged_doc_text=package.merged_doc_text,
    )

    raw = client.call_json(
        step_name="step1_structure_extraction",
        system=templates.STEP1_SYSTEM,
        user=user_prompt,
    )

    bundle = _parse_section_bundle(raw)
    total = sum(len(getattr(bundle, s.lower())) for s in _SECTION_KEYS)
    logger.info("[Step 1] extracted %d items across all sections", total)

    # Extract network APIs from TOOLS section
    network_apis = _extract_network_apis(bundle.tools)
    logger.info("[Step 1] extracted %d network APIs from TOOLS section", len(network_apis))

    return bundle, network_apis


def _extract_network_apis(tools_items: list[SectionItem]) -> list[ToolSpec]:
    """
    Extract network APIs from TOOLS section items.

    TOOLS section may contain:
    1. JSON array of ToolSpec objects (preferred format)
    2. Plain text descriptions of APIs

    This function tries to parse as JSON first, then falls back to text extraction.
    """
    network_apis = []

    for item in tools_items:
        # Try to parse as JSON first
        try:
            # Check if the text looks like JSON (starts with [ or {)
            text = item.text.strip()
            if text.startswith('[') or text.startswith('{'):
                data = json.loads(text)
                if isinstance(data, list):
                    # Array of ToolSpec objects
                    for obj in data:
                        if isinstance(obj, dict) and obj.get("api_type") == "NETWORK_API":
                            tool = _parse_tool_spec(obj)
                            if tool:
                                network_apis.append(tool)
                elif isinstance(data, dict):
                    # Single ToolSpec object
                    if data.get("api_type") == "NETWORK_API":
                        tool = _parse_tool_spec(data)
                        if tool:
                            network_apis.append(tool)
                continue  # Successfully parsed as JSON, move to next item
        except json.JSONDecodeError:
            pass

        # Fall back to text-based extraction for non-JSON tool descriptions
        # This handles cases where tools are described in plain text
        api = _extract_api_from_text(item.text, item.source)
        if api:
            network_apis.append(api)

    return network_apis


def _parse_tool_spec(data: dict) -> Optional[ToolSpec]:
    """Parse a dictionary into a ToolSpec object."""
    try:
        return ToolSpec(
            name=data.get("name", ""),
            api_type=data.get("api_type", "NETWORK_API"),
            url=data.get("url", ""),
            authentication=data.get("authentication", "none"),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", "void"),
            description=data.get("description", ""),
            source_text=data.get("source_text", ""),
        )
    except Exception as e:
        logger.warning(f"Failed to parse ToolSpec: {e}")
        return None


def _extract_api_from_text(text: str, source: str) -> Optional[ToolSpec]:
    """
    Extract network API information from plain text descriptions.

    This is a fallback for when TOOLS section contains text rather than JSON.
    Looks for patterns like:
    - "API: name - description"
    - "Endpoint: url"
    - "Uses: authentication"
    """
    # Pattern to match API descriptions
    # Example: "GitHub API - Interact with GitHub repositories"
    api_pattern = r'([A-Z][a-zA-Z\s]+API|[A-Z][a-zA-Z]+)\s*[-–]\s*(.+)'
    match = re.search(api_pattern, text)

    if match:
        name = match.group(1).strip()
        description = match.group(2).strip()

        # Look for URL patterns
        url_pattern = r'https?://[^\s]+'
        url_match = re.search(url_pattern, text)
        url = url_match.group(0) if url_match else ""

        # Look for authentication
        auth_pattern = r'(API key|OAuth| Bearer|token|authentication)'
        authentication = "apikey" if re.search(auth_pattern, text, re.IGNORECASE) else "none"

        return ToolSpec(
            name=name,
            api_type="NETWORK_API",
            url=url,
            authentication=authentication,
            input_schema={},
            output_schema="void",
            description=description,
            source_text=text,
        )

    return None


def _parse_section_bundle(raw: dict) -> SectionBundle:
    """Convert the LLM JSON response into a typed SectionBundle."""
    def parse_items(key: str) -> list[SectionItem]:
        items = raw.get(key, raw.get(key.lower(), []))
        result = []
        for item in items:
            if isinstance(item, dict):
                result.append(SectionItem(
                    text=item.get("text", ""),
                    source=item.get("source", "unknown"),
                    multi=item.get("multi", False),
                ))
            elif isinstance(item, str):
                result.append(SectionItem(text=item, source="unknown"))
        return result

    return SectionBundle(
        intent=parse_items("INTENT"),
        workflow=parse_items("WORKFLOW"),
        constraints=parse_items("CONSTRAINTS"),
        tools=parse_items("TOOLS"),
        artifacts=parse_items("ARTIFACTS"),
        evidence=parse_items("EVIDENCE"),
        examples=parse_items("EXAMPLES"),
        notes=parse_items("NOTES"),
    )