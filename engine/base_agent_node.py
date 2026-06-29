

import abc
import json
import requests
import os
from typing import Any, Dict, Optional
from enum import Enum
import logging 
from engine.base_node import BaseNode
from engine.registry import register_node
from engine.utils import prepare_agent_input
from engine.langgraph_urls import CREATE_AGENT_URL
from logging_config import setup_logging


def _normalize_memory_mode(memory_mode):
    """Collapse stored memory_mode strings into: 'structured' | 'session' | 'persistent' | None.

    None / '' / unknown -> None (no memory; matches legacy behavior where the
    per-agent toggle was never honored). Only an explicit selection enables memory.
    """
    value = (memory_mode or "").strip().lower()
    if value == "structured":
        return "structured"
    if value in ("session", "short_term", "conversation"):
        return "session"
    if value in ("persistent", "long_term"):
        return "persistent"
    return None


logger = setup_logging("BaseAgentNode", level="INFO")

def _mask_api_key(value: Optional[str]) -> str:
    if not value:
        return ""
    s = str(value)
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}...{s[-4:]}"



class AgentStatus(Enum):
    """Agent execution status"""
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"


class BaseAgentNode(BaseNode, abc.ABC):
    """
    Base class for agent nodes with separated task (prompt) and parameters (context).
    
    KEY ARCHITECTURE: Agents receive three components:
    - task: Natural language instructions
    - config: Agent configuration (tools, LLM, etc.)
    - parameters: Runtime variables for tool execution
    
    Example payload sent to agent:
    {
        "task": "Retrieve and summarize the email",
        "config": {...tools, llm...},
        "parameters": {
            "message_id": "199e7ba0b7230146",
            "thread_id": "thread_abc123"
        }
    }
    """
    
    AGENT_ID = None
    PARAM_LOG_TRUNCATE = 4000

    _ROUTER_LABEL_VALUES = {
        "tools",
        "tool",
        "action",
        "actions",
        "information",
        "info",
        "greeting",
        "kb",
        "knowledge",
    }

    def _is_router_label_text(self, value: str) -> bool:
        normalized = str(value or "").strip().lower()
        return normalized in self._ROUTER_LABEL_VALUES

    def _is_response_agent_compat(self) -> bool:
        node_type = str(self.node_data.get("type", "")).strip().lower()
        label = str(self.node_data.get("label", "")).strip().lower()
        return node_type == "responseagentnode" or label == "response agent"

    def _is_greeting_agent_compat(self) -> bool:
        node_type = str(self.node_data.get("type", "")).strip().lower()
        label = str(self.node_data.get("label", "")).strip().lower()
        return node_type == "greetingagentnode" or label == "greeting agent"

    def _extract_llm_response_from_node_output(self, node_payload: Any) -> Optional[str]:
        """Extract plain-text response from a node output payload."""
        if not isinstance(node_payload, dict):
            return None

        output = node_payload.get("output")
        if isinstance(output, str) and output.strip():
            candidate = output.strip()
            if not self._is_router_label_text(candidate):
                return candidate

        if isinstance(output, dict):
            llm_response = output.get("llm_response")
            if isinstance(llm_response, str) and llm_response.strip():
                candidate = llm_response.strip()
                if not self._is_router_label_text(candidate):
                    return candidate
            response = output.get("response")
            if isinstance(response, str) and response.strip():
                candidate = response.strip()
                if not self._is_router_label_text(candidate):
                    return candidate

        llm_response = node_payload.get("llm_response")
        if isinstance(llm_response, str) and llm_response.strip():
            candidate = llm_response.strip()
            if not self._is_router_label_text(candidate):
                return candidate

        return None

    def _extract_prioritized_upstream_response(self, context: Dict[str, Any]) -> Optional[str]:
        """
        ResponseAgent compatibility shortcut:
        pick the first available upstream agent reply in this priority:
        tool -> knowledge base -> greeting.
        """
        node_outputs = context.get("node_outputs", {})
        if not isinstance(node_outputs, dict):
            return None

        # Prefer explicit mapped fields from workflow data_mapping.
        mapped_values = [
            context.get("tool_response"),
            context.get("kb_response"),
            context.get("greeting_response"),
        ]
        for value in mapped_values:
            if isinstance(value, str) and value.strip() and not self._is_router_label_text(value):
                logger.info("[%s] Using mapped upstream response directly", self.node_id)
                return value.strip()
            if isinstance(value, dict):
                mapped_response = self._extract_llm_response_from_node_output({"output": value})
                if mapped_response:
                    logger.info("[%s] Using mapped upstream response directly (dict)", self.node_id)
                    return mapped_response

        priority_node_ids = ["genericagent-3", "genericagent-2", "greetingagent-7"]
        for node_id in priority_node_ids:
            node_payload = node_outputs.get(node_id)
            response = self._extract_llm_response_from_node_output(node_payload)
            if response:
                logger.info("[%s] Using upstream response directly from %s", self.node_id, node_id)
                return response

        return None
    
    def __init__(self, node_id, node_data):
        super().__init__(node_id, node_data)
        
        details = self.node_data.get("details", {}) if isinstance(self.node_data, dict) else {}
        self.agent_id = (
            self.form_data.get("agent_id")
            or details.get("agent_id")
            or self.AGENT_ID
        )

        requested_temp_llm = bool(self.form_data.get("use_temp_llm", False))
        self.use_temp_llm = False
        self.runtime_temp_agent_mode = False

        if not self.agent_id:
            if self.form_data.get("task") or self._is_response_agent_compat() or self._is_greeting_agent_compat():
                # Compatibility fallback for nodes like ResponseAgentNode where
                # workflows may omit persisted agent_id.
                self.runtime_temp_agent_mode = True
                self.use_temp_llm = True
                if not self.form_data.get("task") and self._is_response_agent_compat():
                    self.form_data["task"] = (
                        "Create a concise final reply for the user using available context. "
                        "Prioritize tool_response, then kb_response, then greeting_response. "
                        "If none exist, answer using user_query/message."
                    )
                if not self.form_data.get("task") and self._is_greeting_agent_compat():
                    self.form_data["task"] = (
                        "You are a greeting agent. Reply warmly and briefly to greetings "
                        "like hi/hello/hey. Keep it to one short line."
                    )
                logger.warning(
                    "[%s] Missing agent_id; auto-running in temporary LLM mode",
                    node_id,
                )
            else:
                raise ValueError(
                    f"Agent node {node_id} requires 'agent_id' in formData or class AGENT_ID"
                )
        elif requested_temp_llm:
            # Preserve existing behavior for persisted agents.
            logger.warning(
                "[%s] Ignoring use_temp_llm=true; forcing persisted LLM mapping",
                node_id,
            )

        self.timeout = self.form_data.get("timeout", 300)
        self.retry_attempts = self.form_data.get("retry_attempts", 1)
        self.create_agent_url = CREATE_AGENT_URL
        
        logger.info(
            f"Initialized {self.__class__.__name__} with agent_id={self.agent_id}"
        )
    
    @abc.abstractmethod
    def prepare_task(self, context: Dict[str, Any]) -> str:
        """
        Prepare the task/prompt (natural language instructions).
        
        Returns:
            Task string for the agent (e.g., "Retrieve and summarize the email")
        """
        pass
    
    def prepare_parameters(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare parameters for the agent's tool execution.
        
        Override this to extract specific fields from workflow context.
        
        Args:
            context: Full workflow context
            
        Returns:
            Dictionary of parameters for tool execution
            
        Example:
            {
                "message_id": "199e7ba0b7230146",
                "thread_id": "thread_abc123",
                "sender": "buyer@company.com"
            }
        """
        # Default: Pass flattened context
        return self._flatten_context(context)
    

    def prepare_config(self, running_tenant_id: int = None) -> Dict[str, Any]:
        """Fetch agent configuration from database.
        
        Args:
            running_tenant_id: The tenant currently executing the workflow.
                               Passed as override so prebuilt/cloned agents
                               pick up the running tenant's OAuth tools instead
                               of the original agent owner's tools.
        """
        if self.runtime_temp_agent_mode:
            self.tenant_id = running_tenant_id
            return {
                "name": f"runtime_{self.node_id}",
                "description": "Runtime temporary agent configuration",
                "llm_provider": "openai",
                "llm_model": "gpt-4o",
                "llm_api_key": os.getenv("OPENAI_API_KEY", ""),
                "instructions": self.form_data.get("task", ""),
                "tools": {},
                "examples": [],
            }

        override_kb_ids = self.form_data.get("knowledge_base_ids")
        if not isinstance(override_kb_ids, list) or not override_kb_ids:
            override_kb_ids = None

        full_input = prepare_agent_input(
            agent_id=self.agent_id,
            task="",
            use_temp_llm=self.use_temp_llm,
            use_temp_mcp_endpoint=True,
            override_tenant_id=running_tenant_id,
            override_kb_ids=override_kb_ids,
            agent_type="none",  # Default, will be overridden in subclasses
            llm_model_override=None,  # Default, will be overridden in subclasses
        )
        self.tenant_id = full_input.get("tenant_id")  # ✅ store it for later use
        return full_input["config"]

    
    def post_process_result(self, raw_result: Dict[str, Any]) -> Any:
        """
        FIXED: Always extract a clean plain-text string from the LangGraph response.
        Priority order:
          1. Top-level string
          2. raw_result["result"]   (string)
          3. raw_result["output"]   (string)
          4. messages[-1].content   (AI message)
          5. tool_output_parameters last tool text
          6. Fall back to original raw_result
        """
        # Case 1: entire response is already a string
        if isinstance(raw_result, str):
            return raw_result.strip()

        # Case 2: "result" key — may be plain string OR LangGraph's
        #         {"llm_response": "...", "tool_result": ...} dict
        result_val = raw_result.get("result")
        if isinstance(result_val, str) and result_val.strip():
            return result_val.strip()

        # Case 2b: result is the {"llm_response":..., "tool_result":...} dict
        #          produced by AgentResponseHandler.build_success_response
        if isinstance(result_val, dict):
            inner = (
                result_val.get("llm_response")
                or result_val.get("response")
                or result_val.get("text")
                or result_val.get("output")
            )
            if isinstance(inner, str) and inner.strip():
                return inner.strip()

        # Case 3: "output" key holds a plain string
        output_val = raw_result.get("output")
        if isinstance(output_val, str) and output_val.strip():
            return output_val.strip()

        # Case 4: LangGraph messages format  {output: {messages: [...]}}
        if isinstance(output_val, dict):
            messages = output_val.get("messages", [])
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("type") == "ai":
                    content = msg.get("content", "")
                    if isinstance(content, str) and content.strip():
                        return content.strip()

            # Also check a top-level "response" inside output dict
            inner_response = output_val.get("response") or output_val.get("text")
            if isinstance(inner_response, str) and inner_response.strip():
                return inner_response.strip()

        # Case 5: tool_output_parameters — last tool's text
        tool_outputs = raw_result.get("tool_output_parameters", [])
        if tool_outputs and isinstance(tool_outputs, list):
            last_tool = tool_outputs[-1]
            if isinstance(last_tool, dict):
                text = (
                    (last_tool.get("structuredContent") or {}).get("text")
                    or last_tool.get("output")
                    or ""
                )
                if isinstance(text, str) and text.strip():
                    return text.strip()

        # Case 6: top-level "response" key
        top_response = raw_result.get("response")
        if isinstance(top_response, str) and top_response.strip():
            return top_response.strip()

        # Case 7: react/chat agent returns {"llm_response": "...", "tool_result": ...}
        llm_response = raw_result.get("llm_response")
        if isinstance(llm_response, str) and llm_response.strip():
            return llm_response.strip()

        # Fallback: return whatever we got
        return raw_result.get("result", raw_result)



    # def execute(self, context: Dict[str, Any],parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    #     """Execute the agent node - returns clean output without raw_result duplication."""
    #     try:
    #         logger.info(f"[{self.node_id}] Executing {self.__class__.__name__}")
            
    #         # Step 1: Prepare task (prompt)
    #         task = self.prepare_task(context)
    #         logger.debug(f"[{self.node_id}] Task: {task[:200]}...")
            
    #         # Step 2: Prepare parameters (runtime variables)
    #         parameters = parameters or self.prepare_parameters(context)
    #         logger.debug(f"[{self.node_id}] Parameters: {list(parameters.keys())}")
            
    #         # Step 3: Fetch config
    #         config = self.prepare_config()
            
    #         # Step 4: Call agent API with retry
    #         raw_result = self._execute_with_retry(task, config, parameters)
            
    #         # Step 5: Post-process
    #         output = self.post_process_result(raw_result)
            
    #         # ✅ Extract tool_output_parameters if available
    #         tool_output_params = raw_result.get("tool_output_parameters", [])
            
    #         logger.info(f"[{self.node_id}] Agent completed successfully")
            
    #         # ✅ Return ONLY output and tool parameters (no raw_result duplication)
    #         return {
    #             "status": AgentStatus.COMPLETED.value,
    #             "output": output,  # The actual agent response/data
    #             "tool_output_parameters": tool_output_params,  # Tool execution details
    #             "error": None
    #         }
            
    #     except Exception as e:
    #         logger.error(f"[{self.node_id}] Agent failed: {str(e)}", exc_info=True)
            
    #         return {
    #             "status": AgentStatus.FAILED.value,
    #             "output": None,
    #             "tool_output_parameters": [],
    #             "error": str(e)
    #         }
    
    
    #- with nro,laized output response -----------
    # def execute(
    #     self,
    #     context: Dict[str, Any],
    #     parameters: Optional[Dict[str, Any]] = None
    # ) -> Dict[str, Any]:
    #     try:
    #         logger.info(f"[{self.node_id}] Executing {self.__class__.__name__}")

    #         #  STEP 1: Prepare parameters FIRST
    #         parameters = parameters or self.prepare_parameters(context)
    #         logger.debug(f"[{self.node_id}] Parameters: {list(parameters.keys())}")

    #         #  STEP 2: Promote user_query into context (ONCE)
    #         if (
    #             "user_query" not in context
    #             and isinstance(parameters, dict)
    #             and parameters.get("user_query")
    #         ):
    #             context["user_query"] = parameters["user_query"]
    #             logger.info(
    #                 f"[{self.node_id}]  Promoted user_query into context"
    #             )

    #         #  STEP 3: Prepare task (NOW it can see user_query)
    #         task = self.prepare_task(context)
    #         logger.debug(f"[{self.node_id}] Task: {task[:200]}...")

    #         # Step 4: Fetch config
    #         config = self.prepare_config()

    #         # Step 5: Call agent API
    #         raw_result = self._execute_with_retry(task, config, parameters)

    #         # Step 6: Post-process
    #         normalized_output = self._normalize_agent_output(raw_result)

    #         return {
    #             "status": AgentStatus.COMPLETED.value,
    #             "output": normalized_output,   # ✅ same object for UI + context
    #             "error": None
    #         }


    #     except Exception as e:
    #         logger.error(f"[{self.node_id}] Agent failed: {str(e)}", exc_info=True)
    #         return {
    #             "status": AgentStatus.FAILED.value,
    #             "output": None,
    #             "tool_output_parameters": [],
    #             "error": str(e)
    #         }
    #------------------------------
    
    # ------------ Lasted code -----------------
    def execute(
        self,
        context: Dict[str, Any],
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        try:
            logger.info(f"[{self.node_id}] Executing {self.__class__.__name__}")

            if self._is_response_agent_compat():
                upstream_response = self._extract_prioritized_upstream_response(context)
                if upstream_response:
                    return {
                        "status": AgentStatus.COMPLETED.value,
                        "output": upstream_response,
                        "tool_output_parameters": [],
                        "error": None,
                    }

            #  STEP 1: Prepare parameters FIRST
            parameters = parameters or self.prepare_parameters(context)
            parameters = self._sanitize_query_fields(parameters)
            logger.debug(f"[{self.node_id}] Parameters: {list(parameters.keys())}")

            #  STEP 2: Promote user_query into context (ONCE)
            if (
                "user_query" not in context
                and isinstance(parameters, dict)
                and parameters.get("user_query")
            ):
                context["user_query"] = parameters["user_query"]
                logger.info(
                    f"[{self.node_id}]  Promoted user_query into context"
                )

            #  STEP 3: Prepare task (NOW it can see user_query)
            task = self.prepare_task(context)
            logger.debug(f"[{self.node_id}] Task: {task[:200]}...")

            # Step 4: Fetch config
            # Extract running tenant_id from context so prebuilt/cloned agents
            # load the correct tenant's OAuth tools (Gmail, HubSpot, etc.)
            running_tenant_id = context.get("tenant_id") or context.get("tenantId")
            if running_tenant_id:
                try:
                    running_tenant_id = int(running_tenant_id)
                except (ValueError, TypeError):
                    running_tenant_id = None
            config = self.prepare_config(running_tenant_id=running_tenant_id)

            # Step 4b: Resolve memory selection and load prior turns for this agent.
            memory_mode, mem_tenant_id, mem_agent_id, mem_run_id, mem_conv_key = (
                self._resolve_memory_context(context, config, parameters)
            )
            history = self._load_agent_memory(
                memory_mode, mem_tenant_id, mem_agent_id, mem_run_id, mem_conv_key
            )
            if history:
                logger.info(
                    "[%s] Loaded %d prior memory turn(s) | mode=%s | key=%s",
                    self.node_id, len(history), memory_mode, mem_conv_key,
                )

            # Step 5: Call agent API
            try:
                raw_result = self._execute_with_retry(task, config, parameters, history=history)
            except Exception as primary_error:
                if self._should_retry_with_slack_fallback(context, config, primary_error):
                    fallback_config = dict(config)
                    fallback_config["llm_provider"] = "anthropic"
                    fallback_config["llm_model"] = os.getenv(
                        "SLACK_FALLBACK_ANTHROPIC_MODEL",
                        "claude-haiku-4-5",
                    )
                    fallback_config["llm_api_key"] = os.getenv("ANTHROPIC_API_KEY", "")
                    logger.warning(
                        "[%s] Slack OpenAI quota failure detected; retrying once with Anthropic model=%s",
                        self.node_id,
                        fallback_config["llm_model"],
                    )
                    raw_result = self._execute_with_retry(task, fallback_config, parameters, history=history)
                else:
                    raise

            # Step 6: Post-process
            output = self.post_process_result(raw_result)
            tool_output_params = raw_result.get("tool_outputs", raw_result.get("tool_output_parameters", []))

            # Step 6b: Persist this turn so the agent can remember it next time.
            # Save ONLY the user message — not the full task (system prompt + user query).
            # The system prompt is static/same for every execution; storing it inflates
            # every memory row and corrupts history when loaded back as prior turns.
            user_message = self._extract_user_message(task, parameters, context)
            self._save_agent_memory(
                memory_mode, mem_tenant_id, mem_agent_id, mem_run_id, user_message, output, mem_conv_key
            )

            logger.info(f"[{self.node_id}] Agent completed successfully")

            return {
                "status": AgentStatus.COMPLETED.value,
                "output": output,
                "tool_output_parameters": tool_output_params,
                "parameters": parameters,
                "error": None
            }

        except Exception as e:
            logger.error(f"[{self.node_id}] Agent failed: {str(e)}", exc_info=True)
            return {
                "status": AgentStatus.FAILED.value,
                "output": None,
                "tool_output_parameters": [],
                "parameters": parameters,
                "error": str(e)
            }

    def _should_retry_with_slack_fallback(
        self,
        context: Dict[str, Any],
        config: Dict[str, Any],
        error: Exception,
    ) -> bool:
        # Production policy: OpenAI-only for this deployment.
        # Keep method for backward compatibility but disable provider switching.
        return False
            
    # ----------------------------------
    
    def _execute_with_retry(
        self,
        task: str,
        config: Dict[str, Any],
        parameters: Dict[str, Any],
        history: Optional[list] = None
    ) -> Dict[str, Any]:
        """Execute API call with retry logic."""
        last_exception = None
        quota_fallback_attempted = False
        logger.info(f"parametrs got in execute query reyr {parameters}")

        for attempt in range(self.retry_attempts):
            try:
                return self._call_agent_api(task, config, parameters, history=history)
                
            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.warning(
                    f"[{self.node_id}] Timeout on attempt {attempt + 1}/{self.retry_attempts}"
                )
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                response_text = ""
                if getattr(e, "response", None) is not None:
                    try:
                        response_text = e.response.text or ""
                    except Exception:
                        response_text = ""

                if (
                    not quota_fallback_attempted
                    and self._is_openai_quota_error(response_text)
                ):
                    fallback = self._build_quota_fallback_config(config)
                    if fallback:
                        quota_fallback_attempted = True
                        config = fallback
                        logger.warning(
                            f"[{self.node_id}] OpenAI quota exceeded; retrying with Anthropic fallback model."
                        )
                        continue

                logger.warning(
                    f"[{self.node_id}] Request failed: {e}"
                )
        
        raise Exception(
            f"Agent failed after {self.retry_attempts} attempts: {str(last_exception)}"
        )

    def _is_openai_quota_error(self, response_text: str) -> bool:
        text = (response_text or "").lower()
        return (
            "insufficient_quota" in text
            or "you exceeded your current quota" in text
            or "ratelimiterror" in text
            or "error code: 429" in text
        )

    def _build_quota_fallback_config(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Production policy: OpenAI-only for this deployment.
        return None

    def _compact_parameters(self, value: Any) -> Any:
        """
        Remove verbose duplicated text from mapped upstream payloads.
        Keeps structured tool data intact while dropping bulky narrative fields.
        """
        if isinstance(value, dict):
            has_tool_result = "tool_result" in value
            compacted = {}
            for k, v in value.items():
                # When tool_result exists, llm_response is usually redundant and very large.
                if has_tool_result and k == "llm_response":
                    continue
                compacted[k] = self._compact_parameters(v)
            return compacted
        if isinstance(value, list):
            return [self._compact_parameters(item) for item in value]
        return value

    def _dedupe_repeated_phrase(self, text: str) -> str:
        """
        Collapse repeated comma-separated copies of the same phrase.
        Example: "Hi, Hi, Hi, Hi" -> "Hi"
        """
        if not isinstance(text, str):
            return text
        cleaned = text.strip()
        if not cleaned:
            return cleaned

        parts = [p.strip() for p in cleaned.split(",") if p and p.strip()]
        if len(parts) <= 1:
            return cleaned

        first = parts[0]
        if first and all(p == first for p in parts):
            return first

        return cleaned

    def _sanitize_query_fields(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(parameters, dict):
            return parameters

        sanitized = dict(parameters)
        for key in ("user_query", "query", "message"):
            value = sanitized.get(key)
            if isinstance(value, str):
                sanitized[key] = self._dedupe_repeated_phrase(value)
        return sanitized

    def _safe_payload_for_log(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return a log-safe payload copy with secrets redacted and huge blobs truncated."""
        safe_payload = dict(payload)
        safe_config = dict(safe_payload.get("config") or {})
        if "llm_api_key" in safe_config:
            safe_config["llm_api_key"] = _mask_api_key(safe_config.get("llm_api_key"))
        safe_payload["config"] = safe_config

        try:
            params_json = json.dumps(safe_payload.get("parameters"), default=str)
        except Exception:
            params_json = "<unserializable>"
        if isinstance(params_json, str) and len(params_json) > self.PARAM_LOG_TRUNCATE:
            safe_payload["parameters"] = {
                "_truncated": True,
                "_note": f"parameters omitted from log; serialized size={len(params_json)} chars",
            }
        return safe_payload
    
    

    def _resolve_memory_context(self, context, config, parameters=None):
        """Resolve (memory_mode, tenant_id, agent_id, run_id, conversation_key).

        memory_mode comes from the workflow node's form_data selection
        (structured/session/persistent). None means no memory was selected.
        conversation_key scopes persistent memory to a specific sender/thread
        when the agent is invoked from a trigger node (WhatsApp, Slack, Gmail).
        """
        memory_mode = _normalize_memory_mode(
            self.form_data.get("memory_mode")
            or (config or {}).get("memory_mode")
        )
        run_id = None
        if isinstance(context, dict):
            run_id = context.get("execution_id") or context.get("run_id")
        try:
            agent_id = int(self.agent_id) if self.agent_id is not None else None
        except (ValueError, TypeError):
            agent_id = None
        try:
            tenant_id = int(self.tenant_id) if self.tenant_id is not None else None
        except (ValueError, TypeError):
            tenant_id = None
        conversation_key = self._extract_conversation_key(context, parameters or {})
        return memory_mode, tenant_id, agent_id, run_id, conversation_key

    def _extract_user_message(self, task: str, parameters: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Extract only the actual user message for memory storage.

        Priority:
          1. parameters.user_query / parameters.message  (injected by executor)
          2. context.user_query                           (promoted in execute() Step 2)
          3. Parse "User query:\\n<text>" suffix from task (prepare_task appends this)
          4. Full task as last resort (preserves old behaviour, avoids losing data)
        """
        # 1. Check parameters (top-level keys injected by workflow executor)
        if isinstance(parameters, dict):
            msg = (
                parameters.get("user_query")
                or parameters.get("message")
                or parameters.get("text")
            )
            if msg and isinstance(msg, str) and msg.strip():
                return msg.strip()

        # 2. Check context
        if isinstance(context, dict):
            msg = context.get("user_query") or context.get("message")
            if msg and isinstance(msg, str) and msg.strip():
                return msg.strip()

        # 3. Extract from task string — prepare_task appends "\n\nUser query:\n<text>"
        if isinstance(task, str) and "User query:" in task:
            parts = task.split("User query:", 1)
            msg = parts[1].strip()
            if msg:
                return msg

        # 4. Fallback — store full task so memory is never silently empty
        return task or ""

    def _extract_conversation_key(self, context: Dict[str, Any], parameters: Dict[str, Any]) -> Optional[str]:
        """Derive a per-sender key for persistent memory partitioning.

        Checks parameters first (when the workflow explicitly maps sender fields
        to agent inputs), then falls back to scanning node_outputs for the raw
        trigger event so workflows that only wire up 'message' still work.

        Returns a namespaced string:
            WhatsApp → "wa:<phone>"
            Slack    → "slack:<user_id>:<channel_id>"
            Gmail    → "gmail:<email>"
        or None when no trigger context is present.
        """
        # 1. Parameters wired directly (explicit mapping in workflow)
        if isinstance(parameters, dict):
            phone = str(parameters.get("phone") or parameters.get("from") or "").strip()
            if phone:
                return f"wa:{phone}"
            user = str(parameters.get("user") or parameters.get("user_id") or "").strip()
            if user:
                channel = str(parameters.get("channel") or parameters.get("channel_id") or "").strip()
                return f"slack:{user}:{channel}" if channel else f"slack:{user}"

        # 2. Scan node_outputs for raw trigger event (works even when only
        #    'message' is wired to the agent — covers the common failure case)
        node_outputs = context.get("node_outputs", {}) if isinstance(context, dict) else {}
        for _, output in node_outputs.items():
            event = output[0] if isinstance(output, list) and output else output
            if not isinstance(event, dict):
                continue
            source = str(event.get("source") or event.get("trigger_type") or "").lower()

            if source == "whatsapp":
                meta = event.get("metadata") or {}
                phone = str(
                    event.get("phone")
                    or meta.get("from_phone")
                    or meta.get("from")
                    or ""
                ).strip()
                if phone:
                    return f"wa:{phone}"

            elif source == "slack":
                meta = event.get("metadata") or {}
                user = str(event.get("user") or meta.get("user") or "").strip()
                if user:
                    channel = str(event.get("channel") or meta.get("channel") or "").strip()
                    return f"slack:{user}:{channel}" if channel else f"slack:{user}"

            elif source in ("gmail", "email"):
                meta = event.get("metadata") or {}
                sender = str(meta.get("from") or event.get("from") or "").strip()
                if sender:
                    return f"gmail:{sender}"

        return None

    def _load_agent_memory(self, memory_mode, tenant_id, agent_id, run_id, conversation_key=None, limit=20):
        """Load prior turns for this agent from tbl_conversations.

        session    -> only turns from this workflow run (session_id='run:<run_id>')
        persistent -> turns for (tenant_id, agent_id, conversation_key), across runs.
                      conversation_key scopes memory to a specific sender/thread when
                      invoked from a trigger node; NULL key = shared pool (legacy).
        structured / None -> no memory
        """
        if memory_mode in (None, "structured") or tenant_id is None or agent_id is None:
            return []
        try:
            from app.database.DatabaseOperationPostgreSQL import db_session
            from app.models import Conversation
            session = next(db_session())
            try:
                query = session.query(Conversation).filter_by(
                    tenant_id=tenant_id, agent_id=agent_id
                )
                if memory_mode == "session":
                    query = query.filter_by(session_id=f"run:{run_id}", memory_type="session")
                else:
                    query = query.filter_by(memory_type="persistent")
                    if conversation_key:
                        query = query.filter_by(conversation_key=conversation_key)
                # Fetch most-recent N turns (desc), then reverse so history is oldest→newest
                rows = query.order_by(Conversation.created_at.desc()).limit(limit).all()
                rows.reverse()
                return [{"query": r.user_input, "response": r.response} for r in rows]
            finally:
                session.close()
        except Exception as e:
            logger.warning("[%s] Failed to load agent memory: %s", self.node_id, e)
            return []

    def _save_agent_memory(self, memory_mode, tenant_id, agent_id, run_id, user_input, response, conversation_key=None):
        """Persist one received/generated turn. No-op for structured/None."""
        if memory_mode in (None, "structured") or tenant_id is None or agent_id is None:
            return
        if not user_input:
            return
        try:
            from app.database.DatabaseOperationPostgreSQL import db_session
            from app.models import Conversation
            session = next(db_session())
            try:
                session.add(Conversation(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    memory_type=memory_mode,
                    session_id=f"run:{run_id}" if memory_mode == "session" else None,
                    conversation_key=conversation_key if memory_mode == "persistent" else None,
                    user_input=str(user_input),
                    response=str(response) if response is not None else "",
                ))
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as e:
            logger.warning("[%s] Failed to save agent memory: %s", self.node_id, e)

    def _call_agent_api(
        self,
        task: str,
        config: Dict[str, Any],
        parameters: Dict[str, Any],
        history: Optional[list] = None
    ) -> Dict[str, Any]:
        """Make API call to CREATE_AGENT_URL."""
        compacted_parameters = self._compact_parameters(parameters)
        if compacted_parameters != parameters:
            logger.info("[%s] Compacted mapped parameters before create_agent call", self.node_id)

        # Ensure tenant_id is always a string
        tenant_id = str(getattr(self, "tenant_id", "")) if getattr(self, "tenant_id", None) is not None else None
    
        # Static behavioral fields belong INSIDE config
        static_fields = {
            "remember_now": True,
            "remember_long": False,
            "sound_natural": False,
            "think_back": False,
            "stay_on_topic": True,
            "explain_clearly": False,
        }
    
        # Merge static fields into config
        merged_config = {**static_fields, **config}

        # Last-mile model guard for OpenAI chat path:
        # realtime model IDs are not supported by this create_agent flow.
        provider = str(merged_config.get("llm_provider", "")).strip().lower()
        model = str(merged_config.get("llm_model", "")).strip().lower()
        if provider == "openai" and "realtime" in model:
            merged_config["llm_model"] = "gpt-4o"
            logger.warning(
                "[%s] Normalized unsupported OpenAI model '%s' -> 'gpt-4o' before create_agent call",
                self.node_id,
                config.get("llm_model"),
            )
    
        payload = {
            "tenant_id": tenant_id,
            "task": task,
            "config": merged_config,
            "parameters": compacted_parameters,
        }
        if history:
            payload["history"] = history
    
        # Log a safe payload: redact keys and avoid dumping huge parameter objects.
        logger.info(
            "[%s] 📨 Payload to CREATE_AGENT_URL:\n%s",
            self.node_id,
            json.dumps(self._safe_payload_for_log(payload), indent=2, default=str),
        )
    
        channel = "unknown"
        if isinstance(compacted_parameters, dict):
            source = str(compacted_parameters.get("source") or compacted_parameters.get("trigger_type") or "").lower()
            if "slack" in source:
                channel = "slack"
            elif "whatsapp" in source:
                channel = "whatsapp"
            elif compacted_parameters.get("channel") or compacted_parameters.get("channel_id"):
                channel = "slack"
            elif compacted_parameters.get("phone") or compacted_parameters.get("from"):
                channel = "whatsapp"

        logger.info(
            "[%s] create_agent call | channel=%s tenant_id=%s provider=%s model=%s key=%s",
            self.node_id,
            channel,
            tenant_id,
            merged_config.get("llm_provider"),
            merged_config.get("llm_model"),
            _mask_api_key(merged_config.get("llm_api_key")),
        )

        response = requests.post(
            self.create_agent_url,
            json=payload,
            timeout=self.timeout,
            headers={"Content-Type": "application/json"}
        )

        logger.info("[%s] create_agent response status=%s", self.node_id, response.status_code)
        response.raise_for_status()
        return response.json()

    def _resolve_field(self, context: Dict[str, Any], path: str) -> Any:
        """
        Resolve field using NODE IDs first, then fallback to labels.
        Supports:
          - node_outputs.pdfextractor-12.extracted_text
          - PDF Extractor Node.extracted_text          (legacy fallback)
          - gmailtrigger-1.metadata.message_id
        """
        if not path or not path.strip():
            return None
    
        try:
            # CASE 1: Direct access via node_outputs + node ID (RECOMMENDED)
            if path.startswith("node_outputs."):
                remaining = path[len("node_outputs."):]
                if "." in remaining:
                    node_key, subpath = remaining.split(".", 1)
                    node_output = context.get("node_outputs", {}).get(node_key)
                    if node_output is not None:
                        return self._deep_get(node_output, subpath)
                else:
                    return context.get("node_outputs", {}).get(remaining)
    
            # CASE 2: Legacy label-based access (e.g., "PDF Extractor Node.extracted_text")
            parts = path.split(".")
            value = context
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                elif isinstance(value, list) and part.isdigit():
                    value = value[int(part)]
                else:
                    return None
            return value
    
        except Exception as e:
            logger.warning(f"[{self.node_id}] Failed to resolve path '{path}': {e}")
            return None
    
    def _deep_get(self, obj: Any, path: str) -> Any:
        """Safely traverse nested dict/list using dot notation"""
        if not path:
            return obj
        keys = path.split(".")
        for key in keys:
            if isinstance(obj, dict):
                obj = obj.get(key)
            elif isinstance(obj, list) and key.isdigit():
                idx = int(key)
                obj = obj[idx] if 0 <= idx < len(obj) else None
            else:
                return None
            if obj is None:
                return None
        return obj
  
    def _flatten_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flatten context for easy access.
        
        Converts:
            {"gmail-1": {"output": {"subject": "..."}, ...}}
        To:
            {"gmail-1": {"subject": "..."}}
        """
        flat = {}
        logger.info(f"recieved context{context}")
        for node_id, output in context.items():
            if isinstance(output, dict) and "output" in output:
                flat[node_id] = output["output"]
            else:
                flat[node_id] = output
        return flat
    
    def _normalize_agent_output(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize LangGraph agent output so:
        - UI and workflow context store IDENTICAL data
        - Works for ReAct, Chat, Tool agents
        """

        tool_outputs = raw_result.get("tool_output_parameters", [])

        # 🔥 CASE 1: ReAct agents return FINAL ANSWER AS STRING
        if isinstance(raw_result.get("output"), str):
            return {
                "response": raw_result["output"],
                "tool_output_parameters": tool_outputs,
                "messages": None,
                "parameters": raw_result.get("parameters")
            }

        output = raw_result.get("output") or {}
        response_text = None

        # 🔥 CASE 2: Tool agent
        if tool_outputs:
            last_tool = tool_outputs[-1]
            response_text = (
                last_tool.get("structuredContent", {}).get("text")
                or last_tool.get("output")
            )

        # 🔥 CASE 3: Chat / KB messages
        if response_text is None:
            messages = output.get("messages", [])
            for msg in reversed(messages):
                if msg.get("type") == "ai" and msg.get("content"):
                    response_text = msg["content"]
                    break

        # 🔥 CASE 4: Explicit response field
        if response_text is None:
            response_text = output.get("response")

        return {
            "response": response_text,
            "tool_output_parameters": tool_outputs,
            "messages": output.get("messages"),
            "parameters": output.get("parameters")
        }
