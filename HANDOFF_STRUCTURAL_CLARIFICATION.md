# Structural Clarification Implementation - Handoff Document

## 当前状态

### ✅ 已完成 (Wave 1-2)

**Wave 1 (100%):**
- `simplified_pipeline/clarification/structural_models.py` - 数据模型
- `simplified_pipeline/clarification/structural_detector.py` - 检测器
- `simplified_pipeline/clarification/indirect_questions.py` - 问题生成器
- `simplified_pipeline/models.py` - 添加 SectionGuidance 到 PipelineResult

**Wave 2 (90%):**
- `simplified_pipeline/clarification/step0_orchestrator.py` - Step 0 协调器
- `simplified_pipeline/clarification/structural_ui.py` - 新 UI 接口
- `simplified_pipeline/steps.py` - 修改 Step 1 接受 guidance 参数

### 🔄 待完成 (Wave 3-4)

**Task 3.2: 更新 prompts.py**
文件: `simplified_pipeline/prompts.py`
需要修改:
1. `render_step1_user()` 函数添加 `guidance_section` 参数
2. `STEP1_SYSTEM` 提示词添加 guidance 使用说明

**Task 4.1: 更新 orchestrator.py**
文件: `simplified_pipeline/orchestrator.py`
需要修改:
1. 在 run_pipeline() 中 Step 1 之前插入 Step 0
2. 传递 structural_guidance 到 Step 1
3. 移除旧的在 Step 1 之后的 clarification 代码

**Wave 4: 测试**
- 单元测试: structural_detector, indirect_questions
- 集成测试: Step 0 → Step 1 流程

## 关键文件位置

```python
# Step 0 入口
from simplified_pipeline.clarification.step0_orchestrator import (
    run_step0_structural_clarification,
    format_guidance_for_prompt,
)

# Step 1 修改位置 (已部分完成)
simplified_pipeline/steps.py:33-55
```

## 实施下一步

1. 更新 prompts.py - 添加 guidance_section 支持
2. 更新 orchestrator.py - 插入 Step 0 调用
3. 编写测试
4. 验证 run_simplify_demo.py 能正常工作

## Acceptance Criteria

- Step 0 在 Step 1 之前运行
- 检测到结构归属模糊性 (如 WORKFLOW vs CONSTRAINTS)
- 生成间接问题 (如"描述工作方式还是硬性限制?")
- 用户答案指导 Step 1 段落分配
- SPL 输出反映澄清后的结构
- 向后兼容 (禁用 clarification 时正常工作)

## 关键代码参考

### prompts.py 需要添加的代码:

```python
def render_step1_user(merged_doc_text: str, guidance_section: str = "") -> str:
    return f"""## Document Package
{merged_doc_text}
{guidance_section}
"""
```

### orchestrator.py 需要修改的位置:

在 Step 1 之前插入:

```python
# ═════════════════════════════════════════════════════════════════════════
# STEP 0: Structural Clarification (NEW - runs BEFORE Step 1)
# ═════════════════════════════════════════════════════════════════════════
structural_guidance = None
if config.enable_clarification:
    from .clarification.step0_orchestrator import run_step0_structural_clarification
    from .clarification.structural_ui import ConsoleStructuralClarificationUI
    
    logger.info("[Step 0] Running structural clarification...")
    structural_guidance = run_step0_structural_clarification(
        merged_doc_text=merged_doc_text,
        ui=ConsoleStructuralClarificationUI(),
        max_questions=config.clarification_max_iterations,
    )
    _save_checkpoint(config, "step0_guidance", structural_guidance)
    logger.info(f"[Step 0] Generated guidance with {len(structural_guidance.section_overrides)} overrides")

# ── Step 1: Structure Extraction ──────────────────────────────────────
logger.info("[Step 1] Extracting structure...")
bundle = run_step1_structure_extraction(
    merged_doc_text=merged_doc_text,
    client=client,
    guidance=structural_guidance,  # NEW: Pass guidance to Step 1
)
```

## 核心设计要点

1. **Step 0 在 Step 1 之前运行** - 在段落提取前澄清归属
2. **检测结构模糊性** - 而非语言模糊性 (弱词、代词等)
3. **间接问题** - 用户看不到 "WORKFLOW"/"CONSTRAINTS" 等技术术语
4. **结果直接指导 Step 1** - 不是文本注释，而是结构化指导
5. **向后兼容** - 禁用 clarification 时原样工作
