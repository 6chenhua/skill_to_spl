# Step 1.5 — API Definition Generation (moved from Step 4D)
s1_5_api_v1 = """
Emit a single API_DECLARATION for an SPL specification.

Called individually for each tool after Step 1 completes.
The generated DEFINE_API block will be stored in the API symbol table
for later use in WORKER generation (Step 4E).

## Complete grammar

API_DECLARATION :=
["\"" STATIC_DESCRIPTION "\""]
API_NAME "<" AUTHENTICATION ">" ["RETRY" <number>] ["LOG" <api-exceptions>]
OPENAPI_SCHEMA
API_IN_SPL

AUTHENTICATION := "none" | "apikey" | "oauth"
OPENAPI_SCHEMA := STRUCTURED_TEXT  # OpenAPI schema in structured text

API_IN_SPL := "{" "functions:" "[" {FUNCTION} "]" "}"
FUNCTION := "{"
"name:" STATIC_DESCRIPTION ","
"url:" <url_string> ","
["description:" STATIC_DESCRIPTION ","]
"parameters:" "{" "parameters:" "[" {PARAMETER} "]" "," "controlled-input:" BOOL "}" ","
"return:" "{" "type:" PARAMETER_TYPE "," "controlled-output:" BOOL "}"
"}"
PARAMETER := "{" "required:" BOOL "," "name:" STATIC_DESCRIPTION "," "type:" PARAMETER_TYPE "}"
PARAMETER_TYPE := TYPE_NAME | "List [" TYPE_NAME "]"
TYPE_NAME := "text" | "image" | "audio" | "number" | "boolean"
BOOL := "true" | "false"
API_NAME := <word>  # PascalCase, derived from tool name
STATIC_DESCRIPTION := <word> | <word> <space> STATIC_DESCRIPTION
<word> is a sequence of characters, digits and symbols without space
<space> is white space or tab

## Input: Single Tool Specification

You receive ONE tool specification as JSON. Generate exactly ONE API_DECLARATION.

### Tool Types

**NETWORK_API**
- URL: HTTPS endpoint from tool.url
- AUTHENTICATION: apikey | oauth from tool.authentication
- OPENAPI_SCHEMA: Generate full OpenAPI schema based on input_schema/output_schema

**SCRIPT**
- URL: scripts/<filename>.py from tool.url
- AUTHENTICATION: none
- OPENAPI_SCHEMA: {} (empty)
- Use source_text to generate the description

**CODE_SNIPPET**
- URL: <library>.<ClassName> from tool.url (e.g., "pypdf.PdfReader")
- AUTHENTICATION: none
- OPENAPI_SCHEMA: {} (empty)
- Use source_text to generate the description

## Generation Rules

1. Convert tool.name to PascalCase for API_NAME (e.g., "fill_pdf_fields" → "FillPdfFields")
2. Use provided authentication value directly
3. Add RETRY 3 only if source mentions retry behavior, otherwise omit
4. controlled-input and controlled-output: false unless explicitly stated
5. If interface is partially described, emit with description "interface partially described"
6. Use source_text for generating meaningful, one-sentence descriptions
7. Map input_schema parameters to PARAMETER entries with proper types

## Type Mapping

- Python str → text
- Python int/float → number
- Python bool → boolean
- Python bytes → text
- List[...] → List [TYPE_NAME]
- Dict/Any/Union/etc. → text (fallback)

## Output Format

Emit ONLY the API_DECLARATION (without the [DEFINE_APIS:] wrapper):

Example:
FillPdfFields<none>
{ }
{
    functions: [
        {
            name: "Fill PDF form fields",
            url: "scripts/fill_fillable_fields.py",
            description: "Populates fillable fields in a PDF form",
            parameters: {
                parameters: [
                    {required: true, name: "input_file", type: text},
                    {required: true, name: "field_data", type: text}
                ],
                controlled-input: false
            },
            return: {
                type: text,
                controlled-output: false
            }
        }
    ]
}

## Rules

- Generate ONE API_DECLARATION only
- Use 4-space indentation
- Output ONLY the API declaration. No prose, no markdown fences, no explanation.
- Do NOT include [DEFINE_APIS:] or [END_APIS] tags
"""
