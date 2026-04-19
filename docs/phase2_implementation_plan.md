# Phase 2: 低风险清理 - 详细实施计划

> **阶段**: Phase 2  
> **预计工期**: 第3-5天（3天）  
> **风险等级**: ⭐ 极低  
> **创建日期**: 2026-04-19  
> **版本**: 1.0  

---

## 执行摘要

Phase 2 专注于**低风险清理操作**：删除备份文件、清理临时文件和 Python 缓存。这些操作不会影响代码功能，且可安全回滚。

### 关键发现

| 项目 | 状态 | 详情 |
|------|------|------|
| `steps.py.bak` | ✅ 待删除 | 33,644 bytes，无活跃引用 |
| `__pycache__` 目录 | ✅ 待清理 | 156 个目录 |
| `.pyc` 文件 | ✅ 待清理 | 1,694 个文件 |
| `.log` 文件 | ✅ 无需处理 | 0 个文件 |
| 废弃模块导入 | ⏳ Phase 3 | 未发现直接引用（需进一步确认） |

---

## 2.1 删除备份文件 `steps.py.bak`

### 文件信息

```yaml
文件路径: pipeline/steps.py.bak
文件大小: 33,644 bytes (33KB)
文件类型: 备份文件
创建原因: 旧版 pipeline steps 实现备份
内容描述: LLM pipeline steps 旧实现（P2, Step 1, Step 2A, Step 3, Step 4）
```

### 引用分析

✅ **安全删除确认**：

1. **当前架构**：`pipeline/steps/__init__.py` 使用新的模块化结构：
   - `p1_reference_graph.py`
   - `p2_file_roles.py`
   - `p3_assembler.py`
   - `step1_structure.py`
   - `step1_5_api.py`
   - `step3_workflow.py`
   - `step4_spl.py`

2. **无活跃引用**：grep 搜索未发现任何 `.py` 文件引用 `steps.py.bak`

3. **架构替换**：旧版 `steps.py.bak` 已被 `pipeline/steps/` 目录下的模块化实现完全替代

### 执行步骤

#### Step 2.1.1: 验证无引用（PowerShell）

```powershell
# 验证无代码引用 steps.py.bak
$references = Select-String -Path . -Pattern "steps\.py\.bak" -Include "*.py" -Recurse
if ($references) {
    Write-Host "⚠️  Found references to steps.py.bak:"
    $references | ForEach-Object { Write-Host "  - $($_.Path):$($_.LineNumber)" }
} else {
    Write-Host "✅ No references to steps.py.bak found"
}
```

#### Step 2.1.2: 备份到安全位置

```powershell
# 创建备份目录（如不存在）
$backupDir = "C:\\temp\\skill-to-cnlp-backups"
if (!(Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
}

# 备份文件
$sourceFile = "pipeline/steps.py.bak"
$backupFile = "$backupDir\\steps.py.bak.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
Copy-Item $sourceFile $backupFile
Write-Host "✅ Backup created: $backupFile"
```

#### Step 2.1.3: 删除文件

```powershell
# 删除备份文件
Remove-Item "pipeline/steps.py.bak" -Force

# 验证删除
if (!(Test-Path "pipeline/steps.py.bak")) {
    Write-Host "✅ steps.py.bak deleted successfully"
} else {
    Write-Host "❌ Failed to delete steps.py.bak"
}
```

#### Step 2.1.4: 验证系统完整性

```powershell
# 验证导入正常
python -c "
from pipeline.steps import (
    P1ReferenceGraphStep,
    P2FileRolesStep, 
    P3AssemblerStep,
    Step1StructureStep,
    Step1_5APIGenStep,
    Step3WorkflowStep,
    Step4SPLStep
)
print('✅ All pipeline steps imported successfully')
"

# 验证 PipelineConfig 导入
python -c "
from pipeline import run_pipeline, PipelineConfig
print('✅ Pipeline API imports working')
"
```

### 验收标准

- [ ] `pipeline/steps.py.bak` 已删除
- [ ] 备份文件已保存到安全位置
- [ ] 所有 pipeline steps 可正常导入
- [ ] PipelineConfig 可正常导入

---

## 2.2 清理临时文件

### 清理清单

| 文件类型 | 数量 | 位置 | 清理命令 |
|----------|------|------|----------|
| `__pycache__` 目录 | 156 | 各子目录下 | 递归删除 |
| `.pyc` 文件 | 1,694 | 各目录下 | 递归删除 |
| `.log` 文件 | 0 | - | 无需处理 |
| `.pytest_cache` | 待确认 | 项目根目录 | 递归删除 |

### 执行步骤

#### Step 2.2.1: 统计清理前状态

```powershell
# 统计 __pycache__ 目录
$pycacheCount = (Get-ChildItem -Path . -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "Found __pycache__ directories: $pycacheCount"

# 统计 .pyc 文件
$pycCount = (Get-ChildItem -Path . -Filter "*.pyc" -Recurse -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "Found .pyc files: $pycCount"

# 统计 .log 文件
$logCount = (Get-ChildItem -Path . -Filter "*.log" -Recurse -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "Found .log files: $logCount"
```

#### Step 2.2.2: 删除 Python 缓存

```powershell
# 删除所有 __pycache__ 目录
Get-ChildItem -Path . -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force
Write-Host "✅ __pycache__ directories removed"

# 删除所有 .pyc 文件
Get-ChildItem -Path . -Filter "*.pyc" -Recurse | Remove-Item -Force
Write-Host "✅ .pyc files removed"

# 删除 .pytest_cache（如存在）
if (Test-Path ".pytest_cache") {
    Remove-Item ".pytest_cache" -Recurse -Force
    Write-Host "✅ .pytest_cache removed"
}
```

#### Step 2.2.3: 验证清理完成

```powershell
# 验证清理结果
$remainingPycache = (Get-ChildItem -Path . -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue | Measure-Object).Count
$remainingPyc = (Get-ChildItem -Path . -Filter "*.pyc" -Recurse -ErrorAction SilentlyContinue | Measure-Object).Count

Write-Host ""
Write-Host "=== Cleanup Verification ==="
Write-Host "Remaining __pycache__ directories: $remainingPycache"
Write-Host "Remaining .pyc files: $remainingPyc"

if ($remainingPycache -eq 0 -and $remainingPyc -eq 0) {
    Write-Host "✅ All Python cache cleaned successfully"
} else {
    Write-Host "⚠️  Some cache files remain"
}
```

### 验收标准

- [ ] `__pycache__` 目录数量 = 0
- [ ] `.pyc` 文件数量 = 0
- [ ] `.pytest_cache` 已删除（如存在）

---

## 2.3 验证 Phase 2

### 测试计划

#### 2.3.1: 单元测试

```powershell
# 模型层测试
pytest test/models/ -v --tb=short
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Model tests passed"
} else {
    Write-Host "❌ Model tests failed"
}

# 预处理层测试
pytest test/pre_processing/ -v --tb=short
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Pre-processing tests passed"
} else {
    Write-Host "❌ Pre-processing tests failed"
}

# 编排层测试
pytest test/orchestrator/ -v --tb=short
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Orchestrator tests passed"
} else {
    Write-Host "❌ Orchestrator tests failed"
}
```

#### 2.3.2: 端到端测试

```powershell
# 创建测试输出目录
$testOutputDir = "output/phase2-test"
if (!(Test-Path $testOutputDir)) {
    New-Item -ItemType Directory -Path $testOutputDir -Force | Out-Null
}

# 运行端到端测试（pdf skill）
python main.py --skill skills/pdf --output $testOutputDir

# 验证输出
$splFiles = Get-ChildItem -Path $testOutputDir -Filter "*.spl"
if ($splFiles) {
    Write-Host "✅ SPL files generated:"
    $splFiles | ForEach-Object { Write-Host "  - $($_.Name)" }
    
    # 验证 SPL 内容
    $splContent = Get-Content $splFiles[0].FullName -Raw
    if ($splContent -match "\[DEFINE_AGENT:") {
        Write-Host "✅ Valid SPL structure found"
    } else {
        Write-Host "⚠️  SPL structure validation failed"
    }
} else {
    Write-Host "❌ No SPL files generated"
}
```

#### 2.3.3: 导入测试

```powershell
# 全面导入测试
python -c "
import sys
sys.path.insert(0, '.')

# 测试所有关键导入
try:
    from pipeline import run_pipeline, PipelineConfig
    from pipeline.llm_client import LLMClient, LLMConfig
    from pipeline.steps import (
        P1ReferenceGraphStep,
        P2FileRolesStep,
        P3AssemblerStep,
        Step1StructureStep,
        Step1_5APIGenStep,
        Step3WorkflowStep,
        Step4SPLStep
    )
    from models import (
        FileNode,
        FileReferenceGraph,
        SectionBundle,
        SectionItem,
        EntitySpec,
        WorkflowStep,
        SPLSpec
    )
    from pre_processing import (
        ReferenceGraphBuilder,
        FileRoleResolver,
        SkillPackageAssembler
    )
    print('✅ All imports successful')
except Exception as e:
    print(f'❌ Import failed: {e}')
    sys.exit(1)
"
```

### 验收标准

- [ ] 所有单元测试通过
- [ ] 端到端测试通过
- [ ] SPL 文件正确生成
- [ ] 所有关键导入正常

---

## 风险缓解

### 风险矩阵

| 风险项 | 概率 | 影响 | 风险等级 | 缓解措施 |
|--------|------|------|----------|----------|
| steps.py.bak 误删 | 极低 | 低 | ⭐ | 已备份到安全位置 |
| 缓存清理影响运行 | 极低 | 低 | ⭐ | 缓存可自动重建 |
| 测试失败 | 低 | 中 | ⭐⭐ | 独立测试，不影响其他阶段 |

### 回滚计划

```powershell
# 如果需要恢复 steps.py.bak
$backupFile = "C:\temp\skill-to-cnlp-backups\steps.py.bak.*"
$latestBackup = Get-ChildItem $backupFile | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestBackup) {
    Copy-Item $latestBackup.FullName "pipeline/steps.py.bak"
    Write-Host "✅ steps.py.bak restored from backup"
}
```

---

## Git 提交计划

### Commit 2.1: 删除备份文件

```bash
# 提交信息
git add -A
git commit -m "Phase 2.1: Remove legacy backup file steps.py.bak

- Deleted pipeline/steps.py.bak (33,644 bytes)
- Backup saved to C:\temp\skill-to-cnlp-backups
- No active references found in codebase
- New modular steps implementation in pipeline/steps/ already active

Refs: cleanup_plan_detailed.md Phase 2.1"
```

### Commit 2.2: 清理临时文件

```bash
# 提交信息
git add -A
git commit -m "Phase 2.2: Clean Python cache and temporary files

- Removed 156 __pycache__ directories
- Removed 1,694 .pyc files
- Cleaned .pytest_cache (if existed)
- No functional changes

Refs: cleanup_plan_detailed.md Phase 2.2"
```

---

## 交付物

### 文件变更

| 操作 | 文件/目录 | 大小变化 |
|------|-----------|----------|
| 删除 | `pipeline/steps.py.bak` | -33,644 bytes |
| 删除 | `__pycache__/` (156 个) | ~5-10 MB |
| 删除 | `*.pyc` (1,694 个) | ~2-5 MB |

### 验证报告模板

```markdown
## Phase 2 完成报告

### 执行时间
- 开始时间: [YYYY-MM-DD HH:MM]
- 完成时间: [YYYY-MM-DD HH:MM]
- 执行者: [Name]

### 删除文件统计
- steps.py.bak: 33,644 bytes ✅
- __pycache__ directories: 156 ✅
- .pyc files: 1,694 ✅
- Total size freed: ~10-15 MB

### 测试结果
- Unit tests: [PASS/FAIL]
- Integration tests: [PASS/FAIL]
- End-to-end test (pdf): [PASS/FAIL]

### 验证清单
- [ ] steps.py.bak deleted
- [ ] No import errors
- [ ] All tests pass
- [ ] SPL output valid

### 备注
[Any issues or observations]
```

---

## 下一步

完成 Phase 2 后，进入 **Phase 3: 废弃模块分析**：

1. 分析 `models/data_models.py` 依赖
2. 分析 `models/deprecated.py` 依赖
3. 更新导入语句（如需要）
4. 验证并删除废弃模块

---

**文档版本**: 1.0  
**最后更新**: 2026-04-19  
**状态**: 待执行
