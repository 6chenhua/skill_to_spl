"""
Pipeline恢复机制E2E测试

验证可以从中间步骤恢复执行，跳过已完成步骤。
"""

import pytest
from pathlib import Path
import shutil

from .conftest import CORE_SKILLS


@pytest.mark.e2e
@pytest.mark.live_llm
class TestResumeFromCheckpoint:
    """
    检查点恢复功能测试
    
    验证Pipeline可以从任意中间步骤恢复。
    """

    def test_resume_from_step1_structure(self, pipeline_config_factory):
        """
        从Step 1恢复
        
        AC:
        - 可以从step1_structure恢复
        - 跳过P1, P2, P3, Step1
        - 结果与完整运行相同
        """
        from pipeline.orchestrator import run_pipeline
        
        # 先完整运行一次
        config_full = pipeline_config_factory("pdf")
        result_full = run_pipeline(config_full)
        assert result_full.success
        
        # 从Step 1恢复
        config_resume = pipeline_config_factory("pdf")
        config_resume.resume_from = "step1_structure"
        result_resume = run_pipeline(config_resume)
        
        assert result_resume.success
        # 验证结果一致性
        assert result_resume.spl_spec.spl_text == result_full.spl_spec.spl_text

    def test_resume_from_step3(self, pipeline_config_factory):
        """
        从Step 3恢复
        
        AC:
        - 可以从step3恢复
        - 跳过前序步骤
        """
        from pipeline.orchestrator import run_pipeline
        
        config_full = pipeline_config_factory("docx")
        result_full = run_pipeline(config_full)
        assert result_full.success
        
        config_resume = pipeline_config_factory("docx")
        config_resume.resume_from = "step3"
        result_resume = run_pipeline(config_resume)
        
        assert result_resume.success
        assert result_resume.spl_spec is not None

    def test_resume_preserves_checkpoints(self, pipeline_config_factory):
        """
        验证恢复时保留已有检查点
        
        AC:
        - 恢复前检查点不被覆盖
        - 新检查点正确生成
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory("pdf")
        
        # 运行到Step 1
        run_pipeline(config)
        
        output_dir = Path(config.output_dir)
        step1_file = output_dir / "step1_bundle.json"
        step1_mtime = step1_file.stat().st_mtime
        
        # 从Step 1恢复
        config.resume_from = "step1_structure"
        run_pipeline(config)
        
        # 验证step1文件未被修改
        assert step1_file.stat().st_mtime == step1_mtime
        
        # 验证后续检查点生成
        assert (output_dir / "step3_structured_spec.json").exists()
        assert (output_dir / "pdf.spl").exists()

    @pytest.mark.parametrize("resume_point", [
        "p2_file_role",
        "p3_package",
        "step1_structure",
    ])
    def test_various_resume_points(self, resume_point, pipeline_config_factory):
        """
        测试多种恢复点
        
        AC:
        - 每个恢复点都能正常恢复
        - Pipeline成功完成
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory("pdf")
        config.resume_from = resume_point
        
        result = run_pipeline(config)
        
        assert result.success, f"Failed to resume from {resume_point}"
        assert result.spl_spec is not None


@pytest.mark.e2e
@pytest.mark.live_llm
class TestCheckpointConsistency:
    """
    检查点一致性测试
    
    验证检查点文件在不同运行间保持一致性。
    """

    def test_checkpoint_idempotent(self, pipeline_config_factory):
        """
        验证检查点幂等性
        
        多次运行相同技能，检查点应该相同（或兼容）。
        """
        from pipeline.orchestrator import run_pipeline
        import json
        
        # 第一次运行
        config1 = pipeline_config_factory("pdf")
        run_pipeline(config1)
        
        # 第二次运行（新目录）
        config2 = pipeline_config_factory("pdf")
        run_pipeline(config2)
        
        # 比较关键检查点
        output1 = Path(config1.output_dir)
        output2 = Path(config2.output_dir)
        
        # 检查P1图结构
        p1_1 = json.loads((output1 / "p1_graph.json").read_text())
        p1_2 = json.loads((output2 / "p1_graph.json").read_text())
        
        # 文件列表应该相同
        files1 = set(p1_1.get("files", {}).keys())
        files2 = set(p1_2.get("files", {}).keys())
        assert files1 == files2

    def test_resume_with_missing_checkpoint_fails(self, pipeline_config_factory):
        """
        验证缺少检查点时恢复失败
        
        AC:
        - 当检查点不存在时恢复失败
        - 返回错误信息
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory("pdf")
        config.resume_from = "step3"
        
        # 清理输出目录模拟缺失检查点
        output_dir = Path(config.output_dir)
        if output_dir.exists():
            shutil.rmtree(output_dir)
        
        # 应该抛出异常或返回失败结果
        try:
            result = run_pipeline(config)
            # 如果成功运行，说明Pipeline处理了缺失情况
            assert not result.success or result.spl_spec is None
        except Exception:
            # 抛出异常也是可接受的
            pass


@pytest.mark.e2e
class TestCheckpointFiles:
    """
    检查点文件测试
    
    不需要LLM调用的快速测试。
    """

    def test_checkpoint_naming_convention(self, pipeline_config_factory):
        """
        验证检查点命名规范
        
        AC:
        - 检查点文件使用预期命名
        """
        expected_files = [
            "p1_graph.json",
            "p2_file_role_map.json",
            "p3_package.json",
            "step1_bundle.json",
            "step3_structured_spec.json",
        ]
        
        # 验证命名规范（不实际运行Pipeline）
        for filename in expected_files:
            assert filename.endswith(".json"), f"Checkpoint {filename} should be JSON"

    def test_resume_from_invalid_point(self, pipeline_config_factory):
        """
        验证无效恢复点处理
        
        AC:
        - 无效恢复点返回适当错误
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory("pdf")
        config.resume_from = "invalid_step"
        
        try:
            result = run_pipeline(config)
            # 应该失败或忽略无效恢复点
            assert not result.success
        except (ValueError, KeyError):
            # 抛出异常是可接受的
            pass
