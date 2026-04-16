from datetime import datetime
import atexit
import asyncio
import sys
import os

from examples.step4_substeps_example import step_config

# Windows asyncio 修复：禁止 ProactorEventLoop 警告
if sys.platform == 'win32':
    # 设置环境变量来禁用 asyncio 警告
    os.environ['PYTHONASYNCIODEBUG'] = '0'
    
    # 替换 ProactorEventLoop 的 __del__ 方法来抑制错误
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
        original_del = _ProactorBasePipeTransport.__del__
        def _suppress_del(self):
            try:
                original_del(self)
            except RuntimeError:
                pass  # 忽略 "Event loop is closed" 错误
        _ProactorBasePipeTransport.__del__ = _suppress_del
    except Exception:
        pass

from pipeline.llm_client import LLMConfig, StepLLMConfig
from pipeline.orchestrator import run_pipeline, PipelineConfig
import logging

# 配置 logging - 这一行是必须的！
logging.basicConfig(
    level=logging.INFO,  # 设置为 INFO 级别，让 info/log/debug 都显示
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)


def _cleanup_on_exit():
    """Clean up asyncio resources on program exit to prevent Windows warnings."""
    try:
        # Try to get and close the event loop
        try:
            loop = asyncio.get_event_loop()
            if loop and not loop.is_closed():
                # Cancel all pending tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                # Run until all tasks are cancelled
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()
        except RuntimeError:
            pass
    except Exception:
        pass


if __name__ == '__main__':
    # Register cleanup handler for Windows
    if sys.platform == 'win32':
        atexit.register(_cleanup_on_exit)

    skill = "pdf"
    # 生成当前时间字符串（格式：年-月-日_时-分-秒）
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 拼接带时间戳的输出目录
    output_dir = f'output/{skill}_{current_time}'
    output_dir = f'output/{skill}-v2'

    llm_config = LLMConfig(
        # base_url='https://openrouter.ai/api/v1',
        # api_key='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',
        model='gpt-4o',
        max_tokens=16000,
    )

    tep_config = StepLLMConfig(
        step_models={
            # === Pre-steps ===
            "step1_structure_extraction": "gpt-4o",
            "step1_5_api_generation": "gpt-4o",

            # === Old Step 3 ===
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
            "step4c_variables_files": "gpt-4o",

            # S4E: Worker - **最关键**，生成工作流逻辑
            "step4e_worker": "gpt-4",  # 用最强模型

            # S4E1: Nesting Detection - 检测嵌套问题
            "step4e1_nesting_detection": "gpt-4o",

            # S4E2: Nesting Fix - 修复嵌套问题
            "step4e2_nesting_fix": "gpt-4o",

            # S4F: Examples - 生成示例
            "step4f_examples": "gpt-4o",
        }
    )

    config = PipelineConfig(
        skill_root=f'skills/{skill}',
        output_dir=output_dir,
        llm_config=llm_config,
        # step_llm_config=step_config,
        # capability_profile=capability_profile,
        save_checkpoints=True,
        use_new_step3=True,
    )

    result = run_pipeline(config)
    print(result.spl_spec.spl_text)

