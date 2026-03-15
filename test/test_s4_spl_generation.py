"""
test_s4_spl_generation.py
Unit tests for the five Round-2 SPL generation steps: S4A–S4E.

Each step generates one SPL block. Tests validate:
  - INPUT: rendered prompt contains required symbols / source sections
  - OUTPUT: SPL block contains correct keywords, structure, and references
             to symbols defined in earlier Round-1 steps

S4A → DEFINE_PERSONA
S4B → DEFINE_CONSTRAINTS
S4C → DEFINE_VARIABLES + DEFINE_FILES
S4D → DEFINE_APIS
S4E → DEFINE_WORKER (the large orchestration block)
"""

import os
import re
import pytest

# ============================================================================
# Shared symbol table (output of Round 1: S4A→S4D)
# ============================================================================

SYMBOL_TABLE = {
    "AspectNames": [
        "NoDeprecatedApis",         # c-001 HARD
        "ApiKeyInEnvVars",          # c-004 HARD
        "ToolNamingSnakeCase",      # c-006 HARD
        "LimitParamRequired",       # c-007 HARD
        "CodeComposability",        # c-002 MEDIUM
        "NoCopyPaste",              # c-003 MEDIUM
        "FileSanitization",         # c-005 MEDIUM
        "EvalIndependence",         # c-008 MEDIUM
        "EvalNonDestructive",       # c-009 MEDIUM
        "ApiCoveragePriority",      # c-011 GUIDELINE
    ],
    "VarNames": ["implementation_plan", "evaluation_suite"],
    "FileNames": ["mcp_server_project"],
    "ApiNames": ["WebFetch"],
}

# ============================================================================
# S4A — DEFINE_PERSONA
# ============================================================================

S4A_INTENT_TEXT = """\
- Create MCP (Model Context Protocol) servers that enable LLMs to interact with external services through well-designed tools. [source: SKILL.md]
- The quality of an MCP server is measured by how well it enables LLMs to accomplish real-world tasks. [source: SKILL.md]
"""

S4A_NOTES_TEXT = """\
- TypeScript is the recommended language: high-quality SDK support, broad usage, static typing, good AI code generation. [source: SKILL.md]
- Python (FastMCP) is acceptable for local servers or when the user prefers Python. [source: SKILL.md]
- Streamable HTTP for remote servers (stateless JSON). stdio for local servers. [source: SKILL.md]
"""

EXPECTED_S4A_SPL = """\
[DEFINE_PERSONA:]
    ROLE: Create MCP (Model Context Protocol) servers that enable LLMs to interact with external services through well-designed tools.
    DOMAIN: Model Context Protocol server development and external API integration.
    EXPERTISE: Software engineering with TypeScript or Python and API integration experience.
[END_PERSONA]"""


class TestS4AInput:

    def test_system_prompt_exists(self):
        from prompts.templates import S4A_SYSTEM
        assert "PERSONA" in S4A_SYSTEM

    def test_rendered_user_contains_intent(self):
        from prompts.templates import render_s4a_user
        rendered = render_s4a_user(intent_text=S4A_INTENT_TEXT, notes_text=S4A_NOTES_TEXT)
        assert "LLMs to interact with external services" in rendered

    def test_rendered_user_excludes_constraints(self):
        """S4A only gets INTENT + NOTES — not CONSTRAINTS."""
        from prompts.templates import render_s4a_user
        rendered = render_s4a_user(intent_text=S4A_INTENT_TEXT, notes_text=S4A_NOTES_TEXT)
        assert "DO NOT use" not in rendered
        assert "snake_case" not in rendered


class TestS4AExpectedOutput:

    def test_contains_define_persona(self):
        assert "[DEFINE_PERSONA:]" in EXPECTED_S4A_SPL
        assert "[END_PERSONA]" in EXPECTED_S4A_SPL

    def test_role_describes_mcp_server_creation(self):
        assert "MCP" in EXPECTED_S4A_SPL
        assert "ROLE:" in EXPECTED_S4A_SPL

    def test_domain_field_present(self):
        assert "DOMAIN:" in EXPECTED_S4A_SPL

    def test_expertise_field_present(self):
        assert "EXPERTISE:" in EXPECTED_S4A_SPL

    def test_no_constraints_leaked_into_persona(self):
        assert "DO NOT" not in EXPECTED_S4A_SPL
        assert "snake_case" not in EXPECTED_S4A_SPL


@pytest.mark.live_llm
class TestS4ALiveLLM:

    def test_persona_block_well_formed(self, llm_client):
        from prompts.templates import S4A_SYSTEM, render_s4a_user
        user = render_s4a_user(intent_text=S4A_INTENT_TEXT, notes_text=S4A_NOTES_TEXT)
        spl = llm_client.call(system=S4A_SYSTEM, user=user)
        assert "[DEFINE_PERSONA:]" in spl
        assert "[END_PERSONA]" in spl
        assert "ROLE:" in spl

    def test_mcp_mentioned_in_role(self, llm_client):
        from prompts.templates import S4A_SYSTEM, render_s4a_user
        user = render_s4a_user(intent_text=S4A_INTENT_TEXT, notes_text=S4A_NOTES_TEXT)
        spl = llm_client.call(system=S4A_SYSTEM, user=user)
        assert "MCP" in spl


# ============================================================================
# S4B — DEFINE_CONSTRAINTS
# ============================================================================

S4B_CLASSIFIED_CLAUSES = [
    {"clause_id": "c-001", "classification": "COMPILABLE_HARD",   "clause_type": "rule", "original_text": "DO NOT use: Old deprecated APIs such as `server.tool()`, `server.setRequestHandler(ListToolsRequestSchema, ...)`, or manual handler registration", "source_file": "reference/node_mcp_server.md"},
    {"clause_id": "c-002", "classification": "COMPILABLE_MEDIUM", "clause_type": "rule", "original_text": "Your implementation MUST prioritize composability and code reuse", "source_file": "reference/node_mcp_server.md"},
    {"clause_id": "c-003", "classification": "COMPILABLE_MEDIUM", "clause_type": "rule", "original_text": "NEVER copy-paste similar code between tools", "source_file": "reference/node_mcp_server.md"},
    {"clause_id": "c-004", "classification": "COMPILABLE_HARD",   "clause_type": "rule", "original_text": "Store API keys in environment variables, never in code", "source_file": "reference/mcp_best_practices.md"},
    {"clause_id": "c-005", "classification": "COMPILABLE_MEDIUM", "clause_type": "rule", "original_text": "Sanitize file paths to prevent directory traversal", "source_file": "reference/mcp_best_practices.md"},
    {"clause_id": "c-006", "classification": "COMPILABLE_HARD",   "clause_type": "rule", "original_text": "Use snake_case with service prefix for tool names", "source_file": "reference/mcp_best_practices.md"},
    {"clause_id": "c-007", "classification": "COMPILABLE_HARD",   "clause_type": "rule", "original_text": "Always respect the `limit` parameter", "source_file": "reference/mcp_best_practices.md"},
    {"clause_id": "c-008", "classification": "COMPILABLE_MEDIUM", "clause_type": "rule", "original_text": "Questions MUST be independent — each should NOT depend on the answer to any other question", "source_file": "reference/evaluation.md"},
    {"clause_id": "c-009", "classification": "COMPILABLE_MEDIUM", "clause_type": "rule", "original_text": "Questions MUST require ONLY NON-DESTRUCTIVE AND IDEMPOTENT tool use", "source_file": "reference/evaluation.md"},
    {"clause_id": "c-011", "classification": "NON_COMPILABLE",    "clause_type": "rule", "original_text": "When uncertain, prioritize comprehensive API coverage", "source_file": "SKILL.md"},
]

EXPECTED_S4B_SPL = """\
[DEFINE_CONSTRAINTS:]
    NoDeprecatedApis: DO NOT use: Old deprecated APIs such as `server.tool()`, `server.setRequestHandler(ListToolsRequestSchema, ...)`, or manual handler registration. LOG reference/node_mcp_server.md:c-001
    ApiKeyInEnvVars: Store API keys in environment variables, never in code. LOG reference/mcp_best_practices.md:c-004
    ToolNamingSnakeCase: Use snake_case with service prefix for tool names. LOG reference/mcp_best_practices.md:c-006
    LimitParamRequired: Always respect the `limit` parameter. LOG reference/mcp_best_practices.md:c-007
    CodeComposability: Your implementation MUST prioritize composability and code reuse. LOG reference/node_mcp_server.md:c-002
    NoCopyPaste: NEVER copy-paste similar code between tools. LOG reference/node_mcp_server.md:c-003
    FileSanitization: Sanitize file paths to prevent directory traversal. LOG reference/mcp_best_practices.md:c-005
    EvalIndependence: Questions MUST be independent — each should NOT depend on the answer to any other question. LOG reference/evaluation.md:c-008
    EvalNonDestructive: Questions MUST require ONLY NON-DESTRUCTIVE AND IDEMPOTENT tool use. LOG reference/evaluation.md:c-009
    [GUIDELINE] ApiCoveragePriority: When uncertain, prioritize comprehensive API coverage.
[END_CONSTRAINTS]"""


class TestS4BInput:

    def test_rendered_user_contains_all_clauses(self):
        from prompts.templates import render_s4b_user
        import json
        rendered = render_s4b_user(classified_clauses_json=json.dumps(S4B_CLASSIFIED_CLAUSES))
        assert "server.tool()" in rendered
        assert "environment variables" in rendered
        assert "snake_case" in rendered

    def test_rendered_user_contains_step_clauses_excluded(self):
        """S4B only receives clause_type='rule' items (steps go to S4E)."""
        for clause in S4B_CLASSIFIED_CLAUSES:
            assert clause["clause_type"] == "rule"


class TestS4BExpectedOutput:

    def test_define_constraints_block(self):
        assert "[DEFINE_CONSTRAINTS:]" in EXPECTED_S4B_SPL
        assert "[END_CONSTRAINTS]" in EXPECTED_S4B_SPL

    def test_hard_constraints_have_log(self):
        for aspect in ["NoDeprecatedApis", "ApiKeyInEnvVars", "ToolNamingSnakeCase", "LimitParamRequired"]:
            pattern = rf"{aspect}:.*LOG"
            assert re.search(pattern, EXPECTED_S4B_SPL), f"{aspect} is HARD but missing LOG"

    def test_medium_constraints_have_log(self):
        for aspect in ["CodeComposability", "NoCopyPaste", "EvalIndependence"]:
            pattern = rf"{aspect}:.*LOG"
            assert re.search(pattern, EXPECTED_S4B_SPL), f"{aspect} is MEDIUM but missing LOG"

    def test_non_compilable_has_guideline_tag(self):
        assert "[GUIDELINE] ApiCoveragePriority" in EXPECTED_S4B_SPL

    def test_aspect_names_match_symbol_table(self):
        for aspect in SYMBOL_TABLE["AspectNames"]:
            if aspect != "ApiCoveragePriority":  # GUIDELINE skips DEFINE_CONSTRAINTS LOG line
                assert aspect in EXPECTED_S4B_SPL, f"AspectName {aspect} missing from S4B output"

    def test_no_soft_tag_used(self):
        """This skill has no SOFT clauses — [SOFT] tag must not appear."""
        assert "[SOFT]" not in EXPECTED_S4B_SPL


@pytest.mark.live_llm
class TestS4BLiveLLM:

    def test_all_hard_aspects_have_log(self, llm_client):
        import json
        from prompts.templates import S4B_SYSTEM, render_s4b_user
        user = render_s4b_user(constraints_text=json.dumps(S4B_CLASSIFIED_CLAUSES))
        spl = llm_client.call(system=S4B_SYSTEM, user=user)
        assert "[DEFINE_CONSTRAINTS:]" in spl
        # Spot-check one HARD aspect
        assert "LOG" in spl


# ============================================================================
# S4C — DEFINE_VARIABLES + DEFINE_FILES
# ============================================================================

S4C_ENTITIES = [
    {"entity_id": "implementation_plan", "kind": "Record",   "is_file": False, "file_path": "", "schema_notes": "endpoints: List[text], auth_strategy: text, response_format: text, char_limit: number"},
    {"entity_id": "mcp_server_project",  "kind": "Artifact", "is_file": True,  "file_path": "", "schema_notes": "{service}-mcp-server/ directory"},
    {"entity_id": "evaluation_suite",    "kind": "Evidence", "is_file": False, "file_path": "", "schema_notes": "List[{question: text, answer: text}] — 10+ items"},
]
S4C_OMIT_FILES = [
    {"path": "scripts/example_evaluation.xml", "kind": "data"},
    {"path": "scripts/requirements.txt",       "kind": "data"},
]

EXPECTED_S4C_SPL = """\
[DEFINE_VARIABLES:]
    "Structured implementation plan produced during Phase 1 research"
    implementation_plan: {
        endpoints: List [text],
        auth_strategy: text,
        response_format: text,
        char_limit: number
    }

    "Collection of QA pairs verifying LLM effectiveness with the MCP server"
    evaluation_suite: List [{ question: text, answer: text }]
[END_VARIABLES]

[DEFINE_FILES:]
    "The implemented MCP server project directory"
    mcp_server_project < > : { }

    "Example evaluation XML file (reference only)"
    example_evaluation_xml < scripts/example_evaluation.xml > : { }

    "Python dependencies manifest"
    requirements_txt < scripts/requirements.txt > : { }
[END_FILES]"""


class TestS4CExpectedOutput:

    def test_define_variables_block(self):
        assert "[DEFINE_VARIABLES:]" in EXPECTED_S4C_SPL
        assert "[END_VARIABLES]" in EXPECTED_S4C_SPL

    def test_implementation_plan_in_variables(self):
        assert "implementation_plan" in EXPECTED_S4C_SPL

    def test_evaluation_suite_in_variables(self):
        assert "evaluation_suite" in EXPECTED_S4C_SPL

    def test_define_files_block(self):
        assert "[DEFINE_FILES:]" in EXPECTED_S4C_SPL
        assert "[END_FILES]" in EXPECTED_S4C_SPL

    def test_mcp_project_is_file_with_runtime_path(self):
        """mcp_server_project is_file=True with unknown path → uses < > placeholder."""
        assert "mcp_server_project < >" in EXPECTED_S4C_SPL

    def test_omit_files_referenced_with_literal_paths(self):
        assert "scripts/example_evaluation.xml" in EXPECTED_S4C_SPL
        assert "scripts/requirements.txt" in EXPECTED_S4C_SPL

    def test_var_names_match_symbol_table(self):
        for var in SYMBOL_TABLE["VarNames"]:
            assert var in EXPECTED_S4C_SPL

    def test_file_names_match_symbol_table(self):
        for fname in SYMBOL_TABLE["FileNames"]:
            assert fname in EXPECTED_S4C_SPL


# ============================================================================
# S4D — DEFINE_APIS
# ============================================================================

S4D_NETWORK_STEPS = [
    {
        "step_id": "step.load_framework_docs",
        "description": "Fetch SDK READMEs and documentation via WebFetch",
        "tool_hint": "WebFetch",
        "effects": ["NETWORK"],
        "urls": [
            "https://raw.githubusercontent.com/modelcontextprotocol/typescript-sdk/main/README.md",
            "https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md",
        ],
    },
    {
        "step_id": "step.research_target_api",
        "description": "Review target service API documentation",
        "tool_hint": "WebFetch",
        "effects": ["NETWORK"],
        "urls": [],  # dynamic — URL known only at runtime
    },
]

EXPECTED_S4D_SPL = """\
[DEFINE_APIS:]
    "HTTP fetch tool for loading remote documentation, SDK READMEs, and API specifications"
    WebFetch <none> RETRY 3 LOG [network_error, timeout]
    { }
    {
        functions: [
            {
                name: fetch_url,
                url: <url_not_stated>,
                description: Fetch the content of a URL and return it as text,
                parameters: {
                    parameters: [
                        { required: true, name: url, type: text, description: The URL to fetch }
                    ],
                    controlled-input: false
                },
                return: { type: text, controlled-output: false, description: Page content as text }
            }
        ]
    }
[END_APIS]"""


class TestS4DExpectedOutput:

    def test_define_apis_block(self):
        assert "[DEFINE_APIS:]" in EXPECTED_S4D_SPL
        assert "[END_APIS]" in EXPECTED_S4D_SPL

    def test_webfetch_declared(self):
        assert "WebFetch" in EXPECTED_S4D_SPL

    def test_retry_policy_present(self):
        assert "RETRY 3" in EXPECTED_S4D_SPL

    def test_log_policy_present(self):
        assert "LOG" in EXPECTED_S4D_SPL

    def test_fetch_url_function_declared(self):
        assert "fetch_url" in EXPECTED_S4D_SPL

    def test_api_name_matches_symbol_table(self):
        for api in SYMBOL_TABLE["ApiNames"]:
            assert api in EXPECTED_S4D_SPL


# ============================================================================
# S4E — DEFINE_WORKER
# ============================================================================

EXPECTED_S4E_SPL_FRAGMENT = """\
[DEFINE_WORKER: "Build a complete MCP server from research through evaluation" McpServerBuilder]
    [INPUTS]
        OPTIONAL <REF>service_name</REF>
        OPTIONAL <REF>language_preference</REF>
    [END_INPUTS]
    [OUTPUTS]
        REQUIRED <APPLY_CONSTRAINTS> EvalIndependence EvalNonDestructive </APPLY_CONSTRAINTS> <REF>evaluation_suite</REF>
        REQUIRED <REF>mcp_server_project</REF>
    [END_OUTPUTS]

    [MAIN_FLOW]
        [SEQUENTIAL_BLOCK]
            COMMAND-1 [INPUT DISPLAY "Which service are we building an MCP server for, and do you prefer TypeScript or Python?" VALUE service_config: { service: text, language: [typescript, python] }]
            COMMAND-2 [CALL WebFetch WITH { url: "https://raw.githubusercontent.com/modelcontextprotocol/typescript-sdk/main/README.md" } RESPONSE ts_sdk_docs: text]
            COMMAND-3 [CALL WebFetch WITH { url: "https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md" } RESPONSE py_sdk_docs: text]
            COMMAND-4 [COMMAND Create a detailed implementation plan covering API endpoints, authentication strategy, response format design, and character limit strategy RESULT implementation_plan]
            DECISION-1 [IF service_config.language == typescript]
                COMMAND-5 [COMMAND PROMPT_TO_CODE Implement the MCP server following node_mcp_server.md patterns using server.registerTool with Zod schemas RESULT mcp_server_project]
                COMMAND-6 [COMMAND LITERAL_CODE npm run build RESULT build_success: boolean]
            [ELSE]
                COMMAND-7 [COMMAND PROMPT_TO_CODE Implement the MCP server using FastMCP patterns from the Python SDK documentation RESULT mcp_server_project]
            [END_IF]
            COMMAND-8 [COMMAND Create 10 complex realistic questions about the target service, solve each to verify the answer RESULT evaluation_suite]
        [END_SEQUENTIAL_BLOCK]
    [END_MAIN_FLOW]

    [EXCEPTION_FLOW: NoDeprecatedApis_violated]
        LOG reference/node_mcp_server.md:c-001
        [SEQUENTIAL_BLOCK]
            COMMAND-E1 [DISPLAY Constraint violated: DO NOT use server.tool(), server.setRequestHandler(), or manual handler registration.]
        [END_SEQUENTIAL_BLOCK]
    [END_EXCEPTION_FLOW]

    [EXCEPTION_FLOW: ApiKeyInEnvVars_violated]
        LOG reference/mcp_best_practices.md:c-004
        [SEQUENTIAL_BLOCK]
            COMMAND-E2 [DISPLAY Constraint violated: Store API keys in environment variables, never in code.]
        [END_SEQUENTIAL_BLOCK]
    [END_EXCEPTION_FLOW]

    [EXCEPTION_FLOW: WebFetch_call_failed]
        LOG step.load_framework_docs
        [SEQUENTIAL_BLOCK]
            COMMAND-E3 [DISPLAY API call failed: Unable to fetch remote documentation. Check network connectivity and retry.]
        [END_SEQUENTIAL_BLOCK]
    [END_EXCEPTION_FLOW]

    [EXCEPTION_FLOW: step.verify_build_failed]
        LOG npm run build failed
        [SEQUENTIAL_BLOCK]
            COMMAND-E4 [DISPLAY Step execution failed: npm run build did not complete successfully. Fix TypeScript compilation errors before proceeding.]
        [END_SEQUENTIAL_BLOCK]
    [END_EXCEPTION_FLOW]
[END_WORKER]"""


class TestS4EExpectedOutput:

    def test_define_worker_block(self):
        assert "[DEFINE_WORKER:" in EXPECTED_S4E_SPL_FRAGMENT
        assert "[END_WORKER]" in EXPECTED_S4E_SPL_FRAGMENT

    def test_inputs_block(self):
        assert "[INPUTS]" in EXPECTED_S4E_SPL_FRAGMENT
        assert "[END_INPUTS]" in EXPECTED_S4E_SPL_FRAGMENT

    def test_outputs_block(self):
        assert "[OUTPUTS]" in EXPECTED_S4E_SPL_FRAGMENT
        assert "[END_OUTPUTS]" in EXPECTED_S4E_SPL_FRAGMENT

    def test_evaluation_suite_in_outputs(self):
        assert "evaluation_suite" in EXPECTED_S4E_SPL_FRAGMENT

    def test_mcp_server_project_in_outputs(self):
        assert "mcp_server_project" in EXPECTED_S4E_SPL_FRAGMENT

    def test_apply_constraints_on_evaluation_suite(self):
        """Evaluation suite must have EvalIndependence and EvalNonDestructive applied."""
        assert "APPLY_CONSTRAINTS" in EXPECTED_S4E_SPL_FRAGMENT
        assert "EvalIndependence" in EXPECTED_S4E_SPL_FRAGMENT
        assert "EvalNonDestructive" in EXPECTED_S4E_SPL_FRAGMENT

    def test_ask_input_command_present(self):
        assert "[INPUT DISPLAY" in EXPECTED_S4E_SPL_FRAGMENT
        assert "service" in EXPECTED_S4E_SPL_FRAGMENT.lower()

    def test_webfetch_call_commands_present(self):
        assert "[CALL WebFetch" in EXPECTED_S4E_SPL_FRAGMENT

    def test_decision_for_language_branch(self):
        assert "DECISION-1" in EXPECTED_S4E_SPL_FRAGMENT
        assert "typescript" in EXPECTED_S4E_SPL_FRAGMENT
        assert "[ELSE]" in EXPECTED_S4E_SPL_FRAGMENT
        assert "[END_IF]" in EXPECTED_S4E_SPL_FRAGMENT

    def test_prompt_to_code_used_for_implementation(self):
        assert "PROMPT_TO_CODE" in EXPECTED_S4E_SPL_FRAGMENT

    def test_literal_code_for_npm_build(self):
        assert "LITERAL_CODE" in EXPECTED_S4E_SPL_FRAGMENT
        assert "npm run build" in EXPECTED_S4E_SPL_FRAGMENT

    def test_hard_rule_exception_flows_present(self):
        assert "[EXCEPTION_FLOW: NoDeprecatedApis_violated]" in EXPECTED_S4E_SPL_FRAGMENT
        assert "[EXCEPTION_FLOW: ApiKeyInEnvVars_violated]" in EXPECTED_S4E_SPL_FRAGMENT

    def test_api_failure_exception_flow_present(self):
        assert "[EXCEPTION_FLOW: WebFetch_call_failed]" in EXPECTED_S4E_SPL_FRAGMENT

    def test_validation_gate_exception_flow_present(self):
        assert "[EXCEPTION_FLOW: step.verify_build_failed]" in EXPECTED_S4E_SPL_FRAGMENT

    def test_all_exception_flows_have_log(self):
        """Every EXCEPTION_FLOW must contain a LOG statement."""
        flows = re.findall(
            r'\[EXCEPTION_FLOW:.*?\[END_EXCEPTION_FLOW\]',
            EXPECTED_S4E_SPL_FRAGMENT,
            re.DOTALL
        )
        assert len(flows) >= 4, f"Expected ≥4 exception flows, found {len(flows)}"
        for flow in flows:
            assert "LOG" in flow, f"EXCEPTION_FLOW missing LOG:\n{flow}"

    def test_all_exception_flows_have_display(self):
        flows = re.findall(
            r'\[EXCEPTION_FLOW:.*?\[END_EXCEPTION_FLOW\]',
            EXPECTED_S4E_SPL_FRAGMENT,
            re.DOTALL
        )
        for flow in flows:
            assert "DISPLAY" in flow, f"EXCEPTION_FLOW missing DISPLAY:\n{flow}"

    def test_symbol_table_vars_referenced(self):
        for var in SYMBOL_TABLE["VarNames"]:
            assert var in EXPECTED_S4E_SPL_FRAGMENT

    def test_symbol_table_api_names_referenced(self):
        for api in SYMBOL_TABLE["ApiNames"]:
            assert api in EXPECTED_S4E_SPL_FRAGMENT


@pytest.mark.live_llm
class TestS4ELiveLLM:
    """Spot-check the most critical structural properties of the live WORKER output."""

    def _call(self, llm_client):
        from templates import S4E_SYSTEM, render_s4e_user
        import json
        user = render_s4e_user(
            workflow_steps_json=json.dumps([]),   # simplified for live test
            symbol_table_json=json.dumps(SYMBOL_TABLE),
        )
        return llm_client.call(system=S4E_SYSTEM, user=user)

    def test_worker_block_well_formed(self, llm_client):
        spl = self._call(llm_client)
        assert "[DEFINE_WORKER:" in spl
        assert "[END_WORKER]" in spl

    def test_inputs_outputs_present(self, llm_client):
        spl = self._call(llm_client)
        assert "[INPUTS]" in spl
        assert "[OUTPUTS]" in spl

    def test_exception_flows_present(self, llm_client):
        spl = self._call(llm_client)
        assert "[EXCEPTION_FLOW:" in spl
