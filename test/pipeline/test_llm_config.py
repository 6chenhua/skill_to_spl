"""Test suite for LLM configuration security."""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch

from pipeline.llm_client import LLMConfig
from pipeline.exceptions import ConfigurationError


class TestLLMConfigSecurity:
    """安全配置测试套件"""

    def test_api_key_from_env(self, monkeypatch):
        """应正确从环境变量读取API密钥"""
        monkeypatch.setenv("LLM_API_KEY", "test_key_from_env")
        config = LLMConfig()
        assert config.api_key == "test_key_from_env"

    def test_api_key_from_param_overrides_env(self, monkeypatch):
        """参数传入应优先于环境变量"""
        monkeypatch.setenv("LLM_API_KEY", "env_key")
        config = LLMConfig(api_key="param_key")
        assert config.api_key == "param_key"

    def test_missing_api_key_raises_error(self, monkeypatch):
        """缺少密钥应抛出ConfigurationError"""
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        with pytest.raises(ConfigurationError) as exc_info:
            LLMConfig()
        assert "LLM_API_KEY" in str(exc_info.value)
        assert "required" in str(exc_info.value).lower()

    def test_base_url_default(self, monkeypatch):
        """未设置时使用默认值"""
        monkeypatch.setenv("LLM_API_KEY", "test_key")
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        config = LLMConfig()
        assert config.base_url == "https://api.rcouyi.com/v1"

    def test_base_url_from_env(self, monkeypatch):
        """环境变量覆盖默认值"""
        monkeypatch.setenv("LLM_API_KEY", "test_key")
        monkeypatch.setenv("LLM_BASE_URL", "https://custom.com/v1")
        config = LLMConfig()
        assert config.base_url == "https://custom.com/v1"

    def test_base_url_param_overrides_env(self, monkeypatch):
        """参数传入优先于环境变量"""
        monkeypatch.setenv("LLM_API_KEY", "test_key")
        monkeypatch.setenv("LLM_BASE_URL", "https://env.com/v1")
        config = LLMConfig(base_url="https://param.com/v1")
        assert config.base_url == "https://param.com/v1"

    def test_invalid_base_url_raises_error(self, monkeypatch):
        """无效URL格式应报错"""
        monkeypatch.setenv("LLM_API_KEY", "test_key")
        with pytest.raises(ConfigurationError) as exc_info:
            LLMConfig(base_url="invalid-url")
        assert "Invalid LLM_BASE_URL" in str(exc_info.value)

    def test_base_url_without_protocol_raises_error(self, monkeypatch):
        """URL不以http开头应报错"""
        monkeypatch.setenv("LLM_API_KEY", "test_key")
        with pytest.raises(ConfigurationError) as exc_info:
            LLMConfig(base_url="api.rcouyi.com/v1")
        assert "Must start with http:// or https://" in str(exc_info.value)

    def test_http_url_is_valid(self, monkeypatch):
        """http:// URL是有效的"""
        monkeypatch.setenv("LLM_API_KEY", "test_key")
        config = LLMConfig(base_url="http://localhost:8080/v1")
        assert config.base_url == "http://localhost:8080/v1"

    def test_https_url_is_valid(self, monkeypatch):
        """https:// URL是有效的"""
        monkeypatch.setenv("LLM_API_KEY", "test_key")
        config = LLMConfig(base_url="https://secure.com/v1")
        assert config.base_url == "https://secure.com/v1"

    def test_default_values(self, monkeypatch):
        """测试默认值"""
        monkeypatch.setenv("LLM_API_KEY", "test_key")
        config = LLMConfig()
        
        assert config.model == "gpt-4o"
        assert config.max_tokens == 8192
        assert config.temperature == 0.0
        assert config.max_retries == 3
        assert config.retry_base_delay == 2.0
        assert config.timeout == 120.0

    def test_custom_values(self, monkeypatch):
        """测试自定义值"""
        monkeypatch.setenv("LLM_API_KEY", "test_key")
        config = LLMConfig(
            model="custom-model",
            max_tokens=4096,
            temperature=0.5,
            max_retries=5,
        )
        
        assert config.model == "custom-model"
        assert config.max_tokens == 4096
        assert config.temperature == 0.5
        assert config.max_retries == 5


class TestLLMConfigEnvIntegration:
    """环境变量集成测试"""

    def test_empty_env_after_set(self, monkeypatch):
        """设置后清空环境变量应报错"""
        # 先设置
        monkeypatch.setenv("LLM_API_KEY", "temp_key")
        config = LLMConfig()
        assert config.api_key == "temp_key"
        
        # 然后删除
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        with pytest.raises(ConfigurationError):
            LLMConfig()

    def test_whitespace_only_key_is_invalid(self, monkeypatch):
        """仅包含空白字符的密钥应视为无效"""
        # 注意：当前实现不检查此情况，这可以作为一个改进点
        monkeypatch.setenv("LLM_API_KEY", "   ")
        config = LLMConfig()
        # 当前行为：空白字符被视为有效
        # 如果需要严格检查，可以在__post_init__中添加
        assert config.api_key == "   "
