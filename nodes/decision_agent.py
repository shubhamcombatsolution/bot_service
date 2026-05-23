
import json
import re
import requests
from typing import Any, Dict
from sqlalchemy.orm import joinedload
import os
from engine.base_node import BaseNode
from engine.registry import register_node
from engine.langgraph_urls import DECISION_AGENT_URL
from app.database.DatabaseOperationPostgreSQL import db_session
from app.models.llm import LLM
from app.services.encryption_utils import decrypt_value
from nodes.utils.resolver import resolve_field
from logging_config import setup_logging

logger = setup_logging("DecisionRouterNode", level="DEBUG")


@register_node("DecisionAgentNode")
@register_node("DecisionRouterNode")
class DecisionRouterNode(BaseNode):
    """
    Decision Router Node (NO agent_id required)

    ✔ Fetches tenant's LLM from DB OR temp LLM based on flag
    ✔ Calls decision_agent endpoint
    ✔ Uses dynamic parameter mapping
    ✔ Routes execution like switch node
    """

    def __init__(self, node_id: str, node_data: Dict[str, Any], debug: bool = True):
        super().__init__(node_id, node_data)

        self.node_id = node_id
        self.debug = debug
        self.data = node_data or {}

        self.form_data = self.data.get("formData", {}) or {}

        # Routing rules
        self.conditions = self.form_data.get("conditions", [])
        self.default_target = self.form_data.get("default_target")
        

        # 🏷 NEW FLAG
        self.use_temp_llm = self.form_data.get("use_temp_llm", False)

        logger.info(
            f"[{self.node_id}] DecisionRouter initialized with {len(self.conditions)} conditions | TEMP_LLM={self.use_temp_llm}"
        )

    # ------------------------------- EXECUTE -------------------------------

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Accept tenant_id from context OR node input OR workflow metadata
            tenant_id = self._get_tenant_id(context)

            if not tenant_id:
                logger.warning(f"[{self.node_id}] ⚠ No tenant_id found — using fallback workflow tenant id")
                tenant_id = self.data.get("tenant_id") or  self.form_data.get("tenant_id") or None

            if not tenant_id:
                raise ValueError("Missing tenant_id in workflow context")


            # Prepare payload
            task = self.prepare_task(context)
            parameters = self.prepare_parameters(context)
            payload = self._prepare_llm_payload(tenant_id, task, parameters)

            if self.debug:
                logger.info(f"[{self.node_id}] 📤 Payload:\n{json.dumps(payload, indent=2)}")

            # Call decision agent endpoint
            resp = requests.post(DECISION_AGENT_URL, json=payload, timeout=60)
            resp.raise_for_status()

            result = resp.json()
            if isinstance(result, dict):
                result.setdefault("decision_data", {})


            if self.debug:
                logger.info(f"[{self.node_id}] 📥 Decision Response:\n{json.dumps(result, indent=2)}")

            # Decision extraction + routing
            decision = self._extract_decision(result)
            branch = self._match_branch(decision,context)
            branch_node_id = self._resolve_branch_node_id(branch, context)

            return {
                "status": "success",
                "decision": decision,
                "branch": branch,
                "branch_node_id": branch_node_id,
                "resolved_branch_id": branch_node_id,
                "parameters": parameters,
                "task_used": task,
                "response": result
            }

        except Exception as e:
            logger.error(f"[{self.node_id}] ❌ Execution failed: {e}", exc_info=True)
            return {"status": "failed", "error": str(e), "branch": self.default_target}

    # ---------------------------- LLM SELECTION ----------------------------

    def _prepare_llm_payload(self, tenant_id, task, parameters) -> Dict[str, Any]:
        """Unified safe LLM selection: DB → fallback temp model."""
        llm_provider = None
        llm_model = None
        llm_key = None

        # Valid OpenAI chat models (chat completion endpoint)
        VALID_OPENAI_MODELS = {
            "gpt-4o", "gpt-4-turbo", "gpt-4-turbo-preview", "gpt-4", 
            "gpt-3.5-turbo", "gpt-3.5-turbo-16k"
        }

        # 1️⃣ Try DB retrieval if temp flag disabled
        if not self.use_temp_llm:
            session = next(db_session())
            llm = session.query(LLM).options(
                joinedload(LLM.base_llm),
                joinedload(LLM.provider),
                joinedload(LLM.model_name)
            ).filter(
                LLM.tenant_id == tenant_id,
                LLM.del_flg == False
            ).order_by(LLM.llm_id.desc()).first()

            session.close()

            if llm:
                base_llm = getattr(llm, "base_llm", None)
                provider_rel = getattr(llm, "provider", None)
                model_rel = getattr(llm, "model_name", None)

                llm_provider = (
                    getattr(base_llm, "base_provider", None)
                    or getattr(provider_rel, "base_provider", None)
                )
                llm_model = (
                    getattr(base_llm, "base_model_name", None)
                    or getattr(model_rel, "base_model_name", None)
                )

                if not llm_provider or not llm_model:
                    raise ValueError(
                        "Tenant LLM is missing a valid provider or model configuration"
                    )

                # ✅ VALIDATE MODEL: Ensure model is supported by OpenAI chat endpoint
                if llm_provider.lower() == "openai" and llm_model not in VALID_OPENAI_MODELS:
                    logger.warning(
                        f"[{self.node_id}] ⚠ Invalid OpenAI model '{llm_model}' (not in chat completions). "
                        f"Valid models: {', '.join(sorted(VALID_OPENAI_MODELS))}. "
                        f"Falling back to gpt-4o."
                    )
                    llm_model = "gpt-4o"

                try:
                    llm_key = decrypt_value(llm.llm_secret_key)
                except Exception as decrypt_err:
                    logger.warning(
                        f"[{self.node_id}] ⚠ Failed to decrypt tenant LLM key: {decrypt_err}"
                    )
                    llm_key = ""

                logger.info(f"[{self.node_id}] 🧠 Using Tenant LLM: {llm_provider} | {llm_model}")
            else:
                logger.warning(
                    f"[{self.node_id}] ⚠ No LLM stored for tenant {tenant_id}, falling back to temporary model..."
                )

        # 2️⃣ TEMP FALLBACK (or default)
        if not llm_provider:
            llm_provider = "openai"
            llm_model = "gpt-4o"
            llm_key = os.getenv("OPENAI_API_KEY", "")

            logger.info(f"[{self.node_id}] 🔧 Using TEMP LLM: {llm_provider} | {llm_model}")

        return {
            "prompt": task,
            "parameters": parameters or {},
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_api_key": llm_key
        }

    def _get_tenant_id(self, context):
        # 1) Direct workflow-level metadata
        if hasattr(context, "tenant_id"):
            return context.tenant_id

        # 2) Stored as metadata in workflow object
        if hasattr(context, "workflow") and isinstance(context.workflow, dict):
            if "tenant_id" in context.workflow:
                return context.workflow["tenant_id"]

        # 3) Stored in node_outputs
        if hasattr(context, "node_outputs") and isinstance(context.node_outputs, dict):
            if "tenant_id" in context.node_outputs:
                return context.node_outputs["tenant_id"]

        # 4) As dict (fallback mode)
        if isinstance(context, dict):
            if "tenant_id" in context:
                return context["tenant_id"]
            if "workflow" in context and "tenant_id" in context["workflow"]:
                return context["workflow"]["tenant_id"]

        return None


    # ----------------------- TASK TEMPLATE HANDLING -----------------------

    def prepare_task(self, context: Dict[str, Any]):
        task_template = self.form_data.get("task", "")
        for ph in re.findall(r"\{([^}]+)\}", task_template):
            task_template = task_template.replace(f"{{{ph}}}", str(resolve_field(context, ph) or ""))
        return task_template

   
    
    def prepare_parameters(self, context: Dict[str, Any]) -> Dict[str, Any]:
        mapping = self.form_data.get("data_mapping")

        # 🔑 CASE 1: Explicit mapping → extract selected fields
        if mapping:
            params = {}
            for key, path in mapping.items():
                try:
                    value = resolve_field(context, path)
                    if value is None:
                        value = self._fallback_parameter_value(context, key, path)
                    params[key] = value
                except:
                    params[key] = self._fallback_parameter_value(context, key, path)
            return params

        # 🔑 CASE 2: No mapping → passthrough runtime parameters
        if isinstance(context, dict):
            return context.get("parameters", {})

        return {}

    def _fallback_parameter_value(self, context: Dict[str, Any], key: str, path: Any):
        candidate_keys = []

        for candidate in (key, path):
            if isinstance(candidate, str) and candidate:
                candidate_keys.append(candidate.split(".")[-1])
                candidate_keys.append(candidate)

        candidate_keys.extend(["user_query", "query", "message"])

        seen = set()
        deduped_keys = []
        for candidate in candidate_keys:
            if candidate not in seen:
                seen.add(candidate)
                deduped_keys.append(candidate)

        if isinstance(context, dict):
            for candidate in deduped_keys:
                if candidate in context and context[candidate] not in (None, ""):
                    return context[candidate]

            parameters = context.get("parameters", {})
            if isinstance(parameters, dict):
                for candidate in deduped_keys:
                    if candidate in parameters and parameters[candidate] not in (None, ""):
                        return parameters[candidate]

            node_outputs = context.get("node_outputs", {})
            if isinstance(node_outputs, dict):
                for output in node_outputs.values():
                    if not isinstance(output, dict):
                        continue
                    for candidate in deduped_keys:
                        value = output.get(candidate)
                        if value not in (None, ""):
                            return value

        return None

    # ----------------------------- ROUTING ------------------------------

    def _extract_decision(self, response):
        def _extract_from_text(raw_text: str) -> str:
            text = str(raw_text or "").strip().strip("`\"'")
            if not text:
                return ""

            kv_match = re.search(
                r'(?im)^[\s\"\']*decision[\s\"\']*[:=]\s*[\"\']?([^\"\'\n\r{}]+)',
                text,
            )
            if kv_match:
                return kv_match.group(1).strip().strip("`\"'").upper()

            first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
            return first_line.strip("`\"'").upper()

        try:
            if isinstance(response, dict):
                decision_block = response.get("decision")

                # Case 1: Already parsed dict
                if isinstance(decision_block, dict):
                    lowered = {str(k).lower(): v for k, v in decision_block.items()}
                    return _extract_from_text(lowered.get("decision", ""))

                # Case 2: Stringified dict - try parsing
                if isinstance(decision_block, str):
                    cleaned = decision_block.strip()

                    fenced_match = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", cleaned, re.IGNORECASE)
                    if fenced_match:
                        cleaned = fenced_match.group(1).strip()

                    cleaned = cleaned.replace("'", "\"")
                    try:
                        parsed = json.loads(cleaned)
                        if isinstance(parsed, dict):
                            lowered = {str(k).lower(): v for k, v in parsed.items()}
                            return _extract_from_text(lowered.get("decision", ""))
                        if isinstance(parsed, str):
                            return _extract_from_text(parsed)
                    except:
                        return _extract_from_text(cleaned)

                return _extract_from_text(decision_block)

        except:
            return "UNKNOWN"

    def _match_branch(self, decision: str, context: Dict[str, Any]) -> str:
        decision = decision.strip().upper()

        if decision == "ACTION" and self._looks_informational_query(context):
            logger.info(
                f"[{self.node_id}] 🔁 Remapping ACTION -> INFORMATION based on query intent heuristic"
            )
            decision = "INFORMATION"

        for rule in self.conditions:
            if rule.get("value", "").upper() == decision:
                target = rule.get("target")

                # If target is dict {"node_id": "..."} support it too
                if isinstance(target, dict):
                    return target.get("node_id")

                return target  # <-- DO NOT RESOLVE HERE

        # Backward-compatible fallback for workflows that were saved without
        # explicit conditions. Use the router's direct children in edge order
        # so GREETING / INFORMATION / ACTION can still flow through the
        # intended branch agents instead of a downstream response node.
        fallback_branch = self._fallback_branch_from_workflow(decision, context)
        if fallback_branch:
            return fallback_branch

        return self.default_target

    def _looks_informational_query(self, context: Dict[str, Any]) -> bool:
        text_candidates = []

        if isinstance(context, dict):
            for key in ("user_query", "message", "text", "query"):
                value = context.get(key)
                if isinstance(value, str) and value.strip():
                    text_candidates.append(value.strip())

            parameters = context.get("parameters", {})
            if isinstance(parameters, dict):
                for key in ("user_query", "message", "text", "query"):
                    value = parameters.get(key)
                    if isinstance(value, str) and value.strip():
                        text_candidates.append(value.strip())

        if not text_candidates:
            return False

        text = text_candidates[0].lower()
        info_patterns = (
            r"^tell me\b",
            r"\ball about\b",
            r"^what\b",
            r"^who\b",
            r"^when\b",
            r"^where\b",
            r"^why\b",
            r"^how\b",
            r"^explain\b",
            r"^describe\b",
            r"^give me\b.*\b(info|information|details|overview)\b",
            r"\babout\b",
        )

        return any(re.search(pattern, text) for pattern in info_patterns)

    def _fallback_branch_from_workflow(self, decision: str, context: Dict[str, Any]) -> str:
        decision_order = ["GREETING", "INFORMATION", "ACTION"]
        if decision not in decision_order:
            return None

        workflow = {}
        if isinstance(context, dict):
            workflow = context.get("workflow", {}) or {}
            if not workflow:
                workflow = (context.get("inputData", {}) or {}).get("workflow", {}) or {}
            if not workflow:
                workflow = (context.get("workflow_graph", {}) or {})
        elif hasattr(context, "workflow") and isinstance(context.workflow, dict):
            workflow = context.workflow or {}

        edges = (
            workflow.get("edges", [])
            or workflow.get("workflow", {}).get("edges", [])
            or []
        )
        direct_children = []
        handle_mapped = {}

        def normalize_handle(value: Any) -> str:
            return (
                str(value or "")
                .strip()
                .lower()
                .replace("-", "")
                .replace("_", "")
                .replace(" ", "")
            )

        for edge in edges:
            if not isinstance(edge, dict):
                continue
            if edge.get("source") != self.node_id:
                continue

            source_handle = normalize_handle(edge.get("sourceHandle"))
            target = edge.get("target")

            if not target:
                continue

            if source_handle:
                if "action" in source_handle:
                    handle_mapped["ACTION"] = target
                elif "info" in source_handle:
                    handle_mapped["INFORMATION"] = target
                elif "greet" in source_handle:
                    handle_mapped["GREETING"] = target
                elif source_handle in {"response", "output", "dragoutput"}:
                    # UI wiring handles (e.g., "response") should not influence
                    # decision fallbacks for GREETING/INFORMATION/ACTION.
                    continue

            if target not in direct_children:
                direct_children.append(target)

        if decision in handle_mapped:
            return handle_mapped[decision]

        if not direct_children:
            return None

        # Heuristic fallback for older diagrams without explicit conditions:
        # first branch = INFORMATION, second = ACTION, GREETING falls back to first.
        if decision == "ACTION":
            if len(direct_children) >= 2:
                return direct_children[1]
            return direct_children[0]
        if decision in {"INFORMATION", "GREETING"}:
            return direct_children[0]

        index = decision_order.index(decision)
        return direct_children[index] if index < len(direct_children) else direct_children[0]

    def _resolve_branch_node_id(self, branch: Any, context: Dict[str, Any]) -> Any:
        """Resolve saved branch labels to the actual workflow node id."""
        if not branch:
            return branch

        workflow_nodes = []

        def extend_nodes(value):
            if isinstance(value, list):
                workflow_nodes.extend([node for node in value if isinstance(node, dict)])

        if isinstance(context, dict):
            workflow = context.get("workflow", {}) or {}
            extend_nodes(workflow.get("nodes", []))
            extend_nodes((workflow.get("workflow", {}) or {}).get("nodes", []))
            extend_nodes((context.get("inputData", {}) or {}).get("workflow", {}).get("nodes", []))
            extend_nodes((context.get("inputData", {}) or {}).get("workflow", {}).get("workflow", {}).get("nodes", []))
        elif hasattr(context, "workflow") and isinstance(context.workflow, dict):
            extend_nodes(context.workflow.get("nodes", []))
            extend_nodes((context.workflow.get("workflow", {}) or {}).get("nodes", []))

        # Deduplicate while preserving order
        seen_ids = set()
        normalized_nodes = []
        for node in workflow_nodes:
            node_id = node.get("id")
            if node_id and node_id not in seen_ids:
                seen_ids.add(node_id)
                normalized_nodes.append(node)
        workflow_nodes = normalized_nodes

        def normalize(text):
            return (
                str(text or "")
                .lower()
                .replace(" ", "")
                .replace("_", "")
                .replace("-", "")
            )

        def tokenize(text):
            return [part for part in re.findall(r"[a-z0-9]+", str(text or "").lower()) if part]

        def resolve_one(value):
            if not value:
                return value
            value_str = str(value).strip()
            if any(node.get("id") == value_str for node in workflow_nodes):
                return value_str

            value_norm = normalize(value_str)
            value_tokens = set(tokenize(value_str))

            for node in workflow_nodes:
                data = node.get("data", {}) or {}
                fd = data.get("formData", {}) or {}
                candidates = [
                    fd.get("agent_name"),
                    fd.get("label"),
                    data.get("label"),
                    fd.get("type"),
                    fd.get("tool_name"),
                    node.get("id"),
                ]

                for candidate in candidates:
                    if not candidate:
                        continue
                    cand_norm = normalize(candidate)
                    cand_tokens = set(tokenize(candidate))

                    if cand_norm == value_norm:
                        return node["id"]
                    if cand_norm.startswith(value_norm) or value_norm.startswith(cand_norm):
                        return node["id"]
                    if cand_tokens and value_tokens:
                        if cand_tokens.issubset(value_tokens) or value_tokens.issubset(cand_tokens):
                            return node["id"]

            return value_str

        if isinstance(branch, list):
            return [resolve_one(item) for item in branch if item]

        return resolve_one(branch)

    
