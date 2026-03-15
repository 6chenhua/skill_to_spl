"""
test_step3_structured_spec.py
Unit tests for Step 3 — Structured Entity & Step Extraction (LLM step).

INPUT  → WORKFLOW + TOOLS + ARTIFACTS + EVIDENCE + EXAMPLES sections
         + NON_COMPILABLE clauses
OUTPUT → StructuredSpec: entities, workflow_steps, interaction_requirements,
         success_criteria
"""

import json
import os
import pytest

# ---------------------------------------------------------------------------
# Input: Step 3 sees WORKFLOW/TOOLS/ARTIFACTS/EVIDENCE/EXAMPLES + NON clauses
# (constructed from real mcp-builder SectionBundle content)
# ---------------------------------------------------------------------------

STEP3_INPUT = {
    "WORKFLOW": """\
- Creating a high-quality MCP server involves four main phases: Phase 1: Deep Research and Planning, Phase 2: Implementation, Phase 3: Review and Test, Phase 4: Create Evaluations. [source: SKILL.md]
- Load framework documentation before implementation: MCP Best Practices, TypeScript Guide, Python Guide, Evaluation Guide. [source: SKILL.md]
- Review the service's API documentation to identify key endpoints, authentication requirements, and data models. [source: SKILL.md]
- Always ensure `npm run build` completes successfully before considering the implementation complete. [source: reference/node_mcp_server.md]
- Create 10 human-readable questions requiring ONLY READ-ONLY, INDEPENDENT, NON-DESTRUCTIVE, and IDEMPOTENT operations to answer. [source: reference/evaluation.md]
- Follow the process: Tool Inspection → Content Exploration → Question Generation → Answer Verification. [source: reference/evaluation.md]
- Output evaluation as XML file with <evaluation><qa_pair><question>...<answer>... structure. [source: reference/evaluation.md]
""",
    "TOOLS": """\
- McpServer.registerTool() with Zod inputSchema and outputSchema [source: reference/node_mcp_server.md]
- FastMCP @mcp.tool decorator with Pydantic models [source: reference/python_mcp_server.md]
- WebFetch to load TypeScript SDK README from https://raw.githubusercontent.com/modelcontextprotocol/typescript-sdk/main/README.md [source: SKILL.md]
- WebFetch to load Python SDK README from https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md [source: SKILL.md]
""",
    "ARTIFACTS": """\
- {service}-mcp-server/ project directory with src/index.ts, package.json, tsconfig.json, dist/ [source: reference/node_mcp_server.md]
- evaluation XML file: <evaluation><qa_pair><question>...<answer>... (10 QA pairs) [source: reference/evaluation.md]
""",
    "EVIDENCE": """\
- npm run build completes without errors [source: reference/node_mcp_server.md]
- 10 QA pairs with verified answers covering realistic multi-tool-call scenarios [source: reference/evaluation.md]
""",
    "EXAMPLES": """\
- QA pair: <question>Find discussions about AI model launches with animal codenames... What number X was being determined for the model named after a spotted wild cat?</question><answer>3</answer> [source: SKILL.md]
- server.registerTool('example_search_users', { title, description, inputSchema, annotations }, async (params) => { ... }) [source: reference/node_mcp_server.md]
""",
    "NON_COMPILABLE_CLAUSES": [
        {"clause_id": "c-011", "original_text": "When uncertain, prioritize comprehensive API coverage"},
    ],
}

# ---------------------------------------------------------------------------
# Gold-standard expected StructuredSpec
# ---------------------------------------------------------------------------

EXPECTED_SPEC = {
    "entities": [
        {
            "entity_id": "implementation_plan",
            "kind": "Record",
            "type_name": "ImplementationPlan",
            "schema_notes": "endpoints: list, auth_strategy: text, response_format: text, char_limit: number",
            "provenance_required": True,
            "is_file": False,
            "file_path": "",
            "from_omit_files": False,
            "provenance": "EXPLICIT",
        },
        {
            "entity_id": "mcp_server_project",
            "kind": "Artifact",
            "type_name": "McpServerProject",
            "schema_notes": "{service}-mcp-server/ with src/index.ts, package.json, tsconfig.json, dist/",
            "provenance_required": True,
            "is_file": True,
            "file_path": "",      # path not known at design time → < > in SPL
            "from_omit_files": False,
            "provenance": "EXPLICIT",
        },
        {
            "entity_id": "evaluation_suite",
            "kind": "Evidence",
            "type_name": "EvaluationSuite",
            "schema_notes": "List of 10+ QA pairs {question: text, answer: text}",
            "provenance_required": True,
            "is_file": False,
            "file_path": "",
            "from_omit_files": False,
            "provenance": "EXPLICIT",
        },
    ],
    "workflow_steps": [
        {
            "step_id": "step.load_framework_docs",
            "description": "Fetch MCP Best Practices, TypeScript Guide, Python Guide, Evaluation Guide, and SDK READMEs via WebFetch",
            "prerequisites": [],
            "produces": [],
            "is_validation_gate": False,
            "effects": ["NETWORK"],
            "execution_mode": "LLM_PROMPT",
            "tool_hint": "WebFetch",
        },
        {
            "step_id": "step.research_target_api",
            "description": "Review the target service's API documentation to identify endpoints, authentication, and data models",
            "prerequisites": [],
            "produces": [],
            "is_validation_gate": False,
            "effects": ["NETWORK"],
            "execution_mode": "LLM_PROMPT",
            "tool_hint": "WebFetch",
        },
        {
            "step_id": "step.create_implementation_plan",
            "description": "Create a detailed implementation plan covering endpoints, authentication strategy, response format, and character limits",
            "prerequisites": [],
            "produces": ["implementation_plan"],
            "is_validation_gate": False,
            "effects": [],
            "execution_mode": "LLM_PROMPT",
            "tool_hint": "",
        },
        {
            "step_id": "step.implement_mcp_server",
            "description": "Implement the MCP server following language-specific best practices; run npm run build for TypeScript",
            "prerequisites": ["implementation_plan"],
            "produces": ["mcp_server_project"],
            "is_validation_gate": False,
            "effects": ["EXEC", "WRITE"],
            "execution_mode": "PROMPT_TO_CODE",
            "tool_hint": "TypeScript SDK / FastMCP",
        },
        {
            "step_id": "step.create_evaluations",
            "description": "Create 10 complex, realistic QA pairs using READ-ONLY exploration, then verify each answer",
            "prerequisites": ["mcp_server_project"],
            "produces": ["evaluation_suite"],
            "is_validation_gate": False,
            "effects": ["WRITE"],
            "execution_mode": "LLM_PROMPT",
            "tool_hint": "",
        },
        {
            "step_id": "step.verify_build",
            "description": "Verify npm run build completes successfully",
            "prerequisites": ["mcp_server_project"],
            "produces": [],
            "is_validation_gate": True,
            "effects": ["EXEC"],
            "execution_mode": "LITERAL_CODE",
            "tool_hint": "npm",
        },
    ],
    "interaction_requirements": [
        {
            "req_id": "ir-001",
            "condition": "target service or language preference is not specified",
            "interaction_type": "ASK",
            "prompt": "Which service are we building an MCP server for, and do you prefer TypeScript or Python?",
            "gates_step": "step.research_target_api",
        },
    ],
    "success_criteria": {
        "description": "MCP server implemented with complete tool coverage, npm build passes, and 10 verified QA pairs confirm LLMs can answer realistic questions",
        "deterministic": False,
    },
}

VALID_ENTITY_KINDS = {"Artifact", "Run", "Evidence", "Record"}
VALID_EXECUTION_MODES = {"LITERAL_CODE", "PROMPT_TO_CODE", "LLM_PROMPT"}
VALID_EFFECTS = {"NETWORK", "EXEC", "WRITE", "READ"}
VALID_INTERACTION_TYPES = {"ASK", "STOP", "ELICIT"}


# ---------------------------------------------------------------------------
# Schema validator
# ---------------------------------------------------------------------------

def validate_structured_spec(spec: dict) -> list[str]:
    errors = []

    # entities
    entities = spec.get("entities", [])
    entity_ids = set()
    for i, e in enumerate(entities):
        ref = f"entities[{i}]"
        for field in ["entity_id", "kind", "type_name", "schema_notes",
                      "provenance_required", "is_file", "provenance"]:
            if field not in e:
                errors.append(f"{ref}: missing '{field}'")
        if e.get("kind") not in VALID_ENTITY_KINDS:
            errors.append(f"{ref}: invalid kind '{e.get('kind')}'")
        if e.get("entity_id") in entity_ids:
            errors.append(f"{ref}: duplicate entity_id")
        entity_ids.add(e.get("entity_id"))

    # workflow_steps
    step_ids = set()
    for i, s in enumerate(spec.get("workflow_steps", [])):
        ref = f"workflow_steps[{i}]"
        for field in ["step_id", "description", "prerequisites", "produces",
                      "is_validation_gate", "effects", "execution_mode"]:
            if field not in s:
                errors.append(f"{ref}: missing '{field}'")
        if s.get("execution_mode") not in VALID_EXECUTION_MODES:
            errors.append(f"{ref}: invalid execution_mode '{s.get('execution_mode')}'")
        for effect in s.get("effects", []):
            if effect not in VALID_EFFECTS:
                errors.append(f"{ref}: invalid effect '{effect}'")
        if s.get("step_id") in step_ids:
            errors.append(f"{ref}: duplicate step_id")
        step_ids.add(s.get("step_id"))

    # interaction_requirements
    for i, ir in enumerate(spec.get("interaction_requirements", [])):
        ref = f"interaction_requirements[{i}]"
        if ir.get("interaction_type") not in VALID_INTERACTION_TYPES:
            errors.append(f"{ref}: invalid interaction_type '{ir.get('interaction_type')}'")
        if not ir.get("prompt", "").strip():
            errors.append(f"{ref}: prompt is empty")

    # success_criteria
    sc = spec.get("success_criteria", {})
    if not sc.get("description", "").strip():
        errors.append("success_criteria.description is empty")

    return errors


# ---------------------------------------------------------------------------
# INPUT tests
# ---------------------------------------------------------------------------

class TestStep3Input:

    def test_system_prompt_exists(self):
        from templates import STEP3_SYSTEM
        assert len(STEP3_SYSTEM) > 100

    def test_rendered_user_contains_workflow(self):
        from templates import render_step3_user
        rendered = render_step3_user(**STEP3_INPUT)
        assert "npm run build" in rendered

    def test_rendered_user_contains_artifacts(self):
        from templates import render_step3_user
        rendered = render_step3_user(**STEP3_INPUT)
        assert "{service}-mcp-server" in rendered

    def test_rendered_user_contains_non_compilable_clauses(self):
        from templates import render_step3_user
        rendered = render_step3_user(**STEP3_INPUT)
        assert "comprehensive API coverage" in rendered

    def test_rendered_user_excludes_hard_medium_clauses(self):
        """Step 3 does not receive HARD/MEDIUM clauses — those are handled by S4B/S4E."""
        from templates import render_step3_user
        rendered = render_step3_user(**STEP3_INPUT)
        # If the template correctly excludes them, it won't contain classification labels
        assert "COMPILABLE_HARD" not in rendered
        assert "COMPILABLE_MEDIUM" not in rendered


# ---------------------------------------------------------------------------
# OUTPUT tests
# ---------------------------------------------------------------------------

class TestStep3ExpectedOutput:

    def test_expected_spec_passes_schema(self):
        errors = validate_structured_spec(EXPECTED_SPEC)
        assert errors == [], f"Gold-standard has schema errors: {errors}"

    def test_three_entities_present(self):
        ids = [e["entity_id"] for e in EXPECTED_SPEC["entities"]]
        assert "implementation_plan" in ids
        assert "mcp_server_project" in ids
        assert "evaluation_suite" in ids

    def test_mcp_server_project_is_artifact(self):
        entity = next(e for e in EXPECTED_SPEC["entities"]
                      if e["entity_id"] == "mcp_server_project")
        assert entity["kind"] == "Artifact"
        assert entity["is_file"] is True

    def test_evaluation_suite_is_evidence(self):
        entity = next(e for e in EXPECTED_SPEC["entities"]
                      if e["entity_id"] == "evaluation_suite")
        assert entity["kind"] == "Evidence"

    def test_implement_step_produces_mcp_project(self):
        step = next(s for s in EXPECTED_SPEC["workflow_steps"]
                    if "implement" in s["step_id"])
        assert "mcp_server_project" in step["produces"]
        assert step["execution_mode"] == "PROMPT_TO_CODE"

    def test_verify_build_is_validation_gate(self):
        step = next(s for s in EXPECTED_SPEC["workflow_steps"]
                    if s.get("is_validation_gate") is True)
        assert "build" in step["step_id"] or "build" in step["description"].lower()
        assert "EXEC" in step["effects"]

    def test_network_steps_use_webfetch(self):
        network_steps = [s for s in EXPECTED_SPEC["workflow_steps"]
                         if "NETWORK" in s["effects"]]
        assert len(network_steps) >= 1
        for step in network_steps:
            assert "WebFetch" in step.get("tool_hint", "")

    def test_interaction_requirement_asks_for_service(self):
        irs = EXPECTED_SPEC["interaction_requirements"]
        assert len(irs) >= 1
        assert irs[0]["interaction_type"] == "ASK"
        prompt = irs[0]["prompt"].lower()
        assert "service" in prompt or "language" in prompt

    def test_success_criteria_mentions_10_qa_pairs(self):
        desc = EXPECTED_SPEC["success_criteria"]["description"].lower()
        assert "10" in desc or "ten" in desc or "qa" in desc


# ---------------------------------------------------------------------------
# LIVE LLM tests
# ---------------------------------------------------------------------------

@pytest.mark.live_llm
class TestStep3LiveLLM:

    def _call(self, llm_client):
        from templates import STEP3_SYSTEM, render_step3_user
        user = render_step3_user(**STEP3_INPUT)
        raw = llm_client.call(system=STEP3_SYSTEM, user=user)
        return json.loads(raw)

    def test_schema_valid(self, llm_client):
        spec = self._call(llm_client)
        errors = validate_structured_spec(spec)
        assert errors == [], f"Schema errors: {errors}"

    def test_mcp_project_entity_present(self, llm_client):
        spec = self._call(llm_client)
        ids = [e["entity_id"] for e in spec.get("entities", [])]
        assert any("mcp" in eid.lower() or "project" in eid.lower() for eid in ids)

    def test_evaluation_entity_present(self, llm_client):
        spec = self._call(llm_client)
        ids = [e["entity_id"] for e in spec.get("entities", [])]
        assert any("eval" in eid.lower() for eid in ids)

    def test_prompt_to_code_step_present(self, llm_client):
        spec = self._call(llm_client)
        modes = [s["execution_mode"] for s in spec.get("workflow_steps", [])]
        assert "PROMPT_TO_CODE" in modes

    def test_network_step_present(self, llm_client):
        spec = self._call(llm_client)
        effects_all = [e for s in spec.get("workflow_steps", []) for e in s.get("effects", [])]
        assert "NETWORK" in effects_all
