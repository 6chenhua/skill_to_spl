"""
Step 1: Structure Extraction

Parse the assembled skill package into 8 canonical sections.
All text is copied verbatim from source. Nothing is dropped.
"""

from __future__ import annotations

import logging
from typing import Any

from models.data_models import SectionBundle, SectionItem, SkillPackage
from pipeline.llm_client import LLMClient
from prompts import templates

logger = logging.getLogger(__name__)

_SECTION_KEYS = ["INTENT", "WORKFLOW", "CONSTRAINTS", "TOOLS",
                 "ARTIFACTS", "EVIDENCE", "EXAMPLES", "NOTES"]


def run_step1_structure_extraction(
    package: SkillPackage,
    client: LLMClient,
) -> SectionBundle:
    """
    Step 1: Parse the assembled skill package into 8 canonical sections.
    All text is copied verbatim from source. Nothing is dropped.

    Returns:
        SectionBundle with verbatim items per section.
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
    return bundle


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
