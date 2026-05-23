import json
import logging
from typing import Any, Dict, Optional

import requests
from sqlalchemy import func, or_

from app.database.DatabaseOperationPostgreSQL import db_session
from app.models.bot_diagram import BotDiagram
from app.models.tool_authorization import ToolAuthorization
from app.services.channel_credentials_service import get_slack_credentials_for_bot
from engine.export_strategies.base import IExportStrategy
from engine.export_strategies.factory import ExportStrategyFactory

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


SLACK_TOOL_NAME_HINTS = {
    "slack",
    "slackapi",
    "slack_api",
    "slackapp",
}

BOT_TOKEN_KEYS = (
    "bot_token",
    "xoxb_token",
    "access_token",
    "token",
)

DEFAULT_CHANNEL_KEYS = (
    "channel_id",
    "default_channel_id",
    "channel",
)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


@ExportStrategyFactory.register("slack")
class SlackExportStrategy(IExportStrategy):
    """Send Slack messages using tenant-scoped bot credentials."""

    def _safe_dict(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def _pick_first_value(self, payload: Dict[str, Any], keys) -> str:
        for key in keys:
            value = payload.get(key)
            if value is not None and str(value).strip() != "":
                return str(value).strip()
        return ""

    def _normalize_tool_name(self, name: Any) -> str:
        if not name:
            return ""
        normalized = str(name).strip().lower()
        normalized = normalized.replace(" ", "").replace("-", "").replace("_", "")
        return normalized

    def _flatten_credentials_payload(self, raw_payload: Any) -> Dict[str, Any]:
        root = self._safe_dict(raw_payload)
        merged: Dict[str, Any] = dict(root)

        nested_keys = ("credentials", "token_json", "data", "auth")
        for key in nested_keys:
            nested = self._safe_dict(root.get(key))
            if nested:
                merged.update(nested)

        return merged

    def _resolve_bot_id(self, form_data: Dict[str, Any]) -> Optional[int]:
        for key in ("bot_id", "botId"):
            value = form_data.get(key)
            if value not in (None, ""):
                try:
                    return int(value)
                except Exception:
                    pass
        diagram_id = form_data.get("diagram_id") or form_data.get("workflow_id")
        if diagram_id not in (None, ""):
            session = next(db_session())
            try:
                diagram = session.query(BotDiagram).filter(BotDiagram.diagram_id == int(diagram_id)).first()
                if diagram and diagram.bot_id:
                    return int(diagram.bot_id)
            except Exception:
                return None
            finally:
                try:
                    session.close()
                except Exception:
                    pass
        return None

    def _load_credentials(self, tenant_id: str, form_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        form_data = form_data or {}
        node_token = str(
            form_data.get("bot_token") or form_data.get("xoxb_token") or form_data.get("access_token") or ""
        ).strip()
        if node_token:
            return {
                "bot_token": node_token,
                "default_channel_id": str(
                    form_data.get("channel_id") or form_data.get("default_channel_id") or form_data.get("channel") or ""
                ).strip(),
            }

        session = next(db_session())
        try:
            bot_creds = get_slack_credentials_for_bot(session, self._resolve_bot_id(form_data))
            if bot_creds.get("bot_token"):
                return {
                    "bot_token": bot_creds.get("bot_token"),
                    "default_channel_id": bot_creds.get("default_channel_id") or "",
                }
        finally:
            try:
                session.close()
            except Exception:
                pass

        session = next(db_session())
        try:
            auth_rows = (
                session.query(ToolAuthorization)
                .filter(
                    ToolAuthorization.tenant_id == int(tenant_id),
                    or_(
                        func.lower(ToolAuthorization.tool_name) == "slack",
                        func.lower(ToolAuthorization.tool_name).like("%slack%"),
                    ),
                    ToolAuthorization.del_flag.is_(False),
                )
                .order_by(ToolAuthorization.updated_at.desc())
                .all()
            )

            if not auth_rows:
                raise ValueError("Slack credentials not found for tenant")

            for auth in auth_rows:
                normalized_tool_name = self._normalize_tool_name(auth.tool_name)
                if (
                    normalized_tool_name not in SLACK_TOOL_NAME_HINTS
                    and "slack" not in normalized_tool_name
                ):
                    continue

                creds = self._flatten_credentials_payload(auth.token_json)
                bot_token = self._pick_first_value(creds, BOT_TOKEN_KEYS)
                default_channel = self._pick_first_value(creds, DEFAULT_CHANNEL_KEYS)

                if bot_token:
                    return {
                        "bot_token": bot_token,
                        "default_channel_id": default_channel,
                    }

            raise ValueError("Slack credentials found but bot token is missing")
        finally:
            try:
                session.close()
            except Exception:
                pass

    def _request_json(self, endpoint_name: str, creds: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = f"https://slack.com/api/{endpoint_name}"
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {creds['bot_token']}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
            timeout=15,
        )

        if response.status_code >= 300:
            logger.error("Slack API call failed [%s]: %s", response.status_code, response.text)
            raise RuntimeError(f"Slack API call failed: {response.text}")

        try:
            response_json = response.json()
        except ValueError:
            raise RuntimeError("Slack API response is not valid JSON")

        if not response_json.get("ok"):
            error_code = response_json.get("error") or "unknown_error"
            raise RuntimeError(f"Slack API call failed: {error_code}")

        return response_json

    def send(self, tenant_id: str, form_data: Dict[str, Any], jwt: Optional[str] = None) -> Dict[str, Any]:
        creds = self._load_credentials(tenant_id, form_data=form_data)

        channel = str(
            form_data.get("channel_id")
            or form_data.get("channel")
            or form_data.get("to")
            or creds.get("default_channel_id")
            or ""
        ).strip()
        if not channel:
            raise ValueError("'channel_id' is required for Slack export")

        text = form_data.get("text") or form_data.get("message") or form_data.get("body")
        blocks = form_data.get("blocks")

        if not text and not blocks:
            raise ValueError("Either 'text' or 'blocks' is required for Slack export")

        payload: Dict[str, Any] = {
            "channel": channel,
        }

        if text:
            payload["text"] = str(text)

        if isinstance(blocks, (dict, list)):
            payload["blocks"] = blocks

        thread_ts = form_data.get("thread_ts") or form_data.get("thread")
        if thread_ts:
            payload["thread_ts"] = str(thread_ts)

        if "reply_broadcast" in form_data:
            payload["reply_broadcast"] = _as_bool(form_data.get("reply_broadcast"), default=False)

        response_json = self._request_json("chat.postMessage", creds, payload)

        message_ts = str(response_json.get("ts") or "")
        response_channel = str(response_json.get("channel") or channel)

        wait_for_reply = _as_bool(form_data.get("wait_for_reply"), default=False)
        if wait_for_reply:
            expected_user = str(
                form_data.get("expected_user")
                or form_data.get("user_id")
                or ""
            ).strip()

            tracking_key = response_channel if not expected_user else f"{response_channel}:{expected_user}"

            return {
                "status": "waiting",
                "channel": "slack",
                "channel_id": response_channel,
                "message_ts": message_ts,
                "wait_for_reply": True,
                "await": {
                    "type": "slack_reply",
                    "channel": response_channel,
                    "user": expected_user or None,
                    "thread_ts": message_ts or str(thread_ts or ""),
                },
                "tracking_key": tracking_key,
                "tracking_type": "slack_channel_user",
                "response": response_json,
            }

        return {
            "status": "success",
            "channel": "slack",
            "channel_id": response_channel,
            "message_ts": message_ts,
            "response": response_json,
        }
