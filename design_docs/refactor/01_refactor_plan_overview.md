# Skill-to-CNL-P 架构重构计划 v2.0

> **版本**: 2.0  
> **创建日期**: 2026-04-17  
> **状态**: 等待用户确认  
> **预计工期**: 10-12 周（分4个Phase）  

---

## 执行摘要

本计划基于深度架构分析，不仅包含命名重构，更包含结构性架构改进。识别出**10个严重架构问题**，按严重程度分为：

| 严重程度 | 数量 | 主要问题 |
|---------|------|---------|
| 🔴 严重 | 6 | 职责过重、代码重复、配置硬编码、错误处理不当 |
| 🟡 中等 | 2 | 并行逻辑复杂、模板管理混乱 |
| 🟢 轻微 | 2 | 导入不统一、缺乏接口定义 |

---

## 一、严重架构问题详细分析

### 🔴 1. Pipeline Orchestrator 严重违反SRP (403行)

**位置**: `pipeline/orchestrator.py`

**问题描述**:
```python
def run_pipeline(config):
    # 第65-403行，238行代码混合了：
    # - P1: Reference Graph构建
    # - P2: File Role解析  
    # - P3: Package组装
    # - Step 1: 结构提取
    # - Step 1.5: API生成
    # - Step 3: Workflow分析 (W→IO→T)
    # - Step 4: 并行SPL发射
    # - 结果组装和输出
```

**违反的原则**: SRP, OCP, ISP

**影响**:
- 测试困难（需要mock整个管道）
- 难以理解（238行连续代码）
- 扩展困难（添加新步骤需修改此文件）
- 代码审查困难

**解决方案**:
```
pipeline/
├── orchestrator/
│   ├── __init__.py              # 公开API
│   ├── base.py                  # PipelineOrchestrator抽象基类
│   ├── builder.py               # PipelineBuilder模式
│   ├── execution_context.py     # 执行上下文
│   ├── step_executor.py         # 步骤执行抽象
│   └── runners/
│       ├── __init__.py
│       ├── sequential.py        # 顺序执行器
│       └── parallel.py          # 并行执行器
```

---

### 🔴 2. Data Models 臃肿 (495行)

**位置**: `models/data_models.py`

**问题描述**: 单个文件包含20+个数据类，职责混杂

**当前结构**:
```python
# models/data_models.py 包含:
# - FileNode, FileReferenceGraph (P1)
# - FileRoleEntry (P2)  
# - SectionItem, SectionBundle (Step 1)
# - EntitySpec, WorkflowStepSpec (Step 3)
# - StructuredSpec (Step 3)
# - APISpec, FunctionSpec (Step 1.5)
# - ToolSpec (Preprocessing)
# - SPLSpec (Step 4)
# - PipelineResult (全局)
# - 还有更多...
```

**违反的原则**: ISP, SRP

**解决方案**:
```
models/
├── __init__.py
├── base.py                      # 基础类型、协议
├── preprocessing/
│   ├── __init__.py
│   ├── reference.py             # FileNode, FileReferenceGraph
│   └── roles.py                 # FileRoleEntry
├── pipeline/
│   ├── __init__.py
│   ├── step1.py                 # SectionBundle, SectionItem
│   ├── step3.py                 # EntitySpec, WorkflowStepSpec, StructuredSpec
│   └── step4.py                 # SPLSpec
├── api.py                       # APISpec, FunctionSpec, UnifiedAPISpec
└── core.py                      # PipelineResult, ToolSpec
```

---

### 🔴 3. P3 Assembler 代码重复 (严重)

**位置**: `pre_processing/p3_assembler.py` 第200-314行

**问题描述**: 完全相同的代码块重复出现

**代码示例**:
```python
# 第202-229行
if task_type == "unified_api":
    if isinstance(result, list) and len(result) > 0:
        unified_apis.extend(result)
        logger.info("[P3/P2.5] Extracted %d unified APIs from %s", ...)
        
# 第253-295行 - 几乎完全相同！
if task_type == "snippet":
    if isinstance(result, list):
        snippet_tools = result
        tools.extend(snippet_tools)
        if snippet_tools:
            logger.info("[P3/P2.5] Extracted %d code snippets from %s", ...)
```

**违反的原则**: DRY

**解决方案**: 提取公共处理逻辑到独立函数

---

### 🔴 4. LLM调用模式重复 (90%+重复代码)

**位置**: `pipeline/llm_steps/step4_spl_emission/substep_calls.py`

**问题描述**: 每个step都有sync和async版本，代码重复率90%+

**当前代码**:
```python
def _call_4a(client, inputs, ...):      # 20行
    return client.call(...)

async def _call_4a_async(client, inputs, ...):  # 20行，完全相同逻辑
    return await client.async_call(...)
```

**违反的原则**: DRY

**解决方案**:
```python
# 统一使用async，提供sync包装
async def step4a_define_persona(client, ...):
    return await client.call(...)

def step4a_define_persona_sync(client, ...):
    return asyncio.run(step4a_define_persona(client, ...))
```

---

### 🔴 5. 硬编码配置与安全风险

**位置**: `pipeline/llm_client.py` 第39-40行

**问题描述**:
```python
@dataclass
class LLMConfig:
    base_url: str = 'https://api.rcouyi.com/v1'  # 硬编码URL
    api_key: str = "sk-V0s4x..."  # ⚠️ 硬编码API密钥！
```

**安全风险**:
- 密钥泄露到版本控制
- 无法多环境配置
- 无法轮换密钥

**违反的原则**: 安全最佳实践

**解决方案**:
```python
@dataclass
class LLMConfig:
    base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://default.com/v1"))
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY"))
    
    def __post_init__(self):
        if not self.api_key:
            raise ValueError("LLM_API_KEY environment variable required")
```

---

### 🔴 6. 错误处理不一致

**位置**: 多个文件

**问题描述**:
```python
# pipeline/orchestrator.py:57
except Exception:
    pass  # 完全忽略异常！

# pipeline/llm_client.py 第186-191行
def __del__(self):
    try:
        self.close()
    except Exception:  # 捕获所有异常
        pass
```

**违反的原则**: 健壮性原则

**解决方案**: 建立统一的错误处理策略，使用结构化异常

---

## 二、重构Phase详细规划

### Phase A: 立即修复 (第1-2周)

#### Week 1: Critical Bug Fixes

**任务 1.1: 修复P3 Assembler代码重复**
- **目标**: 消除pre_processing/p3_assembler.py中的重复代码
- **AC**:
  - [ ] 提取公共处理逻辑到 `_process_task_result()` 函数
  - [ ] 单元测试覆盖率 > 90%
  - [ ] 功能行为不变

**任务 1.2: 移除硬编码API密钥**
- **目标**: 从代码中移除所有硬编码凭证
- **AC**:
  - [ ] LLMConfig使用环境变量
  - [ ] 添加.env.example文件
  - [ ] 更新README配置说明
  - [ ] 检查并轮换已泄露的密钥

**任务 1.3: 统一错误处理**
- **目标**: 建立最小错误处理标准
- **AC**:
  - [ ] 禁止空的 except: pass
  - [ ] 至少记录警告日志
  - [ ] 代码审查检查

---

### Phase B: 数据模型重构 (第3-5周)

#### Week 3: 模型拆分设计

**任务 2.1: 设计新模型结构**
- **目标**: 创建新的models/目录结构
- **AC**:
  - [ ] 完成模型依赖关系图
  - [ ] 定义模块边界
  - [ ] 设计向后兼容策略

**任务 2.2: 创建基础模型**
- **目标**: 实现新的模型结构
- **AC**:
  - [ ] models/preprocessing/ 模块
  - [ ] models/pipeline/ 模块
  - [ ] models/api.py 模块
  - [ ] 全部通过类型检查

#### Week 4-5: 模型迁移

**任务 2.3: 逐步迁移**
- **目标**: 更新导入路径，保持向后兼容
- **AC**:
  - [ ] 所有预处理模块使用新模型
  - [ ] 所有pipeline步骤使用新模型
  - [ ] 旧导入添加弃用警告
  - [ ] 测试全部通过

---

### Phase C: Pipeline架构重构 (第6-9周)

#### Week 6-7: Pipeline Builder实现

**任务 3.1: 创建PipelineBuilder**
- **目标**: 实现Builder模式
- **AC**:
  - [ ] PipelineBuilder类
  - [ ] Step注册机制
  - [ ] 依赖图构建
  - [ ] 并行执行计划生成

**任务 3.2: 创建Step抽象**
- **目标**: 统一Step接口
- **AC**:
  - [ ] PipelineStep协议
  - [ ] StepExecutor抽象
  - [ ] 输入/输出契约定义

#### Week 8-9: Orchestrator重构

**任务 3.3: 重构主Orchestrator**
- **目标**: 拆分orchestrator.py
- **AC**:
  - [ ] orchestrator/base.py
  - [ ] orchestrator/builder.py
  - [ ] orchestrator/runners/
  - [ ] run_pipeline函数 < 50行
  - [ ] 测试覆盖率 > 80%

---

### Phase D: LLM客户端优化 (第10-11周)

#### Week 10: 统一调用模式

**任务 4.1: 统一Async/Sync**
- **目标**: 消除重复代码
- **AC**:
  - [ ] 所有step使用统一async模式
  - [ ] 自动生成sync包装器
  - [ ] 代码重复率 < 10%

**任务 4.2: 错误处理改进**
- **目标**: 改进LLM调用错误处理
- **AC**:
  - [ ] 结构化LLM错误
  - [ ] 重试策略可配置
  - [ ] 详细错误上下文

#### Week 11: 性能优化

**任务 4.3: 连接池管理**
- **目标**: 优化HTTP连接管理
- **AC**:
  - [ ] 连接复用
  - [ ] 优雅关闭
  - [ ] 资源泄漏检测

---

### Phase E: 最终集成与测试 (第12周)

#### Week 12: 集成测试

**任务 5.1: E2E测试**
- **目标**: 完整管道测试
- **AC**:
  - [ ] 所有示例技能包通过
  - [ ] 性能无回归 (±5%)
  - [ ] 内存无泄漏

**任务 5.2: 文档更新**
- **目标**: 更新所有文档
- **AC**:
  - [ ] README.md更新
  - [ ] 架构文档更新
  - [ ] API文档生成
  - [ ] 迁移指南

---

## 三、风险与缓解

### 高风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|-----|-------|-----|---------|
| 模型变更破坏现有代码 | 高 | 高 | 分阶段迁移 + 兼容层 + 全面测试 |
| Orchestrator重构引入bug | 高 | 高 | 详细测试 + 特性开关 |
| 性能回归 | 中 | 高 | 基准测试 + A/B对比 |

### 中风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|-----|-------|-----|---------|
| 开发者学习曲线 | 中 | 中 | 详细文档 + 代码示例 |
| 第三方依赖更新 | 低 | 中 | 依赖锁定 + CI测试 |

---

## 四、测试策略

### 测试金字塔

```
            /\
           /  \     E2E Tests (技能包级)
          /    \    10%
         /------\
        /        \   Integration Tests (模块级)
       /          \  30%
      /------------\
     /              \  Unit Tests (函数/类级)
    /                \ 60%
   /------------------\
```

### 每个Phase的测试要求

- **Phase A**: 单元测试 + 回归测试
- **Phase B**: 模型单元测试 + 集成测试
- **Phase C**: 功能测试 + 性能基准
- **Phase D**: 连接测试 + 错误场景测试
- **Phase E**: 完整E2E测试套件

---

## 五、验收标准汇总

### 整体AC

- [ ] 所有🔴严重问题已修复或缓解
- [ ] 测试覆盖率 >= 80%
- [ ] 性能无回归 (±5%)
- [ ] 代码重复率 < 10%
- [ ] 文档更新完成
- [ ] 向后兼容层工作正常

### Phase特定AC

详见每个Phase的详细AC部分。

---

## 六、文件变更清单

### Phase A
- `pre_processing/p3_assembler.py` - 消除重复
- `pipeline/llm_client.py` - 移除硬编码配置
- `pipeline/orchestrator.py` - 改进错误处理
- `.env.example` - 新增

### Phase B
- `models/data_models.py` - 拆分
- `models/preprocessing/` - 新增目录
- `models/pipeline/` - 新增目录
- `models/api.py` - 新增
- `models/core.py` - 新增

### Phase C
- `pipeline/orchestrator.py` - 重构
- `pipeline/orchestrator/` - 新增目录
- `pipeline/step_executor.py` - 新增

### Phase D
- `pipeline/llm_steps/step4_spl_emission/substep_calls.py` - 重构
- `pipeline/llm_client.py` - 改进

---

## 七、时间线与里程碑

```
Week 1-2:   Phase A - Critical Fixes
Week 3-5:   Phase B - Data Models
Week 6-9:   Phase C - Pipeline Architecture  
Week 10-11: Phase D - LLM Client
Week 12:    Phase E - Integration & Release
```

---

## 八、需要用户确认

1. **优先级**: 您是否同意按Phase A→B→C→D→E的顺序执行？
2. **范围**: 是否需要包括simplified_pipeline/目录？
3. **向后兼容**: 是否需要保持完整的API向后兼容性？
4. **性能要求**: 性能可接受的回归范围是多少？
5. **资源**: 可用的开发/测试资源如何？

---

**文档版本**: 2.0  
**最后更新**: 2026-04-17  
**作者**: Architecture Review Team
