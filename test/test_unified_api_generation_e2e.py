"""
test_unified_api_generation_e2e.py
End-to-end tests for the unified API generation system.

Tests the complete flow from UnifiedAPISpec to APISpec generation,
including SPL format validation and integration with merge_api_spl_blocks.
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import List

from pipeline.llm_steps.step1_5_api_generation import (
    generate_unified_api_definitions,
    merge_api_spl_blocks,
    _generate_single_unified_api,
    _generate_function_url,
)
from models.data_models import (
    UnifiedAPISpec,
    FunctionSpec,
    APISpec,
    APISymbolTable,
)


class TestUnifiedAPIGenerationE2E:
    """End-to-end test cases for unified API generation."""

    # ═══════════════════════════════════════════════════════════════════════
    # Test Case 1: Basic Single Library API Generation
    # ═══════════════════════════════════════════════════════════════════════

    def test_tc001_basic_single_library_api_generation(self):
        """
        TC-001: Basic Single Library API Generation
        
        Input: A UnifiedAPISpec with 3 functions from pypdf library
        Expected: A valid APISpec with SPL text containing all 3 functions
                 in the format `ApiName<none> { } { functions: [...] }`
        """
        # Create mock LLM client
        mock_client = MagicMock()
        mock_spl_output = """PypdfProcessing<none>
{ }
{
functions: [
{
name: "PdfReader",
url: "pypdf.PdfReader",
description: "Create a PDF reader instance from file path",
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
{
name: "extract_text",
url: "pypdf.Page.extract_text",
description: "Extract text content from a PDF page",
parameters: {
parameters: [],
controlled-input: false
},
return: {
type: text,
controlled-output: false
}
},
{
name: "PdfWriter",
url: "pypdf.PdfWriter",
description: "Create a PDF writer instance",
parameters: {
parameters: [],
controlled-input: false
},
return: {
type: PdfWriter,
controlled-output: false
}
}
]
}"""
        mock_client.call.return_value = mock_spl_output

        # Create UnifiedAPISpec with 3 functions from pypdf
        functions = [
            FunctionSpec(
                name="PdfReader",
                signature="PdfReader(file_path: str)",
                description="Create a PDF reader instance from file path",
                input_schema={"file_path": "str"},
                output_schema="PdfReader",
            ),
            FunctionSpec(
                name="extract_text",
                signature="page.extract_text()",
                description="Extract text content from a PDF page",
                input_schema={},
                output_schema="str",
            ),
            FunctionSpec(
                name="PdfWriter",
                signature="PdfWriter()",
                description="Create a PDF writer instance",
                input_schema={},
                output_schema="PdfWriter",
            ),
        ]

        unified_api = UnifiedAPISpec(
            api_id="pypdf_from_doc1",
            api_name="PypdfProcessing",
            primary_library="pypdf",
            all_libraries=["pypdf"],
            language="python",
            functions=functions,
            combined_source="from pypdf import PdfReader, PdfWriter",
            source_file="test.md",
        )

        # Generate API
        result = _generate_single_unified_api(mock_client, unified_api)

        # Assertions
        assert result is not None
        assert isinstance(result, APISpec)
        assert result.name == "PypdfProcessing"
        assert result.spl_text is not None
        assert len(result.spl_text) > 0
        
        # Verify SPL format: ApiName<none> { } { functions: [...] }
        assert "PypdfProcessing<none>" in result.spl_text
        assert "functions:" in result.spl_text
        assert "PdfReader" in result.spl_text
        assert "extract_text" in result.spl_text
        assert "PdfWriter" in result.spl_text
        
        # Verify input/output params are parsed
        assert len(result.input_params) > 0
        assert result.description == "Unified API for pypdf"

    # ═══════════════════════════════════════════════════════════════════════
    # Test Case 2: Multi-Library API Generation
    # ═══════════════════════════════════════════════════════════════════════

    def test_tc002_multi_library_api_generation(self):
        """
        TC-002: Multi-Library API Generation
        
        Input: A UnifiedAPISpec with functions from both pypdf and requests libraries
        Expected: API name should be in format "PypdfAndRequestsProcessing",
                 URL prefixes should match each library
        """
        # Create mock LLM client
        mock_client = MagicMock()
        mock_spl_output = """PypdfAndRequestsProcessing<none>
{ }
{
functions: [
{
name: "PdfReader",
url: "pypdf.PdfReader",
description: "Create a PDF reader instance from file path",
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
{
name: "extract_text",
url: "pypdf.Page.extract_text",
description: "Extract text content from a PDF page",
parameters: {
parameters: [],
controlled-input: false
},
return: {
type: text,
controlled-output: false
}
},
{
name: "post",
url: "requests.post",
description: "Send a POST request",
parameters: {
parameters: [
{required: true, name: "url", type: text},
{required: false, name: "json", type: dict}
],
controlled-input: false
},
return: {
type: Response,
controlled-output: false
}
},
{
name: "json",
url: "requests.Response.json",
description: "Parse response as JSON",
parameters: {
parameters: [],
controlled-input: false
},
return: {
type: dict,
controlled-output: false
}
}
]
}"""
        mock_client.call.return_value = mock_spl_output

        # Create UnifiedAPISpec with functions from both pypdf and requests
        functions = [
            FunctionSpec(
                name="PdfReader",
                signature="PdfReader(file_path: str)",
                description="Create a PDF reader instance from file path",
                input_schema={"file_path": "str"},
                output_schema="PdfReader",
            ),
            FunctionSpec(
                name="extract_text",
                signature="page.extract_text()",
                description="Extract text content from a PDF page",
                input_schema={},
                output_schema="str",
            ),
            FunctionSpec(
                name="post",
                signature="requests.post(url, json)",
                description="Send a POST request",
                input_schema={"url": "str", "json": "dict"},
                output_schema="Response",
            ),
            FunctionSpec(
                name="json",
                signature="response.json()",
                description="Parse response as JSON",
                input_schema={},
                output_schema="dict",
            ),
        ]

        unified_api = UnifiedAPISpec(
            api_id="multi_from_doc1",
            api_name="PypdfAndRequestsProcessing",
            primary_library="pypdf",
            all_libraries=["pypdf", "requests"],
            language="python",
            functions=functions,
            combined_source="import pypdf\nimport requests",
            source_file="test.md",
        )

        # Generate API
        result = _generate_single_unified_api(mock_client, unified_api)

        # Assertions
        assert result is not None
        assert isinstance(result, APISpec)
        
        # Verify API name format: "PypdfAndRequestsProcessing"
        assert result.name == "PypdfAndRequestsProcessing"
        
        # Verify description includes both libraries
        assert "pypdf" in result.description
        assert "requests" in result.description
        
        # Verify SPL contains functions from both libraries
        assert "PdfReader" in result.spl_text
        assert "extract_text" in result.spl_text
        assert "post" in result.spl_text
        assert "json" in result.spl_text
        
        # Verify URL prefixes match each library
        assert "pypdf.PdfReader" in result.spl_text
        assert "pypdf.Page.extract_text" in result.spl_text
        assert "requests.post" in result.spl_text
        assert "requests.Response.json" in result.spl_text

    # ═══════════════════════════════════════════════════════════════════════
    # Test Case 3: API SPL Format Validation
    # ═══════════════════════════════════════════════════════════════════════

    def test_tc003_api_spl_format_validation(self):
        """
        TC-003: API SPL Format Validation
        
        Input: Generated SPL text from UnifiedAPISpec
        Expected: Must validate that SPL has proper structure without extra [END_APIS] markers
        """
        # Create mock LLM client that returns SPL with proper format
        mock_client = MagicMock()
        mock_spl_output = """PypdfProcessing<none>
{ }
{
functions: [
{
name: "PdfReader",
url: "pypdf.PdfReader",
description: "Create a PDF reader instance",
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
}
]
}"""
        mock_client.call.return_value = mock_spl_output

        functions = [
            FunctionSpec(
                name="PdfReader",
                signature="PdfReader(file_path: str)",
                description="Create a PDF reader instance",
                input_schema={"file_path": "str"},
                output_schema="PdfReader",
            ),
        ]

        unified_api = UnifiedAPISpec(
            api_id="pypdf_from_doc1",
            api_name="PypdfProcessing",
            primary_library="pypdf",
            all_libraries=["pypdf"],
            language="python",
            functions=functions,
            combined_source="from pypdf import PdfReader",
            source_file="test.md",
        )

        # Generate API
        result = _generate_single_unified_api(mock_client, unified_api)

        # Assertions for SPL format validation
        assert result is not None
        spl_text = result.spl_text
        
        # Verify proper structure: ApiName<none> { } { functions: [...] }
        assert "PypdfProcessing<none>" in spl_text
        assert "{ }" in spl_text
        assert "functions:" in spl_text
        assert "[" in spl_text and "]" in spl_text
        
        # Verify NO extra [END_APIS] markers in the generated SPL
        # (The [END_APIS] should only be added by merge_api_spl_blocks)
        assert "[END_APIS]" not in spl_text, "Individual API SPL should not contain [END_APIS]"
        assert "[DEFINE_APIS:]" not in spl_text, "Individual API SPL should not contain [DEFINE_APIS:]"
        
        # Verify function structure
        assert "name:" in spl_text
        assert "url:" in spl_text
        assert "description:" in spl_text
        assert "parameters:" in spl_text
        assert "return:" in spl_text

    # ═══════════════════════════════════════════════════════════════════════
    # Test Case 4: URL Generation
    # ═══════════════════════════════════════════════════════════════════════

    def test_tc004_url_generation(self):
        """
        TC-004: URL Generation
        
        Input: library="pypdf", function_name="PdfReader", class_name="PdfReader"
        Expected: URL should be "pypdf.PdfReader"
        """
        # Test basic URL generation
        url = _generate_function_url("pypdf", "PdfReader")
        assert url == "pypdf.PdfReader"
        
        # Test with different library
        url = _generate_function_url("requests", "post")
        assert url == "requests.post"
        
        # Test with method name
        url = _generate_function_url("pypdf", "extract_text")
        assert url == "pypdf.extract_text"
        
        # Test with library containing dots (submodules)
        url = _generate_function_url("matplotlib.pyplot", "plot")
        assert url == "matplotlib.pyplot.plot"

    # ═══════════════════════════════════════════════════════════════════════
    # Test Case 5: Empty Functions Handling
    # ═══════════════════════════════════════════════════════════════════════

    def test_tc005_empty_functions_handling(self):
        """
        TC-005: Empty Functions Handling
        
        Input: UnifiedAPISpec with empty functions list
        Expected: Should handle gracefully
        """
        # Create mock LLM client
        mock_client = MagicMock()
        mock_spl_output = """EmptyProcessing<none>
{ }
{
functions: []
}"""
        mock_client.call.return_value = mock_spl_output

        # Create UnifiedAPISpec with empty functions list
        unified_api = UnifiedAPISpec(
            api_id="empty_from_doc1",
            api_name="EmptyProcessing",
            primary_library="unknown",
            all_libraries=["unknown"],
            language="python",
            functions=[],  # Empty functions list
            combined_source="",
            source_file="test.md",
        )

        # Generate API - should not raise exception
        result = _generate_single_unified_api(mock_client, unified_api)

        # Assertions
        assert result is not None
        assert isinstance(result, APISpec)
        assert result.name == "EmptyProcessing"
        
        # Verify empty input/output params
        assert result.input_params == []
        assert result.output_params == []

    def test_tc005_empty_functions_list_in_generate_unified_api_definitions(self):
        """
        TC-005b: Empty UnifiedAPISpec list handling in batch generation
        """
        mock_client = MagicMock()
        
        # Call with empty list
        result = generate_unified_api_definitions([], mock_client)
        
        # Should return empty APISymbolTable
        assert isinstance(result, APISymbolTable)
        assert result.apis == {}
        assert result.unified_apis == {}

    # ═══════════════════════════════════════════════════════════════════════
    # Test Case 6: Integration with merge_api_spl_blocks
    # ═══════════════════════════════════════════════════════════════════════

    def test_tc006_integration_with_merge_api_spl_blocks(self):
        """
        TC-006: Integration with merge_api_spl_blocks
        
        Input: Multiple UnifiedAPISpec objects
        Expected: Single [DEFINE_APIS:] block with all APIs and only one [END_APIS] at the end
        """
        # Create mock LLM client
        mock_client = MagicMock()
        
        # Define side effect to return different SPL for different APIs
        def mock_call(*args, **kwargs):
            user_prompt = kwargs.get('user', '')
            if "PypdfProcessing" in user_prompt:
                return """PypdfProcessing<none>
{ }
{
functions: [
{
name: "PdfReader",
url: "pypdf.PdfReader",
description: "Create a PDF reader",
parameters: { parameters: [], controlled-input: false },
return: { type: PdfReader, controlled-output: false }
}
]
}"""
            else:
                return """RequestsProcessing<none>
{ }
{
functions: [
{
name: "post",
url: "requests.post",
description: "Send POST request",
parameters: { parameters: [], controlled-input: false },
return: { type: Response, controlled-output: false }
}
]
}"""
        
        mock_client.call.side_effect = mock_call

        # Create multiple UnifiedAPISpec objects
        unified_apis = [
            UnifiedAPISpec(
                api_id="pypdf_from_doc1",
                api_name="PypdfProcessing",
                primary_library="pypdf",
                all_libraries=["pypdf"],
                language="python",
                functions=[
                    FunctionSpec(
                        name="PdfReader",
                        signature="PdfReader(file_path: str)",
                        description="Create a PDF reader",
                        input_schema={},
                        output_schema="PdfReader",
                    ),
                ],
                combined_source="from pypdf import PdfReader",
                source_file="test.md",
            ),
            UnifiedAPISpec(
                api_id="requests_from_doc1",
                api_name="RequestsProcessing",
                primary_library="requests",
                all_libraries=["requests"],
                language="python",
                functions=[
                    FunctionSpec(
                        name="post",
                        signature="requests.post(url, json)",
                        description="Send POST request",
                        input_schema={},
                        output_schema="Response",
                    ),
                ],
                combined_source="import requests",
                source_file="test.md",
            ),
        ]

        # Generate APIs for all UnifiedAPISpec objects
        api_table = generate_unified_api_definitions(unified_apis, mock_client)

        # Assertions on API table
        assert isinstance(api_table, APISymbolTable)
        assert len(api_table.apis) == 2
        assert "PypdfProcessing" in api_table.apis
        assert "RequestsProcessing" in api_table.apis

        # Merge all API SPL blocks
        merged_spl = merge_api_spl_blocks(api_table)

        # Assertions on merged SPL
        assert merged_spl is not None
        assert len(merged_spl) > 0
        
        # Verify single [DEFINE_APIS:] at the beginning
        assert merged_spl.startswith("[DEFINE_APIS:]"), "Should start with [DEFINE_APIS:]"
        
        # Verify only one [END_APIS] at the end
        end_apis_count = merged_spl.count("[END_APIS]")
        assert end_apis_count == 1, f"Should have exactly one [END_APIS], found {end_apis_count}"
        
        # Verify both APIs are present
        assert "PypdfProcessing<none>" in merged_spl
        assert "RequestsProcessing<none>" in merged_spl
        
        # Verify structure: [DEFINE_APIS:] + API1 + API2 + [END_APIS]
        lines = merged_spl.split("\n")
        assert lines[0] == "[DEFINE_APIS:]"
        assert lines[-1] == "[END_APIS]"

    def test_tc006_single_api_merge(self):
        """
        TC-006b: Single API merge produces correct format
        """
        # Create APISymbolTable with single API
        api_spec = APISpec(
            name="SingleApi",
            spl_text="""SingleApi<none>
{ }
{
functions: []
}""",
            input_params=[],
            output_params=[],
            description="Single API",
        )
        
        api_table = APISymbolTable(apis={"SingleApi": api_spec})
        
        # Merge
        merged_spl = merge_api_spl_blocks(api_table)
        
        # Verify structure
        assert merged_spl.startswith("[DEFINE_APIS:]")
        assert "[END_APIS]" in merged_spl
        assert merged_spl.count("[END_APIS]") == 1
        assert "SingleApi<none>" in merged_spl

    def test_tc006_empty_api_table_merge(self):
        """
        TC-006c: Empty API table merge returns empty string
        """
        api_table = APISymbolTable(apis={})
        
        merged_spl = merge_api_spl_blocks(api_table)
        
        assert merged_spl == ""


class TestUnifiedAPIGenerationBatch:
    """Tests for batch generation with multiple UnifiedAPISpec objects."""

    def test_batch_generation_with_multiple_apis(self):
        """Test batch generation creates correct APISymbolTable."""
        mock_client = MagicMock()
        
        # Mock to return simple SPL for any API
        mock_client.call.return_value = """TestApi<none>
{ }
{
functions: []
}"""

        unified_apis = [
            UnifiedAPISpec(
                api_id=f"api_{i}",
                api_name=f"TestApi{i}",
                primary_library="testlib",
                all_libraries=["testlib"],
                language="python",
                functions=[
                    FunctionSpec(
                        name=f"func{i}",
                        signature=f"func{i}()",
                        description=f"Function {i}",
                        input_schema={},
                        output_schema="void",
                    ),
                ],
                combined_source="",
                source_file="test.md",
            )
            for i in range(3)
        ]

        result = generate_unified_api_definitions(unified_apis, mock_client)

        assert len(result.apis) == 3
        assert "TestApi0" in result.apis
        assert "TestApi1" in result.apis
        assert "TestApi2" in result.apis


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
