"""
CLI entry point for the skill-to-CNL-P pipeline.

Usage:
    python -m skill_to_cnlp.cli <skill_root> [OPTIONS]

Examples:
    # Normalize a single skill
    python -m skill_to_cnlp.cli skills/pdf/

    # Specify output directory and enable verbose logging
    python -m skill_to_cnlp.cli skills/pdf/ --output-dir ./out --verbose

    # Pass a capability profile (JSON file) for environment-aware classification
    python -m skill_to_cnlp.cli skills/pdf/ --capability-profile profiles/github.json

    # Use a specific model
    python -m skill_to_cnlp.cli skills/pdf/ --model claude-opus-4-20250514
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from pipeline.llm_client import LLMConfig
from pipeline.orchestrator import PipelineConfig, run_pipeline


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill_to_cnlp",
        description="Normalize a skill package into an SPL specification.",
    )
    parser.add_argument(
        "skill_root",
        help="Path to the skill directory (must contain SKILL.md).",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="Output directory. Defaults to <skill_root>/.cnlp_output/",
    )
    parser.add_argument(
        "--model", "-m",
        default="claude-sonnet-4-20250514",
        help="Anthropic model ID to use for all LLM steps.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=8192,
        help="Maximum tokens per LLM response.",
    )
    parser.add_argument(
        "--capability-profile",
        default=None,
        help=(
            "Path to a JSON file describing the runtime environment's available "
            "effects. Used for Step 2B environment-aware classification. "
            'Expected shape: {"available_effects": ["READ", "EXEC", ...]}'
        ),
    )
    parser.add_argument(
        "--no-checkpoints",
        action="store_true",
        default=False,
        help="Disable saving intermediate stage outputs to disk.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable DEBUG-level logging.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser  = _build_arg_parser()
    args    = parser.parse_args(argv)

    # ── Logging setup ─────────────────────────────────────────────────────────
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── Validate skill_root ───────────────────────────────────────────────────
    skill_root = Path(args.skill_root).resolve()
    if not skill_root.exists():
        print(f"ERROR: skill_root not found: {skill_root}", file=sys.stderr)
        return 1
    if not (skill_root / "SKILL.md").exists():
        print(f"ERROR: no SKILL.md in {skill_root}", file=sys.stderr)
        return 1

    # ── Capability profile ────────────────────────────────────────────────────
    capability_profile = None
    if args.capability_profile:
        profile_path = Path(args.capability_profile)
        if not profile_path.exists():
            print(f"ERROR: capability profile not found: {profile_path}", file=sys.stderr)
            return 1
        with open(profile_path, encoding="utf-8") as fh:
            capability_profile = json.load(fh)

    # ── Build config ──────────────────────────────────────────────────────────
    llm_config = LLMConfig(
        model=args.model,
        max_tokens=args.max_tokens,
    )
    config = PipelineConfig(
        skill_root=str(skill_root),
        output_dir=args.output_dir,
        llm_config=llm_config,
        capability_profile=capability_profile,
        save_checkpoints=not args.no_checkpoints,
    )

    # ── Run ───────────────────────────────────────────────────────────────────
    try:
        result = run_pipeline(config)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        logging.exception("Pipeline failed: %s", exc)
        return 2

    # ── Summary ───────────────────────────────────────────────────────────────
    counts = result.spl_spec.clause_counts
    print(
        f"\n✅  {result.skill_id}  →  "
        f"HARD={counts.get('COMPILABLE_HARD', 0)}  "
        f"MEDIUM={counts.get('COMPILABLE_MEDIUM', 0)}  "
        f"SOFT={counts.get('COMPILABLE_SOFT', 0)}  "
        f"NON={counts.get('NON_COMPILABLE', 0)}"
    )
    if result.needs_review_count:
        print(f"⚠️   {result.needs_review_count} clause(s) flagged NEEDS_REVIEW")
    output_dir = config.output_dir or str(skill_root / ".cnlp_output")
    print(f"📄  output → {output_dir}/{result.skill_id}.spl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
