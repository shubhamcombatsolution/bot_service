from engine.base_node import BaseNode
from engine.registry import register_node
from engine.export_strategies.slack_strategy import SlackExportStrategy
from logging_config import setup_logging
from app.database.DatabaseOperationPostgreSQL import db_session
from app.models.bot_diagram import BotDiagram
from app.services.channel_credentials_service import get_slack_credentials_for_bot

from nodes.slack_node_helpers import (
    get_tenant_id,
    infer_slack_channel,
    infer_slack_message_text,
    infer_slack_thread_ts,
    resolve_form_data,
)

try:
    from get_tool_credential import get_tool_credential
except Exception:
    get_tool_credential = None

logger = setup_logging(__name__, level="DEBUG")


def _extract_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("llm_response", "agent_output", "response", "output", "text", "message", "content"):
            candidate = _extract_text(value.get(key))
            if candidate:
                return candidate
        for nested in value.values():
            candidate = _extract_text(nested)
            if candidate:
                return candidate
        return ""
    if isinstance(value, list):
        for item in reversed(value):
            candidate = _extract_text(item)
            if candidate:
                return candidate
        return ""
    return str(value).strip()


def _pick_first_non_empty_text(*candidates):
    for candidate in candidates:
        text = _extract_text(candidate)
        if text:
            return text
    return ""

def _looks_like_unresolved_template(text: str) -> bool:
    value = (text or "").strip()
    return value.startswith("{{") and value.endswith("}}")


def _resolve_bot_id(session, inputs, form_data):
    for key in ("bot_id", "botId"):
        value = form_data.get(key) or inputs.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except Exception:
                pass

    flow_data = inputs.get("flowData")
    if isinstance(flow_data, dict):
        value = flow_data.get("bot_id")
        if value not in (None, ""):
            try:
                return int(value)
            except Exception:
                pass

    # Workflow executor often nests runtime metadata under workflow.flowData
    workflow_obj = inputs.get("workflow")
    if isinstance(workflow_obj, dict):
        nested_flow = workflow_obj.get("flowData")
        if isinstance(nested_flow, dict):
            value = nested_flow.get("bot_id")
            if value not in (None, ""):
                try:
                    return int(value)
                except Exception:
                    pass
        value = workflow_obj.get("bot_id")
        if value not in (None, ""):
            try:
                return int(value)
            except Exception:
                pass

    diagram_id = form_data.get("diagram_id") or form_data.get("workflow_id") or inputs.get("diagram_id")
    if diagram_id not in (None, ""):
        try:
            diagram = session.query(BotDiagram).filter(BotDiagram.diagram_id == int(diagram_id)).first()
            if diagram and diagram.bot_id:
                return int(diagram.bot_id)
        except Exception:
            pass
    return None


@register_node("slackSendMessageNode")
class SlackSendMessageNode(BaseNode):
    """Send a Slack channel message."""

    def execute(self, inputs):
        form_data = resolve_form_data(self.form_data or {}, inputs)
        slack_form = form_data.get("slack") if isinstance(form_data.get("slack"), dict) else {}
        tenant_id = get_tenant_id(inputs, form_data)
        if not tenant_id:
            raise ValueError("slackSendMessageNode: Missing tenant_id")

        has_slack_event_context = bool(inputs.get("latest_slack_event") or inputs.get("slack_events"))

        trigger_data = inputs if isinstance(inputs, dict) else {}

        session = next(db_session())
        try:
            bot_id = _resolve_bot_id(session, trigger_data, form_data)
            bot_creds = get_slack_credentials_for_bot(session, bot_id)
            logger.debug(
                "[SLACK DEBUG] Resolved bot_id=%s bot_creds_present=%s",
                bot_id,
                bool(bot_creds.get("bot_token")),
            )
        finally:
            try:
                session.close()
            except Exception:
                pass
        node_channel = (
            form_data.get("channel_id")
            or form_data.get("channel")
            or slack_form.get("channel_id")
            or slack_form.get("channel")
            or slack_form.get("default_channel_id")
        )
        if isinstance(node_channel, str) and _looks_like_unresolved_template(node_channel):
            logger.warning(
                "[SLACK] Unresolved template detected in configured channel; falling back to trigger/default channel"
            )
            node_channel = None
        node_bot_token = (
            form_data.get("bot_token")
            or slack_form.get("bot_token")
        )
        use_node_credentials = bool(node_bot_token or node_channel)

        cred = None
        if callable(get_tool_credential) and not use_node_credentials:
            try:
                cred = get_tool_credential(
                    tenant_id=tenant_id,
                    tool_name="slack"
                )
            except Exception:
                cred = None

        db_channel = None
        db_token = None
        if isinstance(cred, dict):
            credentials = cred.get("credentials", {})
            # Support both canonical and legacy keys stored by older UI payloads.
            db_channel = credentials.get("default_channel_id") or credentials.get("channel_id")
            db_token = credentials.get("bot_token") or credentials.get("xoxb_token") or credentials.get("access_token")
        if isinstance(db_channel, str):
            db_channel = db_channel.strip()
        if not db_channel:
            db_channel = None

        # Do not log raw credential payloads.
        logger.debug(
            "[SLACK DEBUG] Global credential presence: %s",
            bool((cred or {}).get("credentials")),
        )
        logger.debug(f"[SLACK DEBUG] Extracted DB channel: {db_channel}")
        logger.debug(f"[SLACK DEBUG] Trigger channel: {trigger_data.get('channel')}")

        trigger_channel = trigger_data.get("channel")

        if node_bot_token:
            db_token = str(node_bot_token).strip()
        elif bot_creds.get("bot_token"):
            db_token = str(bot_creds.get("bot_token")).strip()

        if bot_creds.get("default_channel_id"):
            db_channel = str(bot_creds.get("default_channel_id")).strip()

        # Priority: node config channel (if set) > trigger channel > bot/global default channel.
        channel_id = node_channel if node_channel else (trigger_channel if trigger_channel else db_channel)
        if isinstance(channel_id, str):
            channel_id = channel_id.strip()

        logger.debug(f"[SLACK DEBUG] Final channel used: {channel_id}")
        logger.info(f"[SLACK] Channel source: {'TRIGGER' if trigger_channel else 'DB'} -> {channel_id}")

        if not channel_id or channel_id == "C0000000000":
            raise ValueError("Invalid Slack channel ID")

        runtime_channel = (
            inputs.get("channel")
            or inputs.get("channel_id")
            or inputs.get("to")
        )
        configured_channel = (
            form_data.get("channel")
            or form_data.get("channel_id")
            or form_data.get("to")
            or slack_form.get("channel")
            or slack_form.get("channel_id")
            or slack_form.get("default_channel_id")
        )
        inferred_channel = infer_slack_channel(inputs)
        if has_slack_event_context:
            channel = channel_id or runtime_channel or inferred_channel or configured_channel
        else:
            channel = channel_id or runtime_channel or configured_channel or inferred_channel

        runtime_text = (
            inputs.get("agent_output")
            or inputs.get("response")
            or inputs.get("text")
            or inputs.get("message")
            or inputs.get("body")
        )
        configured_text = (
            form_data.get("text")
            or form_data.get("message")
            or form_data.get("body")
            or slack_form.get("text")
            or slack_form.get("message")
            or slack_form.get("body")
        )
        inferred_text = infer_slack_message_text(inputs)
        # In Slack-triggered runs, runtime text is often the original inbound
        # user message from trigger context. Prefer configured/inferred output
        # so we send agent/LLM response instead of echoing the prompt.
        if has_slack_event_context:
            text = _pick_first_non_empty_text(configured_text, inferred_text, runtime_text)
        else:
            text = _pick_first_non_empty_text(runtime_text, configured_text, inferred_text)

        if _looks_like_unresolved_template(text):
            logger.warning(
                "[SLACK] Unresolved template detected in outgoing text; falling back to inferred/runtime text"
            )
            text = _pick_first_non_empty_text(inferred_text, runtime_text)

        if _looks_like_unresolved_template(text):
            text = "Sorry, something went wrong."

        if not channel:
            logger.error("slackSendMessageNode: Missing Slack channel; skipping send")
            return {
                "status": "skipped",
                "node": "slackSendMessageNode",
                "reason": "missing_channel",
            }
        if not text:
            raise ValueError("slackSendMessageNode: Missing message text")

        runtime_thread_ts = inputs.get("thread_ts")
        inferred_thread_ts = infer_slack_thread_ts(inputs)
        if has_slack_event_context:
            resolved_thread_ts = runtime_thread_ts or inferred_thread_ts or form_data.get("thread_ts")
        else:
            resolved_thread_ts = runtime_thread_ts or form_data.get("thread_ts") or inferred_thread_ts

        strategy = SlackExportStrategy()
        payload = {
            **form_data,
            "type": "slack",
            "export_mode": "slack",
            "channel": str(channel),
            "text": str(text),
            "wait_for_reply": False,
        }
        if db_token:
            payload["bot_token"] = db_token

        if resolved_thread_ts:
            payload["thread_ts"] = str(resolved_thread_ts)

        result = strategy.send(str(tenant_id), payload)
        return {
            "status": "success",
            "node": "slackSendMessageNode",
            "channel": str(channel),
            "result": result,
        }
