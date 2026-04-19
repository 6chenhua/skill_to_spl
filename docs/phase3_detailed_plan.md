# Phase 3: 废弃模块分析与迁移详细计划

> **阶段**: Phase 3 - 废弃模块分析  
> **预计工期**: 第6-9天  
> **状态**: 已分析完成，待执行  
> **创建日期**: 2026-04-19  

---

## 执行摘要

### 发现的关键问题

| 问题 | 严重程度 | 影响 |
|------|----------|------|
| `models/__init__.py` 包含兼容性导入层 | **高** | 直接删除会导致 ImportError |
| `models/data_models.py` 存在循环导入风险 | **中** | 虽然当前工作，但设计脆弱 |
| `models/deprecated.py` 几乎完全重复 | **低** | 冗余代码，可安全删除 |
| 无外部直接导入 | **好** | 仅需修改 models/__init__.py |

### 迁移策略

由于 `models/__init__.py` 包含以下代码（L127-140），**必须先修改此文件才能删除废弃模块**:

```python
try:
    from models.data_models import (
        FileNode as _FileNode,
        FileReferenceGraph as _FileReferenceGraph,
        FileRoleEntry as _FileRoleEntry,
        SkillPackage as _SkillPackage,
    )
    _DATA_MODELS_AVAILABLE = True
except ImportError:
    _DATA_MODELS_AVAILABLE = False
```

---

## Day 6: 准备阶段 - models/__init__.py 重构

### 6.1 任务: 移除 models/__init__.py 中的兼容性导入层

**文件**: `models/__init__.py`

**当前状态**: 
- L119-140 包含 try/except 导入 data_models 的代码
- L228-234 在模块加载时发出 DeprecationWarning

**修改计划**:

```python
# 删除以下代码块（L119-140）:
# ═══════════════════════════════════════════════════════════════════════════════
# Re-export from data_models for backward compatibility (deprecated)
# These will be removed in v3.0
# ═══════════════════════════════════════════════════════════════════════════════

# Import common types from data_models that might be referenced
# This ensures existing code continues to work while warning about deprecation
import warnings

try:
    # Try to import from existing data_models as fallback
    from models.data_models import (
        FileNode as _FileNode,
        FileReferenceGraph as _FileReferenceGraph,
        FileRoleEntry as _FileRoleEntry,
        SkillPackage as _SkillPackage,
    )

    # These imports work, so data_models still exists
    # The module itself will issue deprecation warnings
    _DATA_MODELS_AVAILABLE = True
except ImportError:
    _DATA_MODELS_AVAILABLE = False

# 删除以下代码块（L228-234）:
# Issue a one-time deprecation notice if models.data_models exists
if _DATA_MODELS_AVAILABLE:
    warnings.warn(
        "models.data_models is deprecated. Use 'from models import X' instead. "
        "This compatibility layer will be removed in v3.0.",
        DeprecationWarning,
        stacklevel=2,
    )

# 可选: 删除未使用的函数（L221-224）:
def check_deprecated_imports() -> None:
    """Check if deprecated imports are being used and warn."""
    pass
```

**修改后验证**:
```bash
# 1. 语法检查
python -c "import ast; ast.parse(open('models/__init__.py').read()); print('Syntax OK')"

# 2. 导入测试
python -c "from models import FileNode, SectionBundle, EntitySpec; print('Imports OK')"

# 3. 运行单元测试
pytest test/models/ -v --tb=short -x
```

**验收标准**:
- [x] models/__init__.py 不再引用 models.data_models
- [x] 所有公开 API 仍可从 models 导入
- [x] 无 DeprecationWarning 发出
- [x] 单元测试通过

---

## Day 7: 执行阶段 - 删除废弃模块

### 7.1 任务: 删除 models/data_models.py

**风险等级**: ⭐ 低（已移除依赖）

**执行步骤**:
```bash
# 1. 最终确认无外部导入
grep -rn "from models.data_models import\|import models.data_models" --include="*.py" . 2>/dev/null | grep -v "models/__init__.py" || echo "No external imports found"

# 2. Git 删除
git rm models/data_models.py

# 3. 提交
git commit -m "Phase 3.1: Remove deprecated models/data_models.py

- Removed backward compatibility layer
- All imports should now use: from models import X
- Part of Phase 3 cleanup (Day 7)"
```

**验证**:
```bash
# 1. 确认文件已删除
[ ! -f models/data_models.py ] && echo "✓ File deleted"

# 2. 导入仍然工作
python -c "from models import FileNode; print('✓ Import works')"

# 3. 尝试导入旧路径应失败
python -c "from models.data_models import FileNode" 2>&1 | grep -q "ModuleNotFoundError" && echo "✓ Old import correctly fails"
```

### 7.2 任务: 删除 models/deprecated.py

**风险等级**: ⭐ 低

**执行步骤**:
```bash
# 1. 最终确认无外部导入
grep -rn "from models.deprecated import\|import models.deprecated" --include="*.py" . 2>/dev/null || echo "No imports found"

# 2. Git 删除
git rm models/deprecated.py

# 3. 提交
git commit -m "Phase 3.2: Remove deprecated models/deprecated.py

- Removed duplicate backward compatibility module
- Part of Phase 3 cleanup (Day 7)"
```

**验证**:
```bash
# 1. 确认文件已删除
[ ! -f models/deprecated.py ] && echo "✓ File deleted"

# 2. 系统仍然工作
python -c "from models import FileNode, SectionBundle; print('✓ All imports work')"
```

---

## Day 8: 验证阶段 - 全面测试

### 8.1 任务: 运行完整测试套件

```bash
# 1. 清理环境
rm -rf output/phase3-test
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# 2. 模型层测试
echo "=== Testing models layer ==="
pytest test/models/ -v --tb=short

# 3. 预处理层测试
echo "=== Testing pre_processing layer ==="
pytest test/pre_processing/ -v --tb=short

# 4. Pipeline 层测试
echo "=== Testing pipeline layer ==="
pytest test/pipeline/ -v --tb=short

# 5. 端到端测试
echo "=== Running end-to-end test ==="
python main.py --skill skills/pdf --output output/phase3-test --verbose

# 6. 验证输出
echo "=== Validating output ==="
if [ -f "output/phase3-test/pdf.spl" ]; then
    echo "✓ SPL file generated"
    head -20 output/phase3-test/pdf.spl
else
    echo "✗ SPL file not found"
fi
```

### 8.2 任务: 验证导入路径

```python
# scripts/verify_imports.py
#!/usr/bin/env python3
"""Verify all public imports work after Phase 3 cleanup."""

import sys

def test_imports():
    """Test that all public imports work."""
    errors = []
    
    # Test base imports
    try:
        from models import (
            SourceRef, Provenance, Priority, FileKind,
            CANONICAL_SECTIONS, validate_confidence
        )
        print("✓ Base imports")
    except ImportError as e:
        errors.append(f"Base imports failed: {e}")
    
    # Test core imports
    try:
        from models import TokenUsage, SessionUsage, ReviewItem
        print("✓ Core imports")
    except ImportError as e:
        errors.append(f"Core imports failed: {e}")
    
    # Test preprocessing imports
    try:
        from models import (
            FileNode, FileReferenceGraph, SkillPackage,
            FileRoleEntry, ScriptSpec
        )
        print("✓ Preprocessing imports")
    except ImportError as e:
        errors.append(f"Preprocessing imports failed: {e}")
    
    # Test pipeline step imports
    try:
        from models import (
            SectionBundle, SectionItem,
            EntitySpec, WorkflowStep, AlternativeFlow, ExceptionFlow,
            SPLSpec, SPLBlock, UnifiedAPISpec, ToolSpec
        )
        print("✓ Pipeline step imports")
    except ImportError as e:
        errors.append(f"Pipeline step imports failed: {e}")
    
    # Test deprecated paths should FAIL
    try:
        from models.data_models import FileNode
        errors.append("Old import path still works (should have been removed)")
    except ImportError:
        print("✓ Old import path correctly removed")
    
    if errors:
        print("\n✗ Errors found:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("\n✓ All imports verified successfully")
        sys.exit(0)

if __name__ == "__main__":
    test_imports()
```

**执行**:
```bash
chmod +x scripts/verify_imports.py
python scripts/verify_imports.py
```

---

## Day 9: 文档和清理

### 9.1 任务: 更新文档

**更新 README.md** (如果存在相关章节):
```markdown
## Migration Guide (v2.x to v3.0)

### Breaking Changes

The deprecated modules `models.data_models` and `models.deprecated` have been removed.

**Before (v2.x)**:
```python
from models.data_models import FileNode  # Deprecated
```

**After (v3.0)**:
```python
from models import FileNode  # Recommended
```
```

**更新 models/README.md**:
- 移除 "deprecated.py" 和 "data_models.py" 的引用
- 更新目录结构说明
- 更新迁移指南

### 9.2 任务: 更新模型包文档

**修改 models/README.md**:

删除以下内容:
```markdown
### deprecated.py
Backward compatibility layer for old imports (to be removed in v3.0)
```

### 9.3 任务: 提交文档更新

```bash
git add docs/ README.md models/README.md
git commit -m "Phase 3.3: Update documentation for removed deprecated modules

- Updated migration guide
- Removed references to data_models.py and deprecated.py
- Documented breaking changes"
```

---

## 详细风险分析

### 依赖图

```
models/__init__.py (before)
├── imports from models.data_models (L129-134) ──> models/data_models.py
│                                                     └── imports from models (circular)
├── imports from models.deprecated (none directly)
└── re-exports to public API

models/__init__.py (after Day 6)
├── NO imports from deprecated modules
└── re-exports to public API (unchanged)

External code
└── imports from models (unchanged, no impact)
```

### 风险缓解措施

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 循环导入问题 | 低 | 高 | Day 6 先修改 __init__.py，确保无循环依赖 |
| 外部代码使用旧导入 | 极低 | 高 | 已确认无外部导入；旧导入会立即报错 |
| 忘记删除兼容代码 | 中 | 低 | 代码审查 + 验证脚本确保彻底清理 |
| 测试覆盖不足 | 中 | 中 | Day 8 运行完整测试套件，包括 e2e |

---

## 验收检查清单

### Day 6 检查点
- [ ] `models/__init__.py` 已移除 try/except data_models 导入块
- [ ] `models/__init__.py` 已移除 DeprecationWarning 代码
- [ ] 可选: 已移除未使用的 `check_deprecated_imports()` 函数
- [ ] 所有单元测试通过
- [ ] 导入测试通过: `from models import X` 对所有 X 有效

### Day 7 检查点
- [ ] `models/data_models.py` 已删除
- [ ] `models/deprecated.py` 已删除
- [ ] 尝试导入旧路径失败: `from models.data_models import X` 抛出 ImportError
- [ ] 所有单元测试通过
- [ ] Git commit 包含详细消息

### Day 8 检查点
- [ ] 模型层测试通过: `pytest test/models/ -v`
- [ ] 预处理层测试通过: `pytest test/pre_processing/ -v`
- [ ] Pipeline 层测试通过: `pytest test/pipeline/ -v`
- [ ] 端到端测试通过: `python main.py --skill skills/pdf`
- [ ] SPL 输出文件生成正确
- [ ] 验证脚本通过: `python scripts/verify_imports.py`

### Day 9 检查点
- [ ] README.md 已更新（移除废弃模块引用）
- [ ] models/README.md 已更新
- [ ] 文档提交完成
- [ ] 最终代码审查通过

---

## 回滚计划

### 如果需要回滚整个 Phase 3:

```bash
# 查看 Phase 3 的 commits
git log --oneline --since="2026-04-19" | head -20

# 回滚到 Phase 3 开始前的状态
git revert HEAD~3..HEAD  # 回滚最近 3 个 Phase 3 的 commits

# 或者找到 Phase 2 结束时的 commit
git log --oneline --grep="Phase 2" | head -5
git checkout <phase-2-complete-commit>
```

### 如果需要恢复单个文件:

```bash
# 从 Git 历史恢复 data_models.py
git show <commit-before-phase3>:models/data_models.py > models/data_models.py

# 恢复 deprecated.py
git show <commit-before-phase3>:models/deprecated.py > models/deprecated.py

# 恢复 __init__.py
git checkout HEAD~3 -- models/__init__.py
```

---

## 附录: 文件信息

### 待删除文件

| 文件 | 大小 | 说明 |
|------|------|------|
| models/data_models.py | 4,707 bytes | 纯转发模块，无实际代码 |
| models/deprecated.py | 4,350 bytes | 纯转发模块，冗余 |
| **总计** | **9,057 bytes** | |

### 需修改文件

| 文件 | 修改行数 | 说明 |
|------|----------|------|
| models/__init__.py | ~25 行删除 | 移除兼容层代码 |

### 不变文件

所有其他文件保持不变，使用 `from models import X` 的导入方式不受影响。

---

**准备就绪**: 等待 Phase 2 完成后开始执行 Day 6

