from engine.base_node import BaseNode
from engine.registry import register_node
from logging_config import setup_logging

from nodes.slack_node_helpers import (
    normalize_slack_channel,
    normalize_slack_user,
)

logger = setup_logging(__name__, level="DEBUG")


def _normalize_prefetched_event(event, tenant_id):
    if not isinstance(event, dict):
        return event

    metadata = event.get("metadata") or {}
    content = event.get("content") or {}

    text = content.get("text") or event.get("text") or event.get("message") or event.get("user_query") or ""
    if isinstance(text, dict):
        text = text.get("body") or ""
    text = str(text or "").strip()

    channel = normalize_slack_channel(
        metadata.get("channel")
        or metadata.get("channel_id")
        or event.get("channel")
        or event.get("channel_id")
    )
    user = normalize_slack_user(metadata.get("user") or event.get("user") or event.get("user_id"))
    thread_ts = str(
        metadata.get("thread_ts")
        or event.get("thread_ts")
        or event.get("message_ts")
        or ""
    ).strip()

    normalized = dict(event)
    normalized.setdefault("trigger_type", "slack")
    normalized.setdefault("source", "slack")
    normalized.setdefault("event", "message.received")
    normalized["metadata"] = {
        **metadata,
        "channel": channel,
        "channel_id": channel,
        "user": user,
        "thread_ts": thread_ts,
        "message_type": metadata.get("message_type") or "text",
    }
    normalized["content"] = {
        **content,
        "text": text,
    }
    normalized["message"] = text
    normalized["text"] = text
    normalized["channel"] = channel
    normalized["user"] = user
    normalized["thread_ts"] = thread_ts
    normalized["user_query"] = normalized.get("user_query") or text
    normalized["parameters"] = {
        **(normalized.get("parameters") or {}),
        "user_query": normalized.get("user_query") or text,
        "message": text,
        "text": text,
        "channel": channel,
        "channel_id": channel,
        "user": user,
        "thread_ts": thread_ts,
    }
    normalized.setdefault("context", {})
    normalized["context"].setdefault("tenant_id", tenant_id)
    normalized["context"].setdefault("tool_name", "slack")
    # Keep parity with WhatsApp trigger so downstream nodes can reliably
    # resolve tenant-scoped config directly from top-level inputs.
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
        or "text"
    ).strip().lower()

    if message_type in {"bot_message", "message_changed", "message_deleted"}:
        return False

    source = str(event.get("source") or "").strip().lower()
    trigger_type = str(event.get("trigger_type") or "").strip().lower()
    event_name = str(event.get("event") or "").strip().lower()
    channel = str(
        event.get("channel")
        or metadata.get("channel")
        or metadata.get("channel_id")
        or ""
    ).strip()
    message = str(
        event.get("message")
        or event.get("user_query")
        or event.get("text")
        or (event.get("content") or {}).get("text")
        or ""
    ).strip()

    return (
        (source == "slack" or trigger_type == "slack")
        and event_name == "message.received"
        and bool(channel)
        and bool(message)
    )


@register_node("SlackTriggerNode")
@register_node("slackTriggerNode")
class SlackTriggerNode(BaseNode):
    """Trigger node for Slack inbound events."""

    is_trigger_node = True

    def execute(self, inputs):
        tenant_id = inputs.get("tenant_id")
        if not tenant_id:
            raise ValueError("slackTriggerNode: Missing tenant_id")

        prefetched_events = inputs.get("prefetched_events")
        if prefetched_events:
            logger.info("slackTriggerNode using prefetched webhook events")
            normalized_events = [_normalize_prefetched_event(evt, tenant_id) for evt in prefetched_events]
            inbound_user_events = [evt for evt in normalized_events if _is_inbound_user_message(evt)]
            if not inbound_user_events:
                raise ValueError(
                    "slackTriggerNode: No inbound user message events found in prefetched_events."
                )
            logger.info(
                "slackTriggerNode accepted %s inbound user message event(s)",
                len(inbound_user_events),
            )
            return inbound_user_events

        raise ValueError(
            "slackTriggerNode: No inbound user message received. "
            "Execution is blocked until a real Slack webhook message arrives."
        )
