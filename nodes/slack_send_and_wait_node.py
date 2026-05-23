from datetime import datetime, timedelta

from engine.base_node import BaseNode
from engine.registry import register_node
from engine.export_strategies.slack_strategy import SlackExportStrategy
from logging_config import setup_logging

from nodes.slack_node_helpers import (
    build_slack_tracking_key,
    get_tenant_id,
    infer_slack_channel,
    infer_slack_message_text,
    infer_slack_thread_ts,
    infer_slack_user,
    resolve_form_data,
)

logger = setup_logging(__name__, level="DEBUG")


@register_node("slackSendAndWaitNode")
class SlackSendAndWaitNode(BaseNode):
    """Send a Slack message and pause workflow until a reply arrives."""

    def execute(self, inputs):
        form_data = resolve_form_data(self.form_data or {}, inputs)
        tenant_id = get_tenant_id(inputs, form_data)
        if not tenant_id:
            raise ValueError("slackSendAndWaitNode: Missing tenant_id")

        has_slack_event_context = bool(inputs.get("latest_slack_event") or inputs.get("slack_events"))

        runtime_channel = (
            inputs.get("channel")
            or inputs.get("to")
        )
        configured_channel = (
            form_data.get("channel_id")
            or form_data.get("channel")
            or form_data.get("to")
        )
        inferred_channel = infer_slack_channel(inputs)
        if has_slack_event_context:
            channel = runtime_channel or inferred_channel or configured_channel
        else:
            channel = runtime_channel or configured_channel or inferred_channel

        runtime_text = (
            inputs.get("text")
            or inputs.get("message")
            or inputs.get("body")
        )
        configured_text = form_data.get("text") or form_data.get("message") or form_data.get("body")
        inferred_text = infer_slack_message_text(inputs)
        text = runtime_text or configured_text or inferred_text

        if not channel:
            raise ValueError("slackSendAndWaitNode: Missing channel_id")
        if not text:
            raise ValueError("slackSendAndWaitNode: Missing message text")

        runtime_user = inputs.get("user") or inputs.get("user_id")
        configured_user = form_data.get("expected_user") or form_data.get("user_id")
        inferred_user = infer_slack_user(inputs)
        if has_slack_event_context:
            expected_user = runtime_user or inferred_user or configured_user
        else:
            expected_user = runtime_user or configured_user or inferred_user

        runtime_thread_ts = inputs.get("thread_ts")
        configured_thread_ts = form_data.get("thread_ts")
        inferred_thread_ts = infer_slack_thread_ts(inputs)
        if has_slack_event_context:
            thread_ts = runtime_thread_ts or inferred_thread_ts or configured_thread_ts
        else:
            thread_ts = runtime_thread_ts or configured_thread_ts or inferred_thread_ts

        strategy = SlackExportStrategy()
        payload = {
            **form_data,
            "type": "slack",
            "export_mode": "slack",
            "channel_id": str(channel),
            "text": str(text),
            "wait_for_reply": True,
        }

        if expected_user:
            payload["expected_user"] = str(expected_user)
        if thread_ts:
            payload["thread_ts"] = str(thread_ts)

        result = strategy.send(str(tenant_id), payload)
        is_waiting = result.get("status") == "waiting"

        if not is_waiting:
            return {
                "status": "success",
                "node": "slackSendAndWaitNode",
                "channel_id": str(channel),
                "result": result,
            }

        now = datetime.utcnow()

        wait_channel = str(result.get("channel_id") or channel)
        wait_user = str(
            (result.get("await") or {}).get("user")
            or expected_user
            or ""
        ).strip()
        wait_thread_ts = str(
            (result.get("await") or {}).get("thread_ts")
            or result.get("message_ts")
            or thread_ts
            or ""
        ).strip()

        tracking_key = build_slack_tracking_key(wait_channel, wait_user, wait_thread_ts)
        if not tracking_key:
            tracking_key = wait_channel

        return {
            "status": "waiting",
            "node": "slackSendAndWaitNode",
            "channel_id": wait_channel,
            "channel": wait_channel,
            "message": str(text),
            "text": str(text),
            "user_query": str(text),
            "thread_ts": wait_thread_ts,
            "user": wait_user,
            "await": {
                "type": "slack_reply",
                "channel": wait_channel,
                "user": wait_user,
                "thread_ts": wait_thread_ts,
            },
            "tracking_key": tracking_key,
            "tracking_type": "slack_channel_user",
            "config": {
                # Event-driven wait: this URL is a placeholder required by wait-state schema.
                "webhook_url": "https://example.invalid/slack-reply",
                "success_path": "status",
                "success_value": "received",
                # Keep poller effectively dormant; resume happens via Slack webhook route.
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