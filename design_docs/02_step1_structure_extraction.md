# Step 1 设计文档 (Structure Extraction)

## 概述

Step 1 负责将预处理阶段组装好的技能包（SkillPackage）解析为8个规范化的章节（canonical sections）。所有文本都从源文档原样复制，不做任何改写或省略。

## 架构位置

```
┌─────────────────────────────────────────────────────────────────┐
│                         Step 1                                  │
│              Structure Extraction (LLM驱动)                     │
├─────────────────────────────────────────────────────────────────┤
│  输入: SkillPackage (来自P3预处理阶段)                           │
│  输出: SectionBundle + list[ToolSpec] (网络API)                │
└─────────────────────────────────────────────────────────────────┘
                           ↓
                    [进入 Step 3]
```

## 核心职责

1. **章节分割**: 将合并后的文档文本分割为8个标准化章节
2. **原文保留**: 所有文本verbatim（原样）复制，不做改写
3. **网络API提取**: 从TOOLS章节提取网络API并转换为ToolSpec对象
4. **结构化输出**: 生成SectionBundle供后续步骤使用

## 8个规范章节

| 章节 | 说明 | 用途 |
|------|------|------|
| **INTENT** | 技能意图描述 | Step 4A: Persona定义 |
| **WORKFLOW** | 工作流程描述 | Step 3-W: 工作流分析 |
| **CONSTRAINTS** | 约束条件 | Step 4B: Constraints定义 |
| **TOOLS** | 工具/能力说明 | Step 4D: APIs定义 |
| **ARTIFACTS** | 产物/输出 | Step 3-IO: 文件识别 |
| **EVIDENCE** | 证据要求 | Step 3-W: 验证门识别 |
| **EXAMPLES** | 使用示例 | Step 4F: Examples注入 |
| **NOTES** | 备注/其他 | Step 4A: Persona补充 |

## 实现细节

### 文件位置
- **主实现**: `pipeline/llm_steps/step1_structure_extraction.py`
- **系统提示词**: `prompts/step1_system.py`
- **用户提示词模板**: `prompts/templates.py`

### 主入口函数

```python
def run_step1_structure_extraction(
    package: SkillPackage,
    client: LLMClient,
    model: Optional[str] = None,
) -> tuple[SectionBundle, list[ToolSpec]]:
    """
    Step 1: 将SkillPackage解析为8个规范章节。
    
    Args:
        package: P3阶段组装的SkillPackage
        client: LLM客户端
        model: 可选的模型覆盖
        
    Returns:
        (SectionBundle, 从TOOLS提取的网络API列表)
    """
```

### LLM调用

**系统提示词** (`prompts/step1_system.py`):
- 指导LLM将文档分割为8个章节
- 每个章节包含SectionItem列表
- 每个item包含: text (原文), source (来源文件), multi (是否跨章节)

**用户提示词** (`prompts/templates.render_step1_user`):
- 提供合并后的文档文本
- 要求LLM按预定义章节进行分割

**返回格式** (JSON):
```json
{
  "INTENT": [{"text": "...", "source": "SKILL.md", "multi": false}, ...],
  "WORKFLOW": [{"text": "...", "source": "SKILL.md", "multi": false}, ...],
  "CONSTRAINTS": [...],
  "TOOLS": [...],
  "ARTIFACTS": [...],
  "EVIDENCE": [...],
  "EXAMPLES": [...],
  "NOTES": [...]
}
```

### 网络API提取

从TOOLS章节提取网络API:

```python
def _extract_network_apis(tools_items: list[SectionItem]) -> list[ToolSpec]:
    """
    从TOOLS章节项中提取网络API。
    
    TOOLS章节可能包含:
    1. JSON数组格式的ToolSpec对象 (首选格式)
    2. 纯文本描述的API
    
    优先尝试JSON解析，失败则使用文本提取。
    """
```

**JSON解析**:
```python
# 尝试解析为JSON
if text.startswith('[') or text.startswith('{'):
    data = json.loads(text)
    # 提取api_type为"NETWORK_API"的ToolSpec
```

**文本提取** (fallback):
- 模式匹配: `"API名称 - 描述"`
- URL模式: `https?://...`
- 认证模式: `API key`, `OAuth`, `Bearer token`

## 数据模型

### SectionItem
```python
@dataclass
class SectionItem:
    """章节中的单个项目，文本始终原样复制"""
    text: str      # 来自源的原文，绝不改写
    source: str    # 来源文件名
    multi: bool = False  # 如果此项出现在多个章节中则为True
```

### SectionBundle
```python
@dataclass
class SectionBundle:
    """Step 1的输出，8个规范章节"""
    intent: list[SectionItem]      # INTENTION章节
    workflow: list[SectionItem]    # WORKFLOW章节
    constraints: list[SectionItem] # CONSTRAINTS章节
    tools: list[SectionItem]       # TOOLS章节
    artifacts: list[SectionItem]   # ARTIFACTS章节
    evidence: list[SectionItem]   # EVIDENCE章节
    examples: list[SectionItem]   # EXAMPLES章节
    notes: list[SectionItem]      # NOTES章节
    
    def all_sections(self) -> dict[str, list[SectionItem]]:
        """返回所有章节的字典表示"""
        return {
            "INTENT": self.intent,
            "WORKFLOW": self.workflow,
            "CONSTRAINTS": self.constraints,
            "TOOLS": self.tools,
            "ARTIFACTS": self.artifacts,
            "EVIDENCE": self.evidence,
            "EXAMPLES": self.examples,
            "NOTES": self.notes,
        }
```

### ToolSpec (网络API)
```python
@dataclass
class ToolSpec:
    """网络API规范"""
    name: str              # API名称
    api_type: str          # "NETWORK_API"
    url: str               # API端点URL
    authentication: str    # "none" | "apikey" | "oauth"
    input_schema: dict     # 输入参数模式
    output_schema: str     # 输出类型
    description: str       # 功能描述
    source_text: str       # 原始描述文本
```

## 数据流向

```
┌─────────────────────────────────────────────────────────────┐
│  SkillPackage (来自P3)                                     │
│  ├── merged_doc_text (带边界标记的合并文档)                 │
│  ├── file_role_map                                         │
│  └── tools (来自P3的代码/脚本API)                          │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Structure Extraction                               │
│  ├── 渲染用户提示词 (merged_doc_text)                        │
│  ├── 调用LLM (step1_structure_extraction)                  │
│  │   ├── 系统提示词: prompts/step1_system.py               │
│  │   └── 用户提示词: prompts/templates.py                  │
│  ├── 解析LLM JSON响应                                        │
│  │   └── _parse_section_bundle()                           │
│  ├── 从TOOLS提取网络API                                      │
│  │   └── _extract_network_apis()                           │
│  └── 返回 (SectionBundle, network_apis)                     │
└─────────────────────────────────────────────────────────────┘
                           ↓
              ┌────────────┴────────────┐
              ↓                         ↓
┌──────────────────────────┐  ┌──────────────────────────┐
│  SectionBundle            │  │  ToolSpec列表 (网络API)   │
│  ├── intent               │  │  (合并到总tools列表)      │
│  ├── workflow             │  └──────────────────────────┘
│  ├── constraints          │              ↓
│  ├── tools                │  [进入 Step 3]
│  ├── artifacts            │
│  ├── evidence             │
│  ├── examples             │
│  └── notes                │
└───────────────────────────┘
```

## 与其他步骤的关系

### 上游依赖
- **P3**: `SkillPackage` 作为输入

### 下游消费
| 章节 | 消费步骤 | 用途 |
|------|----------|------|
| intent | Step 4A | Persona定义 |
| workflow | Step 3-W | 工作流结构分析 |
| constraints | Step 4B | Constraints定义 |
| tools | Step 4D | APIs定义 (网络API) |
| artifacts | Step 3-IO | 文件识别 |
| evidence | Step 3-W | 验证门识别 |
| examples | Step 4F | Examples注入 |
| notes | Step 4A | Persona补充信息 |

## 关键设计决策

### 1. Verbatim文本保留
所有文本原样复制，不做LLM改写:
- 保持源文档的精确性
- 避免信息丢失
- 便于溯源和调试

### 2. 章节边界明确
8个章节覆盖技能文档的所有方面:
- 标准化工档结构
- 便于后续步骤针对性处理
- 支持多源文档合并

### 3. 网络API独立提取
从TOOLS章节单独提取网络API:
- 与代码/脚本API区分
- 需要不同的SPL生成策略
- 支持外部服务集成

### 4. Multi标记
支持跨章节内容标记:
- 同一内容可能出现在多个章节
- 避免重复处理
- 保持内容完整性

## 错误处理

| 情况 | 处理方式 |
|------|----------|
| LLM返回非JSON | 抛出异常，记录错误 |
| 章节缺失 | 使用空列表 |
| JSON解析失败 | 尝试文本提取(fallback) |
| ToolSpec解析失败 | 记录警告，跳过该API |

## 日志输出

```
[Step 1] extracted {total} items across all sections
[Step 1] extracted {n} network APIs from TOOLS section
```

## 相关文件

- `pipeline/llm_steps/step1_structure_extraction.py` - 主实现
- `prompts/step1_system.py` - 系统提示词
- `prompts/templates.py` - 提示词模板
- `models/data_models.py` - SectionBundle, SectionItem定义
