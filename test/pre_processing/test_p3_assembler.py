"""Test suite for p3_assembler module."""
from __future__ import annotations

import pytest
from unittest.mock import Mock, MagicMock

from pre_processing.p3_assembler import _process_task_result
from models.data_models import ToolSpec


class TestProcessTaskResult:
    """Test suite for _process_task_result function."""

    def test_unified_api_success(self):
        """正常unified_api结果应被添加到列表"""
        # Arrange
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = []
        mock_result = [Mock(api_name="test_api")]

        # Act
        _process_task_result(
            task_type="unified_api",
            rel_path="test.md",
            result=mock_result,
            unified_apis=unified_apis,
            tools=tools,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
        )

        # Assert
        assert len(unified_apis) == 1
        assert unified_apis[0] == mock_result[0]

    def test_unified_api_empty_list(self):
        """空列表应被正确处理（不报错，不添加）"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = []

        _process_task_result(
            task_type="unified_api",
            rel_path="test.md",
            result=[],
            unified_apis=unified_apis,
            tools=tools,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
        )

        assert len(unified_apis) == 0

    def test_unified_api_none_result(self):
        """None结果应被忽略"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = []

        _process_task_result(
            task_type="unified_api",
            rel_path="test.md",
            result=None,
            unified_apis=unified_apis,
            tools=tools,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
        )

        assert len(unified_apis) == 0

    def test_script_with_tool(self):
        """返回ToolSpec的script任务"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = [
            ("script.py", "script", Mock(), Mock()),
        ]
        mock_tool = Mock(spec=ToolSpec)

        _process_task_result(
            task_type="script",
            rel_path="script.py",
            result=mock_tool,
            unified_apis=unified_apis,
            tools=tools,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
        )

        assert len(script_results) == 1
        assert script_results["script.py"][0] == mock_tool

    def test_script_with_none(self):
        """返回None的script任务（分析失败）"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = [
            ("script.py", "script", Mock(), Mock()),
        ]

        _process_task_result(
            task_type="script",
            rel_path="script.py",
            result=None,
            unified_apis=unified_apis,
            tools=tools,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
        )

        assert len(script_results) == 1
        assert script_results["script.py"][0] is None

    def test_script_not_found_in_priority2_tasks(self):
        """script在priority2_tasks中找不到时"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = [
            ("other.py", "script", Mock(), Mock()),
        ]
        mock_tool = Mock(spec=ToolSpec)

        _process_task_result(
            task_type="script",
            rel_path="script.py",
            result=mock_tool,
            unified_apis=unified_apis,
            tools=tools,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
        )

        # 没有找到匹配项，不应修改script_results
        assert len(script_results) == 0

    def test_exception_handling_for_unified_api(self, caplog):
        """unified_api类型的异常应被记录"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = []
        exception = ValueError("test error")

        with caplog.at_level("WARNING"):
            _process_task_result(
                task_type="unified_api",
                rel_path="test.md",
                result=exception,
                unified_apis=unified_apis,
                tools=tools,
                script_results=script_results,
                priority2_tasks=priority2_tasks,
            )

        assert "Task failed for test.md" in caplog.text
        assert len(unified_apis) == 0

    def test_exception_handling_for_script(self, caplog):
        """script类型的异常应记录并添加None到script_results"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = [
            ("script.py", "script", Mock(), Mock(node_id="node1")),
        ]
        exception = ValueError("test error")

        with caplog.at_level("WARNING"):
            _process_task_result(
                task_type="script",
                rel_path="script.py",
                result=exception,
                unified_apis=unified_apis,
                tools=tools,
                script_results=script_results,
                priority2_tasks=priority2_tasks,
            )

        assert "Task failed for script.py" in caplog.text
        assert len(script_results) == 1
        assert script_results["script.py"][0] is None

    def test_script_exception_no_matching_task(self, caplog):
        """script异常时找不到匹配的任务"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = [
            ("other.py", "script", Mock(), Mock()),
        ]
        exception = ValueError("test error")

        with caplog.at_level("WARNING"):
            _process_task_result(
                task_type="script",
                rel_path="script.py",
                result=exception,
                unified_apis=unified_apis,
                tools=tools,
                script_results=script_results,
                priority2_tasks=priority2_tasks,
            )

        assert len(script_results) == 0  # 没有匹配项，不添加

    def test_invalid_task_type(self):
        """未知task_type应被忽略（不产生错误）"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = []
        mock_result = [Mock()]

        # 不应抛出异常
        _process_task_result(
            task_type="unknown_type",
            rel_path="test.md",
            result=mock_result,
            unified_apis=unified_apis,
            tools=tools,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
        )

        # 无任何修改
        assert len(unified_apis) == 0
        assert len(tools) == 0
        assert len(script_results) == 0


class TestP3AssemblerEdgeCases:
    """边界条件测试"""

    def test_multiple_priority2_tasks_matching(self):
        """多个priority2_tasks中只应匹配第一个"""
        unified_apis = []
        tools = []
        script_results = {}
        # 两个相同路径的任务
        priority2_tasks = [
            ("script.py", "script1", Mock(), Mock(node_id="first")),
            ("script.py", "script2", Mock(), Mock(node_id="second")),
        ]
        mock_tool = Mock(spec=ToolSpec)

        _process_task_result(
            task_type="script",
            rel_path="script.py",
            result=mock_tool,
            unified_apis=unified_apis,
            tools=tools,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
        )

        assert len(script_results) == 1
        # 应匹配第一个
        assert script_results["script.py"][3].node_id == "first"

    def test_unified_api_non_list_result(self):
        """unified_api返回非列表时"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = []

        # 非列表应被忽略
        _process_task_result(
            task_type="unified_api",
            rel_path="test.md",
            result=Mock(),  # 不是列表
            unified_apis=unified_apis,
            tools=tools,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
        )

        assert len(unified_apis) == 0

    def test_script_non_toolspec_result(self):
        """script返回非ToolSpec非None时"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = [
            ("script.py", "script", Mock(), Mock()),
        ]

        # 既不是ToolSpec也不是None，应被忽略
        _process_task_result(
            task_type="script",
            rel_path="script.py",
            result="not a toolspec",
            unified_apis=unified_apis,
            tools=tools,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
        )

        assert len(script_results) == 0
