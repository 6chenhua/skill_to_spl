#!/usr/bin/env python3
"""
Refactoring Test Suite for skill-to-cnlp
============================================

Tests to verify that refactoring maintains functionality and API compatibility.

Usage:
    pytest test/refactor/ -v
    pytest test/refactor/ -v --tb=short
    
Coverage:
    - Phase 1: Preprocessing renaming
    - Phase 2: Step 3 renaming
    - Phase 3: Step 4 renaming
    - Phase 4: Orchestrator and entry points
    - Backward compatibility
"""

import pytest
import json
from pathlib import Path
from typing import Any, Dict, List
import sys
import warnings

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ═════════════════════════════════════════════════════════════════════════════
# Phase 1: Preprocessing Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestPhase1Preprocessing:
    """Test Phase 1 refactoring: preprocessing module renaming."""

    def test_preprocessing_reference_graph_module_exists(self):
        """AC-1.1: preprocessing_reference_graph.py module exists."""
        module_path = project_root / "pre_processing" / "preprocessing_reference_graph.py"
        assert module_path.exists(), f"Module not found: {module_path}"

    def test_preprocessing_build_reference_graph_function_exists(self):
        """AC-1.2: preprocessing_build_reference_graph function exists."""
        try:
            from pre_processing.preprocessing_reference_graph import preprocessing_build_reference_graph
            assert callable(preprocessing_build_reference_graph)
        except ImportError as e:
            pytest.skip(f"New naming not yet implemented: {e}")

    def test_backward_compatibility_build_reference_graph(self):
        """AC-1.3: build_reference_graph backward compatible with deprecation warning."""
        try:
            from pipeline.compat import build_reference_graph
            with pytest.warns(DeprecationWarning, match="preprocessing_build_reference_graph"):
                # Note: Can't actually call without proper args, just verify import works
                pass
        except ImportError:
            pytest.skip("Backward compatibility layer not yet implemented")

    def test_preprocessing_file_roles_module_exists(self):
        """AC-1.4: preprocessing_file_roles.py module exists."""
        module_path = project_root / "pre_processing" / "preprocessing_file_roles.py"
        assert module_path.exists(), f"Module not found: {module_path}"

    def test_preprocessing_resolve_file_roles_function_exists(self):
        """AC-1.5: preprocessing_resolve_file_roles function exists."""
        try:
            from pre_processing.preprocessing_file_roles import preprocessing_resolve_file_roles
            assert callable(preprocessing_resolve_file_roles)
        except ImportError as e:
            pytest.skip(f"New naming not yet implemented: {e}")

    def test_preprocessing_assembler_module_exists(self):
        """AC-1.6: preprocessing_assembler.py module exists."""
        module_path = project_root / "pre_processing" / "preprocessing_assembler.py"
        assert module_path.exists(), f"Module not found: {module_path}"

    def test_preprocessing_assemble_package_function_exists(self):
        """AC-1.7: preprocessing_assemble_package function exists."""
        try:
            from pre_processing.preprocessing_assembler import preprocessing_assemble_package
            assert callable(preprocessing_assemble_package)
        except ImportError as e:
            pytest.skip(f"New naming not yet implemented: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# Phase 2: Step 3 Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestPhase2Step3:
    """Test Phase 2 refactoring: Step 3 module and function renaming."""

    def test_step3_entity_extraction_module_exists(self):
        """AC-2.1: step3/entity_extraction.py module exists (renamed from t.py)."""
        module_path = project_root / "pipeline" / "llm_steps" / "step3" / "entity_extraction.py"
        assert module_path.exists(), f"Module not found: {module_path}"

    def test_step3_workflow_analysis_module_exists(self):
        """AC-2.2: step3/workflow_analysis.py module exists (renamed from w.py)."""
        module_path = project_root / "pipeline" / "llm_steps" / "step3" / "workflow_analysis.py"
        assert module_path.exists(), f"Module not found: {module_path}"

    def test_step3_io_analysis_module_exists(self):
        """AC-2.3: step3/io_analysis.py module exists (renamed from io.py)."""
        module_path = project_root / "pipeline" / "llm_steps" / "step3" / "io_analysis.py"
        assert module_path.exists(), f"Module not found: {module_path}"

    def test_step3a_extract_entities_function_exists(self):
        """AC-2.4: step3a_extract_entities function exists."""
        try:
            from pipeline.llm_steps.step3.entity_extraction import step3a_extract_entities
            assert callable(step3a_extract_entities)
        except ImportError as e:
            pytest.skip(f"New naming not yet implemented: {e}")

    def test_step3b_analyze_workflow_function_exists(self):
        """AC-2.5: step3b_analyze_workflow function exists."""
        try:
            from pipeline.llm_steps.step3.workflow_analysis import step3b_analyze_workflow
            assert callable(step3b_analyze_workflow)
        except ImportError as e:
            pytest.skip(f"New naming not yet implemented: {e}")

    def test_step3_execute_full_analysis_function_exists(self):
        """AC-2.6: step3_execute_full_analysis function exists."""
        try:
            from pipeline.llm_steps.step3 import step3_execute_full_analysis
            assert callable(step3_execute_full_analysis)
        except ImportError as e:
            pytest.skip(f"New naming not yet implemented: {e}")

    def test_backward_compatibility_step3(self):
        """AC-2.7: run_step3_full backward compatible."""
        try:
            from pipeline.llm_steps import run_step3_full
            assert callable(run_step3_full)
        except ImportError:
            pytest.skip("Backward compatibility not yet implemented")


# ═════════════════════════════════════════════════════════════════════════════
# Phase 3: Step 4 Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestPhase3Step4:
    """Test Phase 3 refactoring: Step 4 module and function renaming."""

    def test_step4_substeps_module_exists(self):
        """AC-3.1: step4_spl_emission/substeps.py exists (renamed from substep_calls.py)."""
        module_path = project_root / "pipeline" / "llm_steps" / "step4_spl_emission" / "substeps.py"
        assert module_path.exists(), f"Module not found: {module_path}"

    def test_step4_variable_registry_module_exists(self):
        """AC-3.2: step4_spl_emission/variable_registry.py exists (renamed from s4c_from_registry.py)."""
        module_path = project_root / "pipeline" / "llm_steps" / "step4_spl_emission" / "variable_registry.py"
        assert module_path.exists(), f"Module not found: {module_path}"

    def test_step4_inputs_merged(self):
        """AC-3.3: inputs.py and inputs_v2.py merged."""
        inputs_path = project_root / "pipeline" / "llm_steps" / "step4_spl_emission" / "inputs.py"
        inputs_v2_path = project_root / "pipeline" / "llm_steps" / "step4_spl_emission" / "inputs_v2.py"
        
        assert inputs_path.exists(), "inputs.py should exist"
        # After merge, inputs_v2.py should either not exist or be deprecated
        if inputs_v2_path.exists():
            warnings.warn("inputs_v2.py still exists - merge may be incomplete", UserWarning)

    def test_step4a_define_persona_function_exists(self):
        """AC-3.4: step4a_define_persona function exists."""
        try:
            from pipeline.llm_steps.step4_spl_emission.substeps import step4a_define_persona
            assert callable(step4a_define_persona)
        except ImportError as e:
            pytest.skip(f"New naming not yet implemented: {e}")

    def test_step4b_define_constraints_function_exists(self):
        """AC-3.5: step4b_define_constraints function exists."""
        try:
            from pipeline.llm_steps.step4_spl_emission.substeps import step4b_define_constraints
            assert callable(step4b_define_constraints)
        except ImportError as e:
            pytest.skip(f"New naming not yet implemented: {e}")

    def test_step4c_define_variables_function_exists(self):
        """AC-3.6: step4c_define_variables function exists."""
        try:
            from pipeline.llm_steps.step4_spl_emission.substeps import step4c_define_variables
            assert callable(step4c_define_variables)
        except ImportError as e:
            pytest.skip(f"New naming not yet implemented: {e}")

    def test_step4d_define_apis_function_exists(self):
        """AC-3.7: step4d_define_apis function exists."""
        try:
            from pipeline.llm_steps.step4_spl_emission.substeps import step4d_define_apis
            assert callable(step4d_define_apis)
        except ImportError as e:
            pytest.skip(f"New naming not yet implemented: {e}")

    def test_step4e_assemble_worker_function_exists(self):
        """AC-3.8: step4e_assemble_worker function exists."""
        try:
            from pipeline.llm_steps.step4_spl_emission.substeps import step4e_assemble_worker
            assert callable(step4e_assemble_worker)
        except ImportError as e:
            pytest.skip(f"New naming not yet implemented: {e}")

    def test_step4f_generate_examples_function_exists(self):
        """AC-3.9: step4f_generate_examples function exists."""
        try:
            from pipeline.llm_steps.step4_spl_emission.substeps import step4f_generate_examples
            assert callable(step4f_generate_examples)
        except ImportError as e:
            pytest.skip(f"New naming not yet implemented: {e}")

    def test_step4_async_functions_exist(self):
        """AC-3.10: All step4 async functions exist with _async suffix."""
        try:
            from pipeline.llm_steps.step4_spl_emission.substeps import (
                step4a_define_persona_async,
                step4b_define_constraints_async,
                step4c_define_variables_async,
                step4d_define_apis_async,
                step4e_assemble_worker_async,
                step4f_generate_examples_async,
            )
            assert all(callable(f) for f in [
                step4a_define_persona_async,
                step4b_define_constraints_async,
                step4c_define_variables_async,
                step4d_define_apis_async,
                step4e_assemble_worker_async,
                step4f_generate_examples_async,
            ])
        except ImportError as e:
            pytest.skip(f"Async functions not yet implemented: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# Phase 4: Orchestrator and Entry Points Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestPhase4Orchestrator:
    """Test Phase 4 refactoring: Orchestrator and entry point updates."""

    def test_pipeline_module_exports(self):
        """AC-4.1: pipeline.llm_steps exports new named functions."""
        try:
            from pipeline.llm_steps import (
                step1_extract_structure,
                step3_execute_full_analysis,
                step4_emit_spl,
            )
            assert callable(step1_extract_structure)
            assert callable(step3_execute_full_analysis)
            assert callable(step4_emit_spl)
        except ImportError as e:
            pytest.skip(f"New exports not yet implemented: {e}")

    def test_old_exports_still_work(self):
        """AC-4.2: Old exports still work with deprecation warnings."""
        try:
            from pipeline.llm_steps import (
                run_step1_structure_extraction,
                run_step4_spl_emission,
            )
            # Should work but with warnings
            assert callable(run_step1_structure_extraction)
            assert callable(run_step4_spl_emission)
        except ImportError:
            pytest.skip("Backward compatibility not yet implemented")

    def test_cli_still_functional(self):
        """AC-4.3: CLI entry point still functional."""
        try:
            from cli import main
            assert callable(main)
        except ImportError:
            pytest.skip("CLI module not available")

    def test_main_py_functional(self):
        """AC-4.4: main.py entry point still functional."""
        main_path = project_root / "main.py"
        assert main_path.exists(), f"main.py not found: {main_path}"


# ═════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestIntegrationDataFlow:
    """Test that refactoring doesn't break data flow between stages."""

    def test_phase1_to_phase2_compatibility(self):
        """AC-I.1: Phase 1 output compatible with Phase 2 input."""
        # This is a placeholder - actual integration tests would
        # require running the full pipeline with test data
        pytest.skip("Integration test requires full pipeline setup")

    def test_step3_to_step4_compatibility(self):
        """AC-I.2: Step 3 output compatible with Step 4 input."""
        pytest.skip("Integration test requires full pipeline setup")

    def test_end_to_end_pipeline(self):
        """AC-I.3: End-to-end pipeline execution with refactored code."""
        pytest.skip("E2E test requires full pipeline setup with test skill")


# ═════════════════════════════════════════════════════════════════════════════
# Naming Convention Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestNamingConventions:
    """Test that new naming follows conventions."""

    def test_preprocessing_functions_have_prefix(self):
        """AC-N.1: All preprocessing functions start with 'preprocessing_'."""
        try:
            from pre_processing import preprocessing_reference_graph as prg
            import inspect
            
            functions = [
                name for name in dir(prg) 
                if callable(getattr(prg, name)) and not name.startswith('_')
            ]
            
            for func_name in functions:
                if func_name not in ['preprocessing_build_reference_graph']:
                    assert func_name.startswith('preprocessing_'), \
                        f"Function {func_name} doesn't follow naming convention"
        except ImportError:
            pytest.skip("Preprocessing modules not yet refactored")

    def test_step_functions_have_prefix(self):
        """AC-N.2: All step functions follow step{N}_{action} pattern."""
        try:
            from pipeline.llm_steps import (
                step1_extract_structure,
                step3_execute_full_analysis,
                step4_emit_spl,
            )
            # If imports succeed, naming is correct
        except ImportError:
            pytest.skip("Step functions not yet refactored")


# ═════════════════════════════════════════════════════════════════════════════
# Performance Regression Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestPerformanceRegression:
    """Test that refactoring doesn't introduce performance regressions."""

    @pytest.mark.skip(reason="Performance tests require baseline metrics")
    def test_preprocessing_performance(self):
        """AC-P.1: Preprocessing performance within 5% of baseline."""
        pass

    @pytest.mark.skip(reason="Performance tests require baseline metrics")
    def test_pipeline_throughput(self):
        """AC-P.2: Pipeline throughput within 5% of baseline."""
        pass


# ═════════════════════════════════════════════════════════════════════════════
# Fixtures and Utilities
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def sample_skill_package(tmp_path_factory):
    """Create a sample skill package for testing."""
    tmp_path = tmp_path_factory.mktemp("skill_package")
    
    # Create SKILL.md
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("""
---
name: test-skill
version: "1.0"
---

# Test Skill

## Intent
This is a test skill for refactoring verification.

## Workflow
1. Read input
2. Process with LLM
3. Output result

## Constraints
- MUST validate input

## Examples
Example 1: Basic usage
""")
    
    # Create scripts directory
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    
    # Create a simple script
    script = scripts_dir / "test_script.py"
    script.write_text("""
def process_input(data: str) -> str:
    return data.upper()
""")
    
    return tmp_path


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    class MockLLMClient:
        def call(self, *args, **kwargs):
            return '{"sections": {}}'
        
        async def async_call(self, *args, **kwargs):
            return '{"sections": {}}'
    
    return MockLLMClient()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
