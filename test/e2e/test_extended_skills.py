"""
扩展技能包E2E测试

测试剩余的技能包，这些测试标记为"slow"，可在CI中跳过。
建议定期运行以验证Pipeline对所有技能包的兼容性。

Tested Skills (12):
- algorithmic-art
- claude-api
- doc-coauthoring
- frontend-design
- internal-comms
- mcp-builder
- skill-creator
- slack-gif-creator
- theme-factory
- ui-ux-pro-max
- web-artifacts-builder
- webapp-testing

Note: Run with --run-slow to execute these tests.
"""

import pytest
from pathlib import Path

from .conftest import EXTENDED_SKILLS, ALL_SKILLS, SKILLS_DIR


# 标记为slow测试，默认跳过
pytestmark = [pytest.mark.e2e, pytest.mark.slow, pytest.mark.live_llm]


@pytest.mark.parametrize("skill_name", EXTENDED_SKILLS)
class TestExtendedSkillsPipeline:
    """
    扩展技能Pipeline E2E测试
    
    这些技能测试要求与核心技能相同，但运行频率较低。
    """

    def test_pipeline_completes(self, skill_name, pipeline_config_factory):
        """
        验证Pipeline成功完成
        
        AC:
        - Pipeline成功
        - 返回有效结果
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory(skill_name)
        result = run_pipeline(config)
        
        assert result is not None, f"Pipeline for '{skill_name}' returned None"
        assert result.success, f"Pipeline failed for '{skill_name}'"

    def test_spl_file_created(self, skill_name, pipeline_config_factory):
        """
        验证SPL文件创建
        
        AC:
        - SPL文件存在且非空
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory(skill_name)
        run_pipeline(config)
        
        output_dir = Path(config.output_dir)
        spl_file = output_dir / f"{skill_name}.spl"
        
        assert spl_file.exists(), f"SPL file not created: {spl_file}"
        assert spl_file.stat().st_size > 100, f"SPL file too small: {spl_file}"

    def test_spl_has_basic_structure(self, skill_name, pipeline_config_factory):
        """
        验证SPL基本结构
        
        AC:
        - 包含PERSONA
        - 包含WORKER
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory(skill_name)
        run_pipeline(config)
        
        output_dir = Path(config.output_dir)
        spl_file = output_dir / f"{skill_name}.spl"
        spl_content = spl_file.read_text(encoding="utf-8")
        
        assert "[DEFINE_PERSONA:]" in spl_content, f"Missing PERSONA in {skill_name}"
        assert "[END_PERSONA]" in spl_content, f"Missing END_PERSONA in {skill_name}"
        assert "[DEFINE_WORKER:" in spl_content, f"Missing WORKER in {skill_name}"


def test_all_skills_list_integrity():
    """
    验证技能包列表完整性
    
    AC:
    - skills/目录下的所有子目录都在测试列表中
    - 无遗漏的技能包
    """
    # 获取实际存在的技能包
    actual_skills = [
        d.name for d in SKILLS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".") and d.name != "__pycache__" and d.name != "AGENTS.md"
    ]
    
    # 检查是否有遗漏
    missing_in_list = set(actual_skills) - set(ALL_SKILLS)
    extra_in_list = set(ALL_SKILLS) - set(actual_skills)
    
    assert not missing_in_list, f"Skills not in test list: {missing_in_list}"
    assert not extra_in_list, f"Skills in test list but not found: {extra_in_list}"


def test_extended_skills_have_skill_md():
    """
    验证扩展技能包都有SKILL.md
    """
    missing = []
    for skill_name in EXTENDED_SKILLS:
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        if not skill_md.exists():
            missing.append(skill_name)
    
    assert not missing, f"Extended skills missing SKILL.md: {missing}"


@pytest.mark.parametrize("skill_name", ["mcp-builder", "skill-creator"])
class TestMetaSkills:
    """
    元技能测试
    
    这些技能处理其他技能或自身，结构通常更复杂。
    """

    def test_meta_skill_completes(self, skill_name, pipeline_config_factory):
        """
        元技能Pipeline完成测试
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory(skill_name)
        result = run_pipeline(config)
        
        assert result.success, f"Meta skill '{skill_name}' failed"
        assert result.spl_spec is not None


class TestSkillVariety:
    """
    技能多样性测试
    
    验证不同类型的技能包都能被正确处理。
    """

    @pytest.mark.parametrize("category,examples", [
        ("文档处理", ["pdf", "docx", "pptx", "xlsx"]),
        ("设计/图形", ["canvas-design", "theme-factory", "algorithmic-art"]),
        ("开发工具", ["mcp-builder", "skill-creator", "claude-api"]),
        ("内容生成", ["brand-guidelines", "doc-coauthoring", "slack-gif-creator"]),
    ])
    def test_category_skills_exist(self, category, examples):
        """
        验证各分类的技能包都存在
        """
        missing = []
        for skill in examples:
            skill_path = SKILLS_DIR / skill
            if not skill_path.exists():
                missing.append(skill)
        
        assert not missing, f"{category} skills missing: {missing}"
