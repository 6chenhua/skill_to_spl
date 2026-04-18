"""
核心技能性能测试

验证Pipeline执行时间和内存使用是否在可接受范围内，
并检测相对于基准的性能回归。

Usage:
    # 运行性能测试
    pytest test/performance/test_performance_core.py -v

    # 生成基准
    pytest test/performance/test_performance_core.py -v --performance-baseline

    # 对比基准
    pytest test/performance/test_performance_core.py -v --performance-compare

    # 设置自定义阈值
    pytest test/performance/ -v --performance-compare --performance-threshold=10.0
"""

import pytest
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from test.e2e.conftest import CORE_SKILLS
from .conftest import measure_performance, REGRESSION_THRESHOLD, MAX_MEMORY_MB


# 选择代表性技能进行性能测试
PERFORMANCE_TEST_SKILLS = ["pdf", "docx"]


@pytest.mark.performance
@pytest.mark.live_llm
@pytest.mark.parametrize("skill_name", PERFORMANCE_TEST_SKILLS)
class TestPerformanceCore:
    """
    核心技能性能测试
    
    测试执行时间和内存使用，检测性能回归。
    """

    def test_execution_time_within_limits(
        self,
        skill_name,
        pipeline_config_factory,
        performance_baseline,
        compare_baseline,
        regression_threshold,
    ):
        """
        验证执行时间在可接受范围内
        
        AC:
        - 执行时间 < 基准 * (1 + threshold)
        - 或生成新基准
        
        Note:
            第一次运行时会生成基准，后续运行进行对比。
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory(skill_name)
        
        with measure_performance(skill_name) as perf:
            result = run_pipeline(config)
        
        assert result.success, f"Pipeline failed for {skill_name}"
        
        # 如果有基准，进行对比
        if compare_baseline and skill_name in performance_baseline:
            baseline_time = performance_baseline[skill_name].get("elapsed_time")
            if baseline_time:
                max_acceptable = baseline_time * (1 + regression_threshold)
                
                assert perf.elapsed_time <= max_acceptable, (
                    f"Performance regression detected for '{skill_name}':\n"
                    f"  Current:  {perf.elapsed_time:.2f}s\n"
                    f"  Baseline: {baseline_time:.2f}s\n"
                    f"  Max allowed: {max_acceptable:.2f}s\n"
                    f"  Regression: {((perf.elapsed_time - baseline_time) / baseline_time * 100):.1f}%"
                )
        
        # 记录结果
        pytest.performance_results = getattr(pytest, 'performance_results', {})
        pytest.performance_results[skill_name] = perf

    def test_memory_usage_within_limits(self, skill_name, pipeline_config_factory):
        """
        验证内存使用在合理范围内
        
        AC:
        - 内存使用 < MAX_MEMORY_MB (500MB)
        - 无内存泄漏迹象
        """
        from pipeline.orchestrator import run_pipeline
        
        config = pipeline_config_factory(skill_name)
        
        with measure_performance(skill_name) as perf:
            result = run_pipeline(config)
        
        assert result.success
        
        # 验证内存使用
        assert perf.peak_memory_mb < MAX_MEMORY_MB, (
            f"Memory usage too high for '{skill_name}':\n"
            f"  Peak: {perf.peak_memory_mb:.1f}MB\n"
            f"  Max allowed: {MAX_MEMORY_MB}MB"
        )

    def test_performance_reproducibility(self, skill_name, pipeline_config_factory):
        """
        验证性能可重复性
        
        运行两次，验证时间差异在合理范围内。
        
        AC:
        - 两次运行时间差异 < 20%
        """
        from pipeline.orchestrator import run_pipeline
        
        times = []
        
        for i in range(2):
            config = pipeline_config_factory(skill_name)
            
            with measure_performance(f"{skill_name}_run_{i}") as perf:
                result = run_pipeline(config)
            
            assert result.success
            times.append(perf.elapsed_time)
        
        # 计算差异
        time_diff = abs(times[0] - times[1])
        avg_time = sum(times) / len(times)
        variance = time_diff / avg_time
        
        assert variance < 0.20, (
            f"Performance not reproducible for '{skill_name}':\n"
            f"  Run 1: {times[0]:.2f}s\n"
            f"  Run 2: {times[1]:.2f}s\n"
            f"  Variance: {variance*100:.1f}%"
        )


@pytest.mark.performance
@pytest.mark.live_llm
def test_performance_comparison_between_skills(pipeline_config_factory):
    """
    比较不同技能的性能
    
    验证相似复杂度的技能有相似的执行时间。
    
    AC:
    - 相似技能执行时间差异 < 50%
    """
    from pipeline.orchestrator import run_pipeline
    
    results = {}
    
    for skill_name in ["pdf", "docx"]:
        config = pipeline_config_factory(skill_name)
        
        with measure_performance(skill_name) as perf:
            result = run_pipeline(config)
        
        assert result.success
        results[skill_name] = perf
    
    # 比较执行时间
    pdf_time = results["pdf"].elapsed_time
    docx_time = results["docx"].elapsed_time
    
    time_diff = abs(pdf_time - docx_time)
    avg_time = (pdf_time + docx_time) / 2
    variance = time_diff / avg_time
    
    assert variance < 0.50, (
        f"Performance variance between skills too high:\n"
        f"  pdf:  {pdf_time:.2f}s\n"
        f"  docx: {docx_time:.2f}s\n"
        f"  Variance: {variance*100:.1f}%"
    )


@pytest.mark.performance
def test_performance_baseline_exists():
    """
    验证性能基准文件存在
    
    AC:
    - baseline.json文件存在
    - 包含测试技能的基准数据
    """
    from .conftest import BASELINE_PATH
    
    import json
    
    if BASELINE_PATH.exists():
        with open(BASELINE_PATH) as f:
            baseline = json.load(f)
        
        # 验证包含关键技能
        for skill in PERFORMANCE_TEST_SKILLS:
            assert skill in baseline, f"Baseline missing data for '{skill}'"
            assert "elapsed_time" in baseline[skill]
            assert "peak_memory_mb" in baseline[skill]
    else:
        pytest.skip("Performance baseline not yet generated. Run with --performance-baseline")


@pytest.mark.performance
def test_save_baseline(pytestconfig, save_baseline):
    """
    生成性能基准
    
    当指定--performance-baseline时生成新的基准文件。
    """
    if not pytestconfig.getoption("--performance-baseline"):
        pytest.skip("Use --performance-baseline to generate baseline")
    
    # 如果有收集到的结果，保存为基准
    if hasattr(pytest, 'performance_results'):
        save_baseline(pytest.performance_results)
    else:
        pytest.skip("No performance results to save. Run performance tests first.")


@pytest.mark.performance
class TestPerformanceReport:
    """
    性能报告测试
    
    生成性能报告摘要。
    """

    def test_performance_summary(self, pytestconfig):
        """
        输出性能测试摘要
        """
        if hasattr(pytest, 'performance_results'):
            results = pytest.performance_results
            
            print("\n" + "=" * 60)
            print("PERFORMANCE TEST SUMMARY")
            print("=" * 60)
            
            for skill_name, perf in results.items():
                print(f"\nSkill: {skill_name}")
                print(f"  Time:   {perf.elapsed_time:.2f}s")
                print(f"  Memory: {perf.peak_memory_mb:.1f}MB")
                if perf.tokens_used:
                    print(f"  Tokens: {perf.tokens_used}")
            
            print("\n" + "=" * 60)
