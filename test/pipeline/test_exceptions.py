"""Test suite for pipeline exceptions module."""
from __future__ import annotations

import logging
import pytest
from unittest.mock import Mock

from pipeline.exceptions import (
    PipelineError,
    ConfigurationError,
    LLMError,
    LLMParseError,
    LLMRetryExhausted,
    PreprocessingError,
    ValidationError,
    log_exception,
    suppress_exceptions,
    require_non_empty,
    get_required_env,
    get_optional_env,
)


class TestExceptionHierarchy:
    """异常继承体系测试"""

    def test_pipeline_error_is_base(self):
        """PipelineError是所有异常的基类"""
        assert issubclass(ConfigurationError, PipelineError)
        assert issubclass(LLMError, PipelineError)
        assert issubclass(PreprocessingError, PipelineError)
        assert issubclass(ValidationError, PipelineError)

    def test_llm_errors_inherit(self):
        """LLM相关错误继承自LLMError"""
        assert issubclass(LLMParseError, LLMError)
        assert issubclass(LLMRetryExhausted, LLMError)

    def test_configuration_error_message(self):
        """ConfigurationError可以正确设置消息"""
        error = ConfigurationError("test message")
        assert str(error) == "test message"

    def test_llm_parse_error_stores_raw_response(self):
        """LLMParseError存储原始响应"""
        error = LLMParseError("parse failed", "raw response text")
        assert error.raw_response == "raw response text"
        assert str(error) == "parse failed"


class TestLogExceptionDecorator:
    """log_exception装饰器测试"""

    def test_logs_warning_by_default(self, caplog):
        """默认应记录WARNING级别日志"""
        @log_exception()
        def failing_func():
            raise ValueError("test error")

        with caplog.at_level(logging.WARNING):
            with pytest.raises(ValueError):
                failing_func()

        assert "failing_func" in caplog.text
        assert "test error" in caplog.text

    def test_logs_at_custom_level(self, caplog):
        """应支持自定义日志级别"""
        @log_exception(level=logging.ERROR)
        def failing_func():
            raise ValueError("test error")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError):
                failing_func()

        assert "ERROR" in caplog.text

    def test_reraise_false_returns_default(self):
        """reraise=False时返回默认值"""
        @log_exception(reraise=False, default_return="default")
        def failing_func():
            raise ValueError("test error")

        result = failing_func()
        assert result == "default"

    def test_reraise_true_raises_exception(self):
        """reraise=True时抛出异常"""
        @log_exception(reraise=True)
        def failing_func():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            failing_func()

    def test_no_exception_when_success(self, caplog):
        """函数成功执行时不记录错误"""
        @log_exception()
        def success_func():
            return "success"

        with caplog.at_level(logging.WARNING):
            result = success_func()

        assert result == "success"
        assert "success_func" not in caplog.text


class TestSuppressExceptionsDecorator:
    """suppress_exceptions装饰器测试"""

    def test_no_exception_raised(self):
        """不应抛出异常"""
        @suppress_exceptions
        def failing_func():
            raise ValueError("test error")

        # 不应抛出
        result = failing_func()
        assert result is None

    def test_logs_debug_message(self, caplog):
        """应记录DEBUG级别日志"""
        @suppress_exceptions
        def failing_func():
            raise ValueError("test error")

        with caplog.at_level(logging.DEBUG):
            failing_func()

        assert "failing_func" in caplog.text
        assert "DEBUG" in caplog.text


class TestRequireNonEmptyDecorator:
    """require_non_empty装饰器测试"""

    def test_empty_raises_error(self):
        """空值应抛出异常"""
        @require_non_empty("Value cannot be empty")
        def empty_func():
            return []

        with pytest.raises(ValueError, match="Value cannot be empty"):
            empty_func()

    def test_non_empty_returns_value(self):
        """非空值正常返回"""
        @require_non_empty("Value cannot be empty")
        def non_empty_func():
            return [1, 2, 3]

        result = non_empty_func()
        assert result == [1, 2, 3]

    def test_none_raises_error(self):
        """None应视为空"""
        @require_non_empty("Value cannot be empty")
        def none_func():
            return None

        with pytest.raises(ValueError):
            none_func()

    def test_empty_string_raises_error(self):
        """空字符串应视为空"""
        @require_non_empty("Value cannot be empty")
        def empty_string_func():
            return ""

        with pytest.raises(ValueError):
            empty_string_func()


class TestGetRequiredEnv:
    """get_required_env测试"""

    def test_existing_env_var(self, monkeypatch):
        """存在的环境变量应返回其值"""
        monkeypatch.setenv("TEST_VAR", "test_value")
        result = get_required_env("TEST_VAR")
        assert result == "test_value"

    def test_missing_env_var_raises(self, monkeypatch):
        """缺失的环境变量应抛出ConfigurationError"""
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(ConfigurationError) as exc_info:
            get_required_env("MISSING_VAR")
        assert "MISSING_VAR" in str(exc_info.value)
        assert "required" in str(exc_info.value).lower()

    def test_empty_string_raises(self, monkeypatch):
        """空字符串值应抛出异常"""
        monkeypatch.setenv("EMPTY_VAR", "")
        with pytest.raises(ConfigurationError):
            get_required_env("EMPTY_VAR")


class TestGetOptionalEnv:
    """get_optional_env测试"""

    def test_existing_env_var(self, monkeypatch):
        """存在的环境变量应返回其值"""
        monkeypatch.setenv("TEST_VAR", "test_value")
        result = get_optional_env("TEST_VAR")
        assert result == "test_value"

    def test_missing_returns_default(self, monkeypatch):
        """缺失的环境变量返回默认值"""
        monkeypatch.delenv("MISSING_VAR", raising=False)
        result = get_optional_env("MISSING_VAR", "default_value")
        assert result == "default_value"

    def test_missing_with_empty_default(self, monkeypatch):
        """缺失的环境变量返回空字符串（默认）"""
        monkeypatch.delenv("MISSING_VAR", raising=False)
        result = get_optional_env("MISSING_VAR")
        assert result == ""
