"""
Demo script for the simplified pipeline.

This script demonstrates how to use the simplified pipeline
to process merged_doc_text directly and generate SPL output.
"""

import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simplified_pipeline.orchestrator import run_pipeline, PipelineConfig
from simplified_pipeline.llm_client import LLMConfig


def main():
    """Run the simplified pipeline demo with direct text input."""
    with open('input/智能调度系统.txt', 'r', encoding='utf-8') as f:
        merged_doc_text = f.read()

    # Configure pipeline
    print("Configuring pipeline...")
    llm_config = LLMConfig(
        model="gpt-4o",
    )

    config = PipelineConfig(
        merged_doc_text=merged_doc_text,
        skill_id="sample_skill",
        output_dir="output/sample_simplified",
        llm_config=llm_config,
        save_checkpoints=True,
        enable_clarification=True,
    )
    print(f"Output directory: {config.output_dir}")
    print()

    # Run pipeline
    print("Running simplified pipeline...")
    print("-" * 70)

    try:
        result = run_pipeline(config)

        print("-" * 70)
        print()
        print("SUCCESS! Pipeline completed.")
        print()
        print(f"Skill ID: {result.skill_id}")
        print(
            f"Section Bundle sections: {len([s for s in [result.section_bundle.intent, result.section_bundle.workflow, result.section_bundle.constraints, result.section_bundle.examples, result.section_bundle.notes] if s])}")
        print(f"Variables extracted: {len(result.structured_spec.variables)}")
        print(f"Workflow steps: {len(result.structured_spec.workflow_steps)}")
        print(f"Alternative flows: {len(result.structured_spec.alternative_flows)}")
        print(f"Exception flows: {len(result.structured_spec.exception_flows)}")
        print()
        print("Generated SPL:")
        print("=" * 70)
        print(result.spl_spec.spl_text)
        print("=" * 70)
        print()
        print(f"Output written to: {config.output_dir}/{result.skill_id}.spl")

        return 0

    except Exception as e:
        print("-" * 70)
        print()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())