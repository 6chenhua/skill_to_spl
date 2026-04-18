"""
E2E测试配置和共享Fixtures

End-to-end test configuration for skill-to-cnl-p pipeline.
Tests the full pipeline execution on real skill packages.

Usage:
    # Run all E2E tests
    pytest test/e2e/ -v

    # Run specific skill test
    pytest test/e2e/test_core_skills.py::test_core_skill_pipeline -v -k "pdf"

    # Run with live LLM (requires API key)
    LIVE_LLM=1 pytest test/e2e/ -v

Directory structure:
    test/e2e/
    ├── conftest.py          # This file - shared fixtures
    ├── test_core_skills.py  # Core skill E2E tests
    ├── test_extended_skills.py # Extended skill tests
    └── test_resume_functionality.py # Checkpoint resume tests
"""

import os
import json
import pathlib
import pytest
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"

# 核心技能包列表（优先级最高）
CORE_SKILLS = [
    "pdf",                  # PDF处理技能
    "docx",                 # Word文档处理
    "pptx",                 # PowerPoint处理
    "xlsx",                 # Excel处理
    "skill-to-cnlp",        # Self-reference技能
    "brand-guidelines",     # 品牌指南
    "canvas-design",        # Canvas设计
]

# 扩展技能包列表
EXTENDED_SKILLS = [
    "algorithmic-art",
    "claude-api",
    "doc-coauthoring",
    "frontend-design",
    "internal-comms",
    "mcp-builder",
    "skill-creator",
    "slack-gif-creator",
    "theme-factory",
    "ui-ux-pro-max",
    "web-artifacts-builder",
    "webapp-testing",
]

# 所有技能包
ALL_SKILLS = CORE_SKILLS + EXTENDED_SKILLS


# ── pytest配置 ───────────────────────────────────────────────────────────────

def pytest_configure(config):
    """配置pytest，添加自定义标记"""
    config.addinivalue_line(
        "markers",
        "e2e: end-to-end tests that run the full pipeline",
    )
    config.addinivalue_line(
        "markers",
        "slow: slow tests that may be skipped in CI",
    )
    config.addinivalue_line(
        "markers",
        "live_llm: tests that call the real LLM API",
    )
    config.addinivalue_line(
        "markers",
        "performance: performance and benchmark tests",
    )


def pytest_collection_modifyitems(config, items):
    """修改测试项，根据环境变量跳过测试"""
    # 如果没有LIVE_LLM环境变量，跳过需要真实LLM的测试
    if os.environ.get("LIVE_LLM") != "1":
        skip_live = pytest.mark.skip(
            reason="Set LIVE_LLM=1 to run tests with real LLM API"
        )
        for item in items:
            if "live_llm" in item.keywords:
                item.add_marker(skip_live)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def llm_config():
    """
    E2E测试专用LLM配置
    
    Returns:
        LLMConfig configured for E2E testing
    """
    # 延迟导入，避免导入错误影响其他测试
    try:
        from pipeline.llm_client import LLMConfig
    except ImportError:
        pytest.skip("pipeline.llm_client not available")
    
    # 使用环境变量或默认值
    model = os.getenv("E2E_TEST_MODEL", "gpt-4o")
    max_tokens = int(os.getenv("E2E_TEST_MAX_TOKENS", "16000"))
    
    return LLMConfig(
        model=model,
        max_tokens=max_tokens,
        temperature=0.1,  # E2E测试使用低temperature确保可重复性
    )


@pytest.fixture(scope="function")
def temp_output_dir(tmp_path):
    """
    为每次测试提供临时输出目录
    
    Returns:
        Path to temporary output directory
    """
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


@pytest.fixture
def pipeline_config_factory(llm_config, temp_output_dir):
    """
    Pipeline配置工厂
    
    创建适合E2E测试的PipelineConfig实例
    
    Usage:
        def test_something(pipeline_config_factory):
            config = pipeline_config_factory("pdf")
            result = run_pipeline(config)
    
    Args:
        skill_name: 技能包名称
        **overrides: 覆盖默认配置的参数
    
    Returns:
        PipelineConfig instance
    """
    try:
        from pipeline.orchestrator import PipelineConfig
    except ImportError:
        pytest.skip("pipeline.orchestrator not available")
    
    def factory(skill_name: str, **overrides) -> "PipelineConfig":
        skill_path = SKILLS_DIR / skill_name
        if not skill_path.exists():
            pytest.skip(f"Skill '{skill_name}' not found at {skill_path}")
        
        config = PipelineConfig(
            skill_root=str(skill_path),
            output_dir=str(temp_output_dir / skill_name),
            llm_config=llm_config,
            save_checkpoints=True,
        )
        
        # 应用覆盖
        for key, value in overrides.items():
            setattr(config, key, value)
        
        return config
    
    return factory


@pytest.fixture
def validate_spl_output():
    """
    SPL输出验证辅助函数
    
    Returns:
        Callable that validates SPL output structure
    """
    def validator(spl_text: str) -> Dict[str, bool]:
        """
        验证SPL输出结构
        
        Args:
            spl_text: SPL文件内容
        
        Returns:
            Dict with validation results
        """
        results = {
            "has_persona": "[DEFINE_PERSONA:]" in spl_text and "[END_PERSONA]" in spl_text,
            "has_worker": "[DEFINE_WORKER:" in spl_text,
            "has_inputs": "[INPUTS]" in spl_text,
            "has_outputs": "[OUTPUTS]" in spl_text,
            "has_main_flow": "[MAIN_FLOW]" in spl_text,
            "not_empty": len(spl_text.strip()) > 100,
        }
        return results
    
    return validator


@pytest.fixture
def check_checkpoints():
    """
    检查点验证辅助函数
    
    Returns:
        Callable that verifies checkpoint files exist
    """
    def checker(output_dir: Path, skill_name: str) -> Dict[str, bool]:
        """
        验证所有检查点文件存在
        
        Args:
            output_dir: 输出目录路径
            skill_name: 技能名称
        
        Returns:
            Dict with checkpoint file existence status
        """
        expected_files = [
            "p1_graph.json",
            "p2_file_role_map.json",
            "p3_package.json",
            "step1_bundle.json",
            "step3_structured_spec.json",
            f"{skill_name}.spl",
        ]
        
        results = {}
        for filename in expected_files:
            file_path = output_dir / filename
            results[filename] = file_path.exists()
        
        return results
    
    return checker
