from datetime import datetime

from pipeline.llm_client import LLMConfig
from pipeline.orchestrator import run_pipeline, PipelineConfig
import logging

# 配置 logging - 这一行是必须的！
logging.basicConfig(
    level=logging.INFO,  # 设置为 INFO 级别，让 info/log/debug 都显示
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)


if __name__ == '__main__':
    skill = "pdf"
    # 生成当前时间字符串（格式：年-月-日_时-分-秒）
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 拼接带时间戳的输出目录
    output_dir = f'output/{skill}_{current_time}'

    llm_config = LLMConfig(
        # base_url='https://openrouter.ai/api/v1',
        # api_key='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',
        model='gpt-4o',
        max_tokens=16000,
    )
    config = PipelineConfig(
        skill_root=f'skills/{skill}',
        output_dir=output_dir,
        llm_config=llm_config,
        # capability_profile=capability_profile,
        save_checkpoints=True,
    )

    result = run_pipeline(config)
    print(result.spl_spec.spl_text)