"""Step 4: SPL Emission step (S4A-F parallel)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Any

from models import EntitySpec, SectionBundle, SectionItem, SPLSpec, StructuredSpec, WorkflowStep
from models.pipeline_steps.step3.models import AlternativeFlow, ExceptionFlow, FlowStep
from pipeline.llm_steps.step1_5_api_generation import merge_api_spl_blocks
from pipeline.llm_steps.step4_spl_emission import (
    _assemble_spl,
    _build_review_summary,
    _call_4a,
    _call_4b,
    _call_4c,
    _call_4e,
    _call_4f,
    _call_s0,
    _extract_symbol_table,
    _format_symbol_table,
    _prepare_step4_inputs_parallel,
    validate_and_fix_worker_nesting,
)
from pipeline.orchestrator.base import PipelineStep
from pipeline.orchestrator.execution_context import ExecutionContext
from pipeline.orchestrator.step_registry import registry


@registry.register
class Step4SPLStep(PipelineStep[dict, dict]):
    """Step 4: Emit final SPL specification.

    Parallel execution with dependency-driven scheduling:
    - S4A: Persona/Audience/Concepts
    - S4B: Constraints
    - S4C: Variables/Files (depends on type_registry)
    - S4D: APIs (uses pre-generated API table from Step 1.5)
    - S4E: Worker (MAIN_FLOW, ALTERNATIVE_FLOW, EXCEPTION_FLOW)
    - S4F: Examples (optional)

    Input:
        Dictionary with:
        - step1_output: Step 1 output (section_bundle)
        - step3_output: Step 3 output (workflow, types, etc.)
        - step1_5_output: Step 1.5 output (api_table)

    Output:
        Dictionary containing:
        - spl_spec: SPLSpec as dict
        - structured_spec: StructuredSpec as dict
    """

    @property
    def name(self) -> str:
        """Step name for logging and checkpointing."""
        return "step4_spl"

    @property
    def dependencies(self) -> list[str]:
        """Step 4 depends on Step 3, Step 1.5, and Step 1 outputs."""
        return ["step3_workflow", "step1_5_api", "step1_structure"]

    def execute(self, context: ExecutionContext, inputs: dict) -> dict:
        """Emit final SPL specification.

        Args:
            context: Execution context with LLM client
            inputs: Dictionary with step outputs

        Returns:
            Dictionary with SPL specification
        """
        context.logger.info("[Step 4] Launching parallel sub-steps...")
        context.logger.debug("[Step 4] Received inputs with keys: %s", list(inputs.keys()))
        
        # Validate required inputs
        if "step1_structure" not in inputs:
            raise ValueError(
                f"step1_structure not found in inputs. "
                f"Available keys: {list(inputs.keys())}"
            )

        # Get Step 1 output
        step1_data = inputs["step1_structure"]
        if not isinstance(step1_data, dict):
            raise ValueError(
                f"step1_structure is not a dict, got {type(step1_data)}: {step1_data}"
            )

        context.logger.debug("[Step 4] step1_structure keys: %s", list(step1_data.keys()))

        bundle_data = step1_data.get("section_bundle")
        if bundle_data is None:
            raise ValueError(
                f"section_bundle not found in step1_structure. "
                f"Available keys: {list(step1_data.keys())}"
            )

        # Reconstruct SectionBundle from dict - handle SectionItem dicts
        bundle_sections = {}
        for key, items in bundle_data.items():
            if key == "skill_id":
                bundle_sections[key] = items
            elif isinstance(items, list):
                # Convert dict items to SectionItem objects
                section_items = []
                for item in items:
                    if isinstance(item, dict):
                        section_items.append(SectionItem(**item))
                    else:
                        section_items.append(item)
                bundle_sections[key] = section_items
            else:
                bundle_sections[key] = items
        
        bundle = SectionBundle(**bundle_sections)

        # Get Step 3 output
        step3_data = inputs.get("step3_workflow", {})

        # Reconstruct workflow steps
        workflow_steps: list[WorkflowStep] = []
        for s in step3_data.get("workflow_steps", []):
            if isinstance(s, dict):
                workflow_steps.append(WorkflowStep(**s))
            else:
                workflow_steps.append(s)

        # Reconstruct alternative_flows and exception_flows from dicts
        alternative_flows: list[AlternativeFlow] = []
        for flow_data in step3_data.get("alternative_flows", []):
            if isinstance(flow_data, dict):
                # Reconstruct FlowStep objects for steps
                steps = []
                for step_data_item in flow_data.get("steps", []):
                    if isinstance(step_data_item, dict):
                        # Filter only valid FlowStep fields
                        valid_fields = {k: v for k, v in step_data_item.items() if k in FlowStep.__dataclass_fields__}
                        steps.append(FlowStep(**valid_fields))
                    else:
                        steps.append(step_data_item)
                flow_data["steps"] = steps
                alternative_flows.append(AlternativeFlow(**flow_data))
            else:
                alternative_flows.append(flow_data)

        exception_flows: list[ExceptionFlow] = []
        for flow_data in step3_data.get("exception_flows", []):
            if isinstance(flow_data, dict):
                # Reconstruct FlowStep objects for steps
                steps = []
                for step_data_item in flow_data.get("steps", []):
                    if isinstance(step_data_item, dict):
                        # Filter only valid FlowStep fields
                        valid_fields = {k: v for k, v in step_data_item.items() if k in FlowStep.__dataclass_fields__}
                        steps.append(FlowStep(**valid_fields))
                    else:
                        steps.append(step_data_item)
                flow_data["steps"] = steps
                exception_flows.append(ExceptionFlow(**flow_data))
            else:
                exception_flows.append(flow_data)

        type_registry = step3_data.get("type_registry", {})
        types_spl = step3_data.get("types_spl", "")

        # Convert global_registry to entities
        entities: list[EntitySpec] = []
        global_registry_data = step3_data.get("global_registry", {})
        if global_registry_data:
            entities = self._convert_registry_to_entities(global_registry_data)

        context.logger.info(
            "[Step 4] Input: %d workflow steps, %d entities",
            len(workflow_steps),
            len(entities),
        )

        # Get API table from Step 1.5
        step1_5_data = inputs.get("step1_5_api", {})
        from models import APISymbolTable, APISpec

        api_table = APISymbolTable(
            apis={
                name: APISpec(**spec_data)
                for name, spec_data in step1_5_data.get("apis", {}).items()
            }
        )

        # Prepare Step 4 inputs
        s4a_in, s4b_in, s4c_in, s4d_in, s4e_in, s4f_in = _prepare_step4_inputs_parallel(
            bundle, entities, workflow_steps, alternative_flows, exception_flows, type_registry
        )

        # Phase 1: Launch S4C (needs type_registry)
        model_4c = context.config.get_step_model("step4c_variables_files")
        block_4c = _call_4c(context.client, s4c_in, model=model_4c)

        # Extract symbol table from S4C output
        symbol_table = _extract_symbol_table(block_4c)
        symbol_table_text = _format_symbol_table(symbol_table)
        context.logger.info(
            "[Step 4] Symbol table - types: %d, variables: %d, files: %d",
            len(symbol_table.get("types", [])),
            len(symbol_table["variables"]),
            len(symbol_table["files"]),
        )

        # Re-prepare inputs with complete workflow info
        s4a_inputs, s4b_inputs, _, s4d_inputs, s4e_inputs, s4f_inputs = _prepare_step4_inputs_parallel(
            bundle, entities, workflow_steps, alternative_flows, exception_flows, type_registry
        )

        # Prepare API SPL block from Step 1.5
        block_4d = merge_api_spl_blocks(api_table)
        context.logger.info("[Step 4] Prepared APIs block (%d chars)", len(block_4d))

        # Phase 2: Launch S4A, S4B, S0 in parallel
        with ThreadPoolExecutor(max_workers=3) as pool:
            # Submit parallel tasks
            future_4a = pool.submit(
                _call_4a, context.client, s4a_inputs, symbol_table_text,
                context.config.get_step_model("step4a_persona")
            )
            future_4b = pool.submit(
                _call_4b, context.client, s4b_inputs, symbol_table_text,
                context.config.get_step_model("step4b_constraints")
            )

            # S0: Generate DEFINE_AGENT header
            intent_text = bundle.to_text(["INTENT"])
            notes_text = bundle.to_text(["NOTES"])
            future_s0 = pool.submit(
                _call_s0, context.client, bundle_data.get("skill_id", "unknown"), intent_text, notes_text,
                context.config.get_step_model("step0_define_agent")
            )

            # Collect results
            block_4a = future_4a.result()
            block_4b = future_4b.result()
            block_s0 = future_s0.result()

        # Phase 3: S4E (merge point)
        context.logger.info("[Step 4] Phase 3: S4E (worker)...")
        block_4e_original = _call_4e(
            context.client, s4e_inputs, symbol_table_text, block_4d,
            context.config.get_step_model("step4e_worker")
        )

        # Phase 4: S4E1/S4E2 - Validate and fix nested BLOCK structures
        block_4e, nesting_result = validate_and_fix_worker_nesting(
            context.client, block_4e_original,
            context.config.get_step_model("step4e1_nesting_fix")
        )

        if nesting_result.get("has_violations", False):
            context.logger.info(
                "[Step 4] Phase 4: S4E1 detected %d violations, S4E2 fixed them",
                len(nesting_result.get("violations", []))
            )
        else:
            context.logger.info("[Step 4] Phase 4: S4E1 - no nested BLOCK violations found")

        # Phase 5: S4F (final)
        block_4f = ""
        if s4f_inputs.get("has_examples"):
            context.logger.info("[Step 4] Phase 5: S4F (examples)...")
            block_4f = _call_4f(
                context.client, s4f_inputs, block_4e,
                context.config.get_step_model("step4f_examples")
            )

        # Assemble final SPL
        skill_id = bundle_data.get("skill_id", "unknown")
        spl_text = _assemble_spl(
            skill_id, block_s0, block_4a, block_4b, block_4c, block_4d, block_4e, block_4f, types_spl
        )
        review_summary = _build_review_summary()
        clause_counts: dict = {}

        context.logger.info("[Step 4] SPL assembled (%d chars)", len(spl_text))

        # Create SPLSpec
        spl_spec = SPLSpec(
            skill_id=skill_id,
            spl_text=spl_text,
            review_summary=review_summary,
            clause_counts=clause_counts,
        )

        # Write final output
        output_dir = context.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        spl_path = output_dir / f"{skill_id}.spl"
        spl_path.write_text(spl_text, encoding="utf-8")
        context.logger.info("[Output] SPL written to %s", spl_path)

        # Create StructuredSpec
        structured_spec = StructuredSpec(
            entities=[],
            workflow_steps=workflow_steps,
            alternative_flows=alternative_flows,
            exception_flows=exception_flows,
        )

        return {
            "spl_spec": asdict(spl_spec),
            "structured_spec": asdict(structured_spec),
        }

    def _convert_registry_to_entities(
        self, registry_data: dict
    ) -> list[EntitySpec]:
        """Convert GlobalVarRegistry dict to list of EntitySpec for S4C compatibility.

        Args:
            registry_data: Global variable registry as dict (from Step 3 JSON output)

        Returns:
            List of EntitySpec objects
        """
        from models.step3_types import TypeExpr

        entities: list[EntitySpec] = []

        def _reconstruct_type_expr(type_data: dict | str) -> TypeExpr:
            """Reconstruct TypeExpr from serialized dict or string."""
            if isinstance(type_data, str):
                # Simple type like "text", "number", etc.
                return TypeExpr.simple(type_data)
            elif isinstance(type_data, dict):
                # Reconstruct from dict (handling nested types)
                kind = type_data.get("kind", "simple")
                if kind == "simple":
                    return TypeExpr.simple(type_data.get("type_name", "text"))
                elif kind == "enum":
                    values = type_data.get("values", [])
                    return TypeExpr.enum(list(values))
                elif kind == "array":
                    element_data = type_data.get("element_type")
                    element_type = _reconstruct_type_expr(element_data) if element_data else TypeExpr.simple("any")
                    return TypeExpr.array(element_type)
                elif kind == "struct":
                    fields_data = type_data.get("fields", {})
                    fields = {k: _reconstruct_type_expr(v) for k, v in fields_data.items()}
                    return TypeExpr.struct(fields)
                else:
                    return TypeExpr.simple("any")
            else:
                return TypeExpr.simple("any")

        # Convert variables (non-file) to EntitySpec
        for var_name, var_spec_data in registry_data.get("variables", {}).items():
            if isinstance(var_spec_data, dict):
                type_expr = _reconstruct_type_expr(var_spec_data.get("type_expr", "text"))
                description = var_spec_data.get("description", "")
            else:
                # Fallback: treat as simple type
                type_expr = TypeExpr.simple("text")
                description = ""

            entity = EntitySpec(
                entity_id=var_name,
                kind="Run",
                type_name=type_expr.to_spl(),
                schema_notes=description,
                provenance_required=False,
                provenance="EXPLICIT",
                source_text="Extracted from Step 3-IO analysis",
                is_file=False,
                file_path="",
                from_omit_files=False,
            )
            entities.append(entity)

        # Convert files to EntitySpec
        for var_name, var_spec_data in registry_data.get("files", {}).items():
            if isinstance(var_spec_data, dict):
                type_expr = _reconstruct_type_expr(var_spec_data.get("type_expr", "text"))
                description = var_spec_data.get("description", "")
            else:
                # Fallback: treat as simple type
                type_expr = TypeExpr.simple("text")
                description = ""

            entity = EntitySpec(
                entity_id=var_name,
                kind="Artifact",
                type_name=type_expr.to_spl(),
                schema_notes=description,
                provenance_required=False,
                provenance="EXPLICIT",
                source_text="Extracted from Step 3-IO analysis",
                is_file=True,
                file_path=var_name,
                from_omit_files=False,
            )
            entities.append(entity)

        return entities
