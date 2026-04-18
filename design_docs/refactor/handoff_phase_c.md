# Phase C重构启动 - 上下文交接文档

> **创建日期**: 2026-04-17
> **创建会话**: [当前会话]
> **用途**: 供新会话启动Phase C重构
> **状态**: ✅ 准备就绪，可随时启动

---

## 1. 项目基本信息

```yaml
Project: skill-to-cnlp
Location: C:\WorkingLocation\UGAiForge\nl2spl_improve\skill_to_cnlp
Language: Python 3.11+
Purpose: Normalize Claude skill packages into SPL/CNL-P specifications
Git Repo: Yes (当前分支: 请确认)
```

**关键路径**:
- 详细计划: `design_docs/refactor/02_phase_c_pipeline_architecture.md`
- 原Orchestrator: `pipeline/orchestrator.py` (403行，需要重构)
- 新项目结构将建在: `pipeline/orchestrator/` (还不存在，需创建)

---

## 2. Phase C重构目标

### 2.1 核心目标
将 `pipeline/orchestrator.py` (403行) 重构为可扩展的Pipeline架构：

**当前问题**:
- 违反SRP - 混合了所有预处理(P1-P3)和LLM步骤(Step 1-4)的逻辑
- 测试困难 - 无法单独测试单个步骤
- 扩展困难 - 添加新步骤需修改此文件

**目标架构**:
```
pipeline/
├── orchestrator.py              # 保持向后兼容的入口（<50行）✅
└── orchestrator/                # 新模块（新建）📁
    ├── __init__.py
    ├── base.py                  # PipelineStep抽象基类
    ├── config.py                # 配置管理
    ├── execution_context.py     # 执行上下文（依赖注入）
    ├── builder.py               # PipelineBuilder（Builder模式）
    ├── dependency_graph.py      # Step依赖图管理
    ├── step_executor.py         # Step执行器
    ├── step_registry.py         # Step注册表（单例模式）
    ├── checkpoint.py            # Checkpoint管理
    └── runners/                 # 执行器策略
        ├── __init__.py
        ├── base.py              # Runner抽象
        ├── sequential.py        # 顺序执行
        └── parallel.py          # 并行执行（ThreadPoolExecutor）
```

### 2.2 设计模式
- **Builder模式**: `PipelineBuilder` - 逐步构建Pipeline
- **Registry模式**: `StepRegistry` - 动态Step注册
- **Strategy模式**: `Runner` - 切换顺序/并行执行
- **Dependency Injection**: `ExecutionContext` - 注入依赖

---

## 3. 详细任务清单（4周计划）

### Week 6: 基础架构搭建

#### 任务 C.1: 创建基础抽象层 (2天)
**目标**: 创建3个核心抽象文件

**步骤**: 1. 创建 `pipeline/orchestrator/base.py` - 定义 `PipelineStep` 抽象基类
2. 创建 `pipeline/orchestrator/execution_context.py` - 定义 `ExecutionContext` 数据类
3. 创建 `pipeline/orchestrator/config.py` - 定义新的 `PipelineConfig`

**验收标准**:
- [ ] 所有抽象类有完整的类型注解
- [ ] 通过 `mypy` 类型检查
- [ ] 单元测试覆盖率 >90%

**关键代码模式** (参考详细计划文档):
```python
class PipelineStep(abc.ABC, Generic[T, Output]):
    @property
    @abc.abstractmethod
    def name(self) -> str: ...
    
    @property
    @abc.abstractmethod  
    def dependencies(self) -> list[str]: ...
    
    @abc.abstractmethod
    def execute(self, context: ExecutionContext, inputs: T) -> Output: ...
```

---

#### 任务 C.2: Step注册表与依赖图 (2天)
**目标**: 实现Step注册和依赖解析

**步骤**:
1. 创建 `pipeline/orchestrator/step_registry.py` - Step注册表（单例模式）
2. 创建 `pipeline/orchestrator/dependency_graph.py` - 依赖图管理

**验收标准**:
- [ ] 依赖图能正确检测循环依赖
- [ ] `topological_sort()` 返回正确顺序
- [ ] `get_execution_plan()` 支持resume_from功能
- [ ] 单元测试覆盖率 >85%

---

### Week 7: Runner实现与Checkpoint管理

#### 任务 C.3: Step Executor与Runner (3天)
**目标**: 实现Step执行器和两种Runner

**步骤**:
1. 创建 `pipeline/orchestrator/step_executor.py` - Step执行器
2. 创建 `pipeline/orchestrator/runners/base.py` - Runner抽象
3. 创建 `pipeline/orchestrator/runners/sequential.py` - 顺序执行器
4. 创建 `pipeline/orchestrator/runners/parallel.py` - 并行执行器

**验收标准**:
- [ ] SequentialRunner通过单元测试
- [ ] ParallelRunner正确处理依赖关系
- [ ] 错误处理：步骤失败时抛出有意义的异常
- [ ] 单元测试覆盖率 >80%

---

#### 任务 C.4: Checkpoint管理器 (1天)
**目标**: 将checkpoint逻辑从orchestrator中分离

**步骤**:
1. 创建 `pipeline/orchestrator/checkpoint.py`

**验收标准**:
- [ ] 支持dataclass序列化
- [ ] 错误处理：保存/加载失败时记录警告但不中断
- [ ] 单元测试覆盖率 >90%

---

### Week 8: Step封装与Builder实现

#### 任务 C.5: 封装现有步骤为PipelineStep (3天)
**目标**: 将现有函数式步骤封装为PipelineStep类

**步骤**:
创建 `pipeline/steps/` 目录，并封装以下步骤：

| 步骤 | 类名 | 依赖 |
|-----|------|-----|
| P1 | `P1ReferenceGraphStep` | [] |
| P2 | `P2FileRolesStep` | [p1_reference_graph] |
| P3 | `P3AssemblerStep` | [p2_file_roles] |
| Step 1 | `Step1StructureStep` | [p3_assembler] |
| Step 1.5 | `Step1_5APIGenStep` | [step1_structure] |
| Step 3 | `Step3WorkflowStep` | [step1_structure] |
| Step 4 | `Step4SPLStep` | [step3_workflow, step1_5_api] |

**使用装饰器注册**:
```python
from pipeline.orchestrator.step_registry import registry

@registry.register
class P1ReferenceGraphStep(PipelineStep[Any, dict]):
    @property
    def name(self) -> str:
        return "p1_reference_graph"
    
    @property
    def dependencies(self) -> list[str]:
        return []
```

**验收标准**:
- [ ] 所有现有步骤都有对应的PipelineStep封装
- [ ] 依赖关系正确配置
- [ ] 每个步骤单元测试覆盖率 >80%

---

#### 任务 C.6: PipelineBuilder实现 (2天)
**目标**: 实现Builder模式用于构建Pipeline

**步骤**:
1. 创建 `pipeline/orchestrator/builder.py`

**关键特性**:
- 链式调用API: `builder.with_config(...).with_steps(...).build()`
- 支持sequential和parallel两种runner
- 支持resume_from配置

**验收标准**:
- [ ] Builder模式正确实现
- [ ] 支持sequential和parallel两种runner
- [ ] 支持resume_from配置
- [ ] 单元测试覆盖率 >85%

---

### Week 9: 集成与兼容性层

#### 任务 C.7: 向后兼容层 (3天)
**目标**: 重构 `pipeline/orchestrator.py` 为兼容层

**步骤**:
1. 重写 `pipeline/orchestrator.py` 为新架构的入口
2. 保持原API完全兼容:
   - `run_pipeline(config)` 函数签名不变
   - `PipelineConfig` 类属性不变
3. 使用Builder构建Pipeline
4. 从results构建 `PipelineResult`

**关键约束**:
- ⚠️ **文件内容必须<50行业务逻辑**
- ⚠️ **现有测试套件必须100%通过**
- ⚠️ **生成的SPL输出必须与原实现完全一致**

**验收标准**:
- [ ] `run_pipeline(config)` API签名完全一致
- [ ] `PipelineConfig` 类属性完全一致
- [ ] 现有测试套件通过（无需修改测试代码）
- [ ] 生成的SPL输出与原实现完全一致

---

#### 任务 C.8: 集成测试与回归测试 (2天)
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
3. 对比输出SPL（语义等价）
4. 确保功能一致性

**验收标准**:
- [ ] 所有新模块单元测试通过率100%
- [ ] 整体测试覆盖率 >80%
- [ ] 回归测试：新旧实现输出语义等价
- [ ] E2E测试：pdf/docx/xlsx技能通过

---

## 4. 启动时需要执行的命令

### 4.1 创建目录结构
```bash
cd C:\WorkingLocation\UGAiForge\nl2spl_improve\skill_to_cnlp

# 创建新模块目录
mkdir -p pipeline/orchestrator/runners
mkdir -p pipeline/steps

# 初始化 __init__.py
touch pipeline/orchestrator/__init__.py
touch pipeline/orchestrator/runners/__init__.py
touch pipeline/steps/__init__.py
```

### 4.2 安装依赖（如有需要）
```bash
pip install -e .
```

---

## 5. 从哪个文件开始

**建议启动顺序**:

### Week 6 Day 1: 从 base.py 开始
```python
# pipeline/orchestrator/base.py
"""Pipeline orchestrator base classes."""
from __future__ import annotations

import abc
from typing import Any, Generic, TypeVar

from pipeline.orchestrator.execution_context import ExecutionContext

T = TypeVar('T')
Output = TypeVar('Output')


class PipelineStep(abc.ABC, Generic[T, Output]):
    """抽象基类：单个Pipeline步骤。"""
    
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
        """执行步骤逻辑。"""
        ...
    
    def should_skip(self, context: ExecutionContext) -> bool:
        """是否可以跳过此步骤（用于resume_from功能）."""
        return False


class PipelineOrchestrator(abc.ABC):
    """Pipeline编排器抽象基类."""
    
    @abc.abstractmethod
    def run(self, initial_inputs: dict[str, Any]) -> dict[str, Any]:
        """运行完整Pipeline."""
        ...
```

---

## 6. 需要注意的事项

### 6.1 向后兼容性 (⚠️ 关键)
- **必须**保持 `run_pipeline(config)` 函数签名完全一致
- **必须**保持 `PipelineConfig` 类属性完全一致
- 现有代码使用方式必须无需修改即可工作
- 建议在 `orchestrator.py` 中保留旧的导入导出

### 6.2 类型注解
- 所有公共函数/方法必须有类型注解
- 使用 `from __future__ import annotations` 支持Python 3.11+特性
- 运行 `mypy` 检查类型正确性

### 6.3 测试策略
- **每个新模块**必须有单元测试
- 测试覆盖率目标: >80%
- 使用 `pytest` 运行测试
- 旧测试套件在新实现上必须100%通过

### 6.4 代码规范
- 遵循项目现有风格（参考 `AGENTS.md`）
- 使用 `logger = logging.getLogger(__name__)` 模式
- 文档字符串使用Google风格
- 禁止 `print()`，使用 `logger.debug()`

### 6.5 并行执行
- Step 4的并行逻辑需要特别注意线程安全
- 使用 `ThreadPoolExecutor` 时注意资源管理
- 保持与原 `orchestrator.py` 相同的并行执行语义

---

## 7. 参考资源

### 文档
- **详细实施计划**: `design_docs/refactor/02_phase_c_pipeline_architecture.md`
- **重构计划总览**: `design_docs/refactor/01_refactor_plan_overview.md`
- **项目知识库**: `AGENTS.md`
- **Pipeline知识库**: `pipeline/AGENTS.md`

### 源代码参考
- **原Orchestrator**: `pipeline/orchestrator.py` (403行)
- **LLM Client**: `pipeline/llm_client.py`
- **现有Step实现**: `pipeline/llm_steps/`

### 示例技能
```
skills/
├── pdf/               # 用于回归测试
├── docx/              # 用于回归测试
└── xlsx/              # 用于回归测试
```

---

## 8. 快速检查清单

在开始新会话前，确认：

- [ ] 当前工作目录是 `C:\WorkingLocation\UGAiForge\nl2spl_improve\skill_to_cnlp`
- [ ] Python版本 >= 3.11
- [ ] 依赖已安装 (`pip install -e .`)
- [ ] 已阅读 `design_docs/refactor/02_phase_c_pipeline_architecture.md`
- [ ] 理解向后兼容性的重要性
- [ ] 知道从哪个文件开始（`pipeline/orchestrator/base.py`）

---

## 9. 常见问题

### Q: 我可以修改现有测试代码吗？
**A**: 尽量不要。新架构应该能通过现有测试，如果测试失败，说明新实现与原实现不兼容。

### Q: 如果我发现原实现有bug怎么办？
**A**: 先记录，不要在新架构中修复。先保持行为一致，重构完成后再考虑修复。

### Q: 我必须按周实施吗？
**A**: 文档中的"周"是规划单位，你可以根据自己的节奏实施，但建议按任务顺序进行。

### Q: 我可以跳过某些任务吗？
**A**: 不建议。每个任务都有依赖关系，跳过可能导致后续工作困难。

---

## 10. 联系与支持

如果在实施过程中遇到问题：
1. 参考详细计划文档中的"详细设计"章节
2. 查看原 `orchestrator.py` 了解当前实现
3. 检查 `pipeline/AGENTS.md` 了解项目约定

---

**祝重构顺利！**
