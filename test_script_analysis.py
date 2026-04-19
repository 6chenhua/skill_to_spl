#!/usr/bin/env python3
"""测试脚本分析功能 - Phase 5 验证"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from pre_processing.p3_assembler import (
    _analyze_script_with_llm,
    _detect_language_from_extension,
)
from models import UnifiedAPISpec


def create_mock_llm_client():
    """创建一个模拟的 LLM 客户端用于测试。"""
    class MockLLMClient:
        async def async_call_json(self, step_name, system, user, **kwargs):
            # 模拟 LLM 响应 - 用于测试
            # 这个响应模拟了 convert_pdf_to_images.py 的分析结果
            return {
                "has_main_function": True,
                "main_function": {
                    "name": "convert",
                    "description": "Convert PDF pages to PNG images with optional resizing",
                    "input_schema": {
                        "pdf_path": {
                            "type": "text",
                            "required": True,
                            "default": None,
                            "description": "Path to the input PDF file"
                        },
                        "output_dir": {
                            "type": "text",
                            "required": True,
                            "default": None,
                            "description": "Directory to save output images"
                        },
                        "max_dim": {
                            "type": "number",
                            "required": False,
                            "default": "1000",
                            "description": "Maximum dimension for resizing"
                        }
                    },
                    "output_schema": "void",
                    "is_entry_point": True,
                    "command_line_params": ["pdf_path", "output_dir"]
                },
                "all_functions": [
                    {
                        "name": "convert",
                        "description": "Convert PDF pages to PNG images",
                        "input_schema": {
                            "pdf_path": {"type": "text", "required": True},
                            "output_dir": {"type": "text", "required": True},
                            "max_dim": {"type": "number", "required": False}
                        },
                        "output_schema": "void",
                        "is_entry_point": True,
                        "serves_main": False
                    }
                ],
                "auxiliary_functions": [],
                "command_line_usage": "python convert_pdf_to_images.py [input_pdf] [output_directory]",
                "imported_libraries": ["os", "sys", "pdf2image"],
                "script_description": "Convert PDF pages to PNG images with optional resizing"
            }
    
    return MockLLMClient()


def test_pascal_case_conversion():
    """测试 PascalCase 转换函数。"""
    from pre_processing.p3_assembler import _to_pascal_case
    
    test_cases = [
        ("check_bounding_boxes", "CheckBoundingBoxes"),
        ("convert_pdf_to_images", "ConvertPdfToImages"),
        ("fill_fillable_fields", "FillFillableFields"),
        ("main", "Main"),
        ("PDFProcessor", "Pdfprocessor"),  # Note: already PascalCase
    ]
    
    print("\n=== Test: PascalCase Conversion ===")
    all_passed = True
    for input_name, expected in test_cases:
        result = _to_pascal_case(input_name)
        status = "PASS" if result == expected else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"  {status}: '{input_name}' -> '{result}' (expected: '{expected}')")
    
    return all_passed


def test_language_detection():
    """测试语言检测函数。"""
    test_cases = [
        ("script.py", "python"),
        ("script.js", "javascript"),
        ("script.ts", "typescript"),
        ("script.sh", "bash"),
        ("script.rb", "ruby"),
        ("script.unknown", "python"),  # Default
    ]
    
    print("\n=== Test: Language Detection ===")
    all_passed = True
    for filename, expected in test_cases:
        file_path = Path(filename)
        result = _detect_language_from_extension(file_path)
        status = "PASS" if result == expected else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"  {status}: '{filename}' -> '{result}' (expected: '{expected}')")
    
    return all_passed


async def test_script_analysis_with_mock():
    """使用模拟 LLM 测试脚本分析。"""
    print("\n=== Test: Script Analysis with Mock LLM ===")
    
    # Sample script code
    source_code = '''
import os
import sys
from pdf2image import convert_from_path

def convert(pdf_path, output_dir, max_dim=1000):
    images = convert_from_path(pdf_path, dpi=200)
    for i, image in enumerate(images):
        width, height = image.size
        if width > max_dim or height > max_dim:
            scale_factor = min(max_dim / width, max_dim / height)
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            image = image.resize((new_width, new_height))
        image_path = os.path.join(output_dir, f"page_{i+1}.png")
        image.save(image_path)
    print(f"Converted {len(images)} pages to PNG images")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: convert_pdf_to_images.py [input pdf] [output directory]")
        sys.exit(1)
    pdf_path = sys.argv[1]
    output_directory = sys.argv[2]
    convert(pdf_path, output_directory)
'''
    
    file_path = Path("scripts/convert_pdf_to_images.py")
    rel_path = "scripts/convert_pdf_to_images.py"
    client = create_mock_llm_client()
    language = "python"
    
    try:
        result = await _analyze_script_with_llm(
            source_code, file_path, rel_path, client, language
        )
        
        if result is None:
            print("  FAIL: Returned None")
            return False
        
        if not isinstance(result, UnifiedAPISpec):
            print(f"  FAIL: Wrong type {type(result)}")
            return False
        
        print(f"  PASS: Successfully created UnifiedAPISpec")
        print(f"    - api_id: {result.api_id}")
        print(f"    - api_name: {result.api_name}")
        print(f"    - primary_library: {result.primary_library}")
        print(f"    - functions count: {len(result.functions)}")
        
        # Verify function specs
        if result.functions:
            main_func = result.functions[0]
            print(f"    - main function: {main_func.name}")
            print(f"    - input_schema: {main_func.input_schema}")
            print(f"    - output_schema: {main_func.output_schema}")
        
        return True
        
    except Exception as e:
        print(f"  FAIL: Exception raised: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_real_script_loading():
    """测试加载真实脚本文件。"""
    print("\n=== Test: Load Real Script Files ===")
    
    script_files = [
        "skills/pdf/scripts/convert_pdf_to_images.py",
        "skills/pdf/scripts/check_bounding_boxes.py",
        "skills/pdf/scripts/fill_fillable_fields.py",
    ]
    
    all_passed = True
    for script_path in script_files:
        full_path = Path(script_path)
        if full_path.exists():
            try:
                content = full_path.read_text(encoding="utf-8")
                language = _detect_language_from_extension(full_path)
                print(f"  PASS: Loaded '{script_path}' ({len(content)} chars, {language})")
            except Exception as e:
                print(f"  FAIL: Error loading '{script_path}': {e}")
                all_passed = False
        else:
            print(f"  SKIP: File not found '{script_path}'")
    
    return all_passed


async def test_function_spec_parsing():
    """测试 FunctionSpec 解析逻辑。"""
    from pre_processing.p3_assembler import _build_function_spec_from_data
    
    print("\n=== Test: FunctionSpec Parsing ===")
    
    func_data = {
        "name": "get_bounding_box_messages",
        "description": "Check PDF form field bounding boxes",
        "input_schema": {
            "fields_json_stream": {
                "type": "file stream",
                "required": True,
                "description": "JSON file stream"
            }
        },
        "output_schema": "List [text]"
    }
    
    try:
        func_spec = _build_function_spec_from_data(func_data, is_main=True)
        print(f"  PASS: Created FunctionSpec")
        print(f"    - name: {func_spec.name}")
        print(f"    - signature: {func_spec.signature}")
        print(f"    - input_schema: {func_spec.input_schema}")
        print(f"    - output_schema: {func_spec.output_schema}")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def run_all_tests():
    """运行所有测试。"""
    print("=" * 70)
    print("SCRIPT ANALYSIS REFACTOR - PHASE 5: TEST VALIDATION")
    print("=" * 70)
    
    results = []
    
    # Run tests
    results.append(("PascalCase Conversion", test_pascal_case_conversion()))
    results.append(("Language Detection", test_language_detection()))
    results.append(("Script Analysis (Mock)", await test_script_analysis_with_mock()))
    results.append(("Real Script Loading", test_real_script_loading()))
    results.append(("FunctionSpec Parsing", await test_function_spec_parsing()))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[SUCCESS] All tests passed!")
        return 0
    else:
        print(f"\n[WARNING] {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
