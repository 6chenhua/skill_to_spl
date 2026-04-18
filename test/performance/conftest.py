"""
性能测试配置和工具

提供性能测量基础设施，用于建立基准和检测回归。

Usage:
    # 运行性能测试
    pytest test/performance/ -v

    # 生成基准
    pytest test/performance/ -v --performance-baseline

    # 对比基准
    pytest test/performance/ -v --performance-compare
"""

import pytest
import time
import tracemalloc
import json
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
BASELINE_PATH = Path(__file__).parent / "baseline.json"
RESULTS_PATH = Path(__file__).parent / "results.json"

# 性能回归阈值（5%）
REGRESSION_THRESHOLD = 0.05
# 内存使用上限（MB）
MAX_MEMORY_MB = 500


@dataclass
class PerformanceResult:
    """
    性能测试结果
    
    Attributes:
        skill_name: 技能名称
        elapsed_time: 执行时间（秒）
        peak_memory_mb: 内存峰值（MB）
        tokens_used: LLM token使用量
        timestamp: 测试时间戳
        version: 代码版本
    """
    skill_name: str
    elapsed_time: float
    peak_memory_mb: float
    tokens_used: Optional[int] = None
    timestamp: Optional[str] = None
    version: Optional[str] = None


@contextmanager
def measure_performance(skill_name: str):
    """
    性能测量上下文管理器
    
    用法:
        with measure_performance("pdf") as perf:
            result = run_pipeline(config)
        print(f"耗时: {perf.elapsed_time:.2f}s")
    
    Args:
        skill_name: 被测试的技能名称
    
    Yields:
        PerformanceResult对象
    """
    import datetime
    
    # 启动内存跟踪
    tracemalloc.start()
    
    # 记录开始时间
    start_time = time.perf_counter()
    
    result = PerformanceResult(
        skill_name=skill_name,
        elapsed_time=0.0,
        peak_memory_mb=0.0,
        timestamp=datetime.datetime.now().isoformat(),
    )
    
    try:
        yield result
    finally:
        # 计算耗时
        result.elapsed_time = time.perf_counter() - start_time
        
        # 计算内存峰值
        _, peak = tracemalloc.get_traced_memory()
        result.peak_memory_mb = peak / 1024 / 1024  # 转换为MB
        
        tracemalloc.stop()


def pytest_addoption(parser):
    """添加pytest命令行选项"""
    parser.addoption(
        "--performance-baseline",
        action="store_true",
        default=False,
        help="Generate performance baseline",
    )
    parser.addoption(
        "--performance-compare",
        action="store_true",
        default=False,
        help="Compare against baseline",
    )
    parser.addoption(
        "--performance-threshold",
        action="store",
        default="5.0",
        help="Performance regression threshold in percent (default: 5.0)",
    )


def pytest_configure(config):
    """配置pytest，添加标记"""
    config.addinivalue_line(
        "markers",
        "performance: performance and benchmark tests",
    )
    config.addinivalue_line(
        "markers",
        "benchmark: baseline benchmark tests",
    )


@pytest.fixture(scope="session")
def performance_baseline() -> Dict[str, Dict[str, Any]]:
    """
    加载性能基准数据
    
    Returns:
        Dict with baseline data per skill
    """
    if BASELINE_PATH.exists():
        with open(BASELINE_PATH, 'r') as f:
            data = json.load(f)
            # 移除_metadata
            return {k: v for k, v in data.items() if not k.startswith("_")}
    return {}


@pytest.fixture(scope="session")
def save_baseline():
    """
    保存性能基准的fixture
    
    Returns:
        Callable to save baseline data
    """
    def _save(results: Dict[str, PerformanceResult]):
        """保存性能基准"""
        data = {
            skill: asdict(result)
            for skill, result in results.items()
        }
        
        # 添加元数据
        import datetime
        data["_metadata"] = {
            "created_at": datetime.datetime.now().isoformat(),
            "version": "1.0",
            "description": "Performance baseline for skill-to-cnl-p pipeline",
        }
        
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BASELINE_PATH, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\n[Performance] Baseline saved to: {BASELINE_PATH}")
    
    return _save


@pytest.fixture(scope="session")
def performance_results():
    """
    收集性能测试结果
    
    Yields:
        Dict to collect results
    """
    results = {}
    yield results
    
    # 测试会话结束时保存结果
    if results:
        data = {
            skill: asdict(result)
            for skill, result in results.items()
        }
        
        import datetime
        data["_metadata"] = {
            "created_at": datetime.datetime.now().isoformat(),
            "test_count": len(results),
        }
        
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(RESULTS_PATH, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\n[Performance] Results saved to: {RESULTS_PATH}")


@pytest.fixture
def regression_threshold(pytestconfig):
    """
    获取性能回归阈值
    
    Returns:
        float: 阈值（小数形式，如0.05表示5%）
    """
    threshold = float(pytestconfig.getoption("--performance-threshold"))
    return threshold / 100.0  # 转换为小数


@pytest.fixture
def compare_baseline(pytestconfig):
    """
    是否对比基准
    
    Returns:
        bool: True if --performance-compare was specified
    """
    return pytestconfig.getoption("--performance-compare")


@pytest.fixture
def generate_baseline(pytestconfig):
    """
    是否生成基准
    
    Returns:
        bool: True if --performance-baseline was specified
    """
    return pytestconfig.getoption("--performance-baseline")
