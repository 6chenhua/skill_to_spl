"""功能等价性测试 - 验证重构前后行为一致。

此测试不依赖外部API，通过模拟LLM客户端来验证 assemble_skill_package 的行为。
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import tempfile
import shutil

from pre_processing.p3_assembler import assemble_skill_package, _process_task_result
from pre_processing.p1_reference_graph import build_reference_graph
from models.data_models import FileReferenceGraph, SkillPackage, ToolSpec


class MockLLMClient:
    """模拟LLM客户端，返回固定响应。"""
    
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.call_count = 0
    
    async def async_call_json(self, name, system, prompt):
        """模拟异步JSON调用"""
        self.call_count += 1
        # 返回模拟的API分析结果
        return {
            "name": "test_function",
            "input_schema": {"param1": "text"},
            "output_schema": "text",
            "description": "Test function for validation"
        }
    
    async def async_call(self, name, system, prompt):
        """模拟异步调用"""
        return "Test description"


class TestP3AssemblerFunctionalEquivalence:
    """功能等价性测试 - 验证重构前后输出一致"""
    
    @pytest.fixture
    def temp_skill_dir(self):
        """创建临时技能目录结构"""
        temp_dir = Path(tempfile.mkdtemp())
        skill_dir = temp_dir / "test_skill"
        skill_dir.mkdir()
        
        # 创建SKILL.md
        (skill_dir / "SKILL.md").write_text("""
---
id: test-skill
name: Test Skill
---

# Test Skill

This is a test skill for validation.
""")
        
        # 创建scripts目录
        (skill_dir / "scripts").mkdir()
        (skill_dir / "scripts" / "test_script.py").write_text("""
def main(input_file: str) -> str:
    \"\"\"Process input file.\"\"\"
    return f"Processed: {input_file}"
""")
        
        yield skill_dir
        
        # 清理
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def mock_client(self):
        """创建模拟LLM客户端"""
        return MockLLMClient()
    
    def test_assemble_structure_output(self, temp_skill_dir, mock_client):
        """验证assemble返回正确的SkillPackage结构"""
        # 构建引用图
        graph = build_reference_graph(str(temp_skill_dir))
        
        # 创建文件角色映射
        file_role_map = {
            "SKILL.md": {"role": "doc", "read_priority": 1},
            "scripts/test_script.py": {"role": "script", "read_priority": 2},
        }
        
        # 模拟异步调用
        with patch.object(mock_client, 'async_call_json', return_value={
            "name": "test_function",
            "input_schema": {"param1": "text"},
            "output_schema": "text",
            "description": "Test function"
        }):
            with patch.object(mock_client, 'async_call', return_value="Test description"):
                # 执行assemble
                result = assemble_skill_package(graph, file_role_map, mock_client)
        
        # 验证返回类型
        assert isinstance(result, SkillPackage)
        assert result.skill_id == "test-skill"
        assert result.root_path == str(temp_skill_dir)
        
        # 验证merged_doc_text包含SKILL.md内容
        assert "Test Skill" in result.merged_doc_text
        assert "FILE: SKILL.md" in result.merged_doc_text
        
        # 验证file_role_map正确设置
        assert "SKILL.md" in result.file_role_map
        assert "scripts/test_script.py" in result.file_role_map
    
    def test_assemble_with_no_llm_client(self, temp_skill_dir):
        """验证无LLM客户端时也能正常工作"""
        graph = build_reference_graph(str(temp_skill_dir))
        file_role_map = {
            "SKILL.md": {"role": "doc", "read_priority": 1},
        }
        
        # 不传client
        result = assemble_skill_package(graph, file_role_map, None)
        
        # 验证基本结构
        assert isinstance(result, SkillPackage)
        assert result.skill_id == "test-skill"
        assert result.tools == []  # 无LLM客户端，无tools
        assert "Test Skill" in result.merged_doc_text
    
    def test_process_task_result_unified_api(self):
        """验证_process_task_result处理unified_api"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = []
        
        # 模拟UnifiedAPISpec列表
        mock_api = Mock()
        mock_api.api_name = "test_api"
        
        _process_task_result(
            task_type="unified_api",
            rel_path="test.md",
            result=[mock_api],
            unified_apis=unified_apis,
            tools=tools,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
        )
        
        assert len(unified_apis) == 1
        assert unified_apis[0] == mock_api
    
    def test_process_task_result_script_with_tool(self):
        """验证_process_task_result处理script返回ToolSpec"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = [
            ("script.py", "script", Path("/tmp/script.py"), Mock()),
        ]
        
        mock_tool = Mock(spec=ToolSpec)
        mock_tool.name = "test_tool"
        
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
    
    def test_process_task_result_script_with_none(self):
        """验证_process_task_result处理script返回None"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = [
            ("script.py", "script", Path("/tmp/script.py"), Mock()),
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
    
    def test_process_task_result_exception_handling(self):
        """验证_process_task_result正确处理异常"""
        unified_apis = []
        tools = []
        script_results = {}
        priority2_tasks = [
            ("script.py", "script", Path("/tmp/script.py"), Mock()),
        ]
        
        exception = ValueError("Test error")
        
        # 不应抛出异常
        _process_task_result(
            task_type="script",
            rel_path="script.py",
            result=exception,
            unified_apis=unified_apis,
            tools=tools,
            script_results=script_results,
            priority2_tasks=priority2_tasks,
        )
        
        # 验证记录了失败结果
        assert len(script_results) == 1
        assert script_results["script.py"][0] is None


class TestP3AssemblerOutputStructure:
    """验证输出数据结构一致性"""
    
    def test_skill_package_has_required_fields(self):
        """验证SkillPackage包含所有必需字段"""
        package = SkillPackage(
            skill_id="test",
            root_path="/test",
            frontmatter={},
            merged_doc_text="test content",
            file_role_map={},
            scripts=[],
            tools=[],
        )
        
        # 验证必需字段
        assert hasattr(package, 'skill_id')
        assert hasattr(package, 'root_path')
        assert hasattr(package, 'frontmatter')
        assert hasattr(package, 'merged_doc_text')
        assert hasattr(package, 'file_role_map')
        assert hasattr(package, 'scripts')
        assert hasattr(package, 'tools')
        
        # 验证类型
        assert isinstance(package.skill_id, str)
        assert isinstance(package.root_path, str)
        assert isinstance(package.merged_doc_text, str)
        assert isinstance(package.tools, list)


class TestP3AssemblerEdgeCases:
    """边界情况测试"""
    
    def test_empty_file_role_map(self):
        """测试空文件角色映射"""
        from unittest.mock import Mock
        
        graph = Mock(spec=FileReferenceGraph)
        graph.skill_id = "empty-test"
        graph.root_path = "/tmp"
        graph.frontmatter = {}
        graph.nodes = {}
        
        import asyncio
        result = asyncio.run(
            assemble_skill_package.__wrapped__(graph, {}, None)
        )
        
        assert isinstance(result, SkillPackage)
        assert result.merged_doc_text == ""
    
    def test_only_priority3_files(self):
        """测试只有priority=3的文件（应被跳过）"""
        from unittest.mock import Mock
        
        graph = Mock(spec=FileReferenceGraph)
        graph.skill_id = "test"
        graph.root_path = "/tmp"
        graph.frontmatter = {}
        graph.nodes = {}
        
        file_role_map = {
            "data.json": {"role": "data", "read_priority": 3},
        }
        
        import asyncio
        result = asyncio.run(
            assemble_skill_package.__wrapped__(graph, file_role_map, None)
        )
        
        assert isinstance(result, SkillPackage)
        # priority=3的文件应被跳过
        assert "data.json" not in result.merged_doc_text
