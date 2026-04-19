# Unified API Extraction Implementation Plan

## 1. Overview

### 1.1 Background
当前系统从MD文档的代码片段提取API时，每个代码片段生成独立的`ToolSpec`，导致：
- 同一library的多个方法分散成多个API声明
- 代码片段缺少import时无法正确识别library
- 多library的代码片段处理逻辑缺失

### 1.2 Goal
实现LLM驱动的统一API提取，支持：
- 智能识别代码片段使用的library（基于完整MD上下文）
- 按功能逻辑分组（非简单按library分组）
- 支持多library场景（使用`_and_`连接）
- 自动重试机制保证稳定性

## 2. Key Design Decisions

### 2.1 分组策略
**不是**简单按library分组，而是按"功能逻辑"分组：

```
示例1：同一MD文件中有多个pypdf代码片段
├── 片段1：导入pypdf，创建PdfReader → 属于pypdf组
├── 片段2：继续操作PdfReader对象 → 属于pypdf组
└── 片段3：导入requests，发送HTTP请求 → 属于requests组
结果：生成2个UnifiedAPISpec
- UnifiedAPISpec 1: pypdf（包含片段1+2的功能）
- UnifiedAPISpec 2: requests（包含片段3的功能）

示例2：混合使用多个library完成一个功能
├── 片段：同时使用pypdf读取 + requests上传
结果：生成1个UnifiedAPISpec
- UnifiedAPISpec: pypdf_and_requests（包含完整功能逻辑）
```

### 2.2 URL命名规则（详细到 library.class.method）

#### 单Function场景
```python
# 代码: from pypdf import PdfReader; reader = PdfReader("file.pdf")
url = "pypdf.PdfReader"

# 代码: reader.pages[0].extract_text()
url = "pypdf.PdfReader.pages.extract_text"

# 代码: writer.add_page(page)
url = "pypdf.PdfWriter.add_page"
```

#### 多Function场景（同一Class）
```python
# 代码: PdfReader 的多个方法
functions = [
    {"name": "PdfReader", "url": "pypdf.PdfReader"},
    {"name": "extract_text", "url": "pypdf.PdfReader.pages.extract_text"},
    {"name": "get_num_pages", "url": "pypdf.PdfReader.get_num_pages"}
]
```

#### 多Library场景（按出现顺序连接）
```python
# 代码中先出现pypdf，后出现requests
# ApiName: "PypdfAndRequestsProcessing"
# URL前缀: "pypdf_and_requests"

# Function1: pypdf相关
url = "pypdf.PdfReader.pages.extract_text"

# Function2: requests相关
url = "requests.post"

# Function3: 混合使用
url = "pypdf_and_requests.combined.extract_and_upload"
```

#### URL层级规范
```
格式: {library}[.{class}[.{method}[.{sub_method}]]]

示例:
- pypdf                                    # library本身
- pypdf.PdfReader                          # class
- pypdf.PdfReader.pages                    # class + 属性
- pypdf.PdfReader.pages.extract_text       # class + 属性 + 方法
- pypdf.utils.calc_checksum                # module + function
- requests.post                            # library + 方法
- axios.get                                # JS library + 方法
- fs.readFile                              # Node.js module + method
```

#### ApiName生成规则
```python
def generate_api_name(primary_library: str, all_libraries: list[str]) -> str:
    """
    生成API名称（PascalCase）
    """
    if len(all_libraries) == 1:
        # 单library: 直接使用library名 + 功能描述
        return f"{primary_library.capitalize()}Processing"  # e.g., "PypdfProcessing"
    else:
        # 多library: 用_and_连接，保持出现顺序
        parts = [lib.capitalize() for lib in all_libraries]
        return f"{'And'.join(parts)}Processing"  # e.g., "PypdfAndRequestsProcessing"
```

### 2.3 错误处理
- LLM分析失败时记录详细日志
- 自动重试（最多3次）
- 3次失败后跳过该MD文件，继续处理其他文件

## 3. Data Model Changes

### 3.1 New Models

```python
# models/data_models.py

@dataclass
class FunctionSpec:
    """单个函数的规格"""
    name: str                          # 函数/方法名
    signature: str                     # 代码片段或函数签名
    description: str                   # 功能描述
    input_schema: dict[str, str]      # 输入参数
    output_schema: str                 # 返回类型


@dataclass
class UnifiedAPISpec:
    """统一API规格（包含多个functions，支持多library）"""
    api_id: str                        # 唯一标识符（e.g., "pypdf_from_doc1"）
    api_name: str                      # API名称（PascalCase，用于SPL）
    primary_library: str               # 主要library（用于URL第一部分）
    all_libraries: list[str]           # 所有涉及的libraries
    language: str                      # 编程语言
    functions: list[FunctionSpec]      # 该API包含的所有functions
    combined_source: str               # 合并的源代码（用于SPL生成）
    source_file: str                   # 来源MD文件


@dataclass
class SkillPackage:
    """Updated SkillPackage with unified APIs"""
    skill_id: str
    root_path: str
    frontmatter: dict[str, Any]
    merged_doc_text: str
    file_role_map: dict[str, Any]
    scripts: list[ScriptSpec] = field(default_factory=list)
    tools: list[ToolSpec] = field(default_factory=list)
    unified_apis: list[UnifiedAPISpec] = field(default_factory=list)  # NEW
```

### 3.2 Updated APISymbolTable

```python
@dataclass
class APISymbolTable:
    """API符号表（兼容旧格式+新格式）"""
    apis: dict[str, APISpec]                    # 旧格式（保留兼容）
    unified_apis: dict[str, UnifiedAPISpec]     # 新格式（按api_name索引）
```

## 4. Implementation Steps

### Step 1: Create Unified API Extractor

**文件**: `pre_processing/unified_api_extractor.py`

**核心函数**:
```python
async def extract_unified_apis_from_doc(
    content: str,
    source_file: str,
    client,
    max_retries: int = 3
) -> list[UnifiedAPISpec]:
    """
    使用LLM从MD文件提取统一API规格
    
    Args:
        content: MD文件完整内容
        source_file: 源文件路径（用于logging）
        client: LLM客户端
        max_retries: 最大重试次数
        
    Returns:
        list[UnifiedAPISpec]: 该MD文件提取的所有统一API
    """
    pass


def _build_extraction_prompt(content: str, source_file: str) -> str:
    """
    构建LLM提取prompt
    
    关键指令：
    1. 分析所有代码块及其编程语言
    2. 识别代码块之间的依赖关系
    3. 按功能逻辑分组（非简单按library）
    4. 提取每个function的完整信息
    """
    pass


def _parse_llm_response(response: dict, source_file: str) -> list[UnifiedAPISpec]:
    """解析LLM输出为UnifiedAPISpec对象"""
    pass
```

**LLM Prompt设计**:
```
Task: Analyze this markdown file and extract unified API specifications.

Source: {source_file}

Content:
```markdown
{content}
```

Instructions:
1. Identify all code blocks and their programming language
2. Analyze dependencies between code blocks:
   - If code block B uses variables/objects from code block A, they belong to the same functional group
   - If code block B imports different libraries and performs unrelated operations, it may be a separate group
3. Group code blocks by FUNCTIONAL LOGIC, not just by library
4. For each functional group:
   - Identify all libraries used (primary and secondary)
   - Extract ALL functions/methods/classes demonstrated
   - Note input/output types for each function
   - Generate a descriptive API name

Grouping Rules:
- SCENARIO 1: Sequential dependent code (same group)
  * Block 1: "import pypdf; reader = pypdf.PdfReader('file.pdf')"
  * Block 2: "text = reader.pages[0].extract_text()"  # uses 'reader' from Block 1
  * Result: Both in same "pypdf" group

- SCENARIO 2: Independent code blocks (separate groups)
  * Block 1: "import pypdf; reader = pypdf.PdfReader('file.pdf')"
  * Block 2: "import requests; r = requests.get('https://api.com')"
  * Result: Two groups - "pypdf" and "requests"

- SCENARIO 3: Mixed usage (single group with multiple libraries)
  * Block: "import pypdf; import requests; 
            reader = pypdf.PdfReader('file.pdf');
            requests.post('https://api.com', data=reader.pages[0].extract_text())"
  * Result: Single group "pypdf_and_requests"

Output Format:
```json
[
  {
    "api_name": "PdfProcessing",  // PascalCase, descriptive
    "primary_library": "pypdf",
    "all_libraries": ["pypdf"],
    "language": "python",
    "functions": [
      {
        "name": "PdfReader",
        "signature": "PdfReader(file_path: str)",
        "description": "Create a PDF reader instance from file path",
        "inputs": {"file_path": "text"},
        "outputs": "PdfReader object"
      },
      {
        "name": "extract_text",
        "signature": "page.extract_text()",
        "description": "Extract text content from a PDF page",
        "inputs": {"page": "number"},
        "outputs": "text"
      }
    ],
    "combined_source": "import pypdf\nreader = pypdf.PdfReader(...)\ntext = reader.pages[0].extract_text()"
  }
]
```

Important:
- Include ALL functions demonstrated in the code
- Preserve exact code snippets in "combined_source"
- Use descriptive names, not just library names
- If multiple libraries work together, include all in "all_libraries"
```

### Step 2: Update P3 Assembler

**文件**: `pre_processing/p3_assembler.py`

**修改点**:
```python
async def _extract_snippets_from_doc_async(
    content: str, source_file: str, client
) -> tuple[list[ToolSpec], list[UnifiedAPISpec]]:
    """
    更新：同时返回旧的ToolSpec和新的UnifiedAPISpec
    
    迁移策略：
    - 保留旧逻辑生成ToolSpec（兼容现有代码）
    - 新增UnifiedAPISpec提取
    """
    # 旧逻辑（保留兼容）
    tools = await _extract_snippets_legacy(content, source_file, client)
    
    # 新逻辑（统一API提取）
    unified_apis = await extract_unified_apis_from_doc(
        content, source_file, client
    )
    
    return tools, unified_apis
```

### Step 3: Update SkillPackage

**文件**: `models/data_models.py`

**修改点**:
```python
@dataclass
class SkillPackage:
    # ... existing fields ...
    unified_apis: list[UnifiedAPISpec] = field(default_factory=list)
```

### Step 4: Update Step 1.5 API Generation

**文件**: `pipeline/llm_steps/step1_5_api_generation.py`

**修改点**:
```python
def generate_unified_api_definitions(
    unified_apis: list[UnifiedAPISpec],
    client: LLMClient,
    max_workers: int = 4,
    model: Optional[str] = None,
) -> APISymbolTable:
    """
    为UnifiedAPISpec生成SPL API定义
    
    与旧版区别：
    - UnifiedAPISpec可能包含多个functions
    - 生成单个API声明，包含所有functions
    """
    pass


def _generate_single_unified_api(
    unified_api: UnifiedAPISpec,
    client: LLMClient,
    model: Optional[str] = None,
) -> APISpec:
    """
    生成包含多个functions的API声明
    
    输出示例：
    PdfProcessing<none>
    { }
    {
      functions: [
        { name: "PdfReader", url: "pypdf.PdfReader", ... },
        { name: "extract_text", url: "pypdf.Page.extract_text", ... }
      ]
    }
    """
    pass
```

**LLM Prompt更新**:
```
Generate a unified API declaration for library/libraries: {libraries}

This API contains {function_count} functions:
{functions_json}

Combined source code:
```python
{combined_source}
```

Generate a single API declaration with:
- API name: {api_name} (PascalCase)
- URL: Use "{library_or_libraries}" format
- functions: List all functions with their signatures

Example output:
PdfProcessing<none>
{ }
{
  functions: [
    {
      name: "Create PDF Reader",
      url: "pypdf.PdfReader",
      description: "Creates a PDF reader from file path",
      parameters: {
        parameters: [
          {required: true, name: "file_path", type: text}
        ],
        controlled-input: false
      },
      return: {
        type: PdfReader,
        controlled-output: false
      }
    },
    ...
  ]
}
```

### Step 5: Update Step 4 SPL Emission

**文件**: `pipeline/llm_steps/step4_spl_emission/orchestrator.py`

**修改点**:
```python
def run_step4_spl_emission(..., unified_apis: list[UnifiedAPISpec] = None):
    """
    更新：支持UnifiedAPISpec
    
    策略：
    - 优先使用unified_apis（如果存在）
    - 否则回退到旧的tools列表
    """
    if unified_apis:
        # 使用新逻辑
        api_table = generate_unified_api_definitions(unified_apis, client)
    else:
        # 回退到旧逻辑
        api_table = generate_api_definitions(tools, client)
```

### Step 6: Retry Logic Implementation

**文件**: `pre_processing/unified_api_extractor.py`

```python
import asyncio
import logging

logger = logging.getLogger(__name__)


async def extract_unified_apis_with_retry(
    content: str,
    source_file: str,
    client,
    max_retries: int = 3
) -> list[UnifiedAPISpec]:
    """
    带重试机制的Unified API提取
    """
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[UnifiedAPI] Extracting from {source_file} (attempt {attempt}/{max_retries})")
            
            result = await _extract_unified_apis_once(content, source_file, client)
            
            if result:
                logger.info(f"[UnifiedAPI] Successfully extracted {len(result)} APIs from {source_file}")
                return result
                
        except Exception as e:
            last_error = e
            logger.warning(
                f"[UnifiedAPI] Attempt {attempt} failed for {source_file}: {str(e)}"
            )
            
            if attempt < max_retries:
                # 指数退避：1s, 2s, 4s
                wait_time = 2 ** (attempt - 1)
                logger.info(f"[UnifiedAPI] Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
    
    # 所有重试都失败
    logger.error(
        f"[UnifiedAPI] All {max_retries} attempts failed for {source_file}. "
        f"Last error: {last_error}"
    )
    
    # 返回空列表（不中断流程）
    return []
```

## 5. Migration Strategy

### Phase 1: 并行运行（Backward Compatible）
- 保留旧的`ToolSpec`提取逻辑
- 新增`UnifiedAPISpec`提取
- Step 1.5优先使用`UnifiedAPISpec`，不存在时回退到`ToolSpec`

### Phase 2: 逐步迁移
- 验证新逻辑稳定性
- 更新下游组件逐步使用`UnifiedAPISpec`

### Phase 3: 清理（可选）
- 移除旧`ToolSpec`提取逻辑（CODE_SNIPPET部分）
- 保留SCRIPT类型（独立API不变）

## 6. Testing Strategy

### 6.1 Unit Tests

```python
# test_unified_api_extractor.py

class TestUnifiedAPIExtractor:
    
    def test_single_library_grouping(self):
        """测试同一library的代码片段正确分组"""
        content = """
        ## PDF处理
        ```python
        import pypdf
        reader = pypdf.PdfReader("file.pdf")
        ```
        
        ```python
        text = reader.pages[0].extract_text()
        ```
        """
        result = extract_unified_apis_from_doc(content, "test.md", mock_client)
        assert len(result) == 1
        assert result[0].primary_library == "pypdf"
        assert len(result[0].functions) == 2
    
    def test_multi_library_grouping(self):
        """测试多library代码片段的分组"""
        content = """
        ```python
        import pypdf
        import requests
        reader = pypdf.PdfReader("file.pdf")
        requests.post("https://api.com", data=reader.pages[0].extract_text())
        ```
        """
        result = extract_unified_apis_from_doc(content, "test.md", mock_client)
        assert len(result) == 1
        assert result[0].api_name == "PypdfAndRequestsProcessing"  # 或类似的
        assert "pypdf" in result[0].all_libraries
        assert "requests" in result[0].all_libraries
    
    def test_retry_mechanism(self):
        """测试重试机制"""
        # 模拟LLM前两次失败，第三次成功
        pass
```

### 6.2 Integration Tests

```python
# test_end_to_end.py

async def test_full_pipeline_with_unified_apis():
    """测试完整pipeline使用新Unified API逻辑"""
    # 1. 准备测试MD文件
    # 2. 运行P3提取
    # 3. 运行Step 1.5生成API
    # 4. 验证生成的SPL包含合并的API
    pass
```

### 6.3 Detailed Test Cases

#### TC-001: Single Library, Multiple Methods (Basic Case)
**输入**:
```markdown
# PDF Processing Guide

## Reading PDF
```python
from pypdf import PdfReader
reader = PdfReader("input.pdf")
text = reader.pages[0].extract_text()
```

## Writing PDF
```python
from pypdf import PdfWriter
writer = PdfWriter()
writer.add_page(reader.pages[0])
writer.write("output.pdf")
```
```

**期望输出**:
```json
{
  "api_name": "PypdfProcessing",
  "primary_library": "pypdf",
  "all_libraries": ["pypdf"],
  "functions": [
    {
      "name": "PdfReader",
      "url": "pypdf.PdfReader",
      "input_schema": {"file_path": "text"},
      "output_schema": "PdfReader"
    },
    {
      "name": "extract_text",
      "url": "pypdf.PdfReader.pages.extract_text",
      "input_schema": {},
      "output_schema": "text"
    },
    {
      "name": "PdfWriter",
      "url": "pypdf.PdfWriter",
      "input_schema": {},
      "output_schema": "PdfWriter"
    },
    {
      "name": "add_page",
      "url": "pypdf.PdfWriter.add_page",
      "input_schema": {"page": "Page"},
      "output_schema": "void"
    },
    {
      "name": "write",
      "url": "pypdf.PdfWriter.write",
      "input_schema": {"file_path": "text"},
      "output_schema": "void"
    }
  ]
}
```

**验证点**:
- [ ] 只生成1个UnifiedAPISpec
- [ ] api_name为"PypdfProcessing"（PascalCase）
- [ ] 包含5个functions
- [ ] URL格式为`pypdf.PdfReader`、`pypdf.PdfReader.pages.extract_text`等

---

#### TC-002: Multi-Library Mixed Usage
**输入**:
```markdown
# Upload PDF Content

```python
import pypdf
import requests

# Read PDF
reader = pypdf.PdfReader("doc.pdf")
text = reader.pages[0].extract_text()

# Upload to cloud
response = requests.post(
    "https://api.example.com/upload",
    json={"content": text, "filename": "doc.pdf"}
)
print(response.json())
```
```

**期望输出**:
```json
{
  "api_name": "PypdfAndRequestsProcessing",
  "primary_library": "pypdf",
  "all_libraries": ["pypdf", "requests"],
  "functions": [
    {
      "name": "PdfReader",
      "url": "pypdf.PdfReader",
      "input_schema": {"file_path": "text"},
      "output_schema": "PdfReader"
    },
    {
      "name": "extract_text",
      "url": "pypdf.PdfReader.pages.extract_text",
      "input_schema": {},
      "output_schema": "text"
    },
    {
      "name": "post",
      "url": "requests.post",
      "input_schema": {"url": "text", "json": "dict"},
      "output_schema": "Response"
    },
    {
      "name": "json",
      "url": "requests.Response.json",
      "input_schema": {},
      "output_schema": "dict"
    }
  ]
}
```

**验证点**:
- [ ] 只生成1个UnifiedAPISpec
- [ ] api_name为"PypdfAndRequestsProcessing"
- [ ] all_libraries包含["pypdf", "requests"]（按出现顺序）
- [ ] requests函数的URL为"requests.post"

---

#### TC-003: JavaScript/TypeScript Support
**输入**:
```markdown
# File Upload

```javascript
import axios from 'axios';
import fs from 'fs';

const data = fs.readFileSync('file.txt');
axios.post('https://api.com/upload', { data })
  .then(res => console.log(res.data));
```
```

**期望输出**:
```json
{
  "api_name": "FsAndAxiosProcessing",
  "primary_library": "fs",
  "all_libraries": ["fs", "axios"],
  "language": "javascript",
  "functions": [
    {
      "name": "readFileSync",
      "url": "fs.readFileSync",
      "input_schema": {"path": "text"},
      "output_schema": "Buffer"
    },
    {
      "name": "post",
      "url": "axios.post",
      "input_schema": {"url": "text", "data": "any"},
      "output_schema": "Promise"
    },
    {
      "name": "then",
      "url": "Promise.then",
      "input_schema": {"callback": "function"},
      "output_schema": "Promise"
    }
  ]
}
```

**验证点**:
- [ ] 正确识别JavaScript代码
- [ ] 支持ES6 import语法
- [ ] URL格式为"axios.post"、"fs.readFileSync"

---

#### TC-004: Missing Import Inference
**输入**:
```markdown
# PDF Operations

```python
import pypdf
reader = pypdf.PdfReader("file.pdf")
```

```python
# Process page (no import!)
text = reader.pages[0].extract_text()
```
```

**期望输出**:
```json
{
  "api_name": "PypdfProcessing",
  "primary_library": "pypdf",
  "functions": [
    {
      "name": "PdfReader",
      "url": "pypdf.PdfReader"
    },
    {
      "name": "extract_text",
      "url": "pypdf.PdfReader.pages.extract_text"
    }
  ]
}
```

**验证点**:
- [ ] 即使第二个代码块没有import，也能识别出使用pypdf
- [ ] 两个代码块合并到同一个API

---

#### TC-005: Retry Mechanism
**场景**:
- 第1次调用LLM：超时异常
- 第2次调用LLM：返回格式错误
- 第3次调用LLM：成功

**期望行为**:
- [ ] 自动重试3次
- [ ] 第1次失败后等待1秒
- [ ] 第2次失败后等待2秒
- [ ] 最终返回正确结果

---

#### TC-006: Multi-Language Support
**输入**:
```markdown
# Multi-Language Guide

```python
import pypdf
```

```javascript
import axios from 'axios';
```

```bash
curl -X POST https://api.com
```
```

**期望输出**:
```json
[
  {
    "api_name": "PypdfProcessing",
    "language": "python",
    "primary_library": "pypdf"
  },
  {
    "api_name": "AxiosProcessing",
    "language": "javascript",
    "primary_library": "axios"
  }
]
```

**验证点**:
- [ ] 识别不同编程语言
- [ ] bash代码被过滤（不在SUPPORTED_LANGUAGES中）
- [ ] 每种语言生成独立的API

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM输出格式不稳定 | 高 | 严格的JSON schema验证 + 重试机制 |
| Token消耗过高 | 中 | MD文件截断到安全长度（当前context足够） |
| 分组逻辑错误 | 高 | 充分的测试覆盖 + fallback到单片段模式 |
| 与旧系统不兼容 | 低 | 保留旧接口，逐步迁移 |

## 8. Timeline Estimate

| Step | Estimated Effort | Priority |
|------|------------------|----------|
| Step 1: Unified API Extractor | 2 days | P0 |
| Step 2: Update P3 Assembler | 1 day | P0 |
| Step 3: Update Data Models | 0.5 day | P0 |
| Step 4: Update Step 1.5 | 1 day | P0 |
| Step 5: Update Step 4 | 0.5 day | P1 |
| Step 6: Retry Logic | 0.5 day | P0 |
| Testing & Validation | 2 days | P0 |
| Documentation | 0.5 day | P2 |
| **Total** | **~8 days** | |

## 9. Acceptance Criteria (Definition of Done)

### AC-001: URL Naming Convention (MUST)
**Given** 代码片段使用pypdf库读取PDF
**When** 提取API规格
**Then** 生成functions的URL格式为：
- `pypdf.PdfReader` (class level)
- `pypdf.PdfReader.pages` (class + property)
- `pypdf.PdfReader.pages.extract_text` (class + property + method)
- `pypdf.PdfWriter.add_page` (class + method)

**验证标准**:
- [ ] URL必须包含完整的调用链（library.class.method）
- [ ] 支持多级属性访问（如`.pages.extract_text`）
- [ ] 单library场景：URL前缀为单一library名

---

### AC-002: Multi-Library URL Naming (MUST)
**Given** 代码片段混合使用pypdf和requests库
**When** 提取API规格
**Then** 生成的API声明满足：
- api_name = "PypdfAndRequestsProcessing"（按出现顺序PascalCase）
- pypdf函数的URL保持"pypdf.PdfReader"格式
- requests函数的URL保持"requests.post"格式
- all_libraries = ["pypdf", "requests"]（按出现顺序）

**验证标准**:
- [ ] 多library场景：api_name用"And"连接（保持出现顺序）
- [ ] 每个function的URL精确指向其所属library
- [ ] 不混合不同library的URL

---

### AC-003: Function Grouping (MUST)
**Given** MD文件中有3个pypdf相关代码片段和2个requests代码片段
**When** 提取统一API
**Then** 根据功能逻辑分组：
- Group 1 (pypdf): 包含3个代码片段中的所有pypdf方法
- Group 2 (requests): 包含2个代码片段中的所有requests方法
- 或 Single Group (如果代码片段间存在依赖关系)

**验证标准**:
- [ ] 依赖的代码片段合并到同一API（代码B使用代码A的变量）
- [ ] 独立的代码片段分到不同API
- [ ] 一个UnifiedAPISpec包含多个FunctionSpec

---

### AC-004: Missing Import Inference (MUST)
**Given** 代码块A导入pypdf，代码块B使用`reader.pages`但没有import
**When** 提取API规格
**Then** 代码块B正确识别为pypdf库，合并到代码块A的API

**验证标准**:
- [ ] 基于上下文推断代码片段使用的library
- [ ] 不依赖import语句也能正确分组
- [ ] LLM能理解代码块间的依赖关系

---

### AC-005: Multi-Language Support (MUST)
**Given** MD文件包含Python、JavaScript、TypeScript代码片段
**When** 提取统一API
**Then** ：
- Python代码生成PascalCase命名的API（如"PypdfProcessing"）
- JavaScript代码生成独立的API（如"AxiosProcessing"）
- TypeScript代码正确处理类型注解

**验证标准**:
- [ ] 支持Python、JavaScript、TypeScript
- [ ] 正确识别各语言的import语法
- [ ] URL格式适应各语言特性（如JS的`axios.get`，Python的`requests.post`）

---

### AC-006: Retry Mechanism (MUST)
**Given** LLM调用失败
**When** 执行提取
**Then** ：
- 自动重试最多3次
- 第1次失败后等待1秒
- 第2次失败后等待2秒
- 第3次失败后记录ERROR日志并返回空列表

**验证标准**:
- [ ] 每次失败记录详细日志（包括失败原因）
- [ ] 指数退避重试间隔
- [ ] 不中断整体流程（失败单个MD文件不影响其他文件）

---

### AC-007: SPL API Generation (MUST)
**Given** UnifiedAPISpec包含多个functions
**When** 生成SPL API声明
**Then** 生成的SPL格式：
```spl
PypdfProcessing<none>
{ }
{
  functions: [
    { name: "PdfReader", url: "pypdf.PdfReader", ... },
    { name: "extract_text", url: "pypdf.PdfReader.pages.extract_text", ... },
    { name: "PdfWriter", url: "pypdf.PdfWriter", ... }
  ]
}
```

**验证标准**:
- [ ] 单个API声明包含所有functions
- [ ] URL格式符合AC-001/AC-002要求
- [ ] SPL语法正确，可被后续步骤使用

---

### AC-008: Backward Compatibility (MUST)
**Given** 旧版系统使用ToolSpec
**When** 集成新版UnifiedAPISpec
**Then** ：
- 未更新的代码继续正常工作
- SkillPackage同时包含`tools`和`unified_apis`字段
- Step 1.5优先使用unified_apis，不存在时回退到tools

**验证标准**:
- [ ] 旧代码无需修改即可运行
- [ ] 新旧API格式可在同一pipeline中共存
- [ ] 测试旧pipeline和新pipeline产生相同结果

---

### AC-009: Performance Requirements (SHOULD)
**Given** 正常大小的MD文件（<50KB）
**When** 提取统一API
**Then** ：
- 单次LLM调用<10秒
- Token消耗<4000（输入+输出）
- 单个MD文件处理时间<30秒

---

### AC-010: Test Coverage (MUST)
**验证标准**:
- [ ] 单元测试覆盖率>80%
- [ ] 包含TC-001到TC-006的测试用例
- [ ] 集成测试覆盖完整pipeline流程
- [ ] 所有测试用例通过

---

**Created**: 2026-04-16
**Author**: AI Assistant
**Status**: Ready for Implementation
