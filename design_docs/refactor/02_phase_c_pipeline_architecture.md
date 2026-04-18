# Phase C: Pipeline架构重构 - 详细实施计划

> **版本**: 1.0
> **创建日期**: 2026-04-17
> **预计工期**: Week 6-9（共4周）
> **负责人**: TBD
> **状态**: 等待开始

---

## 1. 项目背景与目标

### 1.1 当前问题

`pipeline/orchestrator.py` 当前存在以下严重架构问题：

| 问题 | 严重程度 | 描述 |
|-----|---------|------|
| **违反SRP** | 🔴 严重 | 403行代码混合了P1-P3、Step 1-4所有逻辑 |
| **违反OCP** | 🔴 严重 | 添加新步骤需要修改此文件 |
| **测试困难** | 🔴 严重 | 无法单独测试单个步骤 |
| **代码难以理解** | 🟡 中等 | 238行连续代码，难以审查 |

### 1.2 重构目标

将单体Orchestrator重构为**可扩展、可测试、职责分离**的Pipeline架构：

- ✅ 单一职责：每个类只负责一件事
- ✅ 开闭原则：新增步骤无需修改现有代码
- ✅ 可测试性：每个组件可独立单元测试
- ✅ 向后兼容：保持`run_pipeline(config)` API不变

---

## 2. 目标架构

### 2.1 新架构概览

```
pipeline/
├── orchestrator.py                 # 保持向后兼容的入口（<50行）
├── orchestrator/                   # 新模块
│   ├── __init__.py                 # 公开API导出
│   ├── base.py                     # PipelineOrchestrator抽象基类
│   ├── config.py                   # 配置管理
│   ├── execution_context.py        # 执行上下文（依赖注入）
│   ├── builder.py                  # PipelineBuilder（建造者模式）
│   ├── dependency_graph.py         # Step依赖图管理
│   ├── step_executor.py            # Step执行抽象
│   ├── step_registry.py            # Step注册表
│   ├── checkpoint.py               # Checkpoint管理器
│   └── runners/
│       ├── __init__.py
│       ├── base.py                 # Runner抽象基类
│       ├── sequential.py           # 顺序执行器
│       └── parallel.py             # 并行执行器
├── steps/                          # Step封装
│   ├── __init__.py
│   ├── p1_reference_graph.py
│   ├── p2_file_roles.py
│   ├── p3_assembler.py
│   ├── step1_structure.py
│   ├── step1_5_api.py
│   ├── step3_workflow.py
│   └── step4_spl.py
└── llm_steps/                      # 现有（保持不变）
```

### 2.2 架构模式

| 模式 | 应用位置 | 目的 |
|-----|---------|------|
| **Builder模式** | `PipelineBuilder` | 逐步构建Pipeline |
| **Registry模式** | `StepRegistry` | 动态Step注册 |
| **Strategy模式** | `Runner` | 切换执行策略（顺序/并行） |
| **Template Method** | `PipelineStep` | 统一Step执行流程 |
| **Dependency Injection** | `ExecutionContext` | 注入依赖（client、logger等） |

---

## 3. 实施计划详情

### 3.1 Week 6: 基础架构搭建

#### 任务 C.1: 创建基础抽象层

**目标**: 定义Pipeline核心抽象（3个文件）

**详细设计**:

##### C.1.1 `pipeline/orchestrator/base.py`

```python
"""Pipeline orchestrator base classes."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pipeline.orchestrator.execution_context import ExecutionContext

T = TypeVar('T')
Output = TypeVar('Output')


class PipelineStep(abc.ABC, Generic[T, Output]):
    """抽象基类：单个Pipeline步骤。
    
    每个步骤都有明确的输入输出类型契约。
    """
    
    @property
    @abc.abstractmethod
    def name(self) -> str:
        """步骤名称，用于日志和checkpoint."""
        ...
    
    @property
    @abc.abstractmethod
    def dependencies(self) -> list[str]:
        """该步骤依赖的其他步骤名称列表."""
        ...
    
    @abc.abstractmethod
    def execute(self, context: ExecutionContext, inputs: T) -> Output:
        """执行步骤逻辑。
        
        Args:
            context: 执行上下文（包含client、logger等）
            inputs: 步骤输入
            
        Returns:
            步骤输出
        """
        ...
    
    def should_skip(self, context: ExecutionContext) -> bool:
        """是否可以跳过此步骤（用于resume_from功能）."""
        return False


class PipelineOrchestrator(abc.ABC):
    """Pipeline编排器抽象基类."""
    
    @abc.abstractmethod
    def run(self, initial_inputs: dict[str, Any]) -> dict[str, Any]:
        """运行完整Pipeline.
        
        Args:
            initial_inputs: 初始输入数据
            
        Returns:
            所有步骤的最终输出集合
        """
        ...
```

##### C.1.2 `pipeline/orchestrator/execution_context.py`

```python
"""Execution context for pipeline steps."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pipeline.llm_client import LLMClient, SessionUsage
from pipeline.orchestrator.config import PipelineConfig


@dataclass(frozen=True)
class ExecutionContext:
    """执行上下文 - 通过依赖注入传递给每个Step.
    
    Attributes:
        client: LLM客户端
        session_usage: Token使用追踪
        config: Pipeline配置
        output_dir: 输出目录
        logger: 日志记录器
        checkpoint_enabled: 是否启用checkpoint
    """
    client: LLMClient
    session_usage: SessionUsage
    config: PipelineConfig
    output_dir: Path
    logger: logging.Logger
    checkpoint_enabled: bool = True
    
    def get_step_logger(self, step_name: str) -> logging.Logger:
        """获取特定步骤的logger."""
        return self.logger.getChild(step_name)
```

##### C.1.3 `pipeline/orchestrator/config.py`

```python
"""Pipeline configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pipeline.llm_client import LLMConfig, StepLLMConfig


@dataclass
class PipelineConfig:
    """重构后的配置类 - 保持与旧版兼容."""
    
    skill_root: str
    output_dir: str
    llm_config: LLMConfig
    step_llm_config: Optional[StepLLMConfig] = None
    save_checkpoints: bool = True
    resume_from: Optional[str] = None
    use_new_step3: bool = False
    
    # 新配置项（有默认值，保持向后兼容）
    max_parallel_workers: int = 4
    enable_detailed_logging: bool = True
    
    def get_step_model(self, step_name: str) -> Optional[str]:
        """获取指定步骤的模型覆盖."""
        if self.step_llm_config is not None:
            return self.step_llm_config.get_model(step_name, self.llm_config.model)
        return None
```

**验收标准**:
- [ ] 所有抽象类定义完整，类型注解正确
- [ ] 单元测试覆盖率 >90%
- [ ] 通过 `mypy` 类型检查

**工期**: 2天

---

#### 任务 C.2: Step注册表与依赖图

**目标**: 实现Step注册和依赖解析（2个文件）

**详细设计**:

##### C.2.1 `pipeline/orchestrator/step_registry.py`

```python
"""Step注册表 - 管理所有可用Step."""
from __future__ import annotations

import logging
from typing import Type, Optional

from pipeline.orchestrator.base import PipelineStep

logger = logging.getLogger(__name__)


class StepRegistry:
    """Pipeline步骤注册表."""
    
    _instance: Optional['StepRegistry'] = None
    _steps: dict[str, Type[PipelineStep]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._steps = {}
        return cls._instance
    
    def register(self, step_class: Type[PipelineStep]) -> Type[PipelineStep]:
        """注册Step类（可用作装饰器）.
        
        Example:
            @registry.register
            class Step1StructureExtraction(PipelineStep[SectionBundle]):
                ...
        """
        name = step_class().name
        self._steps[name] = step_class
        logger.debug("Registered step: %s", name)
        return step_class
    
    def get(self, name: str) -> Type[PipelineStep]:
        """获取已注册的Step类."""
        if name not in self._steps:
            raise KeyError(f"Step '{name}' not registered")
        return self._steps[name]
    
    def list_steps(self) -> list[str]:
        """返回所有已注册步骤名称."""
        return list(self._steps.keys())
    
    def clear(self) -> None:
        """清空注册表（主要用于测试）."""
        self._steps.clear()


# 全局单例
registry = StepRegistry()
```

##### C.2.2 `pipeline/orchestrator/dependency_graph.py`

```python
"""Dependency graph for pipeline steps."""
from __future__ import annotations

from collections import deque
from typing import Type, Optional

from pipeline.orchestrator.base import PipelineStep


class DependencyGraph:
    """步骤依赖图 - 用于确定执行顺序."""
    
    def __init__(self, steps: list[Type[PipelineStep]]):
        self._steps = {step().name: step for step in steps}
        self._graph = self._build_graph()
    
    def _build_graph(self) -> dict[str, set[str]]:
        """构建依赖图."""
        graph = {}
        for name, step_class in self._steps.items():
            step = step_class()
            graph[name] = set(step.dependencies)
        return graph
    
    def topological_sort(self) -> list[str]:
        """返回拓扑排序后的步骤名称."""
        # Kahn算法
        in_degree = {name: 0 for name in self._steps}
        for deps in self._graph.values():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] += 1
        
        queue = deque([name for name, degree in in_degree.items() if degree == 0])
        result = []
        
        while queue:
            current = queue.popleft()
            result.append(current)
            
            for name, deps in self._graph.items():
                if current in deps:
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        queue.append(name)
        
        if len(result) != len(self._steps):
            raise ValueError("Circular dependency detected in pipeline steps")
        
        return result
    
    def get_execution_plan(self, resume_from: Optional[str] = None) -> list[str]:
        """获取执行计划，支持从指定步骤恢复."""
        sorted_steps = self.topological_sort()
        
        if resume_from is None:
            return sorted_steps
        
        # 找到resume_from步骤的索引
        try:
            start_idx = sorted_steps.index(resume_from)
            return sorted_steps[start_idx:]
        except ValueError:
            raise ValueError(f"Resume step '{resume_from}' not found in pipeline")
    
    def get_parallel_groups(self) -> list[list[str]]:
        """将步骤分组为可并行执行的批次.
        
        返回可以并行执行的步骤组，例如:
        [['p1', 'p2'], ['step1'], ['step3a', 'step3b'], ['step4']]
        """
        # TODO: 实现并行分组算法
        pass
```

**验收标准**:
- [ ] 依赖图能正确检测循环依赖
- [ ] `topological_sort()` 返回正确顺序
- [ ] `get_execution_plan()` 支持resume_from功能
- [ ] 单元测试覆盖率 >85%

**工期**: 2天

---

### 3.2 Week 7: Runner实现与Step封装

#### 任务 C.3: Step Executor与Runner实现

**目标**: 实现Step执行器和两种Runner（4个文件）

**详细设计**:

##### C.3.1 `pipeline/orchestrator/step_executor.py`

```python
"""Step execution wrapper."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from pipeline.orchestrator.base import PipelineStep
from pipeline.orchestrator.checkpoint import CheckpointManager
from pipeline.orchestrator.execution_context import ExecutionContext

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """步骤执行结果."""
    step_name: str
    success: bool
    output: Any
    duration_ms: int
    token_usage: int
    error: Optional[str] = None


class StepExecutor:
    """单个步骤的执行器."""
    
    def __init__(
        self,
        checkpoint_manager: Optional[CheckpointManager] = None,
    ):
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
    
    def execute(
        self,
        step: PipelineStep,
        context: ExecutionContext,
        inputs: Any,
    ) -> StepResult:
        """执行单个步骤."""
        step_logger = context.get_step_logger(step.name)
        step_logger.info("Starting execution")
        
        start_time = time.time()
        
        try:
            # 检查是否可以跳过
            if step.should_skip(context):
                step_logger.info("Step skipped")
                return StepResult(
                    step_name=step.name,
                    success=True,
                    output=None,
                    duration_ms=0,
                    token_usage=0,
                )
            
            # 检查checkpoint
            if context.checkpoint_enabled:
                cached = self.checkpoint_manager.load(step.name, context.output_dir)
                if cached is not None:
                    step_logger.info("Restored from checkpoint")
                    return StepResult(
                        step_name=step.name,
                        success=True,
                        output=cached,
                        duration_ms=0,
                        token_usage=0,
                    )
            
            # 执行步骤
            output = step.execute(context, inputs)
            
            # 保存checkpoint
            if context.checkpoint_enabled:
                self.checkpoint_manager.save(step.name, output, context.output_dir)
            
            duration_ms = int((time.time() - start_time) * 1000)
            token_usage = context.session_usage.total.total
            
            step_logger.info("Completed in %dms", duration_ms)
            
            return StepResult(
                step_name=step.name,
                success=True,
                output=output,
                duration_ms=duration_ms,
                token_usage=token_usage,
            )
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            step_logger.error("Failed after %dms: %s", duration_ms, error_msg)
            
            return StepResult(
                step_name=step.name,
                success=False,
                output=None,
                duration_ms=duration_ms,
                token_usage=0,
                error=error_msg,
            )
```

##### C.3.2 `pipeline/orchestrator/runners/base.py`

```python
"""Runner base class."""
from __future__ import annotations

import abc
from typing import Any

from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.step_executor import StepExecutor


class Runner(abc.ABC):
    """Pipeline执行器抽象基类."""
    
    def __init__(self, executor: StepExecutor):
        self.executor = executor
    
    @abc.abstractmethod
    def run(
        self,
        execution_plan: list[str],
        context: ExecutionContext,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """执行Pipeline.
        
        Args:
            execution_plan: 拓扑排序后的步骤名称列表
            context: 执行上下文
            inputs: 初始输入数据
            
        Returns:
            所有步骤的输出结果字典
        """
        ...
```

##### C.3.3 `pipeline/orchestrator/runners/sequential.py`

```python
"""Sequential runner - 按顺序执行每个步骤."""
from __future__ import annotations

import logging
from typing import Any

from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.runners.base import Runner
from pipeline.orchestrator.step_executor import StepExecutor
from pipeline.orchestrator.step_registry import registry

logger = logging.getLogger(__name__)


class SequentialRunner(Runner):
    """顺序执行器 - 每个步骤依次执行."""
    
    def __init__(self, executor: StepExecutor):
        super().__init__(executor)
    
    def run(
        self,
        execution_plan: list[str],
        context: ExecutionContext,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """顺序执行所有步骤."""
        results = {}
        current_inputs = inputs.copy()
        
        for step_name in execution_plan:
            step_class = registry.get(step_name)
            step = step_class()
            
            # 准备输入（从依赖步骤的输出构建）
            step_inputs = self._prepare_inputs(step, results, current_inputs)
            
            # 执行
            result = self.executor.execute(step, context, step_inputs)
            
            if not result.success:
                raise RuntimeError(
                    f"Step '{step_name}' failed: {result.error}"
                )
            
            results[step_name] = result.output
        
        return results
    
    def _prepare_inputs(
        self,
        step: 'PipelineStep',
        previous_results: dict[str, Any],
        initial_inputs: dict[str, Any],
    ) -> Any:
        """根据步骤依赖准备输入."""
        # 如果步骤没有依赖，返回初始输入
        if not step.dependencies:
            return initial_inputs
        
        # 否则，从依赖步骤的输出构建输入
        # 具体逻辑根据实际步骤需求实现
        return previous_results
```

##### C.3.4 `pipeline/orchestrator/runners/parallel.py`

```python
"""Parallel runner - 并行执行无依赖的步骤."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.runners.base import Runner
from pipeline.orchestrator.step_executor import StepExecutor
from pipeline.orchestrator.step_registry import registry

logger = logging.getLogger(__name__)


class ParallelRunner(Runner):
    """并行执行器 - 使用ThreadPoolExecutor."""
    
    def __init__(self, executor: StepExecutor, max_workers: int = 4):
        super().__init__(executor)
        self.max_workers = max_workers
    
    def run(
        self,
        execution_plan: list[str],
        context: ExecutionContext,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """执行Pipeline，并行化可并行的步骤."""
        results = {}
        remaining = execution_plan.copy()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            while remaining:
                # 找出当前可执行的步骤（依赖已完成）
                ready = self._get_ready_steps(remaining, results)
                
                if not ready:
                    raise RuntimeError("Deadlock detected in pipeline execution")
                
                # 提交并行执行
                futures = {
                    pool.submit(self._execute_step, name, context, results, inputs): name
                    for name in ready
                }
                
                # 收集结果
                for future in as_completed(futures):
                    step_name = futures[future]
                    try:
                        output = future.result()
                        results[step_name] = output
                    except Exception as e:
                        logger.error("Step %s failed: %s", step_name, e)
                        raise
                
                # 从remaining中移除已完成的步骤
                for name in ready:
                    remaining.remove(name)
        
        return results
    
    def _get_ready_steps(
        self,
        remaining: list[str],
        completed: dict[str, Any],
    ) -> list[str]:
        """找出当前可以执行的步骤."""
        ready = []
        for step_name in remaining:
            step_class = registry.get(step_name)
            step = step_class()
            
            # 检查依赖是否都已完成
            if all(dep in completed for dep in step.dependencies):
                ready.append(step_name)
        
        return ready
    
    def _execute_step(
        self,
        step_name: str,
        context: ExecutionContext,
        completed: dict[str, Any],
        initial_inputs: dict[str, Any],
    ) -> Any:
        """执行单个步骤（用于线程池）."""
        step_class = registry.get(step_name)
        step = step_class()
        
        # 准备输入
        step_inputs = self._prepare_inputs(step, completed, initial_inputs)
        
        # 执行
        result = self.executor.execute(step, context, step_inputs)
        
        if not result.success:
            raise RuntimeError(f"Step '{step_name}' failed: {result.error}")
        
        return result.output
    
    def _prepare_inputs(self, step, completed, initial_inputs):
        """准备步骤输入."""
        # 类似SequentialRunner的实现
        pass
```

**验收标准**:
- [ ] SequentialRunner通过单元测试
- [ ] ParallelRunner正确处理依赖关系
- [ ] 错误处理：步骤失败时抛出有意义的异常
- [ ] 测试覆盖率 >80%

**工期**: 3天

---

#### 任务 C.4: Checkpoint管理器

**目标**: 将checkpoint逻辑从orchestrator中分离

**详细设计**:

##### C.4.1 `pipeline/orchestrator/checkpoint.py`

```python
"""Checkpoint management."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional
from dataclasses import asdict

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Checkpoint管理器."""
    
    def __init__(self, serializer: Optional[callable] = None):
        self.serializer = serializer or self._default_serializer
    
    def _default_serializer(self, obj: Any) -> str:
        """默认序列化器."""
        if hasattr(obj, "__dataclass_fields__"):
            return json.dumps(asdict(obj), indent=2, ensure_ascii=False)
        return json.dumps(obj, indent=2, ensure_ascii=False)
    
    def save(self, step_name: str, data: Any, output_dir: Path) -> Path:
        """保存checkpoint."""
        checkpoint_path = output_dir / f"{step_name}.json"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            content = self.serializer(data)
            checkpoint_path.write_text(content, encoding="utf-8")
            logger.debug("Checkpoint saved: %s", checkpoint_path)
            return checkpoint_path
        except Exception as e:
            logger.warning("Failed to save checkpoint for %s: %s", step_name, e)
            raise
    
    def load(self, step_name: str, output_dir: Path) -> Optional[Any]:
        """加载checkpoint."""
        checkpoint_path = output_dir / f"{step_name}.json"
        
        if not checkpoint_path.exists():
            return None
        
        try:
            content = checkpoint_path.read_text(encoding="utf-8")
            return json.loads(content)
        except Exception as e:
            logger.warning("Failed to load checkpoint for %s: %s", step_name, e)
            return None
    
    def exists(self, step_name: str, output_dir: Path) -> bool:
        """检查checkpoint是否存在."""
        checkpoint_path = output_dir / f"{step_name}.json"
        return checkpoint_path.exists()
    
    def clear(self, output_dir: Path) -> None:
        """清除所有checkpoint."""
        import shutil
        if output_dir.exists():
            shutil.rmtree(output_dir)
            logger.info("Cleared checkpoints: %s", output_dir)
```

**验收标准**:
- [ ] 支持dataclass序列化
- [ ] 错误处理：保存/加载失败时记录警告但不中断
- [ ] 单元测试覆盖率 >90%

**工期**: 1天

---

### 3.3 Week 8: Step封装与Builder实现

#### 任务 C.5: 将现有步骤封装为PipelineStep

**目标**: 将现有函数式步骤封装为PipelineStep类

**步骤列表**:

| 步骤 | 类名 | 依赖 | 输入 | 输出 |
|-----|------|-----|-----|------|
| P1 | P1ReferenceGraphStep | [] | skill_root | FileReferenceGraph |
| P2 | P2FileRolesStep | [p1] | P1 output | FileRoleMap |
| P3 | P3AssemblerStep | [p2] | P2 output | SkillPackage |
| Step 1 | Step1StructureStep | [p3] | SkillPackage | SectionBundle |
| Step 1.5 | Step1_5APIGenStep | [step1] | SectionBundle, tools | APITable |
| Step 3 | Step3WorkflowStep | [step1] | SectionBundle | StructuredSpec |
| Step 4 | Step4SPLStep | [step3, step1.5] | StructuredSpec, APITable | SPLSpec |

**详细设计示例**（以P1为例）:

```python
# pipeline/orchestrator/steps/p1_reference_graph.py
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from pipeline.orchestrator.base import PipelineStep
from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.step_registry import registry
from pre_processing.p1_reference_graph import build_reference_graph


@registry.register
class P1ReferenceGraphStep(PipelineStep[Any, dict]):
    """P1: Reference Graph构建步骤."""
    
    @property
    def name(self) -> str:
        return "p1_reference_graph"
    
    @property
    def dependencies(self) -> list[str]:
        return []  # P1没有依赖
    
    def execute(self, context: ExecutionContext, inputs: Any) -> dict:
        """执行P1."""
        skill_root = context.config.skill_root
        context.logger.info("[P1] Building reference graph...")
        
        graph = build_reference_graph(skill_root)
        
        context.logger.info(
            "[P1] Found %d files, %d doc edges",
            len(graph.nodes),
            len(graph.edges)
        )
        
        # 转换为dict以便序列化
        return {
            "skill_id": graph.skill_id,
            "nodes": [asdict(node) for node in graph.nodes],
            "edges": [asdict(edge) for edge in graph.edges],
        }
```

**验收标准**:
- [ ] 所有现有步骤都有对应的PipelineStep封装
- [ ] 依赖关系正确配置
- [ ] 每个步骤单元测试覆盖率 >80%

**工期**: 3天

---

#### 任务 C.6: PipelineBuilder实现

**目标**: 实现Builder模式用于构建Pipeline

**详细设计**:

##### C.6.1 `pipeline/orchestrator/builder.py`

```python
"""Pipeline builder."""
from __future__ import annotations

import logging
from typing import Any, Optional, Type
from pathlib import Path

from pipeline.orchestrator.base import PipelineStep, PipelineOrchestrator
from pipeline.orchestrator.checkpoint import CheckpointManager
from pipeline.orchestrator.config import PipelineConfig
from pipeline.orchestrator.dependency_graph import DependencyGraph
from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.runners.base import Runner
from pipeline.orchestrator.runners.parallel import ParallelRunner
from pipeline.orchestrator.runners.sequential import SequentialRunner
from pipeline.orchestrator.step_executor import StepExecutor
from pipeline.orchestrator.step_registry import StepRegistry
from pipeline.llm_client import LLMClient, SessionUsage

logger = logging.getLogger(__name__)


class PipelineBuilder:
    """Pipeline构建器."""
    
    def __init__(self):
        self._steps: list[Type[PipelineStep]] = []
        self._config: Optional[PipelineConfig] = None
        self._runner_type: str = "sequential"
        self._max_workers: int = 4
        self._enable_checkpoints: bool = True
    
    def with_config(self, config: PipelineConfig) -> 'PipelineBuilder':
        """设置配置."""
        self._config = config
        return self
    
    def with_runner(self, runner_type: str, max_workers: int = 4) -> 'PipelineBuilder':
        """设置执行器类型."""
        self._runner_type = runner_type
        self._max_workers = max_workers
        return self
    
    def with_steps(self, *steps: Type[PipelineStep]) -> 'PipelineBuilder':
        """添加步骤."""
        self._steps.extend(steps)
        return self
    
    def with_checkpointing(self, enabled: bool = True) -> 'PipelineBuilder':
        """启用/禁用checkpoint."""
        self._enable_checkpoints = enabled
        return self
    
    def build(self) -> PipelineOrchestrator:
        """构建Pipeline."""
        if self._config is None:
            raise ValueError("Config is required")
        
        # 创建执行上下文
        session_usage = SessionUsage()
        client = LLMClient(
            config=self._config.llm_config,
            session_usage=session_usage
        )
        
        context = ExecutionContext(
            client=client,
            session_usage=session_usage,
            config=self._config,
            output_dir=Path(self._config.output_dir),
            logger=logger,
            checkpoint_enabled=self._enable_checkpoints,
        )
        
        # 创建执行器
        executor = StepExecutor(
            checkpoint_manager=CheckpointManager() if self._enable_checkpoints else None
        )
        
        # 创建runner
        runner: Runner
        if self._runner_type == "parallel":
            runner = ParallelRunner(executor, max_workers=self._max_workers)
        else:
            runner = SequentialRunner(executor)
        
        # 构建依赖图
        dependency_graph = DependencyGraph(self._steps)
        
        # 创建编排器
        return ConcretePipelineOrchestrator(
            context=context,
            runner=runner,
            dependency_graph=dependency_graph,
            resume_from=self._config.resume_from,
        )


class ConcretePipelineOrchestrator(PipelineOrchestrator):
    """具体实现."""
    
    def __init__(
        self,
        context: ExecutionContext,
        runner: Runner,
        dependency_graph: DependencyGraph,
        resume_from: Optional[str] = None,
    ):
        self.context = context
        self.runner = runner
        self.dependency_graph = dependency_graph
        self.resume_from = resume_from
    
    def run(self, initial_inputs: dict[str, Any]) -> dict[str, Any]:
        """运行Pipeline."""
        # 获取执行计划
        execution_plan = self.dependency_graph.get_execution_plan(self.resume_from)
        logger.info("Pipeline execution plan: %s", execution_plan)
        
        # 执行
        return self.runner.run(
            execution_plan=execution_plan,
            context=self.context,
            inputs=initial_inputs,
        )
```

**验收标准**:
- [ ] Builder模式正确实现（链式调用）
- [ ] 支持sequential和parallel两种runner
- [ ] 支持resume_from配置
- [ ] 单元测试覆盖率 >85%

**工期**: 2天

---

### 3.4 Week 9: 集成与兼容性层

#### 任务 C.7: 向后兼容层（重构orchestrator.py入口）

**目标**: 重构后的orchestrator.py保持与原API完全兼容

**详细设计**:

##### C.7.1 `pipeline/orchestrator.py`

```python
"""skill-to-CNL-P pipeline orchestrator.

重构后的入口文件 - 保持与原API完全兼容。
所有逻辑已移至pipeline/orchestrator/模块。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from pipeline.llm_client import LLMClient, LLMConfig, SessionUsage, StepLLMConfig
from models import PipelineResult

# 导入新的架构组件
from pipeline.orchestrator.builder import PipelineBuilder
from pipeline.orchestrator.config import PipelineConfig as NewPipelineConfig
from pipeline.orchestrator.steps.p1_reference_graph import P1ReferenceGraphStep
from pipeline.orchestrator.steps.p2_file_roles import P2FileRolesStep
from pipeline.orchestrator.steps.p3_assembler import P3AssemblerStep
from pipeline.orchestrator.steps.step1_structure import Step1StructureStep
from pipeline.orchestrator.steps.step3_workflow import Step3WorkflowStep
from pipeline.orchestrator.steps.step4_spl import Step4SPLStep

logger = logging.getLogger(__name__)


# 保持与原API兼容的配置类
class PipelineConfig:
    """Configuration for a pipeline run.
    
    注意：此类保持与原API兼容，内部已委托给新配置类。
    """
    
    def __init__(
        self,
        skill_root: str,
        output_dir: str,
        llm_config: LLMConfig,
        step_llm_config: Optional[StepLLMConfig] = None,
        save_checkpoints: bool = True,
        resume_from: Optional[str] = None,
        use_new_step3: bool = False,
    ):
        self.skill_root = skill_root
        self.output_dir = output_dir
        self.llm_config = llm_config
        self.step_llm_config = step_llm_config
        self.save_checkpoints = save_checkpoints
        self.resume_from = resume_from
        self.use_new_step3 = use_new_step3
        
        # 内部新配置实例
        self._new_config = NewPipelineConfig(
            skill_root=skill_root,
            output_dir=output_dir,
            llm_config=llm_config,
            step_llm_config=step_llm_config,
            save_checkpoints=save_checkpoints,
            resume_from=resume_from,
            use_new_step3=use_new_step3,
        )


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Execute the full skill-to-CNL-P pipeline.
    
    保持与原API完全兼容。
    
    Args:
        config: PipelineConfig describing the skill to process and run options.
        
    Returns:
        PipelineResult containing all intermediate and final outputs.
    """
    logger.info("=== skill-to-CNL-P pipeline start: %s ===", config.skill_root)
    
    # 使用新的Builder构建Pipeline
    builder = PipelineBuilder()
    
    # 注册所有步骤
    orchestrator = (
        builder
        .with_config(config._new_config)
        .with_steps(
            P1ReferenceGraphStep,
            P2FileRolesStep,
            P3AssemblerStep,
            Step1StructureStep,
            Step3WorkflowStep,
            Step4SPLStep,
        )
        .with_runner(
            runner_type="parallel",
            max_workers=config._new_config.max_parallel_workers,
        )
        .with_checkpointing(config.save_checkpoints)
        .build()
    )
    
    # 执行
    results = orchestrator.run(initial_inputs={})
    
    # 构建PipelineResult（保持与原API兼容）
    return _build_pipeline_result(results, config)


def _build_pipeline_result(
    results: dict[str, Any],
    config: PipelineConfig,
) -> PipelineResult:
    """将新架构结果转换为旧的PipelineResult格式."""
    # TODO: 从results中提取各部分并组装
    # 保持与原PipelineResult字段一致
    pass
```

**验收标准**:
- [ ] `run_pipeline(config)` API签名完全一致
- [ ] `PipelineConfig` 类属性完全一致
- [ ] 现有测试套件通过（无需修改测试代码）
- [ ] 生成的SPL输出与原实现完全一致

**工期**: 3天

---

#### 任务 C.8: 集成测试与回归测试

**目标**: 确保重构不引入功能回归

**测试策略**:

| 测试类型 | 覆盖内容 | 目标覆盖率 |
|---------|---------|-----------|
| 单元测试 | 每个新模块独立测试 | >80% |
| 集成测试 | Step之间协作 | >70% |
| 回归测试 | 与旧orchestrator输出对比 | 100%通过 |
| E2E测试 | 完整技能包处理 | 通过示例技能 |

**回归测试计划**:
1. 选择3个示例技能（pdf, docx, xlsx）
2. 分别用旧实现和新实现处理
3. 对比输出SPL（语义等价，可能有格式差异）
4. 确保功能一致性

**验收标准**:
- [ ] 所有新模块单元测试通过率100%
- [ ] 整体测试覆盖率 >80%
- [ ] 回归测试：新旧实现输出语义等价
- [ ] E2E测试：pdf/docx/xlsx技能通过

**工期**: 2天

---

## 4. 文件变更清单

### 4.1 新建文件（Week 6-8）

```
pipeline/
├── orchestrator/                    # 新模块
│   ├── __init__.py
│   ├── base.py                      # PipelineOrchestrator抽象
│   ├── config.py                    # 配置管理
│   ├── execution_context.py         # 执行上下文
│   ├── builder.py                   # PipelineBuilder
│   ├── dependency_graph.py          # 依赖图管理
│   ├── step_executor.py             # Step执行器
│   ├── step_registry.py             # Step注册表
│   ├── checkpoint.py                # Checkpoint管理器
│   └── runners/
│       ├── __init__.py
│       ├── base.py                  # Runner抽象
│       ├── sequential.py            # 顺序执行器
│       └── parallel.py              # 并行执行器
└── steps/                           # Step封装
    ├── __init__.py
    ├── p1_reference_graph.py
    ├── p2_file_roles.py
    ├── p3_assembler.py
    ├── step1_structure.py
    ├── step1_5_api.py
    ├── step3_workflow.py
    └── step4_spl.py
```

### 4.2 修改文件（Week 9）

```
pipeline/
└── orchestrator.py                  # 重写为兼容层（<50行业务逻辑）
```

---

## 5. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|-----|-------|-----|---------|
| API不兼容 | 中 | 高 | 详尽的向后兼容测试；特性开关 |
| 性能下降 | 低 | 中 | 基准测试；性能对比 |
| Step封装遗漏 | 中 | 高 | 完整步骤清单检查；逐步迁移 |
| 并发问题 | 低 | 高 | ThreadPoolExecutor正确使用；资源隔离 |

---

## 6. 里程碑与检查点

| Week | 里程碑 | 检查点 |
|-----|-------|-------|
| **Week 6结束** | 基础架构完成 | • 抽象层设计评审通过<br>• 所有基础类单元测试通过 |
| **Week 7结束** | Runner实现完成 | • Sequential/Parallel Runner通过测试<br>• Checkpoint功能验证 |
| **Week 8结束** | Step封装完成 | • 所有步骤封装为PipelineStep<br>• Builder模式功能验证 |
| **Week 9结束** | 集成完成 | • 旧测试套件100%通过<br>• 回归测试通过<br>• 代码覆盖率>80% |

---

## 7. 相关文档

- [重构计划总览](./01_refactor_plan_overview.md) - 完整重构计划
- [AGENTS.md](../pipeline/AGENTS.md) - Pipeline模块知识库
- [AGENTS.md](../../AGENTS.md) - 项目知识库

---

**文档版本**: 1.0
**最后更新**: 2026-04-17
**作者**: Sisyphus
