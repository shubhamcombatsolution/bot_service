import re
import ast
import json
from typing import Any, Dict

import requests
from sqlalchemy import func, or_

from app.database.DatabaseOperationPostgreSQL import db_session
from app.models.tool_authorization import ToolAuthorization
from app.models.bot_diagram import BotDiagram
from app.services.channel_credentials_service import get_whatsapp_credentials_for_bot
from engine.base_node import BaseNode
from engine.registry import register_node
from logging_config import setup_logging
from nodes.whatsapp_node_helpers import (
    get_tenant_id,
    infer_whatsapp_message_text,
    infer_whatsapp_recipient,
    resolve_form_data,
)

try:
    from get_tool_credential import get_tool_credential
except Exception:
    get_tool_credential = None

logger = setup_logging(__name__, level="DEBUG")

ACCESS_TOKEN_KEYS = (
    "access_token",
    "accessToken",
    "permanent_token",
    "token",
    "bearer_token",
)
PHONE_NUMBER_ID_KEYS = (
    "phone_number_id",
    "phoneNumberId",
    "business_phone_number_id",
    "business_phone_id",
    "whatsapp_phone_number_id",
    "phone_id",
    "number_id",
)
API_VERSION_KEYS = (
    "api_version",
    "apiVersion",
)
DEFAULT_RECIPIENT_KEYS = (
    "default_recipient_number",
    "defaultRecipientNumber",
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _flatten_auth_payload(raw_payload: Any) -> Dict[str, Any]:
    root = _safe_dict(raw_payload)
    merged = dict(root)
    for key in ("credentials", "token_json", "data", "auth"):
        nested = _safe_dict(root.get(key))
        if nested:
            merged.update(nested)
    return merged


def _pick_first(payload: Dict[str, Any], keys) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _normalize_phone(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _normalize_recipient_e164(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    # Keep a single leading '+' if present; remove spaces and punctuation.
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    return f"+{digits}"


def _extract_text_from_payload(payload: Any) -> str:
    """Extract best user-facing text from nested agent/tool outputs."""
    if payload is None:
        return ""

    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return ""

        # Common bad shape: "{'llm_response': '...', 'tool_result': None}"
        if text.startswith("{") and ("llm_response" in text or "tool_result" in text):
            parsed = None
            try:
                parsed = ast.literal_eval(text)
            except Exception:
                try:
                    parsed = json.loads(text)
                except Exception:
                    parsed = None
            if isinstance(parsed, dict):
                extracted = _extract_text_from_payload(parsed)
                if extracted:
                    return extracted

        return text

    if isinstance(payload, dict):
        preferred_keys = (
            "llm_response",
            "response",
            "message",
            "text",
            "agent_output",
        )
        for key in preferred_keys:
            if payload.get(key) is not None:
                extracted = _extract_text_from_payload(payload.get(key))
                if extracted:
                    return extracted

        # Nested wrappers used by various nodes
        for key in ("output", "result", "data"):
            if payload.get(key) is not None:
                extracted = _extract_text_from_payload(payload.get(key))
                if extracted:
                    return extracted

        # Last-resort scan of values
        for value in payload.values():
            extracted = _extract_text_from_payload(value)
            if extracted:
                return extracted
        return ""

    if isinstance(payload, list):
        parts = []
        for item in payload:
            extracted = _extract_text_from_payload(item)
            if extracted:
                parts.append(extracted)
        return "\n".join(parts).strip()

    return str(payload).strip()


def _format_whatsapp_text(text: str) -> str:
    """Normalize markdown-ish model output into clean WhatsApp text."""
    body = (text or "").strip()
    if not body:
        return ""

    # Remove code fences and markdown emphasis
    body = body.replace("```", "")
    body = body.replace("**", "")
    body = re.sub(r"^#{1,6}\s*", "", body, flags=re.MULTILINE)

    formatted_lines = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            if formatted_lines and formatted_lines[-1] != "":
                formatted_lines.append("")
            continue

        # Convert markdown bullets to simple WhatsApp bullets
        line = re.sub(r"^\s*[-*]\s+", "- ", line)

        # Convert "Key: Value" headings to pointer style for readability
        if ":" in line and not line.startswith("- "):
            key, value = line.split(":", 1)
            if key.strip() and value.strip():
                line = f"- {key.strip()}: {value.strip()}"

        formatted_lines.append(line)

    # Collapse repeated blank lines
    cleaned = []
    for line in formatted_lines:
        if line == "" and cleaned and cleaned[-1] == "":
            continue
        cleaned.append(line)

    return "\n".join(cleaned).strip()


def _pick_first_non_empty_text(*candidates: Any) -> str:
    """Return first candidate that yields non-empty user-facing text."""
    for candidate in candidates:
        extracted = _format_whatsapp_text(_extract_text_from_payload(candidate))
        if extracted:
            return extracted
    return ""


def _extract_previous_node_output(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort extraction of the most recent upstream node output dict."""
    if isinstance(inputs, dict):
        ignored_keys = {
            "node_outputs",
            "workflow",
            "execution_id",
            "tenant_id",
            "message",
            "user_query",
            "text",
            "phone",
            "from",
            "to",
        }
        direct_parent_candidates = [
            value
            for key, value in inputs.items()
            if key not in ignored_keys and isinstance(value, dict)
        ]
        for output in reversed(direct_parent_candidates):
            if (
                output.get("response") is not None
                or output.get("llm_response") is not None
                or output.get("agent_output") is not None
                or output.get("output") is not None
            ):
                return output

    node_outputs = inputs.get("node_outputs")
    if isinstance(node_outputs, dict):
        for _, output in reversed(list(node_outputs.items())):
            if isinstance(output, dict):
                if (
                    output.get("from") is not None
                    or output.get("response") is not None
                    or output.get("llm_response") is not None
                    or output.get("agent_output") is not None
                    or output.get("output") is not None
                ):
                    return output
            elif isinstance(output, list):
                for item in reversed(output):
                    if isinstance(item, dict) and (
                        item.get("from") is not None
                        or item.get("response") is not None
                        or item.get("llm_response") is not None
                        or item.get("agent_output") is not None
                        or item.get("output") is not None
                    ):
                        return item
    return {}


def _load_whatsapp_credentials_from_db(tenant_id: int) -> Dict[str, str]:
    session = next(db_session())
    try:
        auth_rows = (
            session.query(ToolAuthorization)
            .filter(
                ToolAuthorization.tenant_id == int(tenant_id),
                or_(
                    func.lower(ToolAuthorization.tool_name) == "whatsapp",
                    func.lower(ToolAuthorization.tool_name).like("%whatsapp%"),
                ),
                ToolAuthorization.del_flag.is_(False),
            )
            .order_by(ToolAuthorization.updated_at.desc())
            .all()
        )

        for auth in auth_rows:
            creds = _flatten_auth_payload(auth.token_json)
            access_token = _pick_first(creds, ACCESS_TOKEN_KEYS)
            phone_number_id = _normalize_phone(_pick_first(creds, PHONE_NUMBER_ID_KEYS))
            api_version = _pick_first(creds, API_VERSION_KEYS) or "v19.0"

            if access_token and phone_number_id:
                return {
                    "access_token": access_token,
                    "phone_number_id": phone_number_id,
                    "api_version": api_version,
                    "default_recipient_number": _pick_first(creds, DEFAULT_RECIPIENT_KEYS),
                }

        raise ValueError(
            "whatsappSendMessageNode: Missing WhatsApp DB credentials "
            "(access_token and phone_number_id are required)."
        )
    finally:
        session.close()


def _resolve_bot_id(session, inputs: Dict[str, Any], form_data: Dict[str, Any]) -> int | None:
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

    workflow_meta = inputs.get("workflow")
    if isinstance(workflow_meta, dict):
        value = workflow_meta.get("bot_id")
        if value not in (None, ""):
            try:
                return int(value)
            except Exception:
                pass

    prefetched_events = inputs.get("prefetched_events")
    if isinstance(prefetched_events, list) and prefetched_events:
        first_event = prefetched_events[0] if isinstance(prefetched_events[0], dict) else {}
        event_context = first_event.get("context") if isinstance(first_event, dict) else {}
        if isinstance(event_context, dict):
            value = event_context.get("bot_id")
            if value not in (None, ""):
                try:
                    return int(value)
                except Exception:
                    pass

    whatsapp_events = inputs.get("whatsapp_events")
    if isinstance(whatsapp_events, list) and whatsapp_events:
        first_event = whatsapp_events[0] if isinstance(whatsapp_events[0], dict) else {}
        event_context = first_event.get("context") if isinstance(first_event, dict) else {}
        if isinstance(event_context, dict):
            value = event_context.get("bot_id")
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


@register_node("whatsappSendMessageNode")
class WhatsappSendMessageNode(BaseNode):
    """Send a plain WhatsApp message."""

    def execute(self, inputs):
        form_data = resolve_form_data(self.form_data or {}, inputs)
        whatsapp_form = form_data.get("whatsapp") if isinstance(form_data.get("whatsapp"), dict) else {}
        prev_output = _extract_previous_node_output(inputs)
        tenant_id = get_tenant_id(inputs, form_data)
        if not tenant_id:
            # FIX: log full inputs so propagation failures are immediately
            # visible in prod logs instead of a bare "Missing tenant_id".
            logger.error(
                "whatsappSendMessageNode: Missing tenant_id — inputs keys=%s form_data keys=%s",
                list(inputs.keys()) if isinstance(inputs, dict) else inputs,
                list(form_data.keys()) if isinstance(form_data, dict) else form_data,
            )
            raise ValueError("whatsappSendMessageNode: Missing tenant_id")

        session = next(db_session())
        try:
            bot_id = _resolve_bot_id(session, inputs if isinstance(inputs, dict) else {}, form_data)
            node_access_token = form_data.get("access_token") or whatsapp_form.get("access_token")
            node_phone_id = form_data.get("phone_number_id") or whatsapp_form.get("phone_number_id")
            node_api_version = (
                form_data.get("api_version")
                or form_data.get("graph_api_version")
                or whatsapp_form.get("api_version")
                or whatsapp_form.get("graph_api_version")
                or "v19.0"
            )
            node_default_recipient = (
                form_data.get("recipient_number")
                or form_data.get("default_recipient_number")
                or whatsapp_form.get("recipient_number")
                or whatsapp_form.get("default_recipient_number")
            )
            use_node_credentials = bool(node_access_token and node_phone_id)

            if use_node_credentials:
                creds = {
                    "access_token": str(node_access_token).strip(),
                    "phone_number_id": _normalize_phone(node_phone_id),
                    "api_version": str(node_api_version).strip(),
                    "default_recipient_number": str(node_default_recipient or "").strip(),
                }
            else:
                bot_creds = get_whatsapp_credentials_for_bot(session, bot_id)
                if bot_creds.get("access_token") and bot_creds.get("phone_number_id"):
                    creds = {
                        "access_token": bot_creds.get("access_token"),
                        "phone_number_id": _normalize_phone(bot_creds.get("phone_number_id")),
                        "api_version": bot_creds.get("api_version") or "v19.0",
                        "default_recipient_number": bot_creds.get("default_recipient_number") or "",
                    }
                else:
                    creds = _load_whatsapp_credentials_from_db(tenant_id)
        finally:
            try:
                session.close()
            except Exception:
                pass

        if not creds.get("access_token") or not creds.get("phone_number_id"):
            logger.error("whatsappSendMessageNode: Missing DB credentials for tenant_id=%s", tenant_id)
            raise ValueError("whatsappSendMessageNode: Missing DB credentials")

        prev_from = prev_output.get("from")
        configured_recipient = (
            form_data.get("recipient_number")
            or form_data.get("to")
            or form_data.get("send_to")
            or whatsapp_form.get("recipient_number")
            or whatsapp_form.get("to")
            or whatsapp_form.get("send_to")
        )

        trigger_data = inputs if isinstance(inputs, dict) else {}
        cred = None
        if callable(get_tool_credential) and not use_node_credentials:
            try:
                cred = get_tool_credential(
                    tenant_id=tenant_id,
                    tool_name="whatsapp"
                )
            except Exception:
                cred = None

        db_phone = None
        if isinstance(cred, dict):
            db_phone = cred.get("default_recipient_number")
        if not db_phone:
            db_phone = creds.get("default_recipient_number")

        inbound_phone = trigger_data.get("phone") or trigger_data.get("from")
        to_number = inbound_phone if inbound_phone else db_phone
        if isinstance(to_number, str):
            to_number = to_number.strip()

        logger.info("WhatsApp TO number source: %s", "INBOUND" if inbound_phone else ("DB" if db_phone else "UNKNOWN"))

        # Preserve existing fallbacks after primary DB/trigger resolution.
        runtime_recipient = inputs.get("to") or inputs.get("from")
        inferred_recipient = infer_whatsapp_recipient(inputs)
        recipient = _normalize_recipient_e164(
            to_number or prev_from or runtime_recipient or configured_recipient or inferred_recipient
        )

        runtime_body = (
            inputs.get("agent_output")
            or inputs.get("llm_response")
            or prev_output.get("agent_output")
            or prev_output.get("llm_response")
            or prev_output.get("response")
            or prev_output.get("output")
            or inputs.get("response")
            or inputs.get("output")
        )
        configured_body = (
            form_data.get("text")
            or form_data.get("message")
            or form_data.get("body")
            or whatsapp_form.get("text")
            or whatsapp_form.get("message")
            or whatsapp_form.get("body")
        )
        inferred_body = infer_whatsapp_message_text(inputs)
        fallback_body = inputs.get("text") or inputs.get("message") or inputs.get("body")
        body = _pick_first_non_empty_text(runtime_body, configured_body, inferred_body, fallback_body)
        if runtime_body:
            logger.info("[AGENT] reply generated")

        if not recipient:
            raise ValueError("whatsappSendMessageNode: Missing recipient phone number")
        if not body:
            raise ValueError("whatsappSendMessageNode: Missing message body")

        endpoint = (
            f"https://graph.facebook.com/{creds['api_version']}/"
            f"{creds['phone_number_id']}/messages"
        )
        request_payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": body,
            },
        }

        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {creds['access_token']}",
                "Content-Type": "application/json",
            },
            json=request_payload,
            timeout=15,
        )
        if response.status_code >= 300:
            logger.error(
                "whatsappSendMessageNode: Meta API error status=%s body=%s",
                response.status_code,
                response.text,
            )
            raise RuntimeError(f"whatsappSendMessageNode: Meta API error: {response.text}")

        try:
            response_json = response.json()
        except Exception:
            response_json = {"status_code": response.status_code, "text": response.text}

        message_id = None
        try:
            message_id = (response_json.get("messages") or [{}])[0].get("id")
        except Exception:
            message_id = None

        logger.info(
            "[WHATSAPP SEND] sent successfully recipient=%s message_id=%s",
            str(recipient),
            message_id,
        )

        return {
            "status": "success",
            "node": "whatsappSendMessageNode",
            "recipient": str(recipient),
            "message_id": message_id,
            "result": response_json,
        }
