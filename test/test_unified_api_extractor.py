"""Unit tests for unified API extractor.

Tests TC-001 through TC-006 from the implementation plan.
"""

import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from pre_processing.unified_api_extractor import (
    extract_unified_apis_with_retry,
    extract_unified_apis_from_doc,
    FunctionSpec,
    UnifiedAPISpec,
    _build_extraction_prompt,
    _parse_llm_response,
    generate_function_url,
    generate_api_name,
)


class TestUnifiedAPIExtractor:
    """Test cases TC-001 through TC-006."""

    # ═══════════════════════════════════════════════════════════════════════
    # TC-001: Single Library, Multiple Methods (Basic Case)
    # ═══════════════════════════════════════════════════════════════════════
    
    @pytest.mark.asyncio
    async def test_tc001_single_library_grouping(self):
        """TC-001: 测试同一library的代码片段正确分组"""
        content = """
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
"""
        
        # Mock LLM client response
        mock_client = AsyncMock()
        mock_client.async_call_json.return_value = {
            "apis": [
                {
                    "api_name": "PypdfProcessing",
                    "primary_library": "pypdf",
                    "all_libraries": ["pypdf"],
                    "language": "python",
                    "functions": [
                        {
                            "name": "PdfReader",
                            "signature": "PdfReader(file_path: str)",
                            "description": "Create a PDF reader instance from file path",
                            "inputs": {"file_path": "text"},
                            "outputs": "PdfReader"
                        },
                        {
                            "name": "extract_text",
                            "signature": "page.extract_text()",
                            "description": "Extract text content from a PDF page",
                            "inputs": {},
                            "outputs": "text"
                        },
                        {
                            "name": "PdfWriter",
                            "signature": "PdfWriter()",
                            "description": "Create a PDF writer instance",
                            "inputs": {},
                            "outputs": "PdfWriter"
                        },
                        {
                            "name": "add_page",
                            "signature": "writer.add_page(page)",
                            "description": "Add a page to the PDF writer",
                            "inputs": {"page": "Page"},
                            "outputs": "void"
                        },
                        {
                            "name": "write",
                            "signature": "writer.write(file_path: str)",
                            "description": "Write the PDF to a file",
                            "inputs": {"file_path": "text"},
                            "outputs": "void"
                        }
                    ],
                    "combined_source": "from pypdf import PdfReader, PdfWriter\nreader = PdfReader('input.pdf')\ntext = reader.pages[0].extract_text()\nwriter = PdfWriter()\nwriter.add_page(reader.pages[0])\nwriter.write('output.pdf')"
                }
            ]
        }
        
        result = await extract_unified_apis_with_retry(content, "test.md", mock_client)
        
        # 验证点：
        # - 只生成1个UnifiedAPISpec
        assert len(result) == 1
        # - api_name为"PypdfProcessing"（PascalCase）
        assert result[0].api_name == "PypdfProcessing"
        # - 包含5个functions
        assert len(result[0].functions) == 5
        # - primary_library是"pypdf"
        assert result[0].primary_library == "pypdf"
        # - URL格式为pypdf.PdfReader
        assert result[0].functions[0].name == "PdfReader"

    # ═══════════════════════════════════════════════════════════════════════
    # TC-002: Multi-Library Mixed Usage
    # ═══════════════════════════════════════════════════════════════════════
    
    @pytest.mark.asyncio
    async def test_tc002_multi_library_grouping(self):
        """TC-002: 测试多library代码片段的分组"""
        content = """
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
"""
        
        mock_client = AsyncMock()
        mock_client.async_call_json.return_value = {
            "apis": [
                {
                    "api_name": "PypdfAndRequestsProcessing",
                    "primary_library": "pypdf",
                    "all_libraries": ["pypdf", "requests"],
                    "language": "python",
                    "functions": [
                        {
                            "name": "PdfReader",
                            "signature": "PdfReader(file_path: str)",
                            "description": "Create a PDF reader instance from file path",
                            "inputs": {"file_path": "text"},
                            "outputs": "PdfReader"
                        },
                        {
                            "name": "extract_text",
                            "signature": "page.extract_text()",
                            "description": "Extract text content from a PDF page",
                            "inputs": {},
                            "outputs": "text"
                        },
                        {
                            "name": "post",
                            "signature": "requests.post(url, json)",
                            "description": "Send a POST request",
                            "inputs": {"url": "text", "json": "dict"},
                            "outputs": "Response"
                        },
                        {
                            "name": "json",
                            "signature": "response.json()",
                            "description": "Parse response as JSON",
                            "inputs": {},
                            "outputs": "dict"
                        }
                    ],
                    "combined_source": "import pypdf\nimport requests\nreader = pypdf.PdfReader('doc.pdf')\ntext = reader.pages[0].extract_text()\nresponse = requests.post('https://api.example.com/upload', json={'content': text})\nprint(response.json())"
                }
            ]
        }
        
        result = await extract_unified_apis_with_retry(content, "test.md", mock_client)
        
        # 验证点：
        # - 只生成1个UnifiedAPISpec
        assert len(result) == 1
        # - api_name为"PypdfAndRequestsProcessing"
        assert result[0].api_name == "PypdfAndRequestsProcessing"
        # - all_libraries包含["pypdf", "requests"]（按出现顺序）
        assert "pypdf" in result[0].all_libraries
        assert "requests" in result[0].all_libraries
        # - 包含pypdf和requests的函数
        function_names = [f.name for f in result[0].functions]
        assert "PdfReader" in function_names
        assert "post" in function_names

    # ═══════════════════════════════════════════════════════════════════════
    # TC-003: JavaScript/TypeScript Support
    # ═══════════════════════════════════════════════════════════════════════
    
    @pytest.mark.asyncio
    async def test_tc003_javascript_support(self):
        """TC-003: 测试JavaScript/TypeScript支持"""
        content = """
# File Upload

```javascript
import axios from 'axios';
import fs from 'fs';

const data = fs.readFileSync('file.txt');
axios.post('https://api.com/upload', { data })
  .then(res => console.log(res.data));
```
"""
        
        mock_client = AsyncMock()
        mock_client.async_call_json.return_value = {
            "apis": [
                {
                    "api_name": "FsAndAxiosProcessing",
                    "primary_library": "fs",
                    "all_libraries": ["fs", "axios"],
                    "language": "javascript",
                    "functions": [
                        {
                            "name": "readFileSync",
                            "signature": "fs.readFileSync(path)",
                            "description": "Read file synchronously",
                            "inputs": {"path": "text"},
                            "outputs": "Buffer"
                        },
                        {
                            "name": "post",
                            "signature": "axios.post(url, data)",
                            "description": "Send POST request with axios",
                            "inputs": {"url": "text", "data": "any"},
                            "outputs": "Promise"
                        },
                        {
                            "name": "then",
                            "signature": "promise.then(callback)",
                            "description": "Handle promise resolution",
                            "inputs": {"callback": "function"},
                            "outputs": "Promise"
                        }
                    ],
                    "combined_source": "import axios from 'axios';\nimport fs from 'fs';\nconst data = fs.readFileSync('file.txt');\naxios.post('https://api.com/upload', { data })\n  .then(res => console.log(res.data));"
                }
            ]
        }
        
        result = await extract_unified_apis_with_retry(content, "test.md", mock_client)
        
        # 验证点：
        # - 正确识别JavaScript代码
        assert result[0].language == "javascript"
        # - 支持ES6 import语法
        assert "axios" in result[0].all_libraries
        # - URL格式为"axios.post"
        function_names = [f.name for f in result[0].functions]
        assert "post" in function_names

    # ═══════════════════════════════════════════════════════════════════════
    # TC-004: Missing Import Inference
    # ═══════════════════════════════════════════════════════════════════════
    
    @pytest.mark.asyncio
    async def test_tc004_missing_import_inference(self):
        """TC-004: 测试基于上下文推断library（无import）"""
        content = """
# PDF Operations

```python
import pypdf
reader = pypdf.PdfReader("file.pdf")
```

```python
# Process page (no import!)
text = reader.pages[0].extract_text()
```
"""
        
        mock_client = AsyncMock()
        mock_client.async_call_json.return_value = {
            "apis": [
                {
                    "api_name": "PypdfProcessing",
                    "primary_library": "pypdf",
                    "all_libraries": ["pypdf"],
                    "language": "python",
                    "functions": [
                        {
                            "name": "PdfReader",
                            "signature": "PdfReader(file_path: str)",
                            "description": "Create a PDF reader instance from file path",
                            "inputs": {"file_path": "text"},
                            "outputs": "PdfReader"
                        },
                        {
                            "name": "extract_text",
                            "signature": "page.extract_text()",
                            "description": "Extract text content from a PDF page",
                            "inputs": {},
                            "outputs": "text"
                        }
                    ],
                    "combined_source": "import pypdf\nreader = pypdf.PdfReader('file.pdf')\ntext = reader.pages[0].extract_text()"
                }
            ]
        }
        
        result = await extract_unified_apis_with_retry(content, "test.md", mock_client)
        
        # 验证点：
        # - 即使第二个代码块没有import，也能识别出使用pypdf
        assert len(result) == 1
        # - 两个代码块合并到同一个API
        assert result[0].primary_library == "pypdf"
        # - 包含两个functions（PdfReader和extract_text）
        assert len(result[0].functions) == 2

    # ═══════════════════════════════════════════════════════════════════════
    # TC-005: Retry Mechanism
    # ═══════════════════════════════════════════════════════════════════════
    
    @pytest.mark.asyncio
    async def test_tc005_retry_mechanism(self):
        """TC-005: 测试重试机制"""
        content = "```python\nimport pypdf\n```"
        
        mock_client = AsyncMock()
        # 第1次调用失败，第2次调用成功
        mock_client.async_call_json.side_effect = [
            Exception("Timeout"),
            {"apis": [{"api_name": "PypdfProcessing", "primary_library": "pypdf", "all_libraries": ["pypdf"], "language": "python", "functions": []}]}
        ]
        
        with patch('asyncio.sleep', new=AsyncMock()):  # 跳过实际的sleep
            result = await extract_unified_apis_with_retry(content, "test.md", mock_client, max_retries=3)
        
        # 验证点：
        # - 至少重试1次
        assert mock_client.async_call_json.call_count == 2
        # - 最终返回正确结果
        assert len(result) == 1
        assert result[0].api_name == "PypdfProcessing"

    @pytest.mark.asyncio
    async def test_tc005_retry_all_failures(self):
        """TC-005: 测试所有重试都失败后返回空列表"""
        content = "```python\nimport pypdf\n```"
        
        mock_client = AsyncMock()
        # 所有调用都失败
        mock_client.async_call_json.side_effect = [
            Exception("Error 1"),
            Exception("Error 2"),
            Exception("Error 3"),
        ]
        
        with patch('asyncio.sleep', new=AsyncMock()):
            result = await extract_unified_apis_with_retry(content, "test.md", mock_client, max_retries=3)
        
        # 验证点：
        # - 重试3次
        assert mock_client.async_call_json.call_count == 3
        # - 返回空列表
        assert result == []

    # ═══════════════════════════════════════════════════════════════════════
    # TC-006: Multi-Language Support
    # ═══════════════════════════════════════════════════════════════════════
    
    @pytest.mark.asyncio
    async def test_tc006_multi_language_support(self):
        """TC-006: 测试多语言支持"""
        content = """
# Multi-Language Guide

```python
import pypdf
reader = pypdf.PdfReader("file.pdf")
```

```javascript
import axios from 'axios';
axios.get('https://api.com');
```

```bash
curl -X POST https://api.com
```
"""
        
        mock_client = AsyncMock()
        mock_client.async_call_json.return_value = {
            "apis": [
                {
                    "api_name": "PypdfProcessing",
                    "primary_library": "pypdf",
                    "all_libraries": ["pypdf"],
                    "language": "python",
                    "functions": [
                        {
                            "name": "PdfReader",
                            "signature": "PdfReader(file_path: str)",
                            "description": "Create a PDF reader instance from file path",
                            "inputs": {"file_path": "text"},
                            "outputs": "PdfReader"
                        }
                    ],
                    "combined_source": "import pypdf\nreader = pypdf.PdfReader('file.pdf')"
                },
                {
                    "api_name": "AxiosProcessing",
                    "primary_library": "axios",
                    "all_libraries": ["axios"],
                    "language": "javascript",
                    "functions": [
                        {
                            "name": "get",
                            "signature": "axios.get(url)",
                            "description": "Send GET request with axios",
                            "inputs": {"url": "text"},
                            "outputs": "Promise"
                        }
                    ],
                    "combined_source": "import axios from 'axios';\naxios.get('https://api.com');"
                }
            ]
        }
        
        result = await extract_unified_apis_with_retry(content, "test.md", mock_client)
        
        # 验证点：
        # - 识别不同编程语言
        languages = [api.language for api in result]
        assert "python" in languages
        assert "javascript" in languages
        # - 每种语言生成独立的API
        assert len(result) == 2
        # - bash代码被过滤（不在SUPPORTED_LANGUAGES中）- 这部分由调用方处理


class TestHelperFunctions:
    """测试辅助函数."""

    def test_generate_function_url(self):
        """测试URL生成函数."""
        # 测试单library
        assert generate_function_url("pypdf", "PdfReader") == "pypdf.PdfReader"
        # 测试带class
        assert generate_function_url("pypdf", "extract_text", "PdfReader", ["pages"]) == "pypdf.PdfReader.pages.extract_text"

    def test_generate_api_name_single_library(self):
        """测试单library API名称生成."""
        assert generate_api_name("pypdf", ["pypdf"]) == "PypdfProcessing"

    def test_generate_api_name_multi_library(self):
        """测试多library API名称生成."""
        assert generate_api_name("pypdf", ["pypdf", "requests"]) == "PypdfAndRequestsProcessing"


class TestParseLLMResponse:
    """测试LLM响应解析."""

    def test_parse_valid_response(self):
        """测试解析有效的LLM响应."""
        response = {
            "apis": [
                {
                    "api_name": "PypdfProcessing",
                    "primary_library": "pypdf",
                    "all_libraries": ["pypdf"],
                    "language": "python",
                    "functions": [
                        {
                            "name": "PdfReader",
                            "signature": "PdfReader(file_path: str)",
                            "description": "Create a PDF reader",
                            "inputs": {"file_path": "text"},
                            "outputs": "PdfReader"
                        }
                    ],
                    "combined_source": "import pypdf"
                }
            ]
        }
        
        result = _parse_llm_response(response, "test.md")
        
        assert len(result) == 1
        assert result[0].api_name == "PypdfProcessing"
        assert len(result[0].functions) == 1
        assert result[0].functions[0].name == "PdfReader"

    def test_parse_direct_list_response(self):
        """测试解析直接返回list的响应."""
        response = [
            {
                "api_name": "PypdfProcessing",
                "primary_library": "pypdf",
                "all_libraries": ["pypdf"],
                "language": "python",
                "functions": [],
                "combined_source": "import pypdf"
            }
        ]
        
        result = _parse_llm_response(response, "test.md")
        
        assert len(result) == 1

    def test_parse_invalid_response(self):
        """测试解析无效的响应."""
        response = "invalid"
        
        result = _parse_llm_response(response, "test.md")
        
        assert result == []


class TestBuildPrompt:
    """测试Prompt构建."""

    def test_build_prompt_contains_source(self):
        """测试prompt包含源文件信息."""
        content = "```python\nimport pypdf\n```"
        
        prompt = _build_extraction_prompt(content, "test.md")
        
        assert "test.md" in prompt
        assert "```markdown" in prompt

    def test_build_prompt_truncates_long_content(self):
        """测试长内容被截断."""
        content = "x" * 20000
        
        prompt = _build_extraction_prompt(content, "test.md")
        
        # 内容应该被截断
        assert len(prompt) < 25000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
