from engine.base_node import BaseNode
from engine.registry import register_node
from logging_config import setup_logging

logger = setup_logging(__name__, level="DEBUG")


def _normalize_prefetched_event(event, tenant_id):
    if not isinstance(event, dict):
        return event

    metadata = event.get("metadata") or {}
    content = event.get("content") or {}
    text = content.get("text") or ""
    if isinstance(text, dict):
        text = text.get("body") or ""

    message = event.get("message") or event.get("user_query") or text or ""
    phone = str(metadata.get("from") or metadata.get("from_phone") or event.get("phone") or "")

    normalized = dict(event)
    normalized.setdefault("trigger_type", "whatsapp")
    normalized.setdefault("source", "whatsapp")
    normalized.setdefault("event", "message.received")
    normalized["metadata"] = {
        **metadata,
        "from_phone": phone,
        "message_type": metadata.get("message_type") or metadata.get("type") or "unknown",
    }
    normalized["content"] = {
        **content,
        "text": message,
    }
    normalized["message"] = message
    normalized["phone"] = phone
    normalized["user_query"] = normalized.get("user_query") or message
    normalized["parameters"] = {
        **(normalized.get("parameters") or {}),
        "user_query": normalized.get("user_query") or message,
        "message": message,
        "from": normalized["metadata"].get("from_phone") or phone,
        "phone": phone,
        "message_type": normalized["metadata"].get("message_type") or "unknown",
    }
    normalized.setdefault("context", {})
    normalized["context"].setdefault("tenant_id", tenant_id)
    normalized["context"].setdefault("tool_name", "whatsapp")
    # FIX: expose tenant_id at the top level so downstream nodes (LLM agent,
    # send node) can find it via inputs.get("tenant_id") without having to
    # dig into context{}.  Previously it was only in context.tenant_id.
    normalized["tenant_id"] = tenant_id
    return normalized


def _is_inbound_user_message(event):
    if not isinstance(event, dict):
        return False

    metadata = event.get("metadata") or {}
    message_type = str(
        metadata.get("message_type")
        or metadata.get("type")
        or (event.get("parameters") or {}).get("message_type")
        or ""
    ).strip().lower()

    if message_type == "status":
        return False

    source = str(event.get("source") or "").strip().lower()
    trigger_type = str(event.get("trigger_type") or "").strip().lower()
    event_name = str(event.get("event") or "").strip().lower()
    phone = str(
        event.get("phone")
        or metadata.get("from_phone")
        or metadata.get("from")
        or ""
    ).strip()
    message = str(
        event.get("message")
        or event.get("user_query")
        or (event.get("content") or {}).get("text")
        or ""
    ).strip()

    return (
        (source == "whatsapp" or trigger_type == "whatsapp")
        and event_name == "message.received"
        and bool(phone)
        and bool(message)
    )


@register_node("WhatsAppTriggerNode")
@register_node("whatsappTriggerNode")
class WhatsappTriggerNode(BaseNode):
    """Trigger node for WhatsApp inbound events."""

    is_trigger_node = True

    def execute(self, inputs):
        tenant_id = inputs.get("tenant_id")
        if not tenant_id:
            raise ValueError("whatsappTriggerNode: Missing tenant_id")

        prefetched_events = inputs.get("prefetched_events")
        if not isinstance(prefetched_events, list) or not prefetched_events:
            raise ValueError(
                "whatsappTriggerNode: No inbound user message received. "
                "Execution is blocked until a real WhatsApp webhook message arrives."
            )

        normalized_events = [_normalize_prefetched_event(evt, tenant_id) for evt in prefetched_events]
        inbound_user_events = [evt for evt in normalized_events if _is_inbound_user_message(evt)]

        if not inbound_user_events:
            raise ValueError(
                "whatsappTriggerNode: No inbound user message events found in prefetched_events."
            )

        logger.info(
            "whatsappTriggerNode accepted %s inbound user message event(s)",
            len(inbound_user_events),
        )
        return inbound_user_events
