"""Pre-processing: Unified API Extractor (P2.5+).

Responsibilities:
- Extract unified API specifications from markdown code blocks.
- Group code snippets by functional logic (not just by library).
- Support multi-library scenarios.
- Generate detailed URLs: library.class.method.
- Support Python, JavaScript, TypeScript.

Key Features:
- LLM-driven extraction with JSON output.
- Retry mechanism with exponential backoff (1s, 2s, 4s).
- Parses code blocks and detects libraries automatically.
- Groups dependent code blocks together.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from pipeline.llm_client import LLMClient

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Data Models (will be moved to models/data_models.py)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FunctionSpec:
    """单个函数的规格"""
    name: str
    signature: str
    description: str
    input_schema: dict[str, str]
    output_schema: str


@dataclass
class UnifiedAPISpec:
    """统一API规格（包含多个functions，支持多library）"""
    api_id: str
    api_name: str
    primary_library: str
    all_libraries: list[str]
    language: str
    functions: list[FunctionSpec]
    combined_source: str
    source_file: str


# ═══════════════════════════════════════════════════════════════════════════════
# Supported Languages
# ═══════════════════════════════════════════════════════════════════════════════

SUPPORTED_LANGUAGES = {
    'python', 'py',
    'javascript', 'js', 'typescript', 'ts', 'jsx', 'tsx',
}


# ═══════════════════════════════════════════════════════════════════════════════
# Main Extraction Functions
# ═══════════════════════════════════════════════════════════════════════════════

async def extract_unified_apis_with_retry(
    content: str,
    source_file: str,
    client: LLMClient,
    max_retries: int = 3,
) -> list[UnifiedAPISpec]:
    """
    带重试机制的Unified API提取。
    
    Args:
        content: MD文件完整内容
        source_file: 源文件路径（用于logging）
        client: LLM客户端
        max_retries: 最大重试次数
        
    Returns:
        list[UnifiedAPISpec]: 提取的统一API列表
    """
    last_error: Optional[Exception] = None
    
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


async def _extract_unified_apis_once(
    content: str,
    source_file: str,
    client: LLMClient,
) -> list[UnifiedAPISpec]:
    """
    单次LLM调用提取Unified APIs。
    """
    prompt = _build_extraction_prompt(content, source_file)
    
    try:
        response = await client.async_call_json(
            step_name="unified_api_extraction",
            system=_EXTRACTION_SYSTEM_PROMPT,
            user=prompt,
        )
        
        return _parse_llm_response(response, source_file)
        
    except Exception as e:
        logger.error(f"[UnifiedAPI] LLM call failed: {e}")
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# Prompt Building
# ═══════════════════════════════════════════════════════════════════════════════

_EXTRACTION_SYSTEM_PROMPT = """You are an expert code analyzer. Your task is to analyze markdown files containing code snippets and extract unified API specifications.

Key rules:
1. Identify all code blocks and their programming language
2. Analyze dependencies between code blocks - if code block B uses variables/objects from code block A, they belong to the same functional group
3. Group code blocks by FUNCTIONAL LOGIC, not just by library
4. Extract ALL functions/methods demonstrated in each group
5. Generate descriptive API names in PascalCase
6. For multi-library scenarios, connect library names with "_and_"

Respond with valid JSON only."""


def _build_extraction_prompt(content: str, source_file: str) -> str:
    """
    构建LLM提取prompt。
    """
    return f"""Analyze this markdown file and extract unified API specifications.

Source: {source_file}

Content:
```markdown
{content[:15000]}
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
  * Block 2: "text = reader.pages[0].extract_text()" # uses 'reader' from Block 1
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
{{
  "apis": [
    {{
      "api_name": "PdfProcessing",
      "primary_library": "pypdf",
      "all_libraries": ["pypdf"],
      "language": "python",
      "functions": [
        {{
          "name": "PdfReader",
          "signature": "PdfReader(file_path: str)",
          "description": "Create a PDF reader instance from file path",
          "inputs": {{"file_path": "text"}},
          "outputs": "PdfReader object"
        }},
        {{
          "name": "extract_text",
          "signature": "page.extract_text()",
          "description": "Extract text content from a PDF page",
          "inputs": {{}},
          "outputs": "text"
        }}
      ],
      "combined_source": "import pypdf\\nreader = pypdf.PdfReader(...)\\ntext = reader.pages[0].extract_text()"
    }}
  ]
}}
```

Important:
- Include ALL functions demonstrated in the code
- Preserve exact code snippets in "combined_source"
- Use descriptive names, not just library names
- If multiple libraries work together, include all in "all_libraries"
- URL format for functions: library.Class.method or library.function"""


def _parse_llm_response(response: Any, source_file: str) -> list[UnifiedAPISpec]:
    """
    解析LLM输出为UnifiedAPISpec对象。
    """
    # Handle direct list response
    if isinstance(response, list):
        apis_data = response
    elif isinstance(response, dict):
        # Handle nested "apis" key
        apis_data = response.get("apis", [])
    else:
        logger.warning(f"[UnifiedAPI] Invalid response type: {type(response)}")
        return []
    
    if not isinstance(apis_data, list):
        logger.warning(f"[UnifiedAPI] Expected list of APIs, got: {type(apis_data)}")
        return []
    
    result: list[UnifiedAPISpec] = []
    
    for i, api_data in enumerate(apis_data):
        try:
            if not isinstance(api_data, dict):
                continue
                
            # Extract functions
            functions: list[FunctionSpec] = []
            for func_data in api_data.get("functions", []):
                func = FunctionSpec(
                    name=func_data.get("name", "unknown"),
                    signature=func_data.get("signature", ""),
                    description=func_data.get("description", ""),
                    input_schema=func_data.get("inputs", func_data.get("input_schema", {})),
                    output_schema=func_data.get("outputs", func_data.get("output_schema", "void")),
                )
                functions.append(func)
            
            # Generate api_id
            api_id = f"{api_data.get('primary_library', 'api')}_{uuid.uuid4().hex[:8]}"
            
            unified_api = UnifiedAPISpec(
                api_id=api_id,
                api_name=api_data.get("api_name", "UnknownProcessing"),
                primary_library=api_data.get("primary_library", "unknown"),
                all_libraries=api_data.get("all_libraries", [api_data.get("primary_library", "unknown")]),
                language=api_data.get("language", "python"),
                functions=functions,
                combined_source=api_data.get("combined_source", ""),
                source_file=source_file,
            )
            result.append(unified_api)
            
        except Exception as e:
            logger.warning(f"[UnifiedAPI] Failed to parse API {i}: {e}")
            continue
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# URL Generation Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def generate_function_url(
    library: str,
    function_name: str,
    class_name: Optional[str] = None,
    method_chain: Optional[list[str]] = None,
) -> str:
    """
    生成标准化的函数URL。
    
    格式: library[.Class[.method[.sub_method]]]
    
    Examples:
    - pypdf.PdfReader
    - pypdf.PdfReader.pages.extract_text
    - requests.post
    """
    parts = [library]
    
    if class_name:
        parts.append(class_name)
        
        if method_chain:
            parts.extend(method_chain)
            # 添加最终的方法名
            if function_name and not function_name.startswith(("__", "_")):
                parts.append(function_name)
        elif function_name and not function_name.startswith(("__", "_")):
            # class.method 格式
            parts.append(function_name)
    elif function_name and not function_name.startswith(("__", "_")):
        # Standalone function: library.function
        parts.append(function_name)
    
    return ".".join(parts)


def generate_api_name(primary_library: str, all_libraries: list[str]) -> str:
    """
    生成API名称（PascalCase）。
    
    Examples:
    - Single library: "PypdfProcessing"
    - Multi library: "PypdfAndRequestsProcessing"
    """
    if len(all_libraries) == 1:
        return f"{primary_library.capitalize()}Processing"
    else:
        parts = [lib.capitalize() for lib in all_libraries]
        return f"{'And'.join(parts)}Processing"


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy Compatibility
# ═══════════════════════════════════════════════════════════════════════════════

def extract_unified_apis_from_doc(
    content: str,
    source_file: str,
    client: LLMClient,
    max_retries: int = 3,
) -> list[UnifiedAPISpec]:
    """
    同步包装器（用于兼容旧代码）。
    """
    return asyncio.run(extract_unified_apis_with_retry(content, source_file, client, max_retries))
