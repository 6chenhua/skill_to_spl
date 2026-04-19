# 旧代码清理计划

> **版本**: 1.0
> **创建日期**: 2026-04-19
> **预计工期**: 2-3 周
> **状态**: 计划中

---

## 1. 现状分析

### 1.1 发现的旧代码文件

| 文件 | 大小 | 说明 | 风险等级 |
|------|------|------|----------|
| `pipeline/orchestrator.py` | 17,268 bytes | 旧实现（已被新架构替代） | ⚠️ **高** - 需要检查向后兼容 |
| `pipeline/steps.py.bak` | 33,644 bytes | 备份文件 | ✅ **低** - 可安全删除 |
| `models/data_models.py` | 4,707 bytes | 标记为 deprecated 的兼容层 | ⚠️ **中** - 检查是否还有导入 |
| `models/deprecated.py` | 4,350 bytes | 向后兼容代码 | ⚠️ **中** - 检查是否还有导入 |

---

## 2. 分阶段清理计划

### Phase 1: 低风险清理（第1周）

**目标**: 删除明显的备份和临时文件

#### 任务 1.1: 删除备份文件

**文件**: `pipeline/steps.py.bak`

- **操作**: 直接删除
- **风险**: 极低
- **验证**: 确保没有代码引用此文件
- **回滚**: 从 git 恢复

```bash
# 删除前验证
python -c "import ast; ast.parse(open('pipeline/steps.py.bak').read())"

# 检查是否被引用
grep -r "steps.py.bak" --include="*.py" .

# 执行删除
git rm pipeline/steps.py.bak
```

#### 任务 1.2: 清理临时文件

检查并删除其他临时文件：
- `*.pyc`
- `__pycache__/`
- `*.log`
- `.pytest_cache/`

```bash
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} +
```

#### Phase 1 验收标准

- [ ] `pipeline/steps.py.bak` 已删除
- [ ] 所有临时文件已清理
- [ ] `pytest test/` 通过
- [ ] 端到端测试通过（运行 main.py）

---

### Phase 2: 废弃模块清理（第1-2周）

**目标**: 移除 deprecated 兼容层

#### 任务 2.1: 分析 models/data_models.py 使用情况

**当前状态**:
```python
# models/data_models.py
"""Backward compatibility layer for model imports.

DEPRECATED: This module will be removed in v3.0.
Use 'from models import X' instead.
"""
```

**检查步骤**:

1. **检查导入**:
```bash
# 查找所有导入 data_models 的代码
grep -r "from models.data_models import" --include="*.py" .
grep -r "from models import" --include="*.py" . | grep data_models
```

2. **运行时检查**:
```python
# 启动时是否触发 DeprecationWarning
python -c "from models import FileNode" 2>&1 | head -5
```

3. **测试影响**:
```bash
# 运行测试套件
pytest test/models/ -v
```

#### 任务 2.2: 分析 models/deprecated.py 使用情况

**检查步骤**:

```bash
# 查找导入
grep -r "from models.deprecated import" --include="*.py" .
grep -r "import models.deprecated" --include="*.py" .

# 检查是否有运行时引用
grep -r "deprecated\." --include="*.py" . | grep -v "test_"
```

#### 任务 2.3: 替换导入

如果发现有文件仍在使用旧导入，需要更新：

```python
# 旧导入 (deprecated)
from models.data_models import FileNode, SectionBundle

# 新导入
from models import FileNode, SectionBundle
```

**需要更新的文件列表**:
```bash
# 生成报告
grep -rl "from models.data_models import" --include="*.py" . > /tmp/data_models_usage.txt
grep -rl "from models.deprecated import" --include="*.py" . > /tmp/deprecated_usage.txt

cat /tmp/data_models_usage.txt
cat /tmp/deprecated_usage.txt
```

#### 任务 2.4: 删除兼容层

确认无依赖后删除：

```bash
# 删除前备份
git mv models/data_models.py models/data_models.py.backup
git mv models/deprecated.py models/deprecated.py.backup

# 验证无导入错误
python -c "from models import FileNode, SectionBundle, EntitySpec"

# 运行测试
pytest test/models/ -v

# 确认后永久删除
rm models/data_models.py.backup
rm models/deprecated.py.backup
```

#### Phase 2 验收标准

- [ ] 找到并更新了所有旧导入
- [ ] `models/data_models.py` 已删除
- [ ] `models/deprecated.py` 已删除
- [ ] 所有测试通过
- [ ] 端到端测试通过

---

### Phase 3: 重构测试（第2周）

**目标**: 移除测试对旧代码的依赖

#### 任务 3.1: 识别受影响的测试

```bash
# 运行测试套件，识别失败项
pytest test/ -v --tb=line 2>&1 | tee /tmp/test_results.txt

# 检查哪些测试使用了旧代码
grep -l "orchestrator_old\|run_pipeline_old" test/*.py
```

#### 任务 3.2: 修复测试导入

更新测试文件以使用新架构：

```python
# 旧测试导入
from pipeline.orchestrator import run_pipeline

# 新测试导入
from pipeline import run_pipeline  # 向后兼容API
# 或
from pipeline.orchestrator.builder import PipelineBuilder
from pipeline.steps import P1ReferenceGraphStep, ...
```

#### 任务 3.3: 验证测试覆盖

```bash
# 运行模型测试
pytest test/models/ -v --cov=models --cov-report=html

# 运行预处理测试
pytest test/pre_processing/ -v --cov=pre_processing

# 运行 pipeline 测试（新）
pytest test/orchestrator/ -v --cov=pipeline.orchestrator

# 运行完整测试
pytest test/ -v
```

#### Phase 3 验收标准

- [ ] 所有测试通过
- [ ] 测试覆盖率 > 80%
- [ ] 无旧代码导入
- [ ] 端到端测试通过

---

### Phase 4: 核心旧代码清理（第3周）

**目标**: 安全删除 `pipeline/orchestrator.py` 旧实现

#### 任务 4.1: 验证新架构完全替代

确认新架构 (`pipeline/orchestrator/`) 已完全替代旧实现：

```python
# 检查新架构的完整性
from pipeline.orchestrator import (
    PipelineConfig,
    run_pipeline,
    PipelineBuilder,
    PipelineStep,
    PipelineOrchestrator,
)

# 验证功能
config = PipelineConfig(
    skill_root="skills/pdf",
    output_dir="output/test",
    llm_config=LLMConfig(),
)

# 尝试运行（不实际执行LLM）
builder = PipelineBuilder()
orchestrator = builder.with_config(config).build()
print(f"✓ Orchestrator created: {type(orchestrator)}")
```

#### 任务 4.2: 分析向后兼容API

检查 `pipeline/orchestrator/__init__.py` 中的向后兼容实现：

```python
# 当前实现（新架构包装旧API）
def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Backward-compatible entry point."""
    # 使用新架构实现
    ...
```

确认此实现使用新架构，而非调用旧文件。

#### 任务 4.3: 备份并删除旧文件

```bash
# 备份旧文件
git mv pipeline/orchestrator.py pipeline/orchestrator.py.old

# 验证系统仍然工作
python -c "from pipeline import run_pipeline, PipelineConfig"
python main.py --help

# 运行端到端测试（快速模式，使用 mock 或缓存）
python main.py --skill skills/pdf --output output/test-run

# 确认后永久删除
rm pipeline/orchestrator.py.old
```

#### Phase 4 验收标准

- [ ] `pipeline/orchestrator.py` 已删除
- [ ] `from pipeline import run_pipeline` 仍然工作
- [ ] 端到端测试通过
- [ ] 集成测试通过

---

## 3. 详细测试计划

### 3.1 单元测试矩阵

| 模块 | 测试文件 | 覆盖率目标 | 状态检查 |
|------|----------|------------|----------|
| models | test/models/ | > 90% | `pytest test/models/` |
| pre_processing | test/pre_processing/ | > 80% | `pytest test/pre_processing/` |
| pipeline.orchestrator | test/orchestrator/ | > 85% | `pytest test/orchestrator/` |
| pipeline.steps | 集成测试 | > 75% | 端到端测试 |

### 3.2 集成测试

```bash
# Test 1: 完整 Pipeline 运行
python main.py --skill skills/pdf --output output/test-full

# Test 2: 从检查点恢复
python main.py --skill skills/pdf --output output/test-resume --resume-from step3

# Test 3: 并行执行
python main.py --skill skills/docx --output output/test-parallel --parallel-workers 4

# Test 4: 不同技能包
for skill in pdf docx xlsx pptx; do
    python main.py --skill skills/$skill --output output/test-$skill
done
```

### 3.3 回归测试

```bash
# 对比新旧实现输出（如有旧版本）
# 或验证输出格式正确性

# 验证 SPL 输出
python -c "
from pathlib import Path
spl_file = Path('output/test-full/skill.spl')
assert spl_file.exists(), 'SPL file not generated'
content = spl_file.read_text()
assert '[DEFINE_AGENT:' in content, 'Missing DEFINE_AGENT'
assert '[END_AGENT]' in content, 'Missing END_AGENT'
print('✓ SPL output validation passed')
"
```

---

## 4. 风险缓解

### 4.1 高风险操作清单

| 操作 | 风险 | 缓解措施 |
|------|------|----------|
| 删除 `orchestrator.py` | 向后兼容API可能中断 | 确保 `pipeline/__init__.py` 正确包装新架构 |
| 删除 `data_models.py` | 外部导入可能失败 | 提前更新所有导入，保留 stub 一段时间 |
| 删除 `deprecated.py` | 运行时功能丢失 | 检查运行时引用，提供迁移指南 |

### 4.2 回滚计划

每个阶段都有 git 回滚点：

```bash
# 创建阶段标记
git tag phase1-start
git tag phase2-start
git tag phase3-start
git tag phase4-start

# 如果需要回滚
git reset --hard phase3-start

# 恢复单个文件
git checkout phase2-start -- models/data_models.py
```

---

## 5. 执行检查清单

### Phase 1 启动前检查
- [ ] 当前工作目录干净 (`git status`)
- [ ] 所有测试通过
- [ ] 已创建备份分支 (`git branch cleanup-phase1`)

### Phase 2 启动前检查
- [ ] Phase 1 已完成并验证
- [ ] 导入分析报告已生成
- [ ] 受影响的文件清单已确认

### Phase 3 启动前检查
- [ ] Phase 2 已完成并验证
- [ ] 测试套件已更新
- [ ] CI/CD 流程已配置

### Phase 4 启动前检查
- [ ] Phase 3 已完成并验证
- [ ] 新架构完全验证
- [ ] 向后兼容API已确认工作

---

## 6. 时间表

| 阶段 | 预计时间 | 关键里程碑 |
|------|----------|------------|
| Phase 1 | 2-3 天 | 备份文件删除完成 |
| Phase 2 | 3-5 天 | 废弃模块清理完成 |
| Phase 3 | 3-5 天 | 测试重构完成 |
| Phase 4 | 2-3 天 | 核心旧代码删除完成 |
| **总计** | **10-16 天** | (2-3 周) |

---

## 7. 相关文档

- [重构计划总览](./refactor/01_refactor_plan_overview.md)
- [Phase C 详细计划](./refactor/02_phase_c_pipeline_architecture.md)
- [新架构示例用法](../example_usage_new_architecture.py)

---

**下一步**: 开始 Phase 1 - 低风险清理
