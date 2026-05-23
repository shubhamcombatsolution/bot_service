from datetime import datetime, timedelta

from engine.base_node import BaseNode
from engine.registry import register_node
from engine.export_strategies.whatsapp_strategy import WhatsAppExportStrategy
from logging_config import setup_logging
from nodes.whatsapp_node_helpers import (
    get_tenant_id,
    infer_whatsapp_message_text,
    infer_whatsapp_recipient,
    coerce_bool,
    normalize_phone,
    resolve_form_data,
)

logger = setup_logging(__name__, level="DEBUG")


@register_node("whatsappSendAndWaitNode")
class WhatsappSendAndWaitNode(BaseNode):
    """Send a WhatsApp message and pause workflow until a reply arrives."""

    def execute(self, inputs):
        form_data = resolve_form_data(self.form_data or {}, inputs)
        tenant_id = get_tenant_id(inputs, form_data)
        if not tenant_id:
            raise ValueError("whatsappSendAndWaitNode: Missing tenant_id")

        runtime_to = inputs.get("to") or inputs.get("from")
        configured_to = form_data.get("to") or form_data.get("send_to")
        recipient = runtime_to or configured_to or infer_whatsapp_recipient(inputs)

        runtime_message = inputs.get("text") or inputs.get("message") or inputs.get("body")
        configured_message = form_data.get("message") or form_data.get("text") or form_data.get("body")
        body = runtime_message or configured_message or infer_whatsapp_message_text(inputs)
        wait_enabled = coerce_bool(form_data.get("wait_enabled"), default=True)

        if body is not None and not isinstance(body, str):
            body = str(body)
        body = (body or "").strip()

        if not recipient:
            raise ValueError("whatsappSendAndWaitNode: Missing recipient phone number")
        if not body:
            raise ValueError("whatsappSendAndWaitNode: Missing message body")

        strategy = WhatsAppExportStrategy()
        payload = {
            **form_data,
            "type": "whatsapp",
            "export_mode": "whatsapp",
            "to": recipient,
            "body": body,
            "message": body,
            "wait_for_reply": wait_enabled,
        }
        payload.pop("template_name", None)

        result = strategy.send(str(tenant_id), payload)
        is_waiting = wait_enabled and result.get("status") == "waiting"

        if not is_waiting:
            return {
                "status": "success",
                "node": "whatsappSendAndWaitNode",
                "recipient": str(recipient),
                "result": result,
            }

        now = datetime.utcnow()
        normalized_recipient = normalize_phone(recipient) or str(recipient)

        return {
            "status": "waiting",
            "node": "whatsappSendAndWaitNode",
            "recipient": str(recipient),
            "from": normalized_recipient,
            "message": str(body),
            "user_query": str(body),
            "await": {
                "type": "whatsapp_reply",
                "from": normalized_recipient,
            },
            "tracking_key": normalized_recipient,
            "tracking_type": "whatsapp_phone",
            "config": {
                # Event-driven wait: this URL is a placeholder required by wait-state schema.
                "webhook_url": "https://example.invalid/whatsapp-reply",
                "success_path": "status",
                "success_value": "received",
                # Keep poller effectively dormant; resume happens via WhatsApp webhook route.
                "backoff_minutes": [1440],
                "max_retries": 0,
                "timeout_at": (now + timedelta(days=365)).isoformat() + "Z",
                "headers": {},
            },
            "state": {
                "retry_count": 0,
                "next_poll_at": (now + timedelta(days=365)).isoformat() + "Z",
                "created_at": now.isoformat() + "Z",
            },
            "result": result,
        }
