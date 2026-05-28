import logging
import json  # ← ADD THIS
from engine.base_agent_node import BaseAgentNode
from typing import Dict, Any, Optional, List
from engine.registry import register_node
from nodes.utils.resolver import resolve_field
import re
from logging_config import setup_logging
from engine.utils import prepare_agent_input  # 🆕 ADD THIS IMPORT


logger = setup_logging("GenericAgentNode", level="DEBUG")



@register_node("GenericAgentNode")
@register_node("ResponseAgentNode")
@register_node("GreetingAgentNode")
class GenericAgentNode(BaseAgentNode):
    """
    Generic agent node with support for:
    1. Task templating
    2. Dynamic data mapping (from previous nodes)
    3. Static parameters (from workflow configuration)
    4. 🆕 Array path mappings (multiple sources for single field)
    """

    def __init__(self, node_id: str, node_data: Dict[str, Any], debug: bool = True):
        super().__init__(node_id, node_data)
        self.debug = debug

    def prepare_task(self, context: Dict[str, Any]) -> str:
        task_template = self.form_data.get("task")
        if not task_template:
            task_template = (
                self.form_data.get("agent_instructions")
                or self.form_data.get("agent_description")
                or "Analyze the user message and respond clearly."
            )
            logger.warning(
                "[%s] Missing task template; using fallback task text.",
                self.node_id,
            )

        if self.debug:
            logger.info(f"[{self.node_id}] 🧩 Preparing task with template: {task_template}")
            logger.info(f"[{self.node_id}] Context keys: {list(context.keys())}")

        # Support workflow template placeholders like {{sys_rfq_id}}
        task_template = self._resolve_placeholders(task_template, context)

        placeholders = re.findall(r'\{([^}]+)\}', task_template)
        replacements = {}

        for placeholder in placeholders:
            value = resolve_field(context, placeholder)
            if self.debug:
                logger.info(f"[{self.node_id}] 🔍 Placeholder: {placeholder} → {value}")
            replacements[placeholder] = str(value) if value is not None else ""

        task = task_template
        for placeholder, value in replacements.items():
            task = task.replace(f"{{{placeholder}}}", value)


        # 🔹 HARD APPEND user_query IF PRESENT
        user_query = (
            context.get("user_query")
            or context.get("parameters", {}).get("user_query")
        )

        if (
            isinstance(user_query, str)
            and user_query.strip()
            and "User query:" not in task
        ):
            task = f"{task}\n\nUser query:\n{user_query.strip()}"
        elif "User query:" not in task:
            fallback_query = self._extract_fallback_query(context)
            if fallback_query:
                task = f"{task}\n\nUser query:\n{fallback_query.strip()}"

        if self.debug:
            logger.info(f"[{self.node_id}] ✅ Final task after substitution: {task}")

        unresolved_task_placeholders = self._find_template_placeholders(task)
        if unresolved_task_placeholders:
            msg = (
                f"[{self.node_id}] ❌ Unresolved placeholders in task template: {unresolved_task_placeholders}. "
                "Provide values for these keys in the execution context."
            )
            logger.error(msg)
            raise ValueError(msg)

        return task

    def prepare_data(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare dynamic data from previous node outputs.
        
        🆕 SUPPORTS ARRAY MAPPINGS:
        - Single path: "gmail_data": "Gmail trigger.0.metadata.subject"
        - Array paths: "gmail_data": ["Gmail trigger.0.metadata.message_id", "Gmail trigger.0.metadata.subject"]
        
        ✅ BACKWARD COMPATIBLE: Existing single-path mappings work exactly as before
        ✅ ALWAYS RETURNS A DICT (never None)
        """
        data_mapping = self.form_data.get("data_mapping", {})
        pass_all = self.form_data.get("pass_all_context", False)

        if self.debug:
            logger.info(f"[{self.node_id}] ⚙️ Preparing dynamic data")
            logger.info(f"[{self.node_id}] data_mapping: {json.dumps(data_mapping, default=str)}")
            logger.info(f"[{self.node_id}] pass_all_context: {pass_all}")

        # Option 1: Explicit mapping
        if data_mapping:
            data = {}
            for key, path in data_mapping.items():
                try:
                    value = resolve_field(context, path)
                    
                    # 🆕 Enhanced logging for array vs single value
                    if isinstance(path, list):
                        logger.info(f"[{self.node_id}] 🔗 Array mapping {key} <- {len(path)} paths")
                        for i, p in enumerate(path):
                            logger.info(f"[{self.node_id}]   [{i}] {p}")
                        logger.info(f"[{self.node_id}] ✅ Result: {len(value) if isinstance(value, list) else 'N/A'} values")
                    else:
                        logger.info(f"[{self.node_id}] 🔗 Single mapping {key} <- {path} = {value}")
                    
                    # Store the value (will be array if path was array, single value otherwise)
                    if value is not None:
                        data[key] = value
                    elif key in {"user_query", "query", "message"}:
                        fallback_value = self._extract_fallback_query(context)
                        if fallback_value:
                            data[key] = fallback_value
                            logger.info(
                                f"[{self.node_id}] 🔁 Fallback mapped {key} from upstream query context"
                            )
                        
                except Exception as e:
                    logger.error(f"[{self.node_id}] ❌ Error resolving path '{path}': {e}", exc_info=True)
                    if key in {"user_query", "query", "message"}:
                        fallback_value = self._extract_fallback_query(context)
                        if fallback_value:
                            data[key] = fallback_value
                    
            if self.debug:
                logger.info(f"[{self.node_id}] ✅ Final mapped data keys: {list(data.keys())}")
                for key, val in data.items():
                    if isinstance(val, list):
                        logger.info(f"[{self.node_id}]   {key}: [array with {len(val)} items]")
                    else:
                        logger.info(f"[{self.node_id}]   {key}: {type(val).__name__}")
            return self._resolve_placeholders(data, context)

        # Option 2: Pass entire context
        if pass_all:
            flattened = self._flatten_context(context)
            if self.debug:
                logger.info(f"[{self.node_id}] 🔄 Passing entire flattened context ({len(flattened)} keys)")
            return self._resolve_placeholders(flattened, context)

        # ✅ CRITICAL FIX: Always return a dict (never None)
        # This prevents TypeError: 'NoneType' object is not iterable
        if self.debug:
            logger.info(f"[{self.node_id}] ⚠️ No data_mapping or pass_all_context set, returning empty dict")
        return {}
    
    def _safe_parse_json(self, value: Any) -> Any:
        """
        Parse JSON ONLY if the value is clearly JSON.
        Never converts normal text.
        """
        if not isinstance(value, str):
            return value

        s = value.strip()

        # Structural gate
        if not (
            (s.startswith("{") and s.endswith("}")) or
            (s.startswith("[") and s.endswith("]"))
        ):
            return value

        try:
            return json.loads(s)
        except Exception:
            return value

    def _extract_fallback_query(self, context: Dict[str, Any]) -> Optional[str]:
        """Best-effort extraction of the original user query from upstream context."""
        if not isinstance(context, dict):
            return None

        candidate_paths = [
            ("user_query",),
            ("query",),
            ("message",),
            ("parameters", "user_query"),
            ("parameters", "query"),
            ("parameters", "message"),
        ]

        for path in candidate_paths:
            value = context
            for key in path:
                if not isinstance(value, dict):
                    value = None
                    break
                value = value.get(key)
            if isinstance(value, str) and value.strip():
                return value

        node_outputs = context.get("node_outputs", {})
        if isinstance(node_outputs, dict):
            for output in node_outputs.values():
                if not isinstance(output, dict):
                    if isinstance(output, list):
                        for item in output:
                            if isinstance(item, dict):
                                for key in ("user_query", "query", "message", "text"):
                                    value = item.get(key)
                                    if isinstance(value, str) and value.strip():
                                        return value
                    continue
                for key in ("user_query", "query", "message"):
                    value = output.get(key)
                    if isinstance(value, str) and value.strip():
                        return value
                parameters = output.get("parameters", {})
                if isinstance(parameters, dict):
                    for key in ("user_query", "query", "message"):
                        value = parameters.get(key)
                        if isinstance(value, str) and value.strip():
                            return value

        return None

    def _ensure_query_parameter(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure at least one canonical query field exists for downstream planning/retrieval.
        This protects against bad mappings like {"trigger-id": "trigger-id"} where no
        user message is actually passed to the agent.
        """
        if not isinstance(params, dict):
            return params

        for key in ("user_query", "query", "message"):
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                return params

        fallback_query = self._extract_fallback_query(context)
        if isinstance(fallback_query, str) and fallback_query.strip():
            params["user_query"] = fallback_query.strip()
            if self.debug:
                logger.info(
                    f"[{self.node_id}] 🔁 Injected fallback user_query into parameters for KB/tool planning"
                )
        return params


    # def prepare_static_parameters(self) -> Dict[str, Any]:
    #     """
    #     Prepare static parameters from workflow configuration.
    #     These are values that don't come from previous nodes (e.g., Google Sheet IDs).
        
    #     Returns:
    #         Dictionary of static parameters
            
    #     Example form_data:
    #         {
    #             "static_parameters": {
    #                 "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUaCOmMYx",
    #                 "sheet_name": "Sheet1",
    #                 "api_key": "your-api-key"
    #             }
    #         }
    #     """
    #     static_params = self.form_data.get("static_parameters", {})
        
    #     if self.debug:
    #         logger.info(f"[{self.node_id}] 📌 Static parameters: {json.dumps(static_params, default=str)}")
        
    #     return static_params
    
    def prepare_static_parameters(self) -> Dict[str, Any]:
        static_params = self.form_data.get("static_parameters", {})
        parsed = {}

        for key, value in static_params.items():
            parsed_value = self._safe_parse_json(value)
            parsed[key] = parsed_value

            if value is not parsed_value:
                logger.info(
                    f"[{self.node_id}] 🧩 Parsed JSON static param: {key}"
                )

        return parsed

    _TEMPLATE_REGEX = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")
    _HANDLEBARS_SECTION_PREFIXES = ("#", "/", "^", ">")
    _HANDLEBARS_SECTION_KEYWORDS = {"else", "#each", "/each", "#if", "/if", "#unless", "/unless"}

    def _is_handlebars_template(self, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        return any(token in value for token in ("{{#", "{{/", "{{^", "{{>", "{{else"))

    def _find_template_placeholders(self, value: Any) -> List[str]:
        if isinstance(value, dict):
            placeholders = []
            for v in value.values():
                placeholders.extend(self._find_template_placeholders(v))
            return placeholders
        if isinstance(value, list):
            placeholders = []
            for v in value:
                placeholders.extend(self._find_template_placeholders(v))
            return placeholders
        if isinstance(value, str):
            if self._is_handlebars_template(value):
                return []
            return [p for p in self._TEMPLATE_REGEX.findall(value)
                    if not p.startswith(self._HANDLEBARS_SECTION_PREFIXES)
                    and p not in self._HANDLEBARS_SECTION_KEYWORDS]
        return []

    def _resolve_template_string(self, value: str, context: Dict[str, Any]) -> str:
        if not isinstance(value, str):
            return value

        def replace(match):
            lookup_key = match.group(1).strip()
            if lookup_key.startswith(self._HANDLEBARS_SECTION_PREFIXES) or lookup_key in self._HANDLEBARS_SECTION_KEYWORDS:
                return match.group(0)

            resolved = resolve_field(context, lookup_key)
            if resolved is None:
                logger.warning(
                    f"[{self.node_id}] ⚠️ Unresolved template placeholder: {{ {{ {lookup_key} }} }}"
                )
                return match.group(0)
            return str(resolved)

        result = self._TEMPLATE_REGEX.sub(replace, value)
        unresolved = self._find_template_placeholders(result)
        if unresolved:
            logger.warning(
                f"[{self.node_id}] ⚠️ Unresolved template placeholders remain: {unresolved}"
            )
        return result

    def _resolve_placeholders(self, value: Any, context: Dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {k: self._resolve_placeholders(v, context) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_placeholders(v, context) for v in value]
        if isinstance(value, str):
            return self._resolve_template_string(value, context)
        return value

    def prepare_parameters(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare final parameters by merging:
        1. Static parameters (from workflow config) - OPTIONAL, defaults to {}
        2. Dynamic data (from previous nodes)
        3. 🆕 Wait node data (automatically detected and included)
        
        ✅ BACKWARD COMPATIBLE: If static_parameters is not provided,
           behavior is exactly the same as before (only dynamic data).
        
        Static parameters are added first, then dynamic data, then wait data.
        If there are conflicts, later sources take precedence.
        """
        if self.debug:
            logger.info(f"[{self.node_id}] 🧠 Preparing parameters...")
        
        # Start with static parameters (empty dict if not provided)
        params = self.prepare_static_parameters()
        
        # Add dynamic data (overwrites static if keys conflict)
        dynamic_data = self.prepare_data(context)
        params.update(dynamic_data)

        # 🆕 AUTO-INJECT WAIT NODE DATA
        # Detect upstream wait nodes in context and include their data
        wait_data = self._extract_wait_node_data(context)
        if wait_data:
            params.update(wait_data)
            if self.debug:
                logger.info(f"[{self.node_id}] 🔄 Auto-injected wait node data: {list(wait_data.keys())}")

        # ✅ RESOLVE ALL PLACEHOLDERS AFTER MERGING ALL DATA SOURCES
        params = self._resolve_placeholders(params, context)
        params = self._ensure_query_parameter(params, context)

        unresolved_params = self._find_template_placeholders(params)
        if unresolved_params:
            msg = (
                f"[{self.node_id}] ❌ Unresolved placeholders in parameters: {unresolved_params}. "
                "Provide values for these keys in the context or parameter mappings."
            )
            logger.error(msg)
            raise ValueError(msg)
        
        if self.debug:
            logger.info(f"[{self.node_id}] ✅ Final parameters summary:")
            static = self.form_data.get("static_parameters", {})
            for key, val in params.items():
                if key in wait_data:
                    source = "wait_node"
                elif key in dynamic_data:
                    source = "dynamic"
                elif key in static:
                    source = "static"
                else:
                    source = "unknown"
                val_type = "array" if isinstance(val, list) else type(val).__name__
                logger.info(f"[{self.node_id}]   - {key}: {source} ({val_type})")
        
        return params
        
        if self.debug:
            logger.info(f"[{self.node_id}] ✅ Final parameters summary:")
            static = self.form_data.get("static_parameters", {})
            for key, val in params.items():
                if key in wait_data:
                    source = "wait_node"
                elif key in dynamic_data:
                    source = "dynamic"
                elif key in static:
                    source = "static"
                else:
                    source = "unknown"
                val_type = "array" if isinstance(val, list) else type(val).__name__
                logger.info(f"[{self.node_id}]   - {key}: {source} ({val_type})")
        
        return params

    def _extract_wait_node_data(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        🆕 Extract upstream wait node data from context.
        
        Wait nodes store their output in context with keys like 'wait-18'.
        This method detects these keys and extracts key data fields that agents typically need.
        
        Returns flattened dict with wait node data, e.g.:
        {
            'customer_email': 'shivarajuy@bel.co.in',
            'customer_name': 'SHIVARAJU',
            'suppliers': [...],
            'finalized_summary': {...},
            'rfq_id': 'RFQ_523273'
        }
        """
        wait_data = {}
        
        # Find all wait node keys in context (e.g., 'wait-18', 'wait-1')
        wait_node_keys = [key for key in context.keys() if key.startswith('wait-') and isinstance(context.get(key), dict)]
        
        if not wait_node_keys:
            return wait_data
        
        if self.debug:
            logger.info(f"[{self.node_id}] 🔍 Found wait node keys in context: {wait_node_keys}")
        
        for wait_key in wait_node_keys:
            wait_output = context[wait_key]
            
            # Extract key fields that agents typically need
            # Customer data
            customer = wait_output.get('customer', {})
            if isinstance(customer, dict):
                if customer.get('email'):
                    wait_data['customer_email'] = customer['email']
                if customer.get('contact_name'):
                    wait_data['customer_name'] = customer['contact_name']
                if customer.get('company_name'):
                    wait_data['customer_company'] = customer['company_name']
            
            # RFQ data
            if wait_output.get('rfq_id'):
                wait_data['rfq_id'] = wait_output['rfq_id']
            elif wait_output.get('sys_rfq_id'):
                wait_data['sys_rfq_id'] = wait_output['sys_rfq_id']

            # Suppliers data
            suppliers = wait_output.get('suppliers', [])
            if suppliers:
                wait_data['suppliers'] = suppliers

            # Finalized summary
            finalized_summary = wait_output.get('finalized_summary', {})
            if finalized_summary:
                wait_data['finalized_summary'] = finalized_summary
            
            # Finalized data
            finalized = wait_output.get('finalized', {})
            if finalized:
                wait_data['finalized'] = finalized
            
            # Response data (contains all webhook data)
            response = wait_output.get('response', {})
            if response:
                wait_data['wait_response'] = response
            
            if self.debug:
                logger.info(f"[{self.node_id}] 📦 Extracted from {wait_key}: {list(wait_data.keys())}")
        
        return wait_data

    def prepare_config(self, running_tenant_id: int = None) -> Dict[str, Any]:
        """Override to add dynamic agent_type and llm_model from form_data."""
        override_kb_ids = self.form_data.get("knowledge_base_ids")
        if not isinstance(override_kb_ids, list):
            # Frontend-only KB policy for workflow execution.
            # Do not fall back to persisted agent KB mappings.
            override_kb_ids = []

        # Extract dynamic agent_type from form_data.
        # IMPORTANT: if UI does not send agent_type, keep it as None so
        # prepare_agent_input can fall back to DB-stored agent.agent_type.
        raw_agent_type = self.form_data.get("agent_type")
        if isinstance(raw_agent_type, str) and raw_agent_type.strip():
            agent_type = raw_agent_type.strip().lower()
        else:
            agent_type = None

        # Extract dynamic llm_model from form_data
        llm_model_override = self.form_data.get("llm_model")
        if isinstance(llm_model_override, str) and llm_model_override.strip():
            llm_model_override = llm_model_override.strip()
        else:
            llm_model_override = None

        full_input = prepare_agent_input(
            agent_id=self.agent_id,
            task="",
            use_temp_llm=self.use_temp_llm,
            use_temp_mcp_endpoint=True,
            override_tenant_id=running_tenant_id,
            override_kb_ids=override_kb_ids,
            agent_type=agent_type,  # 🆕 PASS DYNAMIC VALUE
            llm_model_override=llm_model_override,  # 🆕 PASS DYNAMIC MODEL
        )
        self.tenant_id = full_input.get("tenant_id")
        return full_input["config"]

