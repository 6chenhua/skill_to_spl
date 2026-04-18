"""
核心技能包E2E测试

测试最常用的技能包，确保Pipeline基本功能正常。
这些技能代表了最常见的使用场景，必须全部通过。

Tested Skills:
- pdf: PDF处理（文档处理类）
- docx: Word文档处理（Office类）
- pptx: PowerPoint处理（Office类）
- xlsx: Excel处理（Office类）
- skill-to-cnlp: Self-reference（元技能）
- brand-guidelines: 品牌指南（内容生成类）
- canvas-design: Canvas设计（图形类）

Note: These tests require LIVE_LLM=1 to run as they call real LLM APIs.
"""

import pytest
from pathlib import Path

# Import from conftest
from .conftest import CORE_SKILLS


@pytest.mark.e2e
@pytest.mark.live_llm
@pytest.mark.parametrize("skill_name", CORE_SKILLS)
class TestCoreSkillsPipeline:
    """
    核心技能Pipeline E2E测试类
    
    每个核心技能都执行完整Pipeline并验证:
    1. Pipeline成功完成（无异常）
    2. 输出有效的SPL文件
    3. SPL文件包含必需的结构元素
    """

    def test_pipeline_completes_successfully(self, skill_name, pipeline_config_factory):
        """
        验证Pipeline成功完成，无异常抛出
        
        AC:
        - Pipeline返回结果对象
        - 结果标记为成功
        - 无异常抛出
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory(skill_name)
        
        # Act - 应该不抛出异常
        result = run_pipeline(config)
        
        # Assert
        assert result is not None, f"Pipeline for '{skill_name}' returned None"
        assert hasattr(result, 'success'), f"Result missing 'success' attribute"
        assert result.success, f"Pipeline failed for '{skill_name}'"

    def test_spl_file_created(self, skill_name, pipeline_config_factory):
        """
        验证输出目录包含最终.spl文件
        
        AC:
        - SPL文件存在
        - SPL文件非空
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory(skill_name)
        result = run_pipeline(config)
        
        output_dir = Path(config.output_dir)
        spl_file = output_dir / f"{skill_name}.spl"
        
        assert spl_file.exists(), f"SPL file not created: {spl_file}"
        assert spl_file.stat().st_size > 0, f"SPL file is empty: {spl_file}"

    def test_spl_has_required_structure(self, skill_name, pipeline_config_factory, validate_spl_output):
        """
        验证SPL输出包含必需的结构元素
        
        AC:
        - 包含PERSONA定义
        - 包含WORKER定义
        - 非空内容
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory(skill_name)
        result = run_pipeline(config)
        
        # Read SPL content
        output_dir = Path(config.output_dir)
        spl_file = output_dir / f"{skill_name}.spl"
        spl_content = spl_file.read_text(encoding="utf-8")
        
        # Validate structure
        validation = validate_spl_output(spl_content)
        
        assert validation["has_persona"], f"'{skill_name}' SPL missing PERSONA"
        assert validation["has_worker"], f"'{skill_name}' SPL missing WORKER definition"
        assert validation["not_empty"], f"'{skill_name}' SPL is too short"

    def test_result_contains_spl_spec(self, skill_name, pipeline_config_factory):
        """
        验证PipelineResult包含有效的SPLSpec
        
        AC:
        - result.spl_spec不为None
        - spl_spec包含spl_text
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory(skill_name)
        result = run_pipeline(config)
        
        assert hasattr(result, 'spl_spec'), f"Result missing 'spl_spec'"
        assert result.spl_spec is not None, f"No SPL spec in result for '{skill_name}'"
        assert hasattr(result.spl_spec, 'spl_text'), f"SPL spec missing 'spl_text'"
        assert len(result.spl_spec.spl_text) > 0, f"SPL text is empty"


@pytest.mark.e2e
@pytest.mark.live_llm
@pytest.mark.parametrize("skill_name", ["pdf", "docx"])
class TestCheckpointSystem:
    """
    检查点系统测试
    
    验证中间检查点文件正确生成。
    """

    def test_all_checkpoints_created(self, skill_name, pipeline_config_factory, check_checkpoints):
        """
        验证所有中间检查点文件存在
        
        AC:
        - p1_graph.json
        - p2_file_role_map.json
        - p3_package.json
        - step1_bundle.json
        - step3_structured_spec.json
        - {skill_name}.spl
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory(skill_name)
        run_pipeline(config)
        
        output_dir = Path(config.output_dir)
        checkpoints = check_checkpoints(output_dir, skill_name)
        
        # 验证所有检查点存在
        missing = [name for name, exists in checkpoints.items() if not exists]
        assert not missing, f"Missing checkpoints for '{skill_name}': {missing}"

    def test_checkpoints_are_valid_json(self, skill_name, pipeline_config_factory):
        """
        验证检查点文件是有效的JSON
        
        AC:
        - 所有.json文件可解析
        - 文件包含预期的字段
        """
        import json
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory(skill_name)
        run_pipeline(config)
        
        output_dir = Path(config.output_dir)
        json_files = [
            "p1_graph.json",
            "p2_file_role_map.json",
            "p3_package.json",
            "step1_bundle.json",
            "step3_structured_spec.json",
        ]
        
        for json_file in json_files:
            file_path = output_dir / json_file
            if file_path.exists():
                try:
                    content = json.loads(file_path.read_text(encoding="utf-8"))
                    assert isinstance(content, (dict, list)), f"{json_file} is not valid JSON object"
                except json.JSONDecodeError as e:
                    pytest.fail(f"Failed to parse {json_file}: {e}")


@pytest.mark.e2e
@pytest.mark.live_llm
def test_skill_with_complex_structure(pipeline_config_factory, validate_spl_output):
    """
    测试复杂技能包（skill-to-cnlp自身）
    
    这个技能包结构最复杂，是最佳测试案例。
    """
    from pipeline.orchestrator import run_pipeline
    
    skill_name = "skill-to-cnlp"
    config = pipeline_config_factory(skill_name)
    result = run_pipeline(config)
    
    assert result.success
    assert result.spl_spec is not None
    
    # 验证复杂SPL结构
    spl_content = result.spl_spec.spl_text
    validation = validate_spl_output(spl_content)
    
    assert validation["has_persona"]
    assert validation["has_worker"]
    assert validation["has_inputs"]
    assert validation["has_outputs"]
    assert validation["has_main_flow"]


@pytest.mark.e2e
def test_skill_package_exists():
    """
    验证所有核心技能包都存在
    
    这是一个快速测试，不需要LLM调用。
    """
    from .conftest import SKILLS_DIR, CORE_SKILLS
    
    missing = []
    for skill_name in CORE_SKILLS:
        skill_path = SKILLS_DIR / skill_name
        if not skill_path.exists():
            missing.append(skill_name)
    
    assert not missing, f"Missing skill packages: {missing}"


@pytest.mark.e2e
def test_skill_has_skill_md():
    """
    验证所有核心技能包都有SKILL.md文件
    
    SKILL.md是必需的入口文件。
    """
    from .conftest import SKILLS_DIR, CORE_SKILLS
    
    missing = []
    for skill_name in CORE_SKILLS:
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        if not skill_md.exists():
            missing.append(skill_name)
    
    assert not missing, f"Skills missing SKILL.md: {missing}"
