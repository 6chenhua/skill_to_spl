# 预处理步骤设计文档 (Pre-processing Steps)

## 概述

预处理阶段负责将异构的技能包（skill package）转换为结构化的中间表示，为后续的LLM驱动步骤提供标准化输入。预处理完全基于代码实现，不依赖LLM调用。

## 架构流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     预处理阶段 (Pre-processing)                 │
│                     纯代码实现，无LLM依赖                         │
└─────────────────────────────────────────────────────────────────┘

Skill Package → P1 → P2 → P3 → SkillPackage (结构化输入)
                  ↓    ↓
              P2.5 (已合并到P3)
```

## 阶段详解

### P1: Reference Graph Builder (引用图构建器)

**文件位置**: `pre_processing/p1_reference_graph.py`

**职责**:
- 递归枚举技能根目录下的所有文件
- 读取所有 `.md` 文件的完整内容
- 读取脚本文件的前导注释（≤5行）
- 使用正则表达式扫描文档中的文件引用
- 输出: `FileReferenceGraph`

**文件分类规则**:
| 类型 | 扩展名 | 处理方式 |
|------|--------|----------|
| doc | `.md` | 读取完整内容，扫描引用 |
| script | `.py`, `.sh`, `.js`, `.ts` | 读取前5行注释 |
| data | `.json`, `.yaml`, `.yml`, `.toml`, `.csv` | 仅记录，不读取内容 |
| asset | 其他 | 仅记录，不读取内容 |

**引用扫描模式**:
- 反引号包裹的引用: `` `filename.ext` ``
- 裸文件名引用: `filename.md`, `script.py`

**关键数据结构**:
```python
@dataclass
class FileNode:
    path: str              # 相对路径
    kind: str              # doc | script | data | asset
    size_bytes: int        # 文件大小
    head_lines: list[str] # 前20行或注释
    references: list[str]  # 引用的其他文件

@dataclass
class FileReferenceGraph:
    skill_id: str
    root_path: str
    skill_md_content: str      # SKILL.md完整内容
    frontmatter: dict          # YAML前置元数据
    nodes: dict[str, FileNode] # 路径 -> 节点
    edges: dict[str, list[str]] # 文档 -> 引用的文件
    docs_content: dict[str, str] # 所有.md文件的完整内容
```

**跳过规则**:
- 目录: `__pycache__`, `node_modules`, `.git`, `.venv`, `venv`
- 文件: `.DS_Store`, `LICENSE.txt`, `LICENSE`, `COPYING`, `NOTICE`, `AUTHORS`

---

### P2: File Role Resolver (文件角色解析器)

**文件位置**: `pre_processing/p2_file_roles.py`

**职责**:
- 基于文件类型分配读取优先级
- 使用确定性规则系统（非LLM驱动）

**优先级分配**:
| 优先级 | 文件类型 | must_read | 说明 |
|--------|----------|-----------|------|
| 1 | doc (.md) | True | 必须读取全部内容，示例将进入SPL EXAMPLE部分 |
| 2 | script (.py/.sh/.js/.ts) | True | 由P2.5（已合并到P3）进行API规范提取 |
| 3 | data (.json/.yaml/.csv) | False | 配置文件或示例数据，不需要处理 |
| 3 | asset (其他) | False | 二进制文件、图片等，不处理 |

**输出**:
```python
dict[str, dict[str, Any]]  # rel_path -> {
    "role": str,                    # doc | script | data | asset
    "read_priority": int,           # 1-3
    "must_read_for_normalization": bool,
    "reasoning": str                # 分配理由
}
```

---

### P3: Skill Package Assembler (技能包组装器)

**文件位置**: `pre_processing/p3_assembler.py`

**职责**:
- 消费 P1 的 `FileReferenceGraph` 和 P2 的 `FileRoleMap`
- 优先级1（文档文件）: 读取完整内容 + 提取代码片段（异步并行）
- 优先级2（脚本文件）: 使用AST + LLM分析生成ToolSpec（异步并行）
- 优先级3（数据/资源）: 完全跳过
- 将内容拼接成 `merged_doc_text`，带有清晰的文件边界标记
- 输出: `SkillPackage`

**支持的语言** (代码片段提取):
```python
SUPPORTED_LANGUAGES = {
    # Python生态
    'python', 'py',
    # JavaScript/TypeScript
    'javascript', 'js', 'typescript', 'ts', 'jsx', 'tsx',
    # Web标记/样式
    'html', 'htm', 'css', 'scss', 'sass', 'less', 'svg',
    # JVM语言
    'java', 'kotlin', 'kt', 'scala', 'sc', 'groovy',
    'csharp', 'cs', 'vb', 'fsharp', 'fs',
    # C家族
    'c', 'cpp', 'cxx', 'cc', 'h', 'hpp', 'hxx',
    'rust', 'rs', 'go', 'golang',
    # 脚本语言
    'bash', 'sh', 'zsh', 'fish', 'shell',
    'powershell', 'ps1', 'psm1', 'pwsh',
    'perl', 'pl', 'pm', 'php', 'ruby', 'rb', 'lua',
    # 数据/配置
    'sql', 'yaml', 'yml', 'json', 'toml', 'xml', 'csv',
    # 其他
    'dockerfile', 'makefile', 'cmake', 'graphql', 'gql',
    ...
}
```

**代码片段提取**:
- 从Markdown文档中提取代码块 (```language ... ```)
- 使用LLM并行分析代码片段，提取API规范
- 生成 `ToolSpec` 对象

**脚本分析 (Python)**:
- 使用AST解析Python脚本
- 提取主函数参数和返回类型
- 生成 `ToolSpec` 对象

**脚本分析 (其他语言)**:
- 使用LLM分析非Python脚本
- 提取函数/方法签名
- 生成 `ToolSpec` 对象

**输出数据结构**:
```python
@dataclass
class SkillPackage:
    skill_id: str
    root_path: str
    frontmatter: dict              # YAML前置元数据
    merged_doc_text: str           # 拼接后的文档文本（带边界标记）
    file_role_map: dict[str, Any]  # 文件角色映射
    scripts: list[ScriptSpec]      # [已废弃] 使用tools代替
    tools: list[ToolSpec]          # 统一的API规范列表

@dataclass
class ToolSpec:
    name: str                      # API名称
    api_type: str                  # SCRIPT | CODE_SNIPPET | NETWORK_API
    url: str                       # 脚本路径 | library.Class | https://...
    authentication: str            # none | apikey | oauth
    input_schema: dict[str, str]   # 参数名 -> 类型
    output_schema: str             # 返回类型或"void"
    description: str               # 功能描述
    source_text: str               # 原始源代码/文本
```

**边界标记格式**:
```
=== FILE: {rel_path} | role: {role} | priority: {priority_label} ===
{content}
```

---

## 数据流向

```
┌─────────────────────────────────────────────────────────────┐
│  Skill Package (文件系统)                                   │
│  ├── SKILL.md                                               │
│  ├── *.py, *.js (脚本)                                      │
│  ├── *.md (文档)                                            │
│  └── *.json, *.yaml (数据)                                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  P1: build_reference_graph()                                │
│  ├── 枚举所有文件                                            │
│  ├── 分类文件类型                                            │
│  ├── 读取内容（docs完整，scripts前5行）                       │
│  └── 扫描引用关系                                            │
│  输出: FileReferenceGraph                                    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  P2: assign_file_priorities()                               │
│  ├── 基于扩展名分配优先级                                    │
│  └── 标记must_read标志                                       │
│  输出: FileRoleMap (dict)                                    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  P3: assemble_skill_package()                               │
│  ├── 优先级1: 读取完整文档 + 提取代码片段(LLM并行)            │
│  ├── 优先级2: AST+LLM分析脚本，生成ToolSpec(并行)             │
│  ├── 优先级3: 跳过                                           │
│  └── 拼接merged_doc_text                                     │
│  输出: SkillPackage                                          │
└─────────────────────────────────────────────────────────────┘
                           ↓
                    [进入 Step 1]
```

---

## 关键设计决策

### 1. 无LLM依赖
预处理阶段完全基于代码实现，确保:
- 确定性行为
- 快速执行
- 可预测的成本

### 2. 文件边界标记
使用明确的边界标记分隔不同文件的内容，帮助后续LLM步骤理解内容来源。

### 3. 引用验证
P1会验证文档中引用的文件是否真实存在，过滤不存在的引用（悬空引用）。

### 4. 并行处理
P3使用异步并行处理:
- 多个代码片段分析并行执行
- 多个脚本文件分析并行执行
- 最大化吞吐量

### 5. ToolSpec统一抽象
所有可调用实体（脚本、代码片段、外部API）都统一为 `ToolSpec`，简化后续步骤的处理逻辑。

---

## 错误处理

| 阶段 | 错误情况 | 处理方式 |
|------|----------|----------|
| P1 | SKILL.md不存在 | 抛出 FileNotFoundError |
| P1 | 文件读取失败 | 记录警告，跳过该文件 |
| P3 | 代码片段分析失败 | 记录警告，继续处理其他片段 |
| P3 | 脚本分析失败 | 记录警告，生成基本ToolSpec |

---

## 相关文件

- `pre_processing/p1_reference_graph.py` - P1实现
- `pre_processing/p2_file_roles.py` - P2实现
- `pre_processing/p3_assembler.py` - P3实现
- `pre_processing/p25_api_analyzer.py` - P2.5（已合并到P3）
- `models/data_models.py` - 数据模型定义
