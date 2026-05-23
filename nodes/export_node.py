import logging
from copy import deepcopy

import jwt
from engine.base_node import BaseNode
from engine.registry import register_node
import engine.export_strategies  # noqa: F401  # Load strategy modules and register decorators.
from engine.export_strategies.factory import ExportStrategyFactory
from nodes.whatsapp_node_helpers import (
    coerce_bool,
    infer_whatsapp_message_text,
    infer_whatsapp_recipient,
    resolve_form_data,
)
from nodes.slack_node_helpers import (
    infer_slack_channel,
    infer_slack_message_text,
    infer_slack_thread_ts,
    infer_slack_user,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@register_node("ExportNode")
class ExportNode(BaseNode):
    """
    A unified export node that supports multiple export types
    (e.g., Gmail, WhatsApp, Slack, etc.) using Strategy + Registry pattern.
    Supports nested field resolution for attachments.
    """

    def _resolve_field(self, context, path: str):
        """
        Fetch nested value from context like:
        'genericagent-10.tool_output_parameters.0.structuredContent.text'
        """
        try:
            parts = path.split(".")
            value = context
            for p in parts:
                if isinstance(value, dict):
                    value = value.get(p)
                elif isinstance(value, list) and p.isdigit():
                    value = value[int(p)]
                else:
                    logger.debug(f"[ExportNode] Path '{path}' not found at '{p}'")
                    return None
            return value
        except Exception as e:
            logger.warning(f"[ExportNode] Failed to resolve field '{path}': {e}")
            return None

    def _resolve_dynamic_form_data(self, form_data: dict, context: dict) -> dict:
        """
        Resolve dynamic placeholders/path references in form_data.
        Supports both scalar and nested field values.
        """
        try:
            return resolve_form_data(form_data, context)
        except Exception as e:
            logger.warning(f"[ExportNode] Failed to resolve dynamic form data: {e}")
            return form_data

    def execute(self, inputs: dict) -> dict:
        # 🔹 1. Extract and decode JWT
        jwt_token = inputs.get("jwt")
        if not jwt_token:
            raise ValueError("Missing JWT in inputs")

        try:
            decoded = jwt.decode(jwt_token, options={"verify_signature": False})
            tenant_id = decoded.get("tenant_id")
        except Exception as e:
            raise ValueError(f"Invalid JWT: {e}")

        if not tenant_id:
            raise ValueError("tenant_id not found in JWT claims")

        # 🔹 2. Load form data from node configuration
        form_data = deepcopy(self.form_data or {})
        if not form_data:
            raise ValueError("Missing form_data in ExportNode configuration")

        form_data = self._resolve_dynamic_form_data(form_data, inputs)

        # 🔹 3. Normalize export type
        export_type = form_data.get("type") or form_data.get("export_mode")
        if not export_type:
            raise ValueError("export_type is required (expected 'type' or 'export_mode')")

        export_type_normalized = str(export_type).strip().lower()

        # 🔹 4. Normalize recipient key if needed
        if "send_to" in form_data and "to" not in form_data:
            form_data["to"] = form_data.pop("send_to")

        # 🔹 4b. WhatsApp smart defaults: infer recipient and body from context when missing.
        if export_type_normalized == "whatsapp":
            if not str(form_data.get("to") or "").strip():
                inferred_to = infer_whatsapp_recipient(inputs)
                if inferred_to:
                    form_data["to"] = inferred_to

            if not str(form_data.get("body") or "").strip() and not str(form_data.get("template_name") or "").strip():
                inferred_body = infer_whatsapp_message_text(inputs)
                if inferred_body:
                    form_data["body"] = inferred_body

            form_data["wait_for_reply"] = coerce_bool(form_data.get("wait_for_reply"), default=False)

        # 🔹 4c. Slack smart defaults: infer channel and message from context when missing.
        if export_type_normalized == "slack":
            if not str(form_data.get("channel_id") or form_data.get("channel") or "").strip():
                inferred_channel = infer_slack_channel(inputs)
                if inferred_channel:
                    form_data["channel_id"] = inferred_channel

            if not str(form_data.get("text") or form_data.get("message") or form_data.get("body") or "").strip():
                inferred_text = infer_slack_message_text(inputs)
                if inferred_text:
                    form_data["text"] = inferred_text

            if not str(form_data.get("thread_ts") or "").strip():
                inferred_thread_ts = infer_slack_thread_ts(inputs)
                if inferred_thread_ts:
                    form_data["thread_ts"] = inferred_thread_ts

            if not str(form_data.get("expected_user") or form_data.get("user_id") or "").strip():
                inferred_user = infer_slack_user(inputs)
                if inferred_user:
                    form_data["expected_user"] = inferred_user

            form_data["wait_for_reply"] = coerce_bool(form_data.get("wait_for_reply"), default=False)

        # 🔹 5. Resolve attachment paths dynamically
        attachments = form_data.get("attachments", [])
        resolved_attachments = []

        if isinstance(attachments, list):
            for a in attachments:
                if isinstance(a, str) and "." in a:
                    resolved = self._resolve_field(inputs, a)
                    if resolved:
                        # Flatten nested lists if any
                        if isinstance(resolved, list):
                            resolved_attachments.extend(resolved)
                        else:
                            resolved_attachments.append(resolved)
                    else:
                        logger.warning(f"[ExportNode] Cannot resolve attachment path: {a}")
                else:
                    resolved_attachments.append(a)
        else:
            resolved_attachments = [attachments]

        form_data["attachments"] = resolved_attachments

        logger.info(f"[ExportNode] Resolved attachments: {resolved_attachments}")

        # 🔹 6. Execute appropriate export strategy
        strategy = ExportStrategyFactory.get_strategy(export_type_normalized)
        result = strategy.send(tenant_id, form_data, jwt_token)

        logger.info(f"[ExportNode] Export completed for {export_type_normalized}")

        return {
            "node": "ExportNode",
            "tenant_id": tenant_id,
            "export_type": export_type_normalized,
            "result": result
        }
