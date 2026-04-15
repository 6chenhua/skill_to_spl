"""
Step 4 子步骤独立配置示例

Step 4 包含多个子步骤，每个都可以独立配置模型。
"""

from pipeline.llm_client import LLMConfig, StepLLMConfig
from pipeline.orchestrator import PipelineConfig


# 示例：为 Step 4 的子步骤配置不同模型
step_config = StepLLMConfig(
    step_models={
        # === Pre-steps ===
        "step1_structure_extraction": "gpt-4o-mini",
        "step1_5_api_generation": "gpt-4o-mini",
        
        # === Step 3 ===
        "step3a_entity_extraction": "gpt-4o",
        "step3b_workflow_analysis": "gpt-4o",
        
        # === Step 4 Substeps ===
        # S0: Agent header - 简单，用便宜模型
        "step0_define_agent": "gpt-4o-mini",
        
        # S4A: Persona - 需要理解 skill 意图
        "step4a_persona": "gpt-4o",
        
        # S4B: Constraints - 需要准确理解约束
        "step4b_constraints": "gpt-4o",
        
        # S4C: Variables/Files - 格式转换，较简单
        "step4c_variables_files": "gpt-4o-mini",
        
        # S4E: Worker - **最关键**，生成工作流逻辑
        "step4e_worker": "gpt-4-turbo",  # 用最强模型
        
        # S4E1: Nesting Detection - 检测嵌套问题
        "step4e1_nesting_detection": "gpt-4o-mini",
        
        # S4E2: Nesting Fix - 修复嵌套问题
        "step4e2_nesting_fix": "gpt-4o",
        
        # S4F: Examples - 生成示例
        "step4f_examples": "gpt-4o",
    }
)

# 创建 Pipeline 配置
config = PipelineConfig(
    skill_root="skills/pdf",
    output_dir="output/pdf",
    llm_config=LLMConfig(model="gpt-4o"),  # 默认模型
    step_llm_config=step_config,
)

print("Step 4 子步骤配置示例：")
print("=" * 60)
for step, model in step_config.step_models.items():
    if step.startswith("step4") or step.startswith("step0"):
        print(f"  {step:<35} -> {model}")
print("=" * 60)
print(f"\n共配置了 {len([s for s in step_config.step_models if s.startswith('step4') or s.startswith('step0')])} 个 Step 4 相关步骤")
