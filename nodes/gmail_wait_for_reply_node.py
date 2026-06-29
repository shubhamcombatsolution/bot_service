from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from engine.base_node import BaseNode
from engine.registry import register_node
from logging_config import setup_logging
from nodes.utils.resolver import resolve_field

logger = setup_logging("GmailWaitForReplyNode", level="DEBUG")


def _get_tenant_id(inputs: Dict[str, Any], form_data: Dict[str, Any]) -> Optional[int]:
    tenant_id = (
        inputs.get("tenant_id")
        or (inputs.get("workflow") or {}).get("tenant_id")
        or form_data.get("tenant_id")
    )
    if tenant_id is None:
        return None
    try:
        return int(tenant_id)
    except (TypeError, ValueError):
        return None


def _resolve_config_var(name: str, config_params: dict, inputs: dict) -> Optional[str]:
    path = config_params.get(name)
    if not path:
        return None
    try:
        context = {
            **inputs,
            "node_outputs": inputs.get("node_outputs") or inputs,
            "workflow": inputs.get("workflow"),
        }
        value = resolve_field(context, path)
        if value is not None:
            return str(value).strip()
    except Exception as e:
        logger.warning("Failed to resolve %s from path %s: %s", name, path, e)
    return None


def _try_resolve_literal(value: Optional[str], inputs: dict) -> Optional[str]:
    """If value looks like a dot-path (e.g. 'nodeId.field.sub'), try to resolve it from inputs."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    if "." in value:
        try:
            context = {
                **inputs,
                "node_outputs": inputs.get("node_outputs") or inputs,
                "workflow": inputs.get("workflow"),
            }
            resolved = resolve_field(context, value)
            if resolved is not None:
                return str(resolved).strip()
        except Exception:
            pass
    return value if value else None


def _discover_thread_id(tenant_id: int, to_email: str, subject: Optional[str] = None) -> Optional[str]:
    """Search Gmail for the most recent sent message to the recipient and return its threadId."""
    try:
        from Tools.GmailTool import GmailTool

        gmail = GmailTool(tenant_id=tenant_id, auth_mode="manual")
        gmail.authenticate()
        if not gmail.service:
            logger.error("Gmail authentication failed for tenant %s", tenant_id)
            return None

        query = f"from:me to:{to_email}"
        if subject:
            safe_subject = subject.replace('"', '\\"')
            query += f' subject:"{safe_subject}"'

        result = gmail.list_messages(query=query, max_results=1)
        messages = result.get("messages") or []
        if not messages:
            logger.warning("No sent messages found for query: %s", query)
            return None

        msg = messages[0]
        thread_id = msg.get("threadId")
        logger.info("Discovered thread_id=%s for to_email=%s", thread_id, to_email)
        return thread_id
    except Exception as e:
        logger.exception("Failed to discover thread_id for %s: %s", to_email, e)
        return None


@register_node("gmailWaitForReplyNode")
class GmailWaitForReplyNode(BaseNode):
    """Pause workflow and wait for an email reply on a Gmail thread."""

    def execute(self, inputs: dict) -> dict:
        logger.info("GmailWaitForReplyNode started: %s", self.node_id)

        config = self.form_data or {}
        config_params = (
            config.get("config_parameters")
            or config.get("dataMapping")
            or {}
        )

        execution_id = inputs.get("execution_id")
        if not execution_id:
            raise ValueError("gmailWaitForReplyNode requires execution_id")

        tenant_id = _get_tenant_id(inputs, config)
        if not tenant_id:
            raise ValueError("gmailWaitForReplyNode requires tenant_id")

        wait_minutes = int(config.get("wait_minutes") or config.get("waitMinutes") or 2880)

        to_email = (
            _resolve_config_var("to_email", config_params, inputs)
            or _resolve_config_var("toEmail", config_params, inputs)
            or _try_resolve_literal(config.get("to_email") or config.get("toEmail"), inputs)
        )

        thread_id = (
            _resolve_config_var("thread_id", config_params, inputs)
            or _resolve_config_var("threadId", config_params, inputs)
            or _try_resolve_literal(config.get("thread_id") or config.get("threadId"), inputs)
        )

        subject = (
            _resolve_config_var("subject", config_params, inputs)
            or _try_resolve_literal(config.get("subject"), inputs)
        )

        if not to_email and not thread_id:
            raise ValueError(
                "gmailWaitForReplyNode requires at least 'to_email' or 'thread_id' "
                "in formData or config_parameters"
            )

        if not thread_id:
            logger.info("No thread_id provided, searching Gmail for thread to %s", to_email)
            thread_id = _discover_thread_id(tenant_id, to_email, subject)
            if not thread_id:
                raise ValueError(
                    f"Could not find a Gmail thread for to_email={to_email}. "
                    "Ensure the email was sent before this node executes."
                )

        logger.info(
            "GmailWaitForReplyNode configured | thread_id=%s to_email=%s wait_minutes=%s",
            thread_id, to_email, wait_minutes,
        )

        now = datetime.utcnow()
        timeout_at = now + timedelta(minutes=wait_minutes)
        first_poll_at = now + timedelta(minutes=min(5, wait_minutes))

        return {
            "status": "waiting",
            "node": "gmailWaitForReplyNode",
            "to_email": to_email or "",
            "thread_id": thread_id,
            "tenant_id": tenant_id,
            "subject": subject or "",
            "await": {
                "type": "gmail_reply",
                "thread_id": thread_id,
                "to_email": to_email or "",
            },
            "tracking_key": thread_id,
            "tracking_type": "gmail_thread",
            "config": {
                "webhook_url": "internal://gmail-reply-check",
                "success_path": "reply_received",
                "success_value": True,
                "backoff_minutes": [wait_minutes],
                "max_retries": 0,
                "timeout_at": timeout_at.isoformat() + "Z",
                "headers": {},
            },
            "state": {
                "retry_count": 0,
                "next_poll_at": first_poll_at.isoformat() + "Z",
                "created_at": now.isoformat() + "Z",
            },
            "mapped_data": {
                "to_email": to_email or "",
                "thread_id": thread_id,
                "subject": subject or "",
                "tenant_id": tenant_id,
            },
        }
