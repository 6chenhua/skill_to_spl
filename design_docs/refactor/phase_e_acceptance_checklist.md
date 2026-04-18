# Phase E 验收检查清单

> **版本**: 1.0  
> **创建日期**: 2026-04-19  
> **状态**: 待执行

---

## 前置条件

- [ ] Phase A-D 所有任务已完成并合并到主分支
- [ ] 所有单元测试通过
- [ ] 代码审查完成
- [ ] CI/CD流水线配置完成

---

## 验收项目

### 1. E2E测试 ✅

| 检查项 | 状态 | 备注 |
|--------|------|------|
| 所有20个技能包通过E2E测试 | ⬜ | 运行: `pytest test/e2e/ -v --live_llm` |
| 核心技能（pdf, docx, pptx, xlsx）测试通过 | ⬜ | 优先验证 |
| 恢复机制测试通过 | ⬜ | `test_resume_functionality.py` |
| 测试执行时间 < 30分钟 | ⬜ | 并行执行 |

**测试命令**:
```bash
# 运行所有E2E测试
LIVE_LLM=1 pytest test/e2e/ -v --tb=short

# 仅核心技能
LIVE_LLM=1 pytest test/e2e/test_core_skills.py -v

# 跳过慢测试
LIVE_LLM=1 pytest test/e2e/ -v -m "not slow"
```

---

### 2. 性能测试 ✅

| 检查项 | 状态 | 备注 |
|--------|------|------|
| 性能基准已建立 | ⬜ | `test/performance/baseline.json` |
| 与基准对比性能回归 < 5% | ⬜ | 运行性能测试对比 |
| 内存使用 < 500MB | ⬜ | 验证峰值内存 |
| 无内存泄漏 | ⬜ | 多次运行对比 |

**测试命令**:
```bash
# 生成基准
pytest test/performance/ -v --performance-baseline --live_llm

# 对比基准
pytest test/performance/ -v --performance-compare --live_llm

# 自定义阈值
pytest test/performance/ -v --performance-compare --performance-threshold=10.0
```

---

### 3. 文档 ✅

| 检查项 | 状态 | 备注 |
|--------|------|------|
| README.md已更新 | ✅ | 包含重构后的架构 |
| 架构文档v2完成 | ⬜ | `design_docs/ARCHITECTURE_v2.md` |
| API文档已生成 | ⬜ | Sphinx/MkDocs |
| 迁移指南完成 | ⬜ | `MIGRATION_GUIDE.md` |

---

### 4. 代码质量

| 检查项 | 状态 | 备注 |
|--------|------|------|
| 测试覆盖率 >= 80% | ⬜ | `pytest --cov` |
| 代码重复率 < 10% | ⬜ | 使用codeclimate或类似工具 |
| 类型检查通过 | ⬜ | `mypy pipeline/ models/` |
| 代码风格检查通过 | ⬜ | `ruff check .` |

**命令**:
```bash
# 覆盖率
pytest test/ --cov=pipeline --cov=pre_processing --cov=models --cov-report=html

# 类型检查
mypy pipeline/ models/ pre_processing/

# 代码风格
ruff check .
black --check .
```

---

### 5. 向后兼容 ✅

| 检查项 | 状态 | 备注 |
|--------|------|------|
| 旧导入路径有效 | ⬜ | `from models.data_models import FileNode` |
| 旧API行为一致 | ⬜ | `run_pipeline(config)` 工作正常 |
| 弃用警告正确显示 | ⬜ | 使用`warnings.warn` |
| 回归测试通过 | ⬜ | `pytest test/regression/` |

---

### 6. 集成

| 检查项 | 状态 | 备注 |
|--------|------|------|
| CLI功能完整 | ⬜ | `skill-to-cnlp --help` |
| 程序化API可用 | ⬜ | `from pipeline.orchestrator import run_pipeline` |
| 与simplified_pipeline兼容 | ⬜ | 如适用 |
| 配置文件解析正常 | ⬜ | `.env`支持 |

---

## 验收标准汇总

### 整体AC

- [ ] 所有🔴严重问题已修复或缓解
- [ ] 测试覆盖率 >= 80%
- [ ] 性能无回归 (±5%)
- [ ] 代码重复率 < 10%
- [ ] 文档更新完成
- [ ] 向后兼容层工作正常

### 必须有

以下项必须全部通过：

1. ✅ E2E测试通过（核心技能）
2. ✅ 性能无回归
3. ✅ 向后兼容性
4. ✅ 关键文档更新

### 应该有

以下项应该通过：

1. ⬜ 所有20个技能E2E测试
2. ⬜ API文档生成
3. ⬜ 迁移指南
4. ⬜ 代码覆盖率 > 85%

---

## 文件清单

### 已创建的文件

| 文件 | 路径 | 状态 |
|------|------|------|
| E2E测试配置 | `test/e2e/conftest.py` | ✅ |
| 核心技能测试 | `test/e2e/test_core_skills.py` | ✅ |
| 扩展技能测试 | `test/e2e/test_extended_skills.py` | ✅ |
| 恢复机制测试 | `test/e2e/test_resume_functionality.py` | ✅ |
| 性能测试配置 | `test/performance/conftest.py` | ✅ |
| 性能测试 | `test/performance/test_performance_core.py` | ✅ |
| 性能基准 | `test/performance/baseline.json` | ✅ |
| 回归测试 | `test/regression/test_regression.py` | ✅ |
| 实施计划 | `design_docs/refactor/phase_e_implementation_plan.md` | ✅ |

### 已更新的文件

| 文件 | 路径 | 变更 |
|------|------|------|
| README.md | `README.md` | 项目结构更新 |

---

## 签字

| 角色 | 姓名 | 日期 | 签字 |
|------|------|------|------|
| 技术负责人 | | | |
| QA负责人 | | | |
| 产品经理 | | | |

---

## 附注

### 执行命令速查

```bash
# 完整测试套件
pytest test/ --cov=pipeline --cov-report=html -v

# E2E测试
LIVE_LLM=1 pytest test/e2e/ -v

# 性能测试
pytest test/performance/ -v --performance-compare --live_llm

# 回归测试
pytest test/regression/ -v

# 类型检查
mypy pipeline/ models/ pre_processing/

# 代码风格
ruff check . && black --check .
```

### 已知限制

1. **E2E测试需要LLM API**: 必须设置`LIVE_LLM=1`环境变量
2. **性能基准需要首次运行**: 使用`--performance-baseline`生成
3. **扩展技能测试较慢**: CI中可使用`-m "not slow"`跳过

---

**文档版本**: 1.0  
**最后更新**: 2026-04-19  
**作者**: Architecture Review Team
