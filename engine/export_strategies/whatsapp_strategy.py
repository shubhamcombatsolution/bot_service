import logging
import re
import base64
import json
from typing import Any, Dict, Optional

import requests
from sqlalchemy import func, or_

from app.database.DatabaseOperationPostgreSQL import db_session
from app.models.bot_diagram import BotDiagram
from app.models.tool_authorization import ToolAuthorization
from app.services.channel_credentials_service import get_whatsapp_credentials_for_bot
from engine.export_strategies.base import IExportStrategy
from engine.export_strategies.factory import ExportStrategyFactory

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


WHATSAPP_TOOL_NAME_HINTS = {
    "whatsapp",
    "whatsappcloudapi",
    "whatsapp_cloud_api",
    "meta_whatsapp",
}

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

WABA_ID_KEYS = (
    "business_account_id",
    "businessAccountId",
    "whatsapp_business_account_id",
    "waba_id",
)

API_VERSION_KEYS = (
    "api_version",
    "apiVersion",
)

def _normalize_phone(value: Optional[str]) -> str:
    if not value:
        return ""
    # Keep digits only; Meta API expects international format without +.
    return re.sub(r"\D", "", str(value))


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


@ExportStrategyFactory.register("whatsapp")
class WhatsAppExportStrategy(IExportStrategy):
    """Send WhatsApp messages using Meta Cloud API credentials."""

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

    def _resolve_phone_number_id_from_waba(
        self,
        access_token: str,
        api_version: str,
        creds_payload: Dict[str, Any],
    ) -> str:
        waba_id = self._pick_first_value(creds_payload, WABA_ID_KEYS)
        if not waba_id:
            return ""

        preferred_phone = _normalize_phone(
            self._pick_first_value(
                creds_payload,
                ("number", "phone_number", "display_phone_number", "phone"),
            )
        )

        endpoint = f"https://graph.facebook.com/{api_version}/{waba_id}/phone_numbers"
        response = requests.get(
            endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )

        if response.status_code >= 300:
            logger.warning(
                "WhatsApp WABA phone number lookup failed [%s]: %s",
                response.status_code,
                response.text,
            )
            return ""

        try:
            data = response.json().get("data") or []
        except Exception:
            data = []

        if not data:
            return ""

        if preferred_phone:
            for phone_item in data:
                display_phone = _normalize_phone(phone_item.get("display_phone_number"))
                if not display_phone:
                    continue
                if preferred_phone.endswith(display_phone) or display_phone.endswith(preferred_phone):
                    return str(phone_item.get("id") or "")

        return str((data[0] or {}).get("id") or "")

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
        node_access_token = self._pick_first_value(form_data, ACCESS_TOKEN_KEYS)
        node_phone_id = self._pick_first_value(form_data, PHONE_NUMBER_ID_KEYS)
        node_api_version = self._pick_first_value(form_data, API_VERSION_KEYS) or "v19.0"
        if node_access_token and node_phone_id:
            return {
                "access_token": node_access_token,
                "phone_number_id": str(node_phone_id),
                "api_version": str(node_api_version),
            }

        session = next(db_session())
        try:
            bot_creds = get_whatsapp_credentials_for_bot(session, self._resolve_bot_id(form_data))
            if bot_creds.get("access_token") and bot_creds.get("phone_number_id"):
                return {
                    "access_token": bot_creds.get("access_token"),
                    "phone_number_id": str(bot_creds.get("phone_number_id")),
                    "api_version": str(bot_creds.get("api_version") or "v19.0"),
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
                        func.lower(ToolAuthorization.tool_name) == "whatsapp",
                        func.lower(ToolAuthorization.tool_name).like("%whatsapp%"),
                    ),
                    ToolAuthorization.del_flag.is_(False),
                )
                .order_by(ToolAuthorization.updated_at.desc())
                .all()
            )

            if not auth_rows:
                raise ValueError("WhatsApp DB credentials not found for tenant")

            for auth in auth_rows:
                normalized_tool_name = self._normalize_tool_name(auth.tool_name)
                if (
                    normalized_tool_name not in WHATSAPP_TOOL_NAME_HINTS
                    and "whatsapp" not in normalized_tool_name
                ):
                    continue

                creds = self._flatten_credentials_payload(auth.token_json)

                access_token = self._pick_first_value(creds, ACCESS_TOKEN_KEYS)
                api_version = self._pick_first_value(creds, API_VERSION_KEYS) or "v19.0"
                phone_number_id = self._pick_first_value(creds, PHONE_NUMBER_ID_KEYS)

                if not phone_number_id and access_token:
                    phone_number_id = self._resolve_phone_number_id_from_waba(
                        access_token=access_token,
                        api_version=str(api_version),
                        creds_payload=creds,
                    )

                if access_token and phone_number_id:
                    return {
                        "access_token": access_token,
                        "phone_number_id": str(phone_number_id),
                        "api_version": str(api_version),
                    }

            raise ValueError(
                "WhatsApp DB credentials found but required fields are missing "
                "(access_token and phone_number_id)."
            )
        finally:
            try:
                session.close()
            except Exception:
                pass

    def _messages_endpoint(self, creds: Dict[str, Any]) -> str:
        return (
            f"https://graph.facebook.com/{creds['api_version']}/"
            f"{creds['phone_number_id']}/messages"
        )

    def _media_upload_endpoint(self, creds: Dict[str, Any]) -> str:
        return (
            f"https://graph.facebook.com/{creds['api_version']}/"
            f"{creds['phone_number_id']}/media"
        )

    def _media_item_endpoint(self, creds: Dict[str, Any], media_id: str) -> str:
        return f"https://graph.facebook.com/{creds['api_version']}/{media_id}"

    def _auth_headers(self, creds: Dict[str, Any], with_json: bool = True) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {creds['access_token']}"}
        if with_json:
            headers["Content-Type"] = "application/json"
        return headers

    def _request_json(
        self,
        method: str,
        endpoint: str,
        creds: Dict[str, Any],
        *,
        json_payload: Optional[Dict[str, Any]] = None,
        data_payload: Optional[Dict[str, Any]] = None,
        files_payload: Optional[Dict[str, Any]] = None,
        timeout: int = 15,
    ) -> Dict[str, Any]:
        with_json = files_payload is None
        response = requests.request(
            method=method,
            url=endpoint,
            headers=self._auth_headers(creds, with_json=with_json),
            json=json_payload,
            data=data_payload,
            files=files_payload,
            timeout=timeout,
        )

        if response.status_code >= 300:
            logger.error("WhatsApp API call failed [%s]: %s", response.status_code, response.text)
            raise RuntimeError(f"WhatsApp API call failed: {response.text}")

        try:
            return response.json()
        except ValueError:
            return {"status_code": response.status_code, "text": response.text}

    def send(self, tenant_id: str, form_data: Dict[str, Any], jwt: Optional[str] = None) -> Dict[str, Any]:
        creds = self._load_credentials(tenant_id, form_data=form_data)

        to_raw = form_data.get("to") or form_data.get("send_to")
        to = _normalize_phone(to_raw)
        if not to:
            raise ValueError("'to' (recipient phone number) is required for WhatsApp export")

        body = form_data.get("body") or form_data.get("message") or ""
        template_name = form_data.get("template_name")
        media_id = form_data.get("media_id")

        if not body and not template_name and not media_id:
            raise ValueError("Either 'body' text or 'template_name' is required for WhatsApp export")

        endpoint = self._messages_endpoint(creds)

        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
        }

        if template_name:
            language_code = form_data.get("template_language") or "en_US"
            payload.update(
                {
                    "type": "template",
                    "template": {
                        "name": template_name,
                        "language": {"code": language_code},
                    },
                }
            )
        elif media_id:
            media_type = str(form_data.get("media_type") or "image").strip().lower()
            caption = form_data.get("caption") or body
            payload.update(
                {
                    "type": media_type,
                    media_type: {
                        "id": str(media_id),
                    },
                }
            )
            if caption and media_type in {"image", "video", "document"}:
                payload[media_type]["caption"] = str(caption)
        else:
            payload.update(
                {
                    "type": "text",
                    "text": {
                        "preview_url": _as_bool(form_data.get("preview_url"), default=False),
                        "body": body,
                    },
                }
            )

        response_json = self._request_json("POST", endpoint, creds, json_payload=payload, timeout=15)
        message_id = None
        try:
            message_id = (response_json.get("messages") or [{}])[0].get("id")
        except Exception:
            message_id = None

        wait_for_reply = _as_bool(form_data.get("wait_for_reply"), default=False)
        if wait_for_reply:
            return {
                "status": "waiting",
                "channel": "whatsapp",
                "to": to,
                "message_id": message_id,
                "wait_for_reply": True,
                "await": {
                    "type": "whatsapp_reply",
                    "from": to,
                },
                "response": response_json,
            }

        return {
            "status": "success",
            "channel": "whatsapp",
            "to": to,
            "message_id": message_id,
            "response": response_json,
        }

    def upload_media(self, tenant_id: str, form_data: Dict[str, Any]) -> Dict[str, Any]:
        creds = self._load_credentials(tenant_id, form_data=form_data)

        file_path = form_data.get("file_path") or form_data.get("path")
        if not file_path:
            raise ValueError("'file_path' is required for WhatsApp media upload")

        file_path = os.path.abspath(str(file_path))
        if not os.path.exists(file_path):
            raise ValueError(f"Media file not found: {file_path}")

        mime_type = form_data.get("mime_type") or "application/octet-stream"
        endpoint = self._media_upload_endpoint(creds)

        with open(file_path, "rb") as file_handle:
            response_json = self._request_json(
                "POST",
                endpoint,
                creds,
                data_payload={
                    "messaging_product": "whatsapp",
                    "type": mime_type,
                },
                files_payload={
                    "file": (os.path.basename(file_path), file_handle, mime_type),
                },
                timeout=30,
            )

        media_id = response_json.get("id")
        return {
            "status": "success",
            "channel": "whatsapp",
            "operation": "upload_media",
            "media_id": media_id,
            "response": response_json,
        }

    def download_media(self, tenant_id: str, form_data: Dict[str, Any]) -> Dict[str, Any]:
        creds = self._load_credentials(tenant_id, form_data=form_data)

        media_id = form_data.get("media_id")
        if not media_id:
            raise ValueError("'media_id' is required for WhatsApp media download")

        media_meta = self._request_json(
            "GET",
            self._media_item_endpoint(creds, str(media_id)),
            creds,
            timeout=15,
        )

        download_url = media_meta.get("url")
        if not download_url:
            raise RuntimeError("WhatsApp media metadata response is missing download URL")

        media_response = requests.get(
            download_url,
            headers=self._auth_headers(creds, with_json=False),
            timeout=30,
        )

        if media_response.status_code >= 300:
            raise RuntimeError(f"WhatsApp media download failed: {media_response.text}")

        payload: Dict[str, Any] = {
            "status": "success",
            "channel": "whatsapp",
            "operation": "download_media",
            "media_id": str(media_id),
            "mime_type": media_meta.get("mime_type"),
            "bytes": len(media_response.content),
            "metadata": media_meta,
        }

        save_to = form_data.get("save_to")
        if save_to:
            save_path = os.path.abspath(str(save_to))
            parent = os.path.dirname(save_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            with open(save_path, "wb") as output_file:
                output_file.write(media_response.content)

            payload["saved_to"] = save_path

        if _as_bool(form_data.get("return_base64"), default=False):
            payload["content_base64"] = base64.b64encode(media_response.content).decode("ascii")

        return payload

    def delete_media(self, tenant_id: str, form_data: Dict[str, Any]) -> Dict[str, Any]:
        creds = self._load_credentials(tenant_id, form_data=form_data)

        media_id = form_data.get("media_id")
        if not media_id:
            raise ValueError("'media_id' is required for WhatsApp media delete")

        response_json = self._request_json(
            "DELETE",
            self._media_item_endpoint(creds, str(media_id)),
            creds,
            timeout=15,
        )

        return {
            "status": "success",
            "channel": "whatsapp",
            "operation": "delete_media",
            "media_id": str(media_id),
            "response": response_json,
        }
