from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.slack_cred import SlackCred
from app.models.tool_authorization import ToolAuthorization
from app.models.whatsapp_cred import WhatsAppCred


def _normalize_tool_name(value: str) -> str:
    text = (value or "").strip().lower()
    return text.replace("jnanic_mcp_", "").replace("_", "").replace("-", "").replace(" ", "")


def _tool_aliases(tool_name: str) -> set[str]:
    base = _normalize_tool_name(tool_name)
    aliases = {base}
    alias_map = {
        "gcalendar": {"calendar", "googlecalendar"},
        "calendar": {"gcalendar", "googlecalendar"},
        "gsheets": {"sheets", "googlesheets"},
        "sheets": {"gsheets", "googlesheets"},
        "gmail": {"googlemail"},
        "gmaps": {"maps", "googlemaps"},
        "maps": {"gmaps", "googlemaps"},
    }
    for key, mapped in alias_map.items():
        if base == key:
            aliases.update(mapped)
    return aliases


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


# def _flatten_auth_payload(raw_payload: Any) -> Dict[str, Any]:
#     root = _safe_dict(raw_payload)
#     merged = dict(root)
#     for key in ("credentials", "token_json", "data", "auth"):
#         nested = _safe_dict(root.get(key))
#         if nested:
#             merged.update(nested)
#     return merged
def _flatten_auth_payload(raw_payload: Any) -> Dict[str, Any]:
    """
    Deterministic normalization:
    1) Prefer the first payload shape that actually contains token/access_token.
    2) If none has token fields, return a stable merged fallback.
    """
    root = _safe_dict(raw_payload)
    candidates = [
        root,
        _safe_dict(root.get("credentials")),
        _safe_dict(root.get("token_json")),
        _safe_dict(root.get("data")),
        _safe_dict(root.get("auth")),
    ]

    for c in candidates:
        if c.get("token") or c.get("access_token"):
            return c

    merged: Dict[str, Any] = {}
    for c in candidates:
        if c:
            merged.update(c)
    return merged


def get_whatsapp_credentials_for_bot(session: Session, bot_id: Optional[int]) -> Dict[str, Any]:
    if not bot_id:
        return {}

    cred = session.query(WhatsAppCred).filter(WhatsAppCred.bot_id == int(bot_id)).first()
    if not cred:
        return {}

    return {
        "access_token": cred.access_token or "",
        "phone_number_id": cred.phone_number_id or "",
        "business_account_id": cred.business_account_id or "",
        "verify_token": cred.verify_token or "",
        "api_version": cred.graph_api_version or "v19.0",
        "graph_api_version": cred.graph_api_version or "v19.0",
        "default_recipient_number": cred.default_recipient_number or "",
    }


def get_slack_credentials_for_bot(session: Session, bot_id: Optional[int]) -> Dict[str, Any]:
    if not bot_id:
        return {}

    cred = session.query(SlackCred).filter(SlackCred.bot_id == int(bot_id)).first()
    if not cred:
        return {}

    return {
        "bot_token": cred.bot_token or "",
        "signing_secret": cred.signing_secret or "",
        "app_token": cred.app_token or "",
        "default_channel_id": cred.default_channel_id or "",
        "channel_id": cred.default_channel_id or "",
    }


def get_legacy_tool_credentials(session: Session, tenant_id: Optional[int], tool_name: str) -> Dict[str, Any]:
    if not tenant_id:
        return {}

    aliases = _tool_aliases(tool_name)
    auth_rows = (
        session.query(ToolAuthorization)
        .filter(
            ToolAuthorization.tenant_id == int(tenant_id),
            ToolAuthorization.del_flag.is_(False),
        )
        .order_by(ToolAuthorization.updated_at.desc())
        .all()
    )

    for auth in auth_rows:
        normalized = _normalize_tool_name(getattr(auth, "tool_name", ""))
        if normalized not in aliases:
            continue

        creds = _flatten_auth_payload(auth.token_json)
        if creds.get("token") or creds.get("access_token"):
            return creds

    return {}
