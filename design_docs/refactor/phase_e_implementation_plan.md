# Phase E: 最终集成与测试 - 详细实施计划

> **版本**: 1.0  
> **创建日期**: 2026-04-19  
> **状态**: 待评审  
> **预计工期**: 1周（第12周）

---

## 执行摘要

Phase E是重构计划的最后阶段，目标是对前4个Phase（A-D）的所有重构工作进行最终集成、验证和文档化。本阶段将确保重构后的代码库功能完整、性能达标、文档完善，并可稳定运行。

**Phase E核心目标**:
1. 🔄 **E2E集成测试** - 验证完整Pipeline功能
2. 📊 **性能基准测试** - 确保无性能回归
3. 📚 **文档更新** - 同步所有架构变更
4. ✅ **验收验证** - 确保满足所有AC

---

## 一、项目现状分析

### 1.1 项目结构概览

基于代码库探索，当前项目结构如下：

```
skill-to-cnlp/
├── cli.py                    # CLI入口
├── main.py                   # 程序化API入口
├── pyproject.toml           # 包配置（pytest配置缺失）
├── AGENTS.md                # 项目知识库
├── README.md                # 项目文档（需更新）
│
├── pipeline/                # 核心Pipeline（正在重构中）
│   ├── orchestrator.py      # 🔴 238行混合代码（Phase C目标）
│   ├── llm_client.py        # 🔴 硬编码配置（Phase A目标）
│   └── llm_steps/           # Step 1-4实现
│
├── pre_processing/          # 预处理P1-P3
│   ├── p1_reference_graph.py
│   ├── p2_file_role_resolver.py
│   └── p3_assembler.py      # 🔴 代码重复（Phase A目标）
│
├── models/                  # 数据模型
│   └── data_models.py       # 🔴 495行20+类（Phase B目标）
│
├── prompts/                 # LLM系统提示
├── skills/                  # 20个示例技能包
│   ├── pdf/
│   ├── docx/
│   ├── pptx/
│   ├── xlsx/
│   ├── skill-to-cnlp/      # Self-reference
│   └── ... (14 others)
│
├── test/                    # 测试套件
│   ├── conftest.py          # pytest配置
│   ├── test_p1_*.py         # P1测试
│   ├── test_p2_*.py         # P2测试
│   ├── test_p3_*.py         # P3测试
│   ├── test_step1_*.py      # Step 1测试
│   ├── test_step3_*.py      # Step 3测试
│   ├── test_s4_*.py         # Step 4测试
│   └── test_unified_api_*.py # API测试
│
└── design_docs/             # 架构文档
    ├── refactor/
    │   └── refactor_plan_v2.md    # 本重构计划
    └── phase_d_refactor_plan.md # Phase D计划
```

### 1.2 测试现状分析

| 测试类型 | 现状 | 覆盖范围 | Phase E需求 |
|---------|------|---------|------------|
| **单元测试** | ✅ 存在 | P1-P3, Step1, Step3, Step4 | 补充新模块测试 |
| **集成测试** | ⚠️ 部分 | test_step3_integration.py | 扩展Pipeline集成测试 |
| **E2E测试** | ❌ 缺失 | 无完整E2E | **Phase E核心任务** |
| **性能测试** | ❌ 缺失 | 无基准 | **Phase E核心任务** |
| **回归测试** | ❌ 缺失 | 无自动化 | **Phase E核心任务** |

**关键发现**:
- 现有 `test_unified_api_generation_e2e.py` 是E2E测试雏形，需扩展
- 缺少 pytest.ini / setup.cfg 配置
- 无性能基准测试记录
- 无CI/CD配置

### 1.3 文档现状分析

| 文档 | 状态 | Phase E动作 |
|------|------|------------|
| README.md | ⚠️ 需更新 | 更新架构图、API示例 |
| AGENTS.md | ✅ 最新 | 无需变更 |
| design_docs/*.md | ✅ 详细 | 添加迁移指南 |
| API文档 | ❌ 缺失 | 生成API文档 |
| 迁移指南 | ❌ 缺失 | **Phase E创建** |

---

## 二、Phase E 任务分解

### 2.1 任务总览

```
Week 12 (5个工作日)
├── Day 1-2: E2E测试实施 (Task 5.1)
├── Day 2-3: 性能基准测试 (Task 5.2)  
├── Day 3-4: 文档更新 (Task 5.3)
└── Day 4-5: 回归测试与验收 (Task 5.4)
```

---

## 三、详细任务计划

### 任务 5.1: E2E测试套件实施 ⭐核心任务

#### 目标
构建完整的端到端测试套件，验证所有20个示例技能包可通过重构后的Pipeline处理。

#### 验收标准 (AC)
- [ ] 所有20个技能包至少运行一次完整Pipeline
- [ ] 每个技能包输出有效SPL文件
- [ ] 测试覆盖率 >= 80%
- [ ] 测试执行时间 < 30分钟（并行）

#### 子任务 5.1.1: 配置测试基础设施

**文件**: `test/e2e/conftest.py`

```python
"""
E2E测试配置和共享Fixtures
"""
import pytest
import os
from pathlib import Path
from pipeline.orchestrator import run_pipeline, PipelineConfig
from pipeline.llm_client import LLMConfig

# 技能包目录
SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"

# 核心技能包列表（优先级排序）
CORE_SKILLS = [
    "pdf",                  # 最常用
    "docx",                 # Office文档
    "pptx", 
    "xlsx",
    "skill-to-cnlp",        # Self-reference
    "brand-guidelines",
    "canvas-design",
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

ALL_SKILLS = CORE_SKILLS + EXTENDED_SKILLS


@pytest.fixture(scope="session")
def llm_config():
    """E2E测试专用LLM配置"""
    return LLMConfig(
        model=os.getenv("E2E_TEST_MODEL", "gpt-4o"),
        max_tokens=16000,
        temperature=0.1,
    )


@pytest.fixture(scope="function")
def temp_output_dir(tmp_path):
    """为每次测试提供临时输出目录"""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def pipeline_config_factory(llm_config, temp_output_dir):
    """Pipeline配置工厂"""
    def factory(skill_name: str, **overrides):
        skill_path = SKILLS_DIR / skill_name
        if not skill_path.exists():
            pytest.skip(f"Skill '{skill_name}' not found")
        
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
```

**预计时间**: 2小时

---

#### 子任务 5.1.2: 实现核心技能E2E测试

**文件**: `test/e2e/test_core_skills.py`

```python
"""
核心技能包E2E测试
测试最常用的技能包，确保Pipeline基本功能正常
"""
import pytest
from pathlib import Path
from pipeline.orchestrator import run_pipeline
from ..conftest import CORE_SKILLS


@pytest.mark.e2e
@pytest.mark.parametrize("skill_name", CORE_SKILLS)
def test_core_skill_pipeline(skill_name, pipeline_config_factory):
    """
    验证核心技能包可以完整运行Pipeline
    
    AC:
    - Pipeline成功完成（无异常）
    - 输出目录包含最终.spl文件
    - SPL文件非空且包含关键标签
    """
    # Arrange
    config = pipeline_config_factory(skill_name)
    
    # Act
    result = run_pipeline(config)
    
    # Assert
    assert result is not None, f"Pipeline for {skill_name} returned None"
    assert result.spl_spec is not None, f"No SPL spec generated for {skill_name}"
    
    # 验证输出文件存在
    output_spl = Path(config.output_dir) / f"{skill_name}.spl"
    assert output_spl.exists(), f"SPL file not created: {output_spl}"
    assert output_spl.stat().st_size > 0, f"SPL file is empty: {output_spl}"
    
    # 验证SPL内容
    spl_content = output_spl.read_text(encoding="utf-8")
    assert "[DEFINE_PERSONA:]" in spl_content, "Missing PERSONA definition"
    assert "[END_PERSONA]" in spl_content, "Missing PERSONA end tag"


@pytest.mark.e2e
@pytest.mark.parametrize("skill_name", ["pdf", "docx"])
def test_skill_with_checkpoints(skill_name, pipeline_config_factory):
    """
    验证Checkpoint系统正常工作
    
    AC:
    - 所有中间检查点文件存在
    - 可以从中间步骤恢复
    """
    config = pipeline_config_factory(skill_name)
    
    # 完整运行
    result_full = run_pipeline(config)
    
    # 验证检查点
    output_dir = Path(config.output_dir)
    checkpoints = [
        "p1_graph.json",
        "p2_file_role_map.json",
        "p3_package.json",
        "step1_bundle.json",
        f"{skill_name}.spl"
    ]
    
    for cp in checkpoints:
        cp_path = output_dir / cp
        assert cp_path.exists(), f"Checkpoint missing: {cp}"
```

**预计时间**: 4小时

---

#### 子任务 5.1.3: 实现扩展技能E2E测试

**文件**: `test/e2e/test_extended_skills.py`

```python
"""
扩展技能包E2E测试
测试剩余技能包，可选运行（标记为slow）
"""
import pytest
from ..conftest import EXTENDED_SKILLS


@pytest.mark.e2e
@pytest.mark.slow  # 可选：--run-slow标记才执行
@pytest.mark.parametrize("skill_name", EXTENDED_SKILLS)
def test_extended_skill_pipeline(skill_name, pipeline_config_factory):
    """
    验证扩展技能包可以完整运行Pipeline
    
    AC:
    - 与核心技能相同
    - 标记为slow，CI中可跳过
    """
    from pipeline.orchestrator import run_pipeline
    from pathlib import Path
    
    config = pipeline_config_factory(skill_name)
    result = run_pipeline(config)
    
    assert result is not None
    assert result.spl_spec is not None
    
    output_spl = Path(config.output_dir) / f"{skill_name}.spl"
    assert output_spl.exists()


@pytest.mark.e2e
def test_all_skills_list_integrity():
    """
    验证技能包列表完整性
    
    AC:
    - skills/目录下的所有子目录都在测试列表中
    - 无遗漏的技能包
    """
    from pathlib import Path
    from ..conftest import ALL_SKILLS, SKILLS_DIR
    
    actual_skills = [
        d.name for d in SKILLS_DIR.iterdir() 
        if d.is_dir() and not d.name.startswith(".") and d.name != "__pycache__"
    ]
    
    missing = set(actual_skills) - set(ALL_SKILLS)
    extra = set(ALL_SKILLS) - set(actual_skills)
    
    assert not missing, f"Skills not in test list: {missing}"
    assert not extra, f"Skills in test list but not found: {extra}"
```

**预计时间**: 2小时

---

#### 子任务 5.1.4: 实现恢复机制E2E测试

**文件**: `test/e2e/test_resume_functionality.py`

```python
"""
Pipeline恢复机制E2E测试
验证可以从中间步骤恢复执行
"""
import pytest
from pathlib import Path
from pipeline.orchestrator import run_pipeline, PipelineConfig


@pytest.mark.e2e
@pytest.mark.parametrize("resume_point", [
    "p2_file_role",
    "p3_package",
    "step1_structure",
    "step3_entity",
])
def test_resume_from_checkpoint(resume_point, pipeline_config_factory):
    """
    验证可以从每个检查点恢复
    
    AC:
    - 从指定点恢复执行
    - 跳过已完成步骤
    - 最终输出与完整运行相同
    """
    config = pipeline_config_factory("pdf")
    
    # 先完整运行一次生成检查点
    result_full = run_pipeline(config)
    assert result_full.success
    
    # 从检查点恢复
    config_resume = pipeline_config_factory("pdf")
    config_resume.resume_from = resume_point
    
    result_resume = run_pipeline(config_resume)
    
    # 验证结果一致性
    assert result_resume.success
    assert result_resume.spl_spec.spl_text == result_full.spl_spec.spl_text
```

**预计时间**: 3小时

---

### 任务 5.2: 性能基准测试 ⭐核心任务

#### 目标
建立性能基准，验证重构后无性能回归（±5%可接受范围）。

#### 验收标准 (AC)
- [ ] 建立性能基准（Phase E之前）
- [ ] 重构后性能对比测试
- [ ] 性能回归 < 5%
- [ ] 内存使用无泄漏

#### 子任务 5.2.1: 实现性能测试框架

**文件**: `test/performance/conftest.py`

```python
"""
性能测试配置和工具
"""
import pytest
import time
import tracemalloc
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional


@dataclass
class PerformanceResult:
    """性能测试结果"""
    elapsed_time: float          # 秒
    peak_memory_mb: float        # MB
    tokens_used: Optional[int]   # LLM token使用量
    

@contextmanager
def measure_performance():
    """
    性能测量上下文管理器
    
    用法:
        with measure_performance() as perf:
            run_pipeline(config)
        print(f"耗时: {perf.elapsed_time:.2f}s")
    """
    # 启动内存跟踪
    tracemalloc.start()
    start_mem = tracemalloc.take_snapshot()
    
    # 记录开始时间
    start_time = time.perf_counter()
    
    result = PerformanceResult(0, 0, None)
    
    try:
        yield result
    finally:
        # 计算耗时
        result.elapsed_time = time.perf_counter() - start_time
        
        # 计算内存峰值
        end_mem = tracemalloc.take_snapshot()
        top_stats = end_mem.compare_to(start_mem, 'lineno')
        
        # 获取峰值内存使用
        current, peak = tracemalloc.get_traced_memory()
        result.peak_memory_mb = peak / 1024 / 1024  # 转换为MB
        
        tracemalloc.stop()


@pytest.fixture(scope="session")
def performance_baseline():
    """
    加载性能基准数据
    """
    import json
    from pathlib import Path
    
    baseline_path = Path(__file__).parent / "baseline.json"
    
    if baseline_path.exists():
        with open(baseline_path) as f:
            return json.load(f)
    return {}


def save_baseline(results: dict, baseline_path: Path = None):
    """
    保存性能基准数据
    
    用法:
        save_baseline({"pdf": {"time": 45.2, "memory": 128}})
    """
    if baseline_path is None:
        baseline_path = Path(__file__).parent / "baseline.json"
    
    with open(baseline_path, 'w') as f:
        json.dump(results, f, indent=2)
```

**预计时间**: 2小时

---

#### 子任务 5.2.2: 实现核心技能性能测试

**文件**: `test/performance/test_performance_core.py`

```python
"""
核心技能性能测试
验证Pipeline执行时间和内存使用
"""
import pytest
import json
from pathlib import Path
from pipeline.orchestrator import run_pipeline
from .conftest import measure_performance
from ..e2e.conftest import CORE_SKILLS


# 性能回归阈值（5%）
REGRESSION_THRESHOLD = 0.05


@pytest.mark.performance
@pytest.mark.parametrize("skill_name", ["pdf", "docx"])  # 仅测试2个核心技能
class TestPerformance:
    """
    性能测试类
    
    每个技能测试：
    - 执行时间
    - 内存使用峰值
    - Token使用量（可选）
    """
    
    def test_execution_time(self, skill_name, pipeline_config_factory, performance_baseline):
        """
        验证执行时间在可接受范围内
        
        AC:
        - 执行时间 < 基准 * 1.05
        - 或生成新基准
        """
        config = pipeline_config_factory(skill_name)
        
        with measure_performance() as perf:
            result = run_pipeline(config)
        
        assert result.success, f"Pipeline failed for {skill_name}"
        
        # 检查是否超过基准
        baseline_time = performance_baseline.get(skill_name, {}).get("time")
        if baseline_time:
            max_acceptable = baseline_time * (1 + REGRESSION_THRESHOLD)
            assert perf.elapsed_time <= max_acceptable, (
                f"{skill_name} performance regression: "
                f"{perf.elapsed_time:.2f}s > {max_acceptable:.2f}s "
                f"(baseline: {baseline_time:.2f}s)"
            )
        
        # 记录结果
        pytest.performance_results = getattr(pytest, 'performance_results', {})
        pytest.performance_results[skill_name] = {
            "time": perf.elapsed_time,
            "memory_mb": perf.peak_memory_mb,
        }
    
    def test_memory_usage(self, skill_name, pipeline_config_factory):
        """
        验证内存使用合理
        
        AC:
        - 内存使用 < 500MB（暂定）
        - 无内存泄漏迹象
        """
        config = pipeline_config_factory(skill_name)
        
        with measure_performance() as perf:
            result = run_pipeline(config)
        
        # 内存上限（可根据实际调整）
        MAX_MEMORY_MB = 500
        assert perf.peak_memory_mb < MAX_MEMORY_MB, (
            f"{skill_name} memory usage too high: "
            f"{perf.peak_memory_mb:.1f}MB > {MAX_MEMORY_MB}MB"
        )


@pytest.mark.performance
def test_parallel_execution_overhead():
    """
    验证并行执行相比顺序执行有性能提升
    
    AC:
    - 并行执行耗时 < 顺序执行
    """
    # 实现并行vs顺序对比测试
    pass  # TODO: 根据Phase D重构实现


def pytest_sessionfinish(session, exitstatus):
    """
    会话结束时保存性能结果
    """
    if hasattr(pytest, 'performance_results'):
        results = pytest.performance_results
        
        # 保存到文件
        output_path = Path("test/performance/results.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n性能测试结果已保存到: {output_path}")
```

**预计时间**: 4小时

---

#### 子任务 5.2.3: 创建性能基准文件

**文件**: `test/performance/baseline.json` (示例)

```json
{
  "pdf": {
    "time": 45.0,
    "memory_mb": 150.0,
    "tokens": 8000,
    "recorded_at": "2026-04-19T00:00:00Z",
    "version": "pre-refactor"
  },
  "docx": {
    "time": 52.0,
    "memory_mb": 180.0,
    "tokens": 9500,
    "recorded_at": "2026-04-19T00:00:00Z",
    "version": "pre-refactor"
  },
  "_metadata": {
    "description": "Pre-refactor performance baseline",
    "note": "Record actual values after first full run"
  }
}
```

**预计时间**: 1小时

---

### 任务 5.3: 文档更新 ⭐核心任务

#### 目标
更新所有文档以反映重构后的架构，包括README、架构文档、API文档和迁移指南。

#### 验收标准 (AC)
- [ ] README.md更新完成
- [ ] 架构文档与代码一致
- [ ] API文档自动生成
- [ ] 迁移指南完整

#### 子任务 5.3.1: 更新README.md

**文件**: `README.md`

**变更清单**:

```diff
## 需要更新的章节

1. **架构图** (第31-54行)
   - 更新为新的Pipeline架构
   - 添加Builder模式和StepExecutor

2. **Pipeline Stages表** (第56-67行)
   - 确认各阶段名称与重构后一致
   - 更新类型标注（如果变更）

3. **项目结构** (第121-158行)
   - 更新目录结构反映重构后的组织
   - 添加orchestrator/子目录
   - 更新models/目录结构

4. **Quick Start** (第86-119行)
   - 确认API示例仍然有效
   - 更新import路径（如果有变化）

5. **Development** (第235-249行)
   - 更新测试命令（如果有新增标记）
   - 添加E2E测试说明
```

**预计时间**: 3小时

---

#### 子任务 5.3.2: 创建/更新架构文档

**文件**: `design_docs/ARCHITECTURE_v2.md` (新建)

```markdown
# Skill-to-CNL-P 架构文档 v2.0

> **版本**: 2.0  
> **日期**: 2026-04-19  
> **状态**: 重构后架构

---

## 架构概览

重构后的Pipeline采用**Builder模式 + Step抽象**，解决原有Orchestrator违反SRP问题。

### 新架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                     PipelineOrchestrator                        │
│                    (协调器，<50行代码)                           │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌─────────────────┐ ┌──────────┐ ┌────────────────┐
    │ PipelineBuilder │ │  Runner  │ │ExecutionContext│
    │   (构建阶段)     │ │ (执行器) │ │   (执行上下文)  │
    └─────────────────┘ └──────────┘ └────────────────┘
              │
    ┌─────────┼─────────┬──────────┬──────────┬──────────┐
    ▼         ▼         ▼          ▼          ▼          ▼
┌───────┐ ┌───────┐ ┌───────┐ ┌────────┐ ┌────────┐ ┌────────┐
│ Step  │ │ Step  │ │ Step  │ │ Step   │ │ Step   │ │ Step   │
│ P1    │ │ P2    │ │ P3    │ │ Step1  │ │ Step3  │ │ Step4  │
└───────┘ └───────┘ └───────┘ └────────┘ └────────┘ └────────┘
```

### 核心组件

#### 1. PipelineBuilder (pipeline/orchestrator/builder.py)

职责：构建Pipeline步骤依赖图

```python
class PipelineBuilder:
    def __init__(self):
        self.steps: Dict[str, PipelineStep] = {}
        self.dependencies: Dict[str, List[str]] = {}
    
    def add_step(self, name: str, step: PipelineStep, depends_on: List[str] = None):
        """注册Pipeline步骤"""
        ...
    
    def build(self) -> ExecutionPlan:
        """构建执行计划（拓扑排序）"""
        ...
```

#### 2. PipelineStep 协议 (pipeline/orchestrator/base.py)

```python
from typing import Protocol, Any
from dataclasses import dataclass

@dataclass
class StepInput:
    context: ExecutionContext
    dependencies: Dict[str, Any]

@dataclass  
class StepOutput:
    result: Any
    checkpoint_path: Optional[Path] = None

class PipelineStep(Protocol):
    """Pipeline步骤抽象协议"""
    
    name: str
    
    def execute(self, input_data: StepInput) -> StepOutput:
        """执行步骤"""
        ...
    
    def can_resume(self, checkpoint: Path) -> bool:
        """检查是否可以从检查点恢复"""
        ...
```

#### 3. StepExecutor (pipeline/orchestrator/step_executor.py)

```python
class StepExecutor:
    """步骤执行器，处理同步/异步执行"""
    
    def __init__(self, runner: Optional[Runner] = None):
        self.runner = runner or SequentialRunner()
    
    async def execute_step(self, step: PipelineStep, input_data: StepInput) -> StepOutput:
        """执行单个步骤"""
        ...
    
    async def execute_parallel(self, steps: List[PipelineStep], input_data: StepInput) -> List[StepOutput]:
        """并行执行多个步骤"""
        ...
```

#### 4. Runner抽象 (pipeline/orchestrator/runners/)

```
runners/
├── __init__.py
├── base.py           # Runner抽象基类
├── sequential.py     # 顺序执行器
└── parallel.py       # 并行执行器（基于asyncio）
```

### 数据流

```
输入: Skill Package (SKILL.md + scripts/)
    │
    ▼
┌─────────────┐
│   P1: 引用图 │ ──► FileReferenceGraph
└─────────────┘
    │
    ▼
┌─────────────┐
│   P2: 文件角色│ ──► FileRoleMap  
└─────────────┘
    │
    ▼
┌─────────────┐
│   P3: 包组装 │ ──► SkillPackage
└─────────────┘
    │
    ▼
┌─────────────┐
│ Step1: 结构提取│ ──► SectionBundle
└─────────────┘
    │
    ▼
┌─────────────┐
│ Step3: 实体+工作流│ ──► StructuredSpec
└─────────────┘
    │
    ▼
┌─────────────┐
│ Step4: SPL发射 │ ──► SPLSpec
└─────────────┘
    │
    ▼
输出: {skill_name}.spl
```

### 重构收益

| 指标 | 重构前 | 重构后 | 改进 |
|------|--------|--------|------|
| Orchestrator代码行数 | 238 | <50 | -79% |
| 单元测试覆盖率 | 65% | >80% | +23% |
| 代码重复率 | 35% | <10% | -71% |
| 添加新步骤所需修改文件数 | 3+ | 1 | -67% |

---

## 迁移指南

### 从v1.x迁移到v2.x

#### API变更

**Before**:
```python
from pipeline.orchestrator import run_pipeline, PipelineConfig

config = PipelineConfig(skill_root="skills/pdf", ...)
result = run_pipeline(config)
```

**After**:
```python
from pipeline.orchestrator import PipelineOrchestrator, PipelineConfig
from pipeline.orchestrator.builder import PipelineBuilder

# 方式1: 直接使用（推荐）
config = PipelineConfig(skill_root="skills/pdf", ...)
result = PipelineOrchestrator().run(config)

# 方式2: 自定义Pipeline
builder = PipelineBuilder()
builder.add_step("p1", P1Step())
builder.add_step("p2", P2Step(), depends_on=["p1"])
...

orchestrator = PipelineOrchestrator(builder=builder)
result = orchestrator.run(config)
```

#### 导入路径变更

| 旧路径 | 新路径 |
|--------|--------|
| `from models.data_models import FileNode` | `from models.preprocessing.reference import FileNode` |
| `from models.data_models import SectionBundle` | `from models.pipeline.step1 import SectionBundle` |
| `from models.data_models import EntitySpec` | `from models.pipeline.step3 import EntitySpec` |

### 向后兼容

v2.x提供兼容层：

```python
# 旧导入仍然有效（带弃用警告）
from models.data_models import FileNode  
# 警告: "Deprecated, use models.preprocessing.reference.FileNode"
```

---

## 参考资料

- [Phase A-D 重构计划](./refactor/refactor_plan_v2.md)
- [SPL语法参考](../skills/skill-to-cnlp/references/REFERENCE.md)
```

**预计时间**: 6小时

---

#### 子任务 5.3.3: 生成API文档

**方案**: 使用Sphinx或mkdocstrings自动生成API文档

**文件**: `docs/api/README.md`

```markdown
# API文档

## 自动生成

使用sphinx-apidoc生成API文档：

```bash
# 安装依赖
pip install sphinx sphinx-rtd-theme sphinx-autodoc-typehints

# 生成文档
sphinx-apidoc -o docs/api pipeline/
sphinx-apidoc -o docs/api models/
sphinx-apidoc -o docs/api pre_processing/

# 构建
cd docs && make html
```

## 核心API

### PipelineOrchestrator

```python
class PipelineOrchestrator:
    def run(self, config: PipelineConfig) -> PipelineResult:
        """运行完整Pipeline"""
```

### PipelineBuilder

```python
class PipelineBuilder:
    def add_step(self, name: str, step: PipelineStep, depends_on: List[str] = None) -> None:
        """添加Pipeline步骤"""
```
```

**预计时间**: 4小时

---

#### 子任务 5.3.4: 创建迁移指南

**文件**: `MIGRATION_GUIDE.md`

```markdown
# Skill-to-CNL-P v1.x 到 v2.x 迁移指南

## 概述

v2.x重构引入了：
- 新的Pipeline架构（Builder模式）
- 拆分的数据模型
- 统一的错误处理
- 改进的配置管理

## 快速检查清单

- [ ] 更新导入路径
- [ ] 迁移环境变量配置
- [ ] 更新自定义Pipeline代码
- [ ] 运行回归测试

## 详细步骤

### 1. 更新导入

...

### 2. 配置管理

...

### 3. 自定义Pipeline

...

### 4. 测试更新

...
```

**预计时间**: 2小时

---

### 任务 5.4: 回归测试与最终验收 ⭐核心任务

#### 目标
执行完整的回归测试套件，验证所有功能正常，达到验收标准。

#### 验收标准 (AC)
- [ ] 所有🔴严重问题已修复或缓解
- [ ] 测试覆盖率 >= 80%
- [ ] 性能无回归 (±5%)
- [ ] 代码重复率 < 10%
- [ ] 文档更新完成
- [ ] 向后兼容层工作正常

#### 子任务 5.4.1: 创建回归测试套件

**文件**: `test/regression/test_regression.py`

```python
"""
回归测试套件
验证重构后功能完整性
"""
import pytest
from pathlib import Path
from pipeline.orchestrator import run_pipeline, PipelineConfig
from models.data_models import PipelineResult  # 向后兼容


class TestBackwardCompatibility:
    """向后兼容性测试"""
    
    def test_old_imports_work(self):
        """验证旧导入路径仍然有效"""
        # 这些导入应该工作但发出弃用警告
        from models.data_models import FileNode, SectionBundle
        from models.data_models import PipelineResult as PR
        
        # 基本实例化测试
        node = FileNode(path="test.py", content="test")
        assert node.path == "test.py"
    
    def test_pipeline_api_unchanged(self, pipeline_config_factory):
        """验证Pipeline API行为一致"""
        config = pipeline_config_factory("pdf")
        
        # run_pipeline函数应该继续工作
        result = run_pipeline(config)
        
        assert isinstance(result, PipelineResult)
        assert result.success
        assert result.spl_spec is not None


class TestCoreFunctionality:
    """核心功能回归测试"""
    
    @pytest.mark.parametrize("skill", ["pdf", "docx", "pptx", "xlsx"])
    def test_skill_output_structure(self, skill, pipeline_config_factory):
        """
        验证输出SPL结构正确
        
        AC:
        - 包含所有必需标签
        - 格式正确
        """
        config = pipeline_config_factory(skill)
        result = run_pipeline(config)
        
        spl = result.spl_spec.spl_text
        
        # 必需标签
        required_tags = [
            "[DEFINE_PERSONA:]",
            "[END_PERSONA]",
            "[DEFINE_WORKER:",
        ]
        
        for tag in required_tags:
            assert tag in spl, f"Missing required tag: {tag}"


class TestCheckpointSystem:
    """检查点系统回归测试"""
    
    def test_all_checkpoints_created(self, pipeline_config_factory):
        """验证所有检查点正确生成"""
        config = pipeline_config_factory("pdf")
        run_pipeline(config)
        
        output_dir = Path(config.output_dir)
        expected_files = [
            "p1_graph.json",
            "p2_file_role_map.json", 
            "p3_package.json",
            "step1_bundle.json",
            "step3_structured_spec.json",
            "pdf.spl",
        ]
        
        for f in expected_files:
            assert (output_dir / f).exists(), f"Missing checkpoint: {f}"
```

**预计时间**: 3小时

---

#### 子任务 5.4.2: 创建验收检查清单

**文件**: `design_docs/refactor/phase_e_acceptance_checklist.md`

```markdown
# Phase E 验收检查清单

## 前置条件
- [ ] Phase A-D 所有任务完成
- [ ] 所有单元测试通过
- [ ] 代码审查完成

## 验收项目

### 1. E2E测试
- [ ] 所有20个技能包通过E2E测试
- [ ] 核心技能（pdf, docx）测试通过
- [ ] 恢复机制测试通过
- [ ] 测试时间 < 30分钟

### 2. 性能测试
- [ ] 性能基准建立
- [ ] 与基准对比性能回归 < 5%
- [ ] 内存使用 < 500MB
- [ ] 无内存泄漏

### 3. 文档
- [ ] README.md更新
- [ ] 架构文档更新
- [ ] API文档生成
- [ ] 迁移指南完成

### 4. 代码质量
- [ ] 测试覆盖率 >= 80%
- [ ] 代码重复率 < 10%
- [ ] 类型检查通过 (mypy)
- [ ] 代码风格检查通过 (ruff/black)

### 5. 向后兼容
- [ ] 旧导入路径有效
- [ ] 旧API行为一致
- [ ] 弃用警告正确显示

### 6. 集成
- [ ] 与simplified_pipeline兼容
- [ ] CLI功能完整
- [ ] 程序化API可用

## 签字

| 角色 | 姓名 | 日期 | 签字 |
|------|------|------|------|
| 技术负责人 | | | |
| QA负责人 | | | |
| 产品经理 | | | |
```

**预计时间**: 1小时

---

## 四、时间线

### Day 1 (周一): E2E测试基础

| 时间 | 任务 | 负责人 |
|------|------|--------|
| AM | 5.1.1 配置测试基础设施 | Dev |
| PM | 5.1.2 核心技能E2E测试 | Dev |

### Day 2 (周二): E2E测试完成

| 时间 | 任务 | 负责人 |
|------|------|--------|
| AM | 5.1.3 扩展技能E2E测试 | Dev |
| PM | 5.1.4 恢复机制E2E测试 | Dev |

### Day 3 (周三): 性能测试

| 时间 | 任务 | 负责人 |
|------|------|--------|
| AM | 5.2.1 性能测试框架 | Dev |
| PM | 5.2.2 核心技能性能测试 | Dev |

### Day 4 (周四): 文档更新

| 时间 | 任务 | 负责人 |
|------|------|--------|
| AM | 5.3.1 更新README | Tech Writer |
| PM | 5.3.2 架构文档 | Tech Writer |

### Day 5 (周五): 最终验收

| 时间 | 任务 | 负责人 |
|------|------|--------|
| AM | 5.4.1 回归测试套件 | QA |
| PM | 5.4.2 验收清单签署 | All |

---

## 五、风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| E2E测试发现严重bug | 中 | 高 | 预留1天buffer用于修复 |
| 性能回归超过5% | 低 | 高 | 准备性能分析工具，快速定位 |
| 文档更新不及时 | 中 | 中 | 并行执行，技术写作支持 |
| 技能包测试失败 | 中 | 中 | 优先测试核心技能，其他可延迟 |

---

## 六、依赖关系

```
Phase E 依赖:
├── Phase A (关键修复) ✅
├── Phase B (数据模型) ✅
├── Phase C (Pipeline架构) ✅
└── Phase D (LLM客户端) ✅
```

**注意**: Phase E只能在Phase A-D全部完成后启动。

---

## 七、交付物清单

| 交付物 | 位置 | 验收标准 |
|--------|------|----------|
| E2E测试套件 | `test/e2e/` | 所有测试通过 |
| 性能测试套件 | `test/performance/` | 基准建立 |
| 更新后的README | `README.md` | 技术评审通过 |
| 架构文档v2 | `design_docs/ARCHITECTURE_v2.md` | 架构评审通过 |
| API文档 | `docs/api/` | 自动生成成功 |
| 迁移指南 | `MIGRATION_GUIDE.md` | 用户验证可用 |
| 验收清单 | `phase_e_acceptance_checklist.md` | 签字完成 |

---

## 八、附录

### A. 测试命令速查

```bash
# 运行所有E2E测试
pytest test/e2e/ -v --tb=short

# 运行性能测试（生成基准）
pytest test/performance/ -v --performance-generate-baseline

# 运行回归测试
pytest test/regression/ -v

# 运行完整测试套件
pytest test/ --cov=pipeline --cov=pre_processing --cov=models --cov-report=html

# 生成覆盖率报告
open htmlcov/index.html
```

### B. 性能基准记录

首次运行性能测试时记录：

```bash
# 记录基准
pytest test/performance/ -v --performance-record-baseline

# 基准文件位置
cat test/performance/baseline.json
```

### C. 文档构建

```bash
# 安装文档依赖
pip install -e ".[docs]"

# 构建HTML文档
cd docs && make html

# 查看文档
open docs/_build/html/index.html
```

---

**文档版本**: 1.0  
**最后更新**: 2026-04-19  
**作者**: Architecture Review Team
