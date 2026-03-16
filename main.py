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
    skill = "brand-guidelines"
    # 生成当前时间字符串（格式：年-月-日_时-分-秒）
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 拼接带时间戳的输出目录
    output_dir = f'output/{skill}_{current_time}'
    output_dir = f'output/{skill}'

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



'''系统性地思考以下问题:

之前我们在Step 1要求必须提取normative statements,否则必须将其放入Notes字段,但是以我对normative的理解,似乎只有Constraints和Workflow需要normative statements吧(你现在在Step1的prompt里只说了Constraint必须normative)?但是我在想一个问题,有没有可能Constraints和Workflow相关的描述由于skill作者书写不规范,导致其虽然是和Constraints和Workflow相关的描述(normative),但是实际上却表述成descriptive text?如果有这种情况,我们是否应该将descriptive text转化为normative statements?

我对normative的理解如下,如果有不正确的地方,请直接指出:



```

---



# 1️⃣ 文档中 “Normative” 的含义



在这份文档里,**Normative 指的是“规范性语句 / 应当遵守的规则”**,也就是:



> **描述“应该做什么(should / must)”的规范,而不是描述系统事实或实现方式。**



这些 Normative 内容通常表现为:



* rule(规则)

* process step(步骤)

* policy constraint(策略约束)



它们会被进一步**拆分为 clause**,并被分类为:



```

Hard

Medium

Soft

Non-compilable

```



换句话说:



**Normative = 可转化为执行规则的规范性要求。**



---



# 2️⃣ 文档明确区分了 Normative 和其他类型内容



文档指出,规范性语句是需要被提取并编译的对象:



> “Break the skill into **atomic clauses (rules + process steps)**.” 



这些 clause 实际上就是 **Normative statements**。



也就是说:



```

normative statement

        ↓

atomic clause

        ↓

classified (Hard/Medium/Soft/Non-compilable)

```



---



# 3️⃣ Normative 的核心特点(文档给出的判断方式)



文档在讨论 clause 分类时说明:



> “Interpretation: you can deterministically check it and enforce it as a gate.” 



这里说的 **“enforce it”** 指的就是 **Normative rule**。



换句话说:



Normative statements 的特点是:



```

可被执行 / 检查 / 评估

```



然后根据可执行程度被分级:



| 类型             | 是否可强制执行 |

| -------------- | ------- |

| Hard           | 可确定性执行  |

| Medium         | 需要证据    |

| Soft           | 只能评分    |

| Non-compilable | 无法编译    |



---



# 4️⃣ Normative 语句的示例



文档中的例子:



### 示例1



> “Check for existing PRs before creating a new PR.” 



这是一个 **Normative rule**,因为它规定:



```

在创建PR之前必须检查已有PR

```



并且可以被自动化系统验证。



---



### 示例2



> “Wait for the page to load instead of using fixed sleeps.” 



这是一个 **Normative guideline**:



```

推荐等待页面加载

而不是sleep

```



属于 Medium 级。



---



# 5️⃣ 文档为什么强调 Normative



因为这篇文档的核心目标是:



**把自然语言 skill 编译成可执行结构。**



因此需要从文本中抽取:



```

descriptive text  → 忽略

normative clauses → 编译

```



也就是:



```

Skill text

   ↓

extract normative statements

   ↓

compile to rules/workflows

```



---



# 6️⃣ 一个简单理解方式



可以用下面这个对比来理解:



| 类型          | 示例                                     |

| ----------- | -------------------------------------- |

| Descriptive | “This tool extracts tables from PDFs.” |

| Normative   | “Use pdfplumber for table extraction.” |



只有 **Normative** 才会被编译。



---



# 7️⃣ 最简总结



在这份文档中:



**Normative = 可执行的规范性要求**



特点:



1️⃣ 描述 **应该做什么**

2️⃣ 可以拆成 **atomic clause**

3️⃣ 被分类为



```

Hard / Medium / Soft / Non-compilable

```



依据来自文档:



* “Break the skill into atomic clauses (rules + process steps).” 

* “Interpretation: you can deterministically check it and enforce it as a gate.” 



---

```
'''