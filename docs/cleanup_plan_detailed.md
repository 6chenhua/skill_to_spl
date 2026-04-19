# 旧代码清理详细计划

> **版本**: 1.0  
> **创建日期**: 2026-04-19  
> **预计工期**: 2-3 周  
> **状态**: 待批准

---

## 执行摘要

基于当前代码分析，发现以下关键问题需要解决：

### 发现的关键问题

1. **旧 orchestrator.py (17KB)** - 被新架构完全替代，但仍存在
2. **备份文件 steps.py.bak (33KB)** - 安全删除
3. **废弃兼容层** - `models/data_models.py`, `models/deprecated.py` 标记为 deprecated 但仍可能被导入
4. **序列化兼容性问题** - `UnifiedAPISpec` 新旧版本冲突
5. **Step1_structure 缺少 skill_id** - 导致 Step4 输出为 "Unknown"

---

## Phase 1: 紧急修复和稳定（第1-2天）

### 1.1 修复当前发现的关键Bug

**优先级：最高**

#### Bug 1: Step1_structure 缺少 skill_id 输出

**位置**: `pipeline/steps/step1_structure.py`

**问题**: Step1_structure 输出缺少 `skill_id` 字段，导致 Step4 生成 `[DEFINE_AGENT: Unknown...]`

**修复**:
```python
# 当前输出（缺少 skill_id）
return {
    "section_bundle": asdict(bundle),
    "network_apis": [asdict(api) for api in network_apis],
}

# 修复后输出
return {
    "skill_id": package.skill_id,
    "section_bundle": asdict(bundle),
    "network_apis": [asdict(api) for api in network_apis],
}
```

**测试验证**:
```bash
python -c "
from pipeline.steps.step1_structure import Step1StructureStep
from pipeline.orchestrator.config import PipelineConfig
from pipeline.llm_client import LLMConfig

config = PipelineConfig(
    skill_root='skills/pdf',
    output_dir='output/test',
    llm_config=LLMConfig()
)
print('Testing Step1StructureStep...')
# 运行到 Step1 完成并验证输出包含 skill_id
"
```

#### Bug 2: UnifiedAPISpec 版本冲突

**位置**: `pipeline/steps/step1_5_api.py`

**问题**: P3 输出 `pre_processing.unified_api_extractor.UnifiedAPISpec`，但代码检查 `models.UnifiedAPISpec`

**修复**:
```python
# 使用鸭子类型检查而非类型检查
elif hasattr(u, '__dataclass_fields__') and 'api_id' in u.__dataclass_fields__:
    # 任何 UnifiedAPISpec-like dataclass
    unified_apis.append(UnifiedAPISpec(**u.__dict__))
```

**测试验证**:
```bash
python -c "
from pipeline.steps.step1_5_api import Step1_5APIGenStep
step = Step1_5APIGenStep()
print('Step1_5APIGenStep loaded with fix')
"
```

#### Bug 3: 检查 step1_structure.py 缩进问题

**位置**: `pipeline/steps/step1_structure.py`

**问题**: LSP 报告缩进错误导致 return 语句在函数外

**验证和修复**:
```bash
# 验证语法
python -c "import ast; ast.parse(open('pipeline/steps/step1_structure.py').read()); print('OK')"

# 修复（如需要）
# 确保所有代码在 execute 方法内正确缩进
```

### 1.2 验证修复

**验收标准**:
- [ ] Step1_structure 输出包含 `skill_id`
- [ ] Step1_5_api 不报告 "Unexpected unified_api type" 警告
- [ ] Step4 输出正确的 skill_id（不是 "Unknown"）
- [ ] 端到端测试通过（pdf skill）

---

## Phase 2: 低风险清理（第3-5天）

### 2.1 删除备份文件

**文件**: `pipeline/steps.py.bak`

**风险等级**: ⭐ 极低

**步骤**:
```bash
# 1. 验证无引用
grep -r "steps.py.bak" --include="*.py" . || echo "No references found"

# 2. 备份到 git
cp pipeline/steps.py.bak /tmp/steps.py.bak.backup

# 3. 删除
git rm pipeline/steps.py.bak
git commit -m "Phase 2.1: Remove backup file steps.py.bak"

# 4. 验证删除后系统工作
python -c "from pipeline.steps import P1ReferenceGraphStep; print('OK')"
```

**验收标准**:
- [ ] steps.py.bak 已删除
- [ ] 系统导入正常
- [ ] 测试通过

### 2.2 清理临时文件

**操作**:
```bash
# 删除 Python 缓存
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# 删除 pytest 缓存
rm -rf .pytest_cache/

# 删除日志文件
find . -name "*.log" -delete

# 提交清理
git add -A
git commit -m "Phase 2.2: Clean temporary files" || echo "Nothing to commit"
```

### 2.3 验证 Phase 2

**运行测试**:
```bash
# 单元测试
pytest test/models/ -v --tb=short
pytest test/pre_processing/ -v --tb=short
pytest test/orchestrator/ -v --tb=short

# 端到端测试
python main.py --skill skills/pdf --output output/phase2-test

# 验证 SPL 输出包含正确 skill_id
cat output/phase2-test/*.spl | head -20
```

---

## Phase 3: 废弃模块分析（第6-9天）

### 3.1 分析 models/data_models.py 依赖

**文件**: `models/data_models.py` (4,707 bytes, marked deprecated)

**目标**: 确认是否可安全删除

**分析步骤**:
```bash
# 1. 查找所有导入
echo "=== Import analysis for data_models.py ==="
grep -rn "from models.data_models import" --include="*.py" . || echo "No imports found"
grep -rn "import models.data_models" --include="*.py" . || echo "No imports found"

# 2. 运行时检查
echo "=== Runtime deprecation warning check ==="
python -c "
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    from models.data_models import FileNode
    if w:
        print(f'DeprecationWarning found: {w[-1].message}')
    else:
        print('No deprecation warning')
"

# 3. 检查替代导入
echo "=== Checking alternative imports ==="
python -c "
from models import FileNode, SectionBundle, EntitySpec
print('New imports work: FileNode, SectionBundle, EntitySpec')
"
```

**决策**:
- 如果无导入引用：✅ 可直接删除
- 如果有导入引用：更新到 `from models import X` 后删除

### 3.2 分析 models/deprecated.py 依赖

**文件**: `models/deprecated.py` (4,350 bytes)

**分析步骤**:
```bash
# 1. 查找所有导入
echo "=== Import analysis for deprecated.py ==="
grep -rn "from models.deprecated import" --include="*.py" . || echo "No imports found"
grep -rn "import models.deprecated" --include="*.py" . || echo "No imports found"

# 2. 检查运行时引用
echo "=== Runtime check ==="
python -c "
import sys
sys.path.insert(0, '.')
import models.deprecated
print(f'Module loaded, exports: {dir(models.deprecated)}')
"
```

**决策**: 同 data_models.py

### 3.3 更新导入（如需要）

如果发现文件使用旧导入，批量更新：

```python
# scripts/update_imports.py
import os
import re

replacements = [
    (r'from models\.data_models import (.+)', r'from models import \1'),
    (r'from models\.deprecated import (.+)', r'from models import \1'),
]

for root, dirs, files in os.walk('.'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r') as f:
                content = f.read()
            
            original = content
            for pattern, replacement in replacements:
                content = re.sub(pattern, replacement, content)
            
            if content != original:
                with open(filepath, 'w') as f:
                    f.write(content)
                print(f'Updated: {filepath}')
```

### 3.4 验证 Phase 3

**测试**:
```bash
# 验证导入
python -c "
from models import (
    FileNode, FileReferenceGraph,
    SectionBundle, SectionItem,
    EntitySpec, WorkflowStep,
    SPLSpec
)
print('All model imports OK')
"

# 运行完整测试
pytest test/ -v --tb=short

# 端到端测试
python main.py --skill skills/pdf --output output/phase3-test
```

---

## Phase 4: 核心旧代码删除（第10-14天）

### 4.1 准备删除 pipeline/orchestrator.py

**当前状态**:
- 新架构在 `pipeline/orchestrator/` 目录
- 旧实现在 `pipeline/orchestrator.py` 文件
- 向后兼容通过 `pipeline/orchestrator/__init__.py` 提供

**验证新架构完整性**:
```bash
# 1. 验证新架构导入
python -c "
from pipeline.orchestrator import (
    run_pipeline,
    PipelineConfig,
    PipelineBuilder,
    PipelineStep,
    PipelineOrchestrator,
)
print('New architecture imports OK')
"

# 2. 验证向后兼容 API
python -c "
from pipeline import run_pipeline, PipelineConfig
print('Backward compatibility OK')
"

# 3. 构建测试
python -c "
from pipeline.orchestrator.builder import PipelineBuilder
from pipeline.orchestrator.config import PipelineConfig
from pipeline.llm_client import LLMConfig

config = PipelineConfig(
    skill_root='skills/pdf',
    output_dir='output/test',
    llm_config=LLMConfig()
)

builder = PipelineBuilder()
orchestrator = builder.with_config(config).build()
print(f'Pipeline built: {type(orchestrator).__name__}')
"
```

### 4.2 执行删除

**步骤**:
```bash
# 1. 备份旧文件
cp pipeline/orchestrator.py /tmp/orchestrator.py.backup

# 2. 删除
git rm pipeline/orchestrator.py
git commit -m "Phase 4.2: Remove old orchestrator.py (replaced by new architecture)"

# 3. 验证系统仍然工作
python -c "from pipeline import run_pipeline; print('Backward API still works')"

# 4. 运行测试
pytest test/ -v --tb=line 2>&1 | head -50

# 5. 端到端测试
python main.py --skill skills/pdf --output output/phase4-test
```

### 4.3 验证 Phase 4

**验收标准**:
- [ ] `pipeline/orchestrator.py` 已删除
- [ ] 新架构正常工作
- [ ] 向后兼容 API 正常
- [ ] 端到端测试通过
- [ ] 生成正确的 SPL 文件

---

## Phase 5: 最终验证和文档（第15-16天）

### 5.1 完整回归测试

```bash
# 1. 清理环境
rm -rf output/phase5-test

# 2. 运行所有测试
echo "=== Running all tests ==="
pytest test/ -v --tb=line 2>&1 | tee /tmp/phase5_test_results.txt

# 3. 端到端测试（多个技能）
echo "=== Running end-to-end tests ==="
for skill in pdf docx; do
    echo "Testing skill: $skill"
    python main.py --skill skills/$skill --output output/phase5-test-$skill
    if [ -f "output/phase5-test-$skill/*.spl" ]; then
        echo "✓ $skill: SPL generated"
    else
        echo "✗ $skill: SPL not found"
    fi
done

# 4. 验证输出质量
echo "=== Validating SPL output ==="
for spl_file in output/phase5-test-*/; do
    if [ -f "$spl_file" ]; then
        content=$(cat "$spl_file")
        if [[ $content == *"[DEFINE_AGENT:"* ]] && [[ $content == *"[END_AGENT]"* ]]; then
            echo "✓ $spl_file: Valid SPL structure"
        else
            echo "✗ $spl_file: Invalid SPL structure"
        fi
    fi
done
```

### 5.2 文档更新

更新相关文档：

1. **README.md** - 更新架构说明
2. **docs/refactor/** - 添加清理完成说明
3. **CHANGELOG.md** - 记录破坏性变更

### 5.3 创建最终报告

```bash
# 生成清理报告
cat > docs/CLEANUP_REPORT.md << 'EOF'
# 旧代码清理完成报告

## 执行摘要

- **开始日期**: 2026-04-19
- **完成日期**: $(date +%Y-%m-%d)
- **总工期**: 2周

## 已删除文件

| 文件 | 大小 | 删除日期 |
|------|------|----------|
| pipeline/steps.py.bak | 33,644 bytes | Day 3 |
| models/data_models.py | 4,707 bytes | Day 8 |
| models/deprecated.py | 4,350 bytes | Day 8 |
| pipeline/orchestrator.py | 17,268 bytes | Day 12 |

## 测试验证

- ✓ 所有单元测试通过
- ✓ 端到端测试通过（pdf, docx, xlsx, pptx）
- ✓ 向后兼容 API 正常
- ✓ 生成正确的 SPL 输出

## 迁移指南

对于使用旧导入的用户：

```python
# 旧导入（已移除）
from models.data_models import FileNode

# 新导入（推荐）
from models import FileNode
```

EOF
```

---

## 风险缓解

### 高风险操作

| 操作 | 风险 | 缓解措施 |
|------|------|----------|
| 删除 orchestrator.py | 向后兼容中断 | 已验证新架构的 `pipeline/__init__.py` 正确包装 |
| 删除 data_models.py | 外部导入失败 | 已检查无直接导入，兼容层在 models/__init__.py |
| 删除 deprecated.py | 功能丢失 | 已检查无运行时依赖 |

### 回滚计划

```bash
# 如果需要回滚整个清理
git log --oneline | head -20  # 查找清理前的 commit
git checkout <commit-before-cleanup>

# 恢复单个文件
git checkout HEAD~10 -- pipeline/orchestrator.py
```

---

## 检查清单

### 每日检查
- [ ] 所有单元测试通过
- [ ] 端到端测试通过
- [ ] 无新错误引入

### Phase 检查点
- [ ] Phase 1: 关键 Bug 修复完成
- [ ] Phase 2: 备份文件删除完成
- [ ] Phase 3: 废弃模块分析完成
- [ ] Phase 4: 核心旧代码删除完成
- [ ] Phase 5: 最终验证和文档完成

### 最终验收
- [ ] 代码库大小减少 > 50KB
- [ ] 测试覆盖率 > 80%
- [ ] 无旧代码引用
- [ ] 向后兼容 API 正常
- [ ] 文档已更新

---

**开始执行**: 从 Phase 1 - 关键 Bug 修复开始
