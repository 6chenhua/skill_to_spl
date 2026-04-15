"""Worker nesting validation and fixing for Step 4."""

from __future__ import annotations

import json
import logging

from pipeline.llm_client import LLMClient
from prompts import templates

logger = logging.getLogger(__name__)


async def _call_4e1_async(client: LLMClient, worker_spl: str, model: str | None = None) -> dict:
    """Detect illegal nested BLOCK structures in WORKER SPL.

    Returns a dict with:
    - has_violations: bool
    - violations: list of violation dicts
    """
    s4e1_user = templates.render_s4e1_user(worker_spl=worker_spl)
    response = await client.async_call(
        step_name="step4e1_nesting_detection",
        system=templates.S4E1_SYSTEM,
        user=s4e1_user,
        model=model,
    )

    # Parse JSON response (handle markdown code blocks)
    try:
        # Strip markdown fences if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Remove opening fence
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        result = json.loads(cleaned)
        return result
    except json.JSONDecodeError as e:
        logger.warning("[Step 4E1] Failed to parse JSON response: %s", e)
        logger.debug("[Step 4E1] Raw response:\n%s", response[:500])
        return {"has_violations": False, "violations": []}


async def _call_4e2_async(client: LLMClient, worker_spl: str, violations: list, model: str | None = None) -> str:
    """Fix illegal nested BLOCK structures by flattening.

    Returns the corrected WORKER SPL text.
    """
    violations_json = json.dumps(violations, indent=2, ensure_ascii=False)
    s4e2_user = templates.render_s4e2_user(
        worker_spl=worker_spl,
        violations_json=violations_json,
    )
    return await client.async_call(
        step_name="step4e2_nesting_fix",
        system=templates.S4E2_SYSTEM,
        user=s4e2_user,
        model=model,
    )


async def validate_and_fix_worker_nesting_async(client: LLMClient, worker_spl: str, model: str | None = None) -> tuple[str, dict]:
    """Validate and fix nested BLOCK structures in WORKER SPL.

    Args:
        client: LLM client for making calls
        worker_spl: The generated WORKER SPL text
        model: Optional model override for LLM calls

    Returns:
        Tuple of (corrected_worker_spl, detection_result)
        - corrected_worker_spl: The fixed SPL (or original if no violations)
        - detection_result: The full S4E1 detection result dict
    """
    logger.info("[Step 4E.1] Checking for illegal BLOCK nesting...")
    detection_result = await _call_4e1_async(client, worker_spl, model=model)

    if detection_result.get("has_violations", False):
        violations = detection_result.get("violations", [])
        logger.warning(
            "[Step 4E.1] Found %d nested BLOCK violations, fixing...",
            len(violations)
        )
        for v in violations:
            logger.debug(
                " - %s inside %s: %s",
                v.get("inner_block", "?"),
                v.get("outer_block", "?"),
                v.get("snippet", "")[:50]
            )

        logger.info("[Step 4E.2] Fixing nested BLOCK structures...")
        fixed_spl = await _call_4e2_async(client, worker_spl, violations, model=model)
        return fixed_spl, detection_result
    else:
        logger.info("[Step 4E.1] No nested BLOCK violations found")
        return worker_spl, detection_result


def validate_and_fix_worker_nesting(client: LLMClient, worker_spl: str, model: str | None = None) -> tuple[str, dict]:
    """Validate and fix nested BLOCK structures in WORKER SPL (sync version).

    Args:
        client: LLM client for making calls
        worker_spl: The generated WORKER SPL text
        model: Optional model override for LLM calls

    Returns:
        Tuple of (corrected_worker_spl, detection_result)
        - corrected_worker_spl: The fixed SPL (or original if no violations)
        - detection_result: The full S4E1 detection result dict
    """
    logger.info("[Step 4E.1] Checking for illegal BLOCK nesting...")

    s4e1_user = templates.render_s4e1_user(worker_spl=worker_spl)
    response = client.call(
        step_name="step4e1_nesting_detection",
        system=templates.S4E1_SYSTEM,
        user=s4e1_user,
        model=model,
    )

    # Parse JSON response (handle markdown code blocks)
    try:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        detection_result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("[Step 4E1] Failed to parse JSON response: %s", e)
        logger.debug("[Step 4E1] Raw response:\n%s", response[:500])
        detection_result = {"has_violations": False, "violations": []}

    if detection_result.get("has_violations", False):
        violations = detection_result.get("violations", [])
        logger.warning(
            "[Step 4E.1] Found %d nested BLOCK violations, fixing...",
            len(violations)
        )
        for v in violations:
            logger.debug(
                " - %s inside %s: %s",
                v.get("inner_block", "?"),
                v.get("outer_block", "?"),
                v.get("snippet", "")[:50]
            )

        logger.info("[Step 4E.2] Fixing nested BLOCK structures...")

        violations_json = json.dumps(violations, indent=2, ensure_ascii=False)
        s4e2_user = templates.render_s4e2_user(
            worker_spl=worker_spl,
            violations_json=violations_json,
        )
        fixed_spl = client.call(
            step_name="step4e2_nesting_fix",
            system=templates.S4E2_SYSTEM,
            user=s4e2_user,
            model=model,
        )
        return fixed_spl, detection_result
    else:
        logger.info("[Step 4E.1] No nested BLOCK violations found")
        return worker_spl, detection_result
