"""
Test for StepLLMConfig and per-step model override functionality.

Tests that:
1. StepLLMConfig correctly maps step names to models
2. LLMClient methods accept and use the model parameter
3. Step functions accept and propagate the model parameter
4. PipelineConfig accepts step_llm_config
"""

import pytest
from unittest.mock import MagicMock, patch, ANY

from pipeline.llm_client import LLMConfig, StepLLMConfig, LLMClient, SessionUsage
from pipeline.orchestrator import PipelineConfig, _step_model


class TestStepLLMConfig:
    """Tests for StepLLMConfig dataclass."""

    def test_empty_config_returns_default(self):
        """Empty StepLLMConfig should return the default model."""
        config = StepLLMConfig()
        assert config.get_model("step1", "gpt-4o") == "gpt-4o"
        assert config.get_model("step2", "claude-3") == "claude-3"

    def test_config_returns_override(self):
        """StepLLMConfig should return the override model for configured steps."""
        config = StepLLMConfig(step_models={
            "step1_structure_extraction": "gpt-4-turbo",
            "step3a_entity_extraction": "claude-3-opus",
        })
        assert config.get_model("step1_structure_extraction", "gpt-4o") == "gpt-4-turbo"
        assert config.get_model("step3a_entity_extraction", "gpt-4o") == "claude-3-opus"
        assert config.get_model("step4_spl_emission", "gpt-4o") == "gpt-4o"

    def test_partial_override(self):
        """Only configured steps should use overrides, others use default."""
        config = StepLLMConfig(step_models={
            "step1": "model-a",
        })
        assert config.get_model("step1", "default") == "model-a"
        assert config.get_model("step2", "default") == "default"
        assert config.get_model("step3", "default") == "default"


class TestPipelineConfigStepLLM:
    """Tests for PipelineConfig with step_llm_config."""

    def test_default_step_llm_config_is_none(self):
        """PipelineConfig should default step_llm_config to None."""
        config = PipelineConfig(skill_root="test/skill")
        assert config.step_llm_config is None

    def test_accepts_step_llm_config(self):
        """PipelineConfig should accept a StepLLMConfig."""
        step_config = StepLLMConfig(step_models={"step1": "model-x"})
        config = PipelineConfig(
            skill_root="test/skill",
            step_llm_config=step_config,
        )
        assert config.step_llm_config is step_config

    def test_step_model_helper_with_config(self):
        """_step_model should return the configured model for a step."""
        step_config = StepLLMConfig(step_models={
            "step1_structure_extraction": "gpt-4-turbo",
        })
        config = PipelineConfig(
            skill_root="test/skill",
            step_llm_config=step_config,
        )
        result = _step_model(config, "step1_structure_extraction")
        assert result == "gpt-4-turbo"

    def test_step_model_helper_without_config(self):
        """_step_model should return None when no step_llm_config is set."""
        config = PipelineConfig(skill_root="test/skill")
        result = _step_model(config, "step1_structure_extraction")
        assert result is None


class TestLLMClientModelParameter:
    """Tests for LLMClient methods accepting model parameter."""

    def test_call_uses_default_model_when_none(self):
        """call() should use config.model when model parameter is None."""
        llm_config = LLMConfig(model="gpt-4o")
        client = LLMClient(config=llm_config)
        
        with patch.object(client, '_client') as mock_client:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="test response"))]
            mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
            mock_client.chat.completions.create.return_value = mock_response
            
            client.call(step_name="test", system="system", user="user")
            
            call_kwargs = mock_client.chat.completions.create.call_args
            assert call_kwargs.kwargs["model"] == "gpt-4o"

    def test_call_uses_override_model(self):
        """call() should use the model parameter when provided."""
        llm_config = LLMConfig(model="gpt-4o")
        client = LLMClient(config=llm_config)
        
        with patch.object(client, '_client') as mock_client:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="test response"))]
            mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
            mock_client.chat.completions.create.return_value = mock_response
            
            client.call(step_name="test", system="system", user="user", model="gpt-4-turbo")
            
            call_kwargs = mock_client.chat.completions.create.call_args
            assert call_kwargs.kwargs["model"] == "gpt-4-turbo"

    def test_call_json_propagates_model(self):
        """call_json() should propagate model parameter to call()."""
        llm_config = LLMConfig(model="gpt-4o")
        client = LLMClient(config=llm_config)
        
        with patch.object(client, '_client') as mock_client:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content='{"result": "ok"}'))]
            mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
            mock_client.chat.completions.create.return_value = mock_response
            
            result = client.call_json(step_name="test", system="system", user="user", model="claude-3")
            
            call_kwargs = mock_client.chat.completions.create.call_args
            assert call_kwargs.kwargs["model"] == "claude-3"
            assert result == {"result": "ok"}


class TestStepFunctionModelParameter:
    """Tests for step functions accepting model parameter."""

    def test_step1_accepts_model_parameter(self):
        """run_step1_structure_extraction should accept model parameter."""
        from pipeline.llm_steps.step1_structure_extraction import run_step1_structure_extraction
        import inspect
        
        sig = inspect.signature(run_step1_structure_extraction)
        params = list(sig.parameters.keys())
        
        assert "model" in params, f"model parameter not found in {params}"
        assert sig.parameters["model"].default is None

    def test_step3a_accepts_model_parameter(self):
        """run_step3a_entity_extraction should accept model parameter."""
        from pipeline.llm_steps.step3_interface_inference import run_step3a_entity_extraction
        import inspect
        
        sig = inspect.signature(run_step3a_entity_extraction)
        params = list(sig.parameters.keys())
        
        assert "model" in params, f"model parameter not found in {params}"
        assert sig.parameters["model"].default is None

    def test_step3b_accepts_model_parameter(self):
        """run_step3b_workflow_analysis should accept model parameter."""
        from pipeline.llm_steps.step3_interface_inference import run_step3b_workflow_analysis
        import inspect
        
        sig = inspect.signature(run_step3b_workflow_analysis)
        params = list(sig.parameters.keys())
        
        assert "model" in params, f"model parameter not found in {params}"
        assert sig.parameters["model"].default is None

    def test_step3_structured_accepts_model_parameter(self):
        """run_step3_structured_extraction should accept model parameter."""
        from pipeline.llm_steps.step3_interface_inference import run_step3_structured_extraction
        import inspect
        
        sig = inspect.signature(run_step3_structured_extraction)
        params = list(sig.parameters.keys())
        
        assert "model" in params, f"model parameter not found in {params}"
        assert sig.parameters["model"].default is None

    def test_generate_api_definitions_accepts_model_parameter(self):
        """generate_api_definitions should accept model parameter."""
        from pipeline.llm_steps.step1_5_api_generation import generate_api_definitions
        import inspect
        
        sig = inspect.signature(generate_api_definitions)
        params = list(sig.parameters.keys())
        
        assert "model" in params, f"model parameter not found in {params}"
        assert sig.parameters["model"].default is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
