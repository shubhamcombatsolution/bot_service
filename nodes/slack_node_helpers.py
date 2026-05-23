from typing import Any, Dict, Optional

from nodes.whatsapp_node_helpers import get_tenant_id, resolve_context_path, resolve_form_data

__all__ = [
    "get_tenant_id",
    "resolve_form_data",
    "normalize_slack_channel",
    "normalize_slack_user",
    "build_slack_tracking_key",
    "infer_slack_channel",
    "infer_slack_user",
    "infer_slack_thread_ts",
    "infer_slack_message_text",
]


def normalize_slack_channel(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_slack_user(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_slack_tracking_key(channel: str, user: str = "", thread_ts: str = "") -> str:
    normalized_channel = normalize_slack_channel(channel)
    normalized_user = normalize_slack_user(user)
    normalized_thread_ts = str(thread_ts or "").strip()

    if not normalized_channel:
        return ""

    if normalized_thread_ts:
        if normalized_user:
            return f"{normalized_channel}:{normalized_thread_ts}:{normalized_user}"
        return f"{normalized_channel}:{normalized_thread_ts}"

    if normalized_user:
        return f"{normalized_channel}:{normalized_user}"

    return normalized_channel


def _extract_text_candidate(value: Any) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None

    if isinstance(value, list):
        for item in reversed(value):
            candidate = _extract_text_candidate(item)
            if candidate:
                return candidate
        return None

    if isinstance(value, dict):
        # Ignore classifier/router payloads that are not end-user responses.
        if (
            "decision" in value
            and "branch" in value
            and "response" in value
            and "status" in value
        ):
            return None

        preferred_keys = [
            "llm_response",
            "agent_output",
            "user_query",
            "text",
            "output",
            "response",
            "answer",
            "message",
            "content",
            "final_answer",
        ]

        for key in preferred_keys:
            if key in value:
                candidate = _extract_text_candidate(value.get(key))
                if candidate:
                    return candidate

        for nested in value.values():
            candidate = _extract_text_candidate(nested)
            if candidate:
                return candidate

    return None


def infer_slack_channel(context: Dict[str, Any]) -> str:
    candidate_paths = [
        "channel_id",
        "channel",
        "parameters.channel_id",
        "parameters.channel",
        "latest_slack_event.channel",
        "latest_slack_event.metadata.channel",
        "latest_slack_event.metadata.channel_id",
        "reply_event.latest_slack_event.channel",
        "reply_event.latest_slack_event.metadata.channel",
        "reply_event.latest_slack_event.metadata.channel_id",
        "slack_events.0.channel",
        "slack_events.0.metadata.channel",
        "slack_events.0.metadata.channel_id",
        "await.channel",
    ]

    for path in candidate_paths:
        channel = normalize_slack_channel(resolve_context_path(context, path))
        if channel:
            return channel

    node_outputs = context.get("node_outputs")
    if isinstance(node_outputs, dict):
        for _, output in reversed(list(node_outputs.items())):
            candidate = output[-1] if isinstance(output, list) and output else output
            if not isinstance(candidate, dict):
                continue

            channel = normalize_slack_channel(
                candidate.get("channel")
                or (candidate.get("metadata") or {}).get("channel")
                or (candidate.get("metadata") or {}).get("channel_id")
                or (candidate.get("await") or {}).get("channel")
                or candidate.get("channel_id")
            )
            if channel:
                return channel

    return ""


def infer_slack_user(context: Dict[str, Any]) -> str:
    candidate_paths = [
        "user",
        "user_id",
        "parameters.user",
        "parameters.user_id",
        "latest_slack_event.user",
        "latest_slack_event.metadata.user",
        "reply_event.latest_slack_event.user",
        "reply_event.latest_slack_event.metadata.user",
        "slack_events.0.user",
        "slack_events.0.metadata.user",
        "await.user",
    ]

    for path in candidate_paths:
        user = normalize_slack_user(resolve_context_path(context, path))
        if user:
            return user

    node_outputs = context.get("node_outputs")
    if isinstance(node_outputs, dict):
        for _, output in reversed(list(node_outputs.items())):
            candidate = output[-1] if isinstance(output, list) and output else output
            if not isinstance(candidate, dict):
                continue

            user = normalize_slack_user(
                candidate.get("user")
                or (candidate.get("metadata") or {}).get("user")
                or (candidate.get("await") or {}).get("user")
                or candidate.get("user_id")
            )
            if user:
                return user

    return ""


def infer_slack_thread_ts(context: Dict[str, Any]) -> str:
    candidate_paths = [
        "thread_ts",
        "parameters.thread_ts",
        "latest_slack_event.thread_ts",
        "latest_slack_event.metadata.thread_ts",
        "reply_event.latest_slack_event.thread_ts",
        "reply_event.latest_slack_event.metadata.thread_ts",
        "slack_events.0.thread_ts",
        "slack_events.0.metadata.thread_ts",
        "await.thread_ts",
    ]

    for path in candidate_paths:
        value = resolve_context_path(context, path)
        if value is not None and str(value).strip() != "":
            return str(value).strip()

    node_outputs = context.get("node_outputs")
    if isinstance(node_outputs, dict):
        for _, output in reversed(list(node_outputs.items())):
            candidate = output[-1] if isinstance(output, list) and output else output
            if not isinstance(candidate, dict):
                continue

            value = (
                candidate.get("thread_ts")
                or (candidate.get("metadata") or {}).get("thread_ts")
                or candidate.get("message_ts")
            )
            if value is not None and str(value).strip() != "":
                return str(value).strip()

    return ""


def infer_slack_message_text(context: Dict[str, Any]) -> str:
    node_outputs = context.get("node_outputs")
    if isinstance(node_outputs, dict):
        for _, output in reversed(list(node_outputs.items())):
            # Skip the Slack trigger node's own output regardless of whether
            # it is stored as a list-of-dicts or a plain dict — otherwise the
            # trigger text gets echoed straight back as the outgoing message.
            if (
                isinstance(output, list)
                and output
                and isinstance(output[0], dict)
                and output[0].get("trigger_type") == "slack"
            ):
                continue

            if isinstance(output, dict) and output.get("trigger_type") == "slack":
                continue

            # Handle direct string output from agent
            if isinstance(output, str) and output.strip():
                return output.strip()

            candidate = _extract_text_candidate(output)
            if candidate:
                return candidate

    candidate_paths = [
        "message",
        "text",
        "parameters.message",
        "parameters.text",
        "parameters.user_query",
        "latest_slack_event.message",
        "latest_slack_event.text",
        "latest_slack_event.content.text",
        "reply_event.latest_slack_event.message",
        "reply_event.latest_slack_event.text",
        "slack_events.0.message",
        "slack_events.0.text",
        "slack_events.0.content.text",
        "user_query",
    ]

    for path in candidate_paths:
        candidate = _extract_text_candidate(resolve_context_path(context, path))
        if candidate:
            return candidate

    return ""
