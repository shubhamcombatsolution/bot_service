# import logging
# from datetime import datetime
# from typing import Dict, Any, List
# from flask import Blueprint, request, jsonify
# from sqlalchemy.orm import Session

# from app.database.DatabaseOperationPostgreSQL import db_session
# from app.models.workflow_trigger import WorkflowTrigger
# from app.models.bot_diagram import BotDiagram
# from engine.workflow_executor import WorkflowExecutor

# logger = logging.getLogger("WebhookRoutes")

# webhook_bp = Blueprint('webhook', __name__)


# def _load_workflow_diagram(session: Session, bot_id: int, flow_id: int) -> Dict[str, Any]:
#     """Load the workflow diagram from database."""
#     diagram = (
#         session.query(BotDiagram)
#         .filter_by(bot_id=bot_id, diagram_id=flow_id)
#         .first()
#     )
    
#     if not diagram:
#         raise ValueError(f"No workflow diagram found for bot_id={bot_id}, flow_id={flow_id}")
    
#     import json
#     return json.loads(diagram.diagram_json)


# def _format_webhook_event(payload: Dict[str, Any], trigger: WorkflowTrigger) -> Dict[str, Any]:
#     """
#     Format incoming webhook payload into standardized event structure.
#     Similar to Gmail event format for consistency.
#     """
#     return {
#         "trigger_type": "webhook",
#         "source": "external_webhook",
#         "event": payload.get("event", "webhook.received"),
#         "metadata": {
#             "trigger_id": trigger.id,
#             "trigger_node_id": trigger.trigger_node_id,
#             "timestamp": payload.get("timestamp") or datetime.utcnow().isoformat() + "Z",
#             "webhook_name": trigger.raw_trigger_json.get("webhook_name") if trigger.raw_trigger_json else None,
#         },
#         "payload": payload,  # Original webhook payload
#         "context": {
#             "tenant_id": trigger.tenant_id,
#             "bot_id": trigger.bot_id,
#             "flow_id": trigger.flow_id,
#             "trigger_type": trigger.trigger_type
#         }
#     }


# @webhook_bp.route('/webhook/<trigger_node_id>', methods=['POST'])
# def receive_webhook(trigger_node_id: str):
#     """
#     Generic webhook endpoint that can trigger any workflow.
    
#     POST /webhook/<trigger_node_id>
#     Body: Any JSON payload
    
#     Example for Supplier Selection:
#     POST /webhook/supplier-select-123
#     {
#         "event": "supplier.selected",
#         "rfq_id": 56,
#         "supplier_id": 2001,
#         "supplier_email": "abc@gmail.com",
#         "name": "ABC Pvt Ltd"
#     }
#     """
#     session = None
    
#     try:
#         # Get webhook payload
#         if not request.is_json:
#             return jsonify({
#                 "status": "error",
#                 "message": "Request must be JSON"
#             }), 400
        
#         payload = request.get_json()
#         logger.info(f"[WEBHOOK] Received webhook for trigger_node_id={trigger_node_id}")
#         logger.debug(f"[WEBHOOK] Payload: {payload}")
        
#         # Find the trigger in database
#         session = next(db_session())
        
#         trigger = (
#             session.query(WorkflowTrigger)
#             .filter_by(trigger_node_id=trigger_node_id, status="active")
#             .first()
#         )
        
#         if not trigger:
#             logger.error(f"[WEBHOOK] No active trigger found for trigger_node_id={trigger_node_id}")
#             return jsonify({
#                 "status": "error",
#                 "message": f"No active webhook trigger found for node: {trigger_node_id}"
#             }), 404
        
#         # Verify it's a webhook trigger
#         if trigger.trigger_type != "webhook":
#             logger.error(f"[WEBHOOK] Trigger {trigger.id} is not a webhook trigger (type: {trigger.trigger_type})")
#             return jsonify({
#                 "status": "error",
#                 "message": f"Trigger is not a webhook trigger (type: {trigger.trigger_type})"
#             }), 400
        
#         # Format the webhook event
#         webhook_event = _format_webhook_event(payload, trigger)
        
#         # Load workflow diagram
#         workflow_json = _load_workflow_diagram(session, trigger.bot_id, trigger.flow_id)
        
#         # Inject required metadata
#         workflow_json.update({
#             "bot_id": trigger.bot_id,
#             "tenant_id": trigger.tenant_id,
#             "trigger_id": trigger.id,
#             "trigger_type": trigger.trigger_type,
#             "diagram_id": trigger.flow_id
#         })
        
#         # Prepare trigger data with prefetched event
#         trigger_data = {
#             trigger_node_id: {
#                 "tenant_id": trigger.tenant_id,
#                 "prefetched_events": [webhook_event]
#             }
#         }
        
#         logger.info(f"[WEBHOOK] Starting workflow execution for trigger_id={trigger.id}, bot_id={trigger.bot_id}")
        
#         # Execute workflow
#         executor = WorkflowExecutor(workflow_json)
#         executor.session_ref = session  # Reuse existing session
        
#         result = executor.execute(
#             trigger_data=trigger_data,
#             return_context=True
#         )
        
#         # Finalize execution record
#         if hasattr(executor, 'execution_db_id'):
#             executor.finalize_execution_record(result)
        
#         # Commit the session
#         session.commit()
        
#         logger.info(f"[WEBHOOK] Workflow execution completed for trigger_id={trigger.id}, "
#                    f"executed_nodes={result.executed_nodes}/{result.total_nodes}, "
#                    f"status={result.to_dict().get('status')}")
        
#         return jsonify({
#             "status": "success",
#             "message": "Webhook received and workflow executed",
#             "trigger_id": trigger.id,
#             "execution_id": executor.execution_db_id if hasattr(executor, 'execution_db_id') else None,
#             "executed_nodes": result.executed_nodes,
#             "total_nodes": result.total_nodes,
#             "workflow_status": result.to_dict().get('status')
#         }), 200
        
#     except ValueError as ve:
#         logger.error(f"[WEBHOOK] Configuration error: {ve}")
#         if session:
#             session.rollback()
#         return jsonify({
#             "status": "error",
#             "message": str(ve)
#         }), 400
        
#     except Exception as e:
#         logger.exception(f"[WEBHOOK] Error processing webhook: {e}")
#         if session:
#             session.rollback()
#         return jsonify({
#             "status": "error",
#             "message": "Internal server error processing webhook",
#             "error": str(e)
#         }), 500
        
#     finally:
#         if session:
#             session.close()


# @webhook_bp.route('/webhook/<trigger_node_id>/info', methods=['GET'])
# def get_webhook_info(trigger_node_id: str):
#     """
#     Get information about a webhook trigger.
#     Useful for testing and debugging.
#     """
#     session = None
    
#     try:
#         session = next(db_session())
        
#         trigger = (
#             session.query(WorkflowTrigger)
#             .filter_by(trigger_node_id=trigger_node_id)
#             .first()
#         )
        
#         if not trigger:
#             return jsonify({
#                 "status": "error",
#                 "message": f"No webhook trigger found for node: {trigger_node_id}"
#             }), 404
        
#         return jsonify({
#             "status": "success",
#             "trigger": {
#                 "id": trigger.id,
#                 "trigger_node_id": trigger.trigger_node_id,
#                 "trigger_type": trigger.trigger_type,
#                 "status": trigger.status,
#                 "bot_id": trigger.bot_id,
#                 "flow_id": trigger.flow_id,
#                 "tenant_id": trigger.tenant_id,
#                 "webhook_name": trigger.raw_trigger_json.get("webhook_name") if trigger.raw_trigger_json else None,
#                 "created_at": trigger.created_at.isoformat() if hasattr(trigger, 'created_at') else None
#             }
#         }), 200
        
#     except Exception as e:
#         logger.exception(f"[WEBHOOK] Error getting webhook info: {e}")
#         return jsonify({
#             "status": "error",
#             "message": "Error retrieving webhook information",
#             "error": str(e)
#         }), 500
        
#     finally:
#         if session:
#             session.close()

# @webhook_bp.route('/webhooks/<int:bot_id>', methods=['GET'])
# def get_all_webhooks_for_bot(bot_id: int):
#     """
#     Get all webhook triggers for a specific bot.
    
#     GET /webhook/webhooks/<bot_id>
    
#     Example: GET /webhook/webhooks/981
#     """
#     session = None
    
#     try:
#         session = next(db_session())
        
#         # Get all active webhook triggers for this bot
#         webhook_triggers = session.query(WorkflowTrigger).filter_by(
#             bot_id=bot_id,
#             trigger_type='webhook',
#             status='active'
#         ).all()
        
#         if not webhook_triggers:
#             return jsonify({
#                 "status": "success",
#                 "data": {
#                     "bot_id": bot_id,
#                     "webhooks": [],
#                     "count": 0
#                 },
#                 "message": "No webhook triggers found for this bot"
#             }), 200
        
#         # Format response with full webhook URLs
#         base_url = request.host_url.rstrip('/')
#         webhooks = []
        
#         for trigger in webhook_triggers:
#             webhook_data = {
#                 "trigger_id": trigger.id,
#                 "trigger_node_id": trigger.trigger_node_id,
#                 "webhook_name": trigger.raw_trigger_json.get('webhook_name') if trigger.raw_trigger_json else None,
#                 "webhook_url": f"{base_url}/webhook/{trigger.trigger_node_id}",
#                 "flow_id": trigger.flow_id,
#                 "tenant_id": trigger.tenant_id,
#                 "status": trigger.status,
#                 "created_at": trigger.created_at.isoformat() if hasattr(trigger, 'created_at') else None,
#                 "event_filter": trigger.raw_trigger_json.get('event_filter', {}) if trigger.raw_trigger_json else {},
#                 "field_mapping": trigger.raw_trigger_json.get('field_mapping', {}) if trigger.raw_trigger_json else {}
#             }
#             webhooks.append(webhook_data)
        
#         logger.info(f"[WEBHOOK] Found {len(webhooks)} webhook(s) for bot_id={bot_id}")
        
#         return jsonify({
#             "status": "success",
#             "data": {
#                 "bot_id": bot_id,
#                 "webhooks": webhooks,
#                 "count": len(webhooks)
#             }
#         }), 200
        
#     except Exception as e:
#         logger.exception(f"[WEBHOOK] Error getting webhooks for bot_id={bot_id}: {e}")
#         return jsonify({
#             "status": "error",
#             "message": "Error retrieving webhooks",
#             "error": str(e)
#         }), 500
        
#     finally:
#         if session:
#             session.close()
import logging
import hashlib
import hmac
import json
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from flask import Blueprint, request, jsonify
from sqlalchemy.orm import Session

from app.database.DatabaseOperationPostgreSQL import db_session
from app.models.workflow_trigger import WorkflowTrigger
from app.models.bot_diagram import BotDiagram
from app.models.tool_authorization import ToolAuthorization
from app.models.processed_trigger_event import ProcessedTriggerEvent
from app.models.workflow_wait_state import WorkflowWaitState
from engine.workflow_executor import WorkflowExecutor
from engine.triggers.trigger_service import enqueue_trigger
from sqlalchemy import text, func, or_
from app.services.channel_credentials_service import (
    get_legacy_tool_credentials,
    get_slack_credentials_for_bot,
    get_whatsapp_credentials_for_bot,
)
from logging_config import setup_logging

logger = setup_logging("WebhookRoutes", level="DEBUG")
webhook_bp = Blueprint('webhook', __name__)
_webhook_redis_client = None


def _load_workflow_diagram(
    session: Session,
    diagram_id: int,
    tenant_id: Optional[int] = None,
    trigger_bot_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Load workflow by diagram_id with tenant/bot scoping when provided."""
    logger.info(
        "[FLOW_TRACE][WEBHOOK][DIAGRAM_LOAD_REQUEST] diagram_id=%s tenant_id=%s bot_id=%s",
        diagram_id,
        tenant_id,
        trigger_bot_id,
    )
    query = session.query(BotDiagram).filter(BotDiagram.diagram_id == diagram_id)
    if tenant_id is not None:
        query = query.filter(BotDiagram.tenant_id == tenant_id)
    if trigger_bot_id is not None:
        # Prefer exact bot binding; allow legacy null bot_id rows and backfill below.
        query = query.filter(
            or_(BotDiagram.bot_id == trigger_bot_id, BotDiagram.bot_id.is_(None))
        )

    diagram = query.first()

    if not diagram:
        raise ValueError(
            f"No workflow diagram found for diagram_id={diagram_id}, "
            f"tenant_id={tenant_id}, bot_id={trigger_bot_id}"
        )

    logger.info(
        "[FLOW_TRACE][WEBHOOK][DIAGRAM_SELECTED] diagram_id=%s tenant_id=%s bot_id=%s db_bot_id=%s status=%s del_flg=%s",
        diagram.diagram_id,
        diagram.tenant_id,
        trigger_bot_id,
        diagram.bot_id,
        getattr(diagram, "status", None),
        getattr(diagram, "del_flg", None),
    )

    if diagram.bot_id is None and trigger_bot_id is not None:
        # Runtime-only binding: do NOT persist here.
        # Persisting can fail when trigger.bot_id is stale/invalid (FK violation)
        # and should not block webhook execution.
        logger.info(
            "[WEBHOOK_BINDING] diagram_id=%s has null db_bot_id; using runtime bot_id=%s (no DB backfill)",
            diagram_id,
            trigger_bot_id,
        )

    import json
    return json.loads(diagram.diagram_json)


def _format_webhook_event(payload: Dict[str, Any], trigger: WorkflowTrigger) -> Dict[str, Any]:
    """Standardize webhook input event format."""
    return {
        "trigger_type": "webhook",
        "source": "external_webhook",
        "event": payload.get("event", "webhook.received"),
        "metadata": {
            "trigger_id": trigger.id,
            "trigger_node_id": trigger.trigger_node_id,
            "timestamp": payload.get("timestamp") or datetime.utcnow().isoformat() + "Z",
            "webhook_name": trigger.raw_trigger_json.get("webhook_name") if trigger.raw_trigger_json else None,
        },
        "payload": payload,
        "context": {
            "tenant_id": trigger.tenant_id,
            "bot_id": trigger.bot_id,
            "flow_id": trigger.flow_id,
            "trigger_type": trigger.trigger_type
        }
    }


def _normalize_phone(value: Any) -> str:
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def _extract_whatsapp_input_data(payload: Dict[str, Any], events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Extract n8n-style primary WhatsApp fields from Meta payload.
    Target path: entry[0].changes[0].value.messages[0]
    """
    input_data: Dict[str, Any] = {}

    if isinstance(payload, dict):
        entry = payload.get("entry") or []
        changes = entry[0].get("changes") if entry else []
        value = changes[0].get("value") if changes else {}
        messages = value.get("messages") or []

        if messages:
            message = messages[0]
            from_phone = _normalize_phone(message.get("from"))
            text_body = (
                (message.get("text") or {}).get("body")
                or (message.get("interactive") or {}).get("button_reply", {}).get("title")
                or (message.get("interactive") or {}).get("list_reply", {}).get("title")
                or ""
            ).strip()

            if text_body and from_phone:
                input_data = {
                    "from": from_phone,
                    "phone": from_phone,
                    "message": text_body,
                    "user_query": text_body,
                    "message_id": message.get("id"),
                    "timestamp": message.get("timestamp"),
                }

    if not input_data and events:
        first_event = events[0] if events else {}
        metadata = (first_event or {}).get("metadata") or {}
        message = (
            (first_event or {}).get("message")
            or (first_event or {}).get("user_query")
            or ((first_event or {}).get("content") or {}).get("text")
            or ""
        )
        if not isinstance(message, str):
            message = str(message or "")

        input_data = {
            "from": _normalize_phone(metadata.get("from_phone") or metadata.get("from")),
            "message": message.strip(),
            "user_query": message.strip(),
            "message_id": metadata.get("message_id"),
            "timestamp": metadata.get("timestamp"),
        }

    if not input_data:
        return {}

    if not input_data.get("user_query"):
        input_data["user_query"] = input_data.get("message") or ""

    return input_data


def _safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _flatten_auth_payload(raw_payload: Any) -> Dict[str, Any]:
    root = _safe_dict(raw_payload)
    merged: Dict[str, Any] = dict(root)

    for key in ("credentials", "token_json", "data", "auth"):
        nested = _safe_dict(root.get(key))
        if nested:
            merged.update(nested)

    return merged


def _resolve_whatsapp_verify_token(session: Session, trigger: WorkflowTrigger) -> str:
    """Resolve verify token from bot-specific creds, then legacy global creds."""
    raw_cfg = trigger.raw_trigger_json or {}
    nested_cfg = raw_cfg.get("whatsapp") if isinstance(raw_cfg.get("whatsapp"), dict) else {}
    for key in ("verify_token", "verifyToken"):
        value = raw_cfg.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
        nested_value = nested_cfg.get(key)
        if nested_value is not None and str(nested_value).strip():
            return str(nested_value).strip()

    bot_creds = get_whatsapp_credentials_for_bot(session, trigger.bot_id)
    token = bot_creds.get("verify_token")
    if token:
        return str(token)

    token_payload = get_legacy_tool_credentials(session, trigger.tenant_id, "whatsapp")
    token = token_payload.get("verify_token") or token_payload.get("verifyToken")
    if token:
        return str(token)
    return ""


def _resolve_whatsapp_phone_number_id(session: Session, trigger: WorkflowTrigger) -> str:
    """Resolve WhatsApp phone_number_id from node config first, then bot creds."""
    raw_cfg = trigger.raw_trigger_json or {}
    nested_cfg = raw_cfg.get("whatsapp") if isinstance(raw_cfg.get("whatsapp"), dict) else {}
    for key in ("phone_number_id", "phoneNumberId", "business_phone_number_id"):
        value = raw_cfg.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
        nested_value = nested_cfg.get(key)
        if nested_value is not None and str(nested_value).strip():
            return str(nested_value).strip()

    bot_creds = get_whatsapp_credentials_for_bot(session, trigger.bot_id)
    value = bot_creds.get("phone_number_id")
    if value:
        return str(value).strip()
    return ""


def _parse_allow_list_values(raw_value: Any) -> List[str]:
    values: List[str] = []
    if isinstance(raw_value, str):
        values = [token.strip() for token in re.split(r"[,\s]+", raw_value) if token.strip()]
    elif isinstance(raw_value, list):
        values = [str(item).strip() for item in raw_value if str(item).strip()]
    elif raw_value is not None:
        values = [str(raw_value).strip()]

    normalized = []
    seen = set()
    for value in values:
        phone = _normalize_phone(value)
        if not phone or phone in seen:
            continue
        seen.add(phone)
        normalized.append(phone)
    return normalized


def _resolve_whatsapp_allow_list(trigger: WorkflowTrigger) -> List[str]:
    cfg = trigger.raw_trigger_json or {}
    filter_cfg = (
        cfg.get("event_filter")
        or cfg.get("eventFilter")
        or cfg.get("filter")
        or {}
    )
    if not isinstance(filter_cfg, dict):
        filter_cfg = {}

    keys = (
        "allow_list",
        "allowList",
        "allowed_numbers",
        "allowedNumbers",
        "allowed_phone_numbers",
        "allowedPhoneNumbers",
        "whitelist",
        "white_list",
    )

    allow_list: List[str] = []
    for key in keys:
        allow_list.extend(_parse_allow_list_values(cfg.get(key)))
        allow_list.extend(_parse_allow_list_values(filter_cfg.get(key)))

    deduped = []
    seen = set()
    for phone in allow_list:
        if phone in seen:
            continue
        seen.add(phone)
        deduped.append(phone)

    return deduped


def _resolve_active_trigger(
    session: Session,
    trigger_node_id: str,
    allowed_types: Optional[set[str]] = None,
) -> Optional[WorkflowTrigger]:
    query = session.query(WorkflowTrigger).filter(
        WorkflowTrigger.trigger_node_id == trigger_node_id,
        WorkflowTrigger.status == "active",
    )
    if allowed_types:
        query = query.filter(WorkflowTrigger.trigger_type.in_(list(allowed_types)))

    return query.order_by(WorkflowTrigger.updated_at.desc(), WorkflowTrigger.id.desc()).first()

def _resolve_active_triggers(
    session: Session,
    trigger_node_id: str,
    allowed_types: Optional[set[str]] = None,
) -> List[WorkflowTrigger]:
    query = session.query(WorkflowTrigger).filter(
        WorkflowTrigger.trigger_node_id == trigger_node_id,
        WorkflowTrigger.status == "active",
    )
    if allowed_types:
        query = query.filter(WorkflowTrigger.trigger_type.in_(list(allowed_types)))
    return query.order_by(WorkflowTrigger.updated_at.desc(), WorkflowTrigger.id.desc()).all()


def _matches_query_binding(trigger: WorkflowTrigger, bot_id_param: Optional[str], diagram_id_param: Optional[str]) -> bool:
    """Optional deterministic binding from webhook URL query params."""
    if diagram_id_param and str(trigger.flow_id) != str(diagram_id_param):
        return False
    if bot_id_param and str(trigger.bot_id) != str(bot_id_param):
        return False
    return True


def _has_valid_workflow_diagram(session: Session, trigger: WorkflowTrigger) -> bool:
    diagram = (
        session.query(BotDiagram.diagram_id)
        .filter(
            BotDiagram.diagram_id == trigger.flow_id,
            BotDiagram.tenant_id == trigger.tenant_id,
            BotDiagram.del_flg.is_(False),
            func.lower(func.coalesce(BotDiagram.status, "")) != "deleted",
        )
        .first()
    )
    return bool(diagram)


def _resolve_active_trigger_with_workflow(
    session: Session,
    trigger_node_id: str,
    allowed_types: Optional[set[str]] = None,
) -> Optional[WorkflowTrigger]:
    query = session.query(WorkflowTrigger).filter(
        WorkflowTrigger.trigger_node_id == trigger_node_id,
        WorkflowTrigger.status == "active",
    )
    if allowed_types:
        query = query.filter(WorkflowTrigger.trigger_type.in_(list(allowed_types)))

    candidates = query.order_by(WorkflowTrigger.updated_at.desc(), WorkflowTrigger.id.desc()).all()
    for candidate in candidates:
        if _has_valid_workflow_diagram(session, candidate):
            return candidate
    return None


def _format_whatsapp_events(payload: Dict[str, Any], trigger: WorkflowTrigger) -> List[Dict[str, Any]]:
    """Parse Meta WhatsApp webhook payload into normalized event objects."""
    events: List[Dict[str, Any]] = []

    raw_cfg = trigger.raw_trigger_json or {}
    include_status_updates = str((raw_cfg or {}).get("include_status_updates", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if not isinstance(payload, dict):
        return events

    def _extract_message_text(message: Dict[str, Any], message_type: str) -> str:
        direct_text = (message.get("text") or {}).get("body")
        if direct_text:
            return direct_text

        if message_type == "text":
            return (message.get("text") or {}).get("body") or ""

        if message_type == "button":
            button_payload = message.get("button") or {}
            return button_payload.get("text") or button_payload.get("payload") or ""

        if message_type == "interactive":
            interactive = message.get("interactive") or {}
            interactive_type = interactive.get("type")
            if interactive_type == "list_reply":
                list_reply = interactive.get("list_reply") or {}
                return list_reply.get("title") or list_reply.get("id") or ""
            if interactive_type == "button_reply":
                button_reply = interactive.get("button_reply") or {}
                return button_reply.get("title") or button_reply.get("id") or ""

        media_payload = message.get(message_type) or {}
        if isinstance(media_payload, dict):
            return media_payload.get("caption") or ""

        return ""

    def _extract_media(message: Dict[str, Any], message_type: str) -> Dict[str, Any]:
        media_types = {"image", "video", "audio", "document", "sticker"}
        if message_type not in media_types:
            return {}

        media_obj = message.get(message_type)
        if not isinstance(media_obj, dict):
            return {}

        return {
            "type": message_type,
            "id": media_obj.get("id"),
            "mime_type": media_obj.get("mime_type"),
            "sha256": media_obj.get("sha256"),
            "filename": media_obj.get("filename"),
            "caption": media_obj.get("caption"),
            "raw": media_obj,
        }

    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            display_phone = metadata.get("display_phone_number")
            phone_number_id = metadata.get("phone_number_id")

            contacts = value.get("contacts") or []
            contact_map = {
                c.get("wa_id"): c
                for c in contacts
                if isinstance(c, dict) and c.get("wa_id")
            }

            for message in value.get("messages", []) or []:
                sender = message.get("from")
                from_phone = _normalize_phone(sender)
                message_type = message.get("type") or ("text" if (message.get("text") or {}).get("body") else "unknown")
                text_body = _extract_message_text(message, message_type)
                if isinstance(text_body, str):
                    text_body = text_body.strip()
                else:
                    text_body = str(text_body or "").strip()

                if not text_body and message_type != "status":
                    text_body = f"[{message_type} message]"

                media_payload = _extract_media(message, message_type)
                message_timestamp = message.get("timestamp")
                contact_info = contact_map.get(sender) or {}

                events.append(
                    {
                        "trigger_type": "whatsapp",
                        "source": "whatsapp",
                        "event": "message.received",
                        "metadata": {
                            "trigger_id": trigger.id,
                            "trigger_node_id": trigger.trigger_node_id,
                            "timestamp": message_timestamp or datetime.utcnow().isoformat() + "Z",
                            "message_id": message.get("id"),
                            "from": sender,
                            "from_phone": from_phone,
                            "type": message_type,
                            "message_type": message_type,
                            "display_phone_number": display_phone,
                            "phone_number_id": phone_number_id,
                            "profile_name": (contact_info.get("profile") or {}).get("name"),
                        },
                        "content": {
                            "text": text_body,
                            "media": media_payload,
                            "interactive": message.get("interactive"),
                            "button": message.get("button"),
                            "raw_message": message,
                            "message_type": message_type,
                        },
                        "message": text_body,
                        "phone": from_phone,
                        "user_query": text_body,
                        "parameters": {
                            "user_query": text_body,
                            "message": text_body,
                            "from": from_phone,
                            "phone": from_phone,
                            "message_type": message_type,
                        },
                        "payload": payload,
                        "context": {
                            "tenant_id": trigger.tenant_id,
                            "bot_id": trigger.bot_id,
                            "flow_id": trigger.flow_id,
                            "trigger_type": trigger.trigger_type,
                        },
                    }
                )

            if include_status_updates:
                for status in value.get("statuses", []) or []:
                    status_phone = _normalize_phone(status.get("recipient_id"))
                    events.append(
                        {
                            "trigger_type": "whatsapp",
                            "source": "whatsapp",
                            "event": "message.status",
                            "metadata": {
                                "trigger_id": trigger.id,
                                "trigger_node_id": trigger.trigger_node_id,
                                "timestamp": datetime.utcnow().isoformat() + "Z",
                                "message_id": status.get("id"),
                                "recipient_id": status.get("recipient_id"),
                                "status": status.get("status"),
                                "display_phone_number": display_phone,
                                "phone_number_id": phone_number_id,
                            },
                            "content": {
                                "raw_status": status,
                                "message_type": "status",
                            },
                            "message": "",
                            "phone": status_phone,
                            "user_query": "",
                            "parameters": {
                                "user_query": "",
                                "message": "",
                                "from": status_phone,
                                "phone": status_phone,
                                "message_type": "status",
                            },
                            "payload": payload,
                            "context": {
                                "tenant_id": trigger.tenant_id,
                                "bot_id": trigger.bot_id,
                                "flow_id": trigger.flow_id,
                                "trigger_type": trigger.trigger_type,
                            },
                        }
                    )

    return events


def _dedupe_whatsapp_events(session: Session, trigger: WorkflowTrigger, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    message_ids = [
        (event.get("metadata") or {}).get("message_id")
        for event in events
        if (event.get("metadata") or {}).get("message_id")
    ]

    if not message_ids:
        return events

    processed_ids = {
        row[0]
        for row in session.query(ProcessedTriggerEvent.event_id)
        .filter(
            ProcessedTriggerEvent.tenant_id == trigger.tenant_id,
            ProcessedTriggerEvent.trigger_id == trigger.id,
            ProcessedTriggerEvent.event_id.in_(message_ids),
        )
        .all()
    }

    deduped: List[Dict[str, Any]] = []
    seen_in_payload = set()
    for event in events:
        message_id = (event.get("metadata") or {}).get("message_id")
        if message_id and message_id in seen_in_payload:
            continue
        if message_id and message_id in processed_ids:
            logger.info("[WHATSAPP_WEBHOOK] Skipping duplicate event_id=%s for trigger_id=%s", message_id, trigger.id)
            continue
        if message_id:
            seen_in_payload.add(message_id)
        deduped.append(event)

    return deduped


def _mark_whatsapp_events_processed(session: Session, trigger: WorkflowTrigger, events: List[Dict[str, Any]]) -> None:
    seen = set()
    for event in events:
        message_id = (event.get("metadata") or {}).get("message_id")
        if not message_id or message_id in seen:
            continue
        seen.add(message_id)

        session.execute(
            text(
                """
                INSERT INTO processed_trigger_events (tenant_id, trigger_id, event_id, event_source, processed_at)
                VALUES (:tenant_id, :trigger_id, :event_id, :event_source, NOW())
                ON CONFLICT ON CONSTRAINT uq_trigger_event_once DO NOTHING
                """
            ),
            {
                "tenant_id": trigger.tenant_id,
                "trigger_id": trigger.id,
                "event_id": str(message_id),
                "event_source": "whatsapp",
            },
        )


def _select_waiting_whatsapp_run(waiting_runs: List[Any], sender_phone: str) -> Optional[Any]:
    """Compatibility helper for selecting a paused run by WhatsApp sender."""
    if not sender_phone:
        return None

    for run in waiting_runs:
        context_json = getattr(run, "context_json", {}) or {}
        waiting_node_id = getattr(run, "current_node_id", None) or context_json.get("waiting_node_id")
        if not waiting_node_id:
            continue

        waiting_output = (context_json.get("node_outputs") or {}).get(waiting_node_id, {})
        expected_from = _normalize_phone(((waiting_output or {}).get("await") or {}).get("from"))
        if not expected_from:
            expected_from = _normalize_phone((waiting_output or {}).get("to"))

        if expected_from and expected_from == sender_phone:
            return run

    return None


def _find_waiting_whatsapp_wait_state(
    session: Session,
    trigger: WorkflowTrigger,
    sender_phone: str,
) -> Optional[WorkflowWaitState]:
    if not sender_phone:
        return None

    waiting_states = (
        session.query(WorkflowWaitState)
        .filter(
            WorkflowWaitState.status == "waiting",
            WorkflowWaitState.bot_id == str(trigger.bot_id),
            WorkflowWaitState.tenant_id == str(trigger.tenant_id),
            WorkflowWaitState.diagram_id == int(trigger.flow_id),
        )
        .order_by(WorkflowWaitState.updated_at.desc())
        .all()
    )

    for wait_state in waiting_states:
        tracked_phone = _normalize_phone(wait_state.tracking_key)
        if tracked_phone and tracked_phone == sender_phone:
            return wait_state

    return None


def _resolve_slack_signing_secret(session: Session, trigger: WorkflowTrigger) -> str:
    """Resolve signing secret from node config, then bot creds, then legacy global creds."""
    raw_json = trigger.raw_trigger_json or {}
    nested_json = raw_json.get("slack") if isinstance(raw_json.get("slack"), dict) else {}
    if isinstance(raw_json, dict):
        for key in ("signing_secret", "signingSecret"):
            value = raw_json.get(key)
            if value:
                return str(value)
            nested_value = nested_json.get(key)
            if nested_value:
                return str(nested_value)

    bot_creds = get_slack_credentials_for_bot(session, trigger.bot_id)
    token = bot_creds.get("signing_secret")
    if token:
        return str(token)

    token_payload = get_legacy_tool_credentials(session, trigger.tenant_id, "slack")
    token = token_payload.get("signing_secret") or token_payload.get("signingSecret")
    if token:
        return str(token)
    return ""


def _resolve_slack_team_id(session: Session, trigger: WorkflowTrigger) -> str:
    """Best-effort resolve Slack team/workspace id for a trigger."""
    raw_json = trigger.raw_trigger_json or {}
    nested_json = raw_json.get("slack") if isinstance(raw_json.get("slack"), dict) else {}
    if isinstance(raw_json, dict):
        for key in ("team_id", "teamId", "workspace_id", "workspaceId"):
            value = raw_json.get(key)
            if value:
                return str(value).strip()
            nested_value = nested_json.get(key)
            if nested_value:
                return str(nested_value).strip()

    token_payload = get_legacy_tool_credentials(session, trigger.tenant_id, "slack")
    for key in ("team_id", "teamId", "workspace_id", "workspaceId"):
        value = token_payload.get(key)
        if value:
            return str(value).strip()
    return ""


def _resolve_slack_default_channel(session: Session, trigger: WorkflowTrigger) -> str:
    """Best-effort resolve default Slack channel id for a trigger."""
    raw_json = trigger.raw_trigger_json or {}
    nested_json = raw_json.get("slack") if isinstance(raw_json.get("slack"), dict) else {}
    if isinstance(raw_json, dict):
        for key in ("default_channel_id", "channel_id", "channel"):
            value = raw_json.get(key)
            if value:
                return str(value).strip()
            nested_value = nested_json.get(key)
            if nested_value:
                return str(nested_value).strip()

    bot_creds = get_slack_credentials_for_bot(session, trigger.bot_id)
    for key in ("default_channel_id", "channel_id", "channel"):
        value = bot_creds.get(key)
        if value:
            return str(value).strip()

    token_payload = get_legacy_tool_credentials(session, trigger.tenant_id, "slack")
    for key in ("default_channel_id", "channel_id", "channel"):
        value = token_payload.get(key)
        if value:
            return str(value).strip()
    return ""


def _resolve_slack_trigger_channel(trigger: WorkflowTrigger) -> str:
    """Resolve channel configured directly on Slack trigger JSON, if present."""
    raw_cfg = _safe_dict(trigger.raw_trigger_json)
    nested_cfg = raw_cfg.get("slack") if isinstance(raw_cfg.get("slack"), dict) else {}
    for key in ("channel", "channel_id", "default_channel_id"):
        value = raw_cfg.get(key)
        if value:
            return str(value).strip()
        nested_value = nested_cfg.get(key)
        if nested_value:
            return str(nested_value).strip()
    return ""


def _verify_slack_signature(raw_body: bytes, timestamp: str, signature: str, signing_secret: str) -> bool:
    if not signing_secret:
        return True

    if not timestamp or not signature:
        return False

    try:
        request_ts = int(timestamp)
    except Exception:
        return False

    now_ts = int(datetime.utcnow().timestamp())
    if abs(now_ts - request_ts) > 60 * 5:
        return False

    if isinstance(raw_body, str):
        raw_bytes = raw_body.encode("utf-8")
    else:
        raw_bytes = raw_body or b""

    basestring = b"v0:" + str(timestamp).encode("utf-8") + b":" + raw_bytes
    # Use hmac.new() which is the correct Python 3 HMAC constructor.
    computed = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        basestring,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, signature)


def _format_slack_events(payload: Dict[str, Any], trigger: WorkflowTrigger) -> List[Dict[str, Any]]:
    """Parse Slack Events API payload into normalized event objects."""
    events: List[Dict[str, Any]] = []

    if not isinstance(payload, dict):
        return events

    payload_type = payload.get("type")
    if payload_type != "event_callback":
        return events

    event = payload.get("event") or {}
    if not isinstance(event, dict):
        return events

    event_type = event.get("type")
    subtype = event.get("subtype")
    if event.get("bot_id"):
        return events
    if event_type not in {"message", "app_mention"}:
        return events
    if subtype in {"bot_message", "message_deleted", "message_changed", "channel_join", "channel_leave"}:
        return events

    text_body = str(event.get("text") or "").strip()
    if not text_body:
        text_body = "[slack event]"

    channel = str(event.get("channel") or "").strip()
    user = str(event.get("user") or "").strip()
    thread_ts = str(event.get("thread_ts") or event.get("ts") or "").strip()
    event_id = str(payload.get("event_id") or event.get("client_msg_id") or event.get("ts") or "").strip()
    event_ts = str(event.get("event_ts") or event.get("ts") or datetime.utcnow().timestamp())

    events.append(
        {
            "trigger_type": "slack",
            "source": "slack",
            "event": "message.received",
            "metadata": {
                "trigger_id": trigger.id,
                "trigger_node_id": trigger.trigger_node_id,
                "timestamp": event_ts,
                "event_id": event_id,
                "channel": channel,
                "channel_id": channel,
                "user": user,
                "thread_ts": thread_ts,
                "message_type": event_type,
                "team_id": payload.get("team_id"),
            },
            "content": {
                "text": text_body,
                "raw_event": event,
                "event_type": event_type,
                "subtype": subtype,
            },
            "message": text_body,
            "text": text_body,
            "channel": channel,
            "user": user,
            "thread_ts": thread_ts,
            "user_query": text_body,
            "parameters": {
                "user_query": text_body,
                "message": text_body,
                "text": text_body,
                "channel": channel,
                "channel_id": channel,
                "user": user,
                "thread_ts": thread_ts,
            },
            "payload": payload,
            "context": {
                "tenant_id": trigger.tenant_id,
                "bot_id": trigger.bot_id,
                "flow_id": trigger.flow_id,
                "trigger_type": trigger.trigger_type,
            },
        }
    )

    return events


def _dedupe_slack_events(session: Session, trigger: WorkflowTrigger, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    event_ids = [
        (event.get("metadata") or {}).get("event_id")
        for event in events
        if (event.get("metadata") or {}).get("event_id")
    ]

    if not event_ids:
        return events

    processed_ids = {
        row[0]
        for row in session.query(ProcessedTriggerEvent.event_id)
        .filter(
            ProcessedTriggerEvent.tenant_id == trigger.tenant_id,
            ProcessedTriggerEvent.trigger_id == trigger.id,
            ProcessedTriggerEvent.event_id.in_(event_ids),
        )
        .all()
    }

    deduped: List[Dict[str, Any]] = []
    seen_in_payload = set()
    for event in events:
        event_id = (event.get("metadata") or {}).get("event_id")
        if event_id and event_id in seen_in_payload:
            continue
        if event_id and event_id in processed_ids:
            logger.info("[SLACK_WEBHOOK] Skipping duplicate event_id=%s for trigger_id=%s", event_id, trigger.id)
            continue
        if event_id:
            seen_in_payload.add(event_id)
        deduped.append(event)

    return deduped


def _mark_slack_events_processed(session: Session, trigger: WorkflowTrigger, events: List[Dict[str, Any]]) -> None:
    seen = set()
    for event in events:
        event_id = (event.get("metadata") or {}).get("event_id")
        if not event_id or event_id in seen:
            continue
        seen.add(event_id)

        session.execute(
            text(
                """
                INSERT INTO processed_trigger_events (tenant_id, trigger_id, event_id, event_source, processed_at)
                VALUES (:tenant_id, :trigger_id, :event_id, :event_source, NOW())
                ON CONFLICT ON CONSTRAINT uq_trigger_event_once DO NOTHING
                """
            ),
            {
                "tenant_id": trigger.tenant_id,
                "trigger_id": trigger.id,
                "event_id": str(event_id),
                "event_source": "slack",
            },
        )


def _acquire_event_advisory_lock(session: Session, tenant_id: int, trigger_id: int, event_id: str) -> bool:
    """
    Attempt to acquire a PostgreSQL advisory transaction-scoped lock keyed on
    (tenant_id, trigger_id, event_id).  Returns True if acquired, False if
    another concurrent transaction already holds the lock for this event.
    The lock is automatically released when the transaction ends.
    """
    import hashlib
    raw = f"{tenant_id}:{trigger_id}:{event_id}"
    # Fold 128-bit MD5 digest into a signed 64-bit integer for pg_try_advisory_xact_lock
    digest = hashlib.md5(raw.encode()).digest()
    key = int.from_bytes(digest[:8], "big", signed=True)
    try:
        result = session.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key})
        return bool(result.scalar())
    except Exception:
        logger.warning("[DEDUP] Advisory lock unavailable — proceeding without lock")
        return True


def _get_webhook_redis_client():
    global _webhook_redis_client
    if _webhook_redis_client is not None:
        return _webhook_redis_client

    try:
        import redis

        _webhook_redis_client = redis.Redis(
            host=os.environ.get("REDIS_HOST", "redis"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            db=int(os.environ.get("REDIS_DB", 0)),
            decode_responses=True,
        )
        return _webhook_redis_client
    except Exception as exc:
        logger.warning("[DEDUP] Redis client unavailable for webhook replay guard: %s", exc)
        _webhook_redis_client = False
        return None


def _acquire_recent_webhook_event_guard(
    source: str,
    tenant_id: int,
    trigger_id: int,
    event_id: str,
) -> bool:
    """
    Best-effort short-lived guard to suppress immediate webhook retries
    before worker-side dedup records are written.
    """
    if not event_id:
        return True

    client = _get_webhook_redis_client()
    if not client:
        return True

    try:
        ttl_seconds = int(os.environ.get("WEBHOOK_EVENT_GUARD_TTL_SECONDS", "180"))
    except Exception:
        ttl_seconds = 180
    ttl_seconds = max(10, ttl_seconds)

    key = f"webhook:event-guard:{source}:{tenant_id}:{trigger_id}:{event_id}"
    try:
        # SET NX EX => only the first request in TTL window succeeds.
        acquired = client.set(key, "1", nx=True, ex=ttl_seconds)
        return bool(acquired)
    except Exception as exc:
        logger.warning("[DEDUP] Redis replay guard error; allowing event processing: %s", exc)
        return True


def _filter_recent_replayed_events(
    source: str,
    trigger: WorkflowTrigger,
    events: List[Dict[str, Any]],
    event_id_field: str,
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for event in events:
        event_id = str((event.get("metadata") or {}).get(event_id_field) or "").strip()
        if not event_id:
            filtered.append(event)
            continue
        if _acquire_recent_webhook_event_guard(source, trigger.tenant_id, trigger.id, event_id):
            filtered.append(event)
            continue
        logger.info(
            "[%s_WEBHOOK] Skipping immediate replay event_id=%s trigger_id=%s",
            source.upper(),
            event_id,
            trigger.id,
        )
    return filtered


def _resolve_unmatched_behavior(trigger: WorkflowTrigger) -> str:
    """
    Read 'unmatched_reply_behavior' from trigger config.
    Returns 'start_new' (default) or 'ignore'.
    """
    raw = trigger.raw_trigger_json or {}
    behavior = str(
        raw.get("unmatched_reply_behavior")
        or raw.get("unmatchedReplyBehavior")
        or "start_new"
    ).strip().lower()
    return behavior if behavior in {"start_new", "ignore"} else "start_new"


def _find_waiting_slack_wait_state(
    session: Session,
    trigger: WorkflowTrigger,
    channel: str,
    user: str,
    thread_ts: str,
) -> Optional[WorkflowWaitState]:
    if not channel:
        return None

    waiting_states = (
        session.query(WorkflowWaitState)
        .filter(
            WorkflowWaitState.status == "waiting",
            WorkflowWaitState.bot_id == str(trigger.bot_id),
            WorkflowWaitState.tenant_id == str(trigger.tenant_id),
            WorkflowWaitState.diagram_id == int(trigger.flow_id),
        )
        .order_by(WorkflowWaitState.updated_at.desc())
        .all()
    )

    for wait_state in waiting_states:
        tracked = str(wait_state.tracking_key or "").strip()
        if not tracked:
            continue

        tracked_channel = tracked
        tracked_thread_ts = ""
        tracked_user = ""
        if ":" in tracked:
            parts = tracked.split(":")
            tracked_channel = parts[0]
            if len(parts) >= 3:
                tracked_thread_ts = parts[1]
                tracked_user = parts[2]
            elif len(parts) == 2:
                # Use tracking_type stored on the wait state to disambiguate
                # a 2-segment key unambiguously instead of guessing from the
                # incoming event's thread_ts.
                #
                # Formats stored by SlackSendAndWaitNode:
                #   "slack_channel_user"  → channel:user
                #   "slack_channel_thread" → channel:thread_ts  (future)
                #   fallback / legacy     → try thread_ts match, else user
                tracking_type = str(getattr(wait_state, "tracking_type", "") or "").strip().lower()

                if tracking_type == "slack_channel_thread":
                    tracked_thread_ts = parts[1]
                elif tracking_type == "slack_channel_user":
                    tracked_user = parts[1]
                else:
                    # Legacy fallback: if the second part matches the incoming
                    # thread_ts exactly, treat it as a thread key; otherwise
                    # treat it as a user key.
                    if thread_ts and parts[1] == thread_ts:
                        tracked_thread_ts = parts[1]
                    else:
                        tracked_user = parts[1]

        tracked_channel = tracked_channel.strip()
        tracked_thread_ts = tracked_thread_ts.strip()
        tracked_user = tracked_user.strip()

        if tracked_channel != channel:
            continue

        if tracked_thread_ts and thread_ts and tracked_thread_ts != thread_ts:
            continue

        if tracked_user and user and tracked_user != user:
            continue

        return wait_state

    return None


@webhook_bp.route('/webhook/<trigger_node_id>', methods=['POST'])
def receive_webhook(trigger_node_id: str):
    """
    Generic webhook endpoint.
    
    POST /webhook/<trigger_node_id>
    
    Example Payload for Supplier Selection:
    {
        "event": "supplier.selected",
        "rfq_id": "RFQ123",
        "supplier_email": "abc@xyz.com",
        "supplier_name": "ABC Pvt Ltd"
    }
    """
    session = None
    
    try:
        if not request.is_json:
            return jsonify({"status": "error", "message": "Request must be JSON"}), 400
        
        payload = request.get_json()
        logger.info(f"[WEBHOOK] Received webhook for trigger_node_id={trigger_node_id}")
        logger.debug(f"[WEBHOOK_PAYLOAD] {payload}")

        session = next(db_session())

        trigger = (
            session.query(WorkflowTrigger)
            .filter_by(trigger_node_id=trigger_node_id, status="active")
            .first()
        )

        if not trigger:
            return jsonify({
                "status": "error",
                "message": f"No active webhook trigger found for node: {trigger_node_id}"
            }), 404
        
        if trigger.trigger_type != "webhook":
            return jsonify({
                "status": "error",
                "message": f"Trigger is not a webhook trigger (type={trigger.trigger_type})"
            }), 400


        # ----------------------------------------------------------------------
        # ✅ SUPPLIER SELECTION LOGIC (Your requirement)
        # ----------------------------------------------------------------------
        rfq_no = payload.get("rfq_id") or payload.get("rfq_no")
        supplier_email = payload.get("supplier_email")

        if rfq_no and supplier_email:
            logger.info(f"[SUPPLIER_SELECTION] Updating selected supplier for RFQ={rfq_no}")

            # Deselect all suppliers for this RFQ
            session.execute(
                text("""
                    UPDATE supplier_quotations
                    SET selected = FALSE
                    WHERE rfq_no = :rfq
                """),
                 {"rfq": rfq_no}
                )

            # Select the chosen supplier
            session.execute(
                text("""
                    UPDATE supplier_quotations
                    SET selected = TRUE
                    WHERE rfq_no = :rfq AND supplier_email = :email
                """),
                {"rfq": rfq_no, "email": supplier_email}
             )

            session.commit()
            logger.info("[SUPPLIER_SELECTION] Supplier successfully marked as selected.")
        else:
            logger.warning("[SUPPLIER_SELECTION] Skipped — Missing rfq_id or supplier_email")


        # ----------------------------------------------------------------------
        # 🔹 Workflow Execution Logic
        # ----------------------------------------------------------------------
        webhook_event = _format_webhook_event(payload, trigger)

        workflow_json = _load_workflow_diagram(
            session,
            trigger.flow_id,
            trigger.tenant_id,
            trigger.bot_id,
        )

        workflow_json.update({
            "bot_id": trigger.bot_id,
            "tenant_id": trigger.tenant_id,
            "trigger_id": trigger.id,
            "trigger_type": trigger.trigger_type,
            "diagram_id": trigger.flow_id
        })

        trigger_data = {
            trigger_node_id: {
                "tenant_id": trigger.tenant_id,
                "prefetched_events": [webhook_event]
            }
        }

        executor = WorkflowExecutor(workflow_json)
        executor.session_ref = session

        result = executor.execute(trigger_data=trigger_data, return_context=True)

        session.commit()

        return jsonify({
            "status": "success",
            "message": "Webhook received, supplier updated, workflow executed",
            "trigger_id": trigger.id,
            "execution_id": executor.execution_db_id if hasattr(executor, 'execution_db_id') else None,
            "executed_nodes": result.executed_nodes,
            "total_nodes": result.total_nodes,
            "workflow_status": result.to_dict().get('status')
        }), 200
        
    except Exception as e:
        if session:
            session.rollback()
        logger.exception(f"[WEBHOOK] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
    finally:
        if session:
            session.close()


@webhook_bp.route('/webhook/whatsapp/<trigger_node_id>', methods=['GET', 'POST'])
@webhook_bp.route('/whatsapp/<trigger_node_id>', methods=['GET', 'POST'])
def receive_whatsapp_webhook(trigger_node_id: str):
    """
    WhatsApp Cloud API webhook endpoint.

    Full path when mounted:
            /whatsapp/<trigger_node_id>
    """
    session = None

    try:
        logger.info(
            "[FLOW_TRACE][WHATSAPP][ENTRY] trigger_node_id=%s method=%s query_bot_id=%s query_diagram_id=%s",
            trigger_node_id,
            request.method,
            request.args.get("bot_id"),
            request.args.get("diagram_id"),
        )
        session = next(db_session())

        trigger = _resolve_active_trigger(
            session,
            trigger_node_id,
            allowed_types={"whatsapp", "webhook"},
        )
        trigger_candidates = _resolve_active_triggers(
            session,
            trigger_node_id,
            allowed_types={"whatsapp", "webhook"},
        )
        bot_id_param = request.args.get("bot_id")
        diagram_id_param = request.args.get("diagram_id")

        explicit_binding_locked = False
        if (bot_id_param or diagram_id_param) and trigger_candidates:
            bound = next(
                (
                    candidate
                    for candidate in trigger_candidates
                    if _matches_query_binding(candidate, bot_id_param, diagram_id_param)
                ),
                None,
            )
            if bound:
                if not trigger or bound.id != trigger.id:
                    logger.info(
                        "[WHATSAPP_WEBHOOK] Matched trigger by URL binding bot_id=%s diagram_id=%s -> trigger_id=%s flow_id=%s tenant_id=%s",
                        bot_id_param,
                        diagram_id_param,
                        bound.id,
                        bound.flow_id,
                        bound.tenant_id,
                    )
                trigger = bound
                explicit_binding_locked = True

        if not trigger:
            return jsonify({
                "status": "error",
                "message": f"No active trigger found for node: {trigger_node_id}",
            }), 404

        if not _has_valid_workflow_diagram(session, trigger):
            fallback = _resolve_active_trigger_with_workflow(
                session,
                trigger_node_id,
                allowed_types={"whatsapp", "webhook"},
            )
            if not fallback:
                return jsonify({
                    "status": "error",
                    "message": f"No valid workflow found for node: {trigger_node_id}",
                }), 404
            if fallback.id != trigger.id:
                logger.warning(
                    "[WORKFLOW] trigger_id=%s has invalid flow_id=%s; falling back to trigger_id=%s flow_id=%s",
                    trigger.id, trigger.flow_id, fallback.id, fallback.flow_id,
                )
                trigger = fallback

        logger.info(
            "[FLOW_TRACE][WHATSAPP][INITIAL_TRIGGER] trigger_node_id=%s trigger_id=%s flow_id=%s tenant_id=%s bot_id=%s",
            trigger_node_id,
            trigger.id,
            trigger.flow_id,
            trigger.tenant_id,
            trigger.bot_id,
        )
        if not isinstance(trigger.bot_id, int) or trigger.bot_id <= 0:
            logger.warning(
                "[FLOW_TRACE][WHATSAPP][INVALID_TRIGGER_BOT_ID] trigger_id=%s flow_id=%s bot_id=%s",
                trigger.id,
                trigger.flow_id,
                trigger.bot_id,
            )

        if trigger.trigger_type not in {"whatsapp", "webhook"}:
            return jsonify({
                "status": "error",
                "message": f"Trigger type {trigger.trigger_type} does not support WhatsApp webhook",
            }), 400

        # 1) Meta verification handshake
        if request.method == 'GET':
            mode = request.args.get("hub.mode")
            challenge = request.args.get("hub.challenge")
            verify_token = request.args.get("hub.verify_token")

            if len(trigger_candidates) > 1 and verify_token:
                for candidate in trigger_candidates:
                    expected = _resolve_whatsapp_verify_token(session, candidate)
                    if expected and verify_token == expected:
                        if candidate.id != trigger.id:
                            logger.info(
                                "[WHATSAPP_WEBHOOK] Matched trigger by verify_token -> trigger_id=%s tenant_id=%s",
                                candidate.id,
                                candidate.tenant_id,
                            )
                        trigger = candidate
                        break

            expected_token = _resolve_whatsapp_verify_token(session, trigger)

            if mode == "subscribe" and challenge and expected_token and verify_token == expected_token:
                logger.info(
                    "[WHATSAPP] verification success trigger_node_id=%s challenge=%s",
                    trigger_node_id,
                    challenge,
                )
                return challenge, 200

            return jsonify({
                "status": "error",
                "message": "Webhook verification failed",
            }), 403

        # 2) Inbound events
        data = request.get_json(silent=True) or {}
        entry = data.get("entry") or []
        changes = entry[0].get("changes") if entry else []
        value = changes[0].get("value") if changes else {}
        messages = value.get("messages") or []
        statuses = value.get("statuses") or []

        if not messages:
            # Non-message events (status updates, read receipts, etc.)
            return "No message event", 200

        msg = messages[0]

        text = (
            msg.get("text", {}).get("body")
            or msg.get("interactive", {}).get("button_reply", {}).get("title")
            or msg.get("interactive", {}).get("list_reply", {}).get("title")
        )

        from_number = msg.get("from")

        if not text or not from_number:
            return "Invalid message content", 200

        normalized_sender = _normalize_phone(from_number)
        logger.info("[WHATSAPP] incoming message from %s", normalized_sender)

        allowed_numbers = _resolve_whatsapp_allow_list(trigger)
        if allowed_numbers and normalized_sender not in set(allowed_numbers):
            logger.info(
                "[WHATSAPP] sender blocked by allow-list sender=%s trigger_id=%s",
                normalized_sender,
                trigger.id,
            )
            return jsonify({
                "status": "success",
                "message": "Sender not allow-listed",
            }), 200

        payload = data

        if len(trigger_candidates) > 1 and explicit_binding_locked:
            logger.info(
                "[FLOW_TRACE][WHATSAPP][BINDING_LOCKED] Skipping phone_number_id rebinding due to explicit URL binding trigger_id=%s flow_id=%s bot_id=%s",
                trigger.id,
                trigger.flow_id,
                trigger.bot_id,
            )
        elif len(trigger_candidates) > 1:
            logger.info(
                "[FLOW_TRACE][WHATSAPP][REBIND_DISABLED] Keeping initial trigger without phone_number_id rebinding trigger_id=%s flow_id=%s bot_id=%s",
                trigger.id,
                trigger.flow_id,
                trigger.bot_id,
            )

        logger.info(
            "[FLOW_TRACE][WHATSAPP][FINAL_TRIGGER] trigger_node_id=%s trigger_id=%s flow_id=%s tenant_id=%s bot_id=%s",
            trigger_node_id,
            trigger.id,
            trigger.flow_id,
            trigger.tenant_id,
            trigger.bot_id,
        )

        events = _format_whatsapp_events(payload, trigger)
        input_data = _extract_whatsapp_input_data(payload, events)

        input_data["message"] = text
        input_data["user_query"] = text
        input_data["phone"] = normalized_sender
        input_data["from"] = normalized_sender

        # Advisory lock: acquire per-event in-flight guard before dedup read
        first_event_id = None
        for ev in events:
            eid = (ev.get("metadata") or {}).get("message_id")
            if eid:
                first_event_id = str(eid)
                break
        if first_event_id:
            if not _acquire_event_advisory_lock(session, trigger.tenant_id, trigger.id, first_event_id):
                logger.info(
                    "[WHATSAPP_WEBHOOK] Advisory lock busy — duplicate in-flight event_id=%s trigger_id=%s",
                    first_event_id, trigger.id,
                )
                return jsonify({"status": "success", "message": "Duplicate event in-flight"}), 200

        events = _dedupe_whatsapp_events(session, trigger, events)
        events = _filter_recent_replayed_events(
            source="whatsapp",
            trigger=trigger,
            events=events,
            event_id_field="message_id",
        )

        if not events:
            return jsonify({
                "status": "success",
                "message": "Webhook received (no new message events)",
            }), 200

        first_sender = _normalize_phone(
            (events[0].get("metadata") or {}).get("from_phone")
            or (events[0].get("metadata") or {}).get("from")
        )

        wait_state = _find_waiting_whatsapp_wait_state(session, trigger, first_sender)

        if wait_state:
            workflow_json = _load_workflow_diagram(
                session,
                int(wait_state.diagram_id),
                int(wait_state.tenant_id),
                int(wait_state.bot_id),
            )
            workflow_nodes = workflow_json.get("nodes", []) if isinstance(workflow_json, dict) else []
            generic_like_count = sum(
                1 for n in workflow_nodes
                if str((n or {}).get("type", "")).strip() in {"GenericAgentNode", "ResponseAgentNode", "GreetingAgentNode"}
            )
            logger.info(
                "[WHATSAPP_WEBHOOK] Resume workflow node check | trigger_id=%s generic_like_nodes=%s total_nodes=%s",
                trigger.id,
                generic_like_count,
                len(workflow_nodes),
            )
            workflow_json.update({
                "bot_id": int(wait_state.bot_id),
                "tenant_id": int(wait_state.tenant_id),
                "diagram_id": int(wait_state.diagram_id),
                "trigger_id": trigger.id,
                "trigger_type": trigger.trigger_type,
            })

            executor = WorkflowExecutor(workflow_json)
            executor.session_ref = session

            result = executor.resume_from_wait_state(
                wait_state_id=wait_state.id,
                event_payload={
                    "whatsapp_events": events,
                    "latest_whatsapp_event": events[0],
                    "sender_phone": first_sender,
                    **input_data,
                },
            )

            _mark_whatsapp_events_processed(session, trigger, events)
            session.commit()

            if result is None:
                return jsonify({
                    "status": "success",
                    "message": "WhatsApp webhook processed (wait state already resumed)",
                    "trigger_id": trigger.id,
                    "wait_state_id": wait_state.id,
                    "events_count": len(events),
                }), 200

            return jsonify({
                "status": "success",
                "message": "WhatsApp webhook processed and waiting workflow resumed",
                "trigger_id": trigger.id,
                "wait_state_id": wait_state.id,
                "events_count": len(events),
                "executed_nodes": result.executed_nodes,
                "total_nodes": result.total_nodes,
            }), 200

        # 3) No wait-state matched: apply configurable unmatched reply behavior.
        unmatched_behavior = _resolve_unmatched_behavior(trigger)
        if unmatched_behavior == "ignore":
            logger.info(
                "[WHATSAPP_WEBHOOK] Unmatched reply ignored (behavior=ignore) trigger_id=%s sender=%s",
                trigger.id, first_sender,
            )
            _mark_whatsapp_events_processed(session, trigger, events)
            session.commit()
            return jsonify({"status": "success", "message": "Unmatched reply ignored"}), 200

        workflow_json = _load_workflow_diagram(
            session,
            trigger.flow_id,
            trigger.tenant_id,
            trigger.bot_id,
        )
        workflow_nodes = workflow_json.get("nodes", []) if isinstance(workflow_json, dict) else []
        generic_like_count = sum(
            1 for n in workflow_nodes
            if str((n or {}).get("type", "")).strip() in {"GenericAgentNode", "ResponseAgentNode", "GreetingAgentNode"}
        )
        logger.info(
            "[WHATSAPP_WEBHOOK] Queue workflow node check | trigger_id=%s generic_like_nodes=%s total_nodes=%s",
            trigger.id,
            generic_like_count,
            len(workflow_nodes),
        )

        # 4) New inbound run: enqueue for background processing and return fast.
        # Do not execute LLM/workflow inline in webhook request thread.
        queue_payload = {
            "trigger_id": trigger.id,
            "trigger_node_id": trigger_node_id,
            "trigger_type": "whatsapp",
            "tenant_id": trigger.tenant_id,
            "bot_id": trigger.bot_id,
            "flow_id": trigger.flow_id,
            "prefetched_events": events,
            "input_data": input_data,
            "received_at": datetime.utcnow().isoformat() + "Z",
        }

        enqueue_trigger(queue_payload)
        logger.info(
            "[QUEUE] job queued trigger_id=%s workflow_id=%s trigger_node_id=%s",
            trigger.id,
            trigger.flow_id,
            trigger_node_id,
        )
        logger.info(
            "[FLOW_TRACE][WHATSAPP][QUEUE_PAYLOAD] trigger_id=%s flow_id=%s tenant_id=%s bot_id=%s prefetched_events=%s input_keys=%s",
            trigger.id,
            trigger.flow_id,
            trigger.tenant_id,
            trigger.bot_id,
            len(events),
            list(input_data.keys()),
        )

        return jsonify({
            "status": "success",
            "message": "WhatsApp webhook accepted and queued for background execution",
            "trigger_id": trigger.id,
            "events_count": len(events),
        }), 200

    except Exception as e:
        if session:
            session.rollback()
        logger.exception(f"[WHATSAPP_WEBHOOK] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        if session:
            session.close()

@webhook_bp.route('/webhook/slack/<trigger_node_id>', methods=['GET', 'POST'])
@webhook_bp.route('/slack/<trigger_node_id>', methods=['GET', 'POST'])
def receive_slack_webhook(trigger_node_id: str):
    """Slack Events API webhook endpoint."""
    session = None

    try:
        raw_body = request.data
        try:
            payload = json.loads(raw_body) if raw_body else {}
        except Exception:
            payload = request.get_json(force=True, silent=True) or {}

        # Slack URL verification challenge must be handled before DB/auth logic.
        if payload.get("type") == "url_verification":
            return jsonify({"challenge": payload.get("challenge")}), 200

        if request.method == "GET":
            return jsonify({
                "status": "ok",
                "message": "Slack webhook endpoint working",
            }), 200

        slack_logger = logging.getLogger(__name__)
        slack_logger.info(f"[SLACK WEBHOOK PAYLOAD] {payload}")

        session = next(db_session())

        trigger = _resolve_active_trigger(
            session,
            trigger_node_id,
            allowed_types={"slack", "webhook"},
        )

        # If multiple tenants share the same trigger node id (e.g. slacktrigger-1),
        # resolve the correct trigger using Slack workspace/team metadata first.
        trigger_candidates = _resolve_active_triggers(
            session,
            trigger_node_id,
            allowed_types={"slack", "webhook"},
        )
        bot_id_param = request.args.get("bot_id")
        diagram_id_param = request.args.get("diagram_id")

        if (bot_id_param or diagram_id_param) and trigger_candidates:
            bound = next(
                (
                    candidate
                    for candidate in trigger_candidates
                    if _matches_query_binding(candidate, bot_id_param, diagram_id_param)
                ),
                None,
            )
            if bound:
                if not trigger or bound.id != trigger.id:
                    logger.info(
                        "[SLACK_WEBHOOK] Matched trigger by URL binding bot_id=%s diagram_id=%s -> trigger_id=%s flow_id=%s tenant_id=%s",
                        bot_id_param,
                        diagram_id_param,
                        bound.id,
                        bound.flow_id,
                        bound.tenant_id,
                    )
                trigger = bound
        if len(trigger_candidates) > 1:
            matched_by_identity = False
            signature = request.headers.get("X-Slack-Signature", "")
            timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
            payload_team_id = str(
                payload.get("team_id")
                or (payload.get("team") or {}).get("id")
                or ((payload.get("event") or {}).get("team"))
                or (
                    ((payload.get("authorizations") or [])[0] or {}).get("team_id")
                    if isinstance(payload.get("authorizations"), list) and payload.get("authorizations")
                    else ""
                )
                or ""
            ).strip()
            payload_channel = str(
                (payload.get("event") or {}).get("channel")
                or ""
            ).strip()

            # 1) Strongest match: signature validation across candidates.
            signature_match = None
            if signature and timestamp:
                for candidate in trigger_candidates:
                    candidate_secret = _resolve_slack_signing_secret(session, candidate)
                    if candidate_secret and _verify_slack_signature(
                        raw_body, timestamp, signature, candidate_secret
                    ):
                        signature_match = candidate
                        break
            if signature_match:
                trigger = signature_match
                matched_by_identity = True
                logger.info(
                    "[SLACK_WEBHOOK] Matched trigger by signature -> trigger_id=%s tenant_id=%s",
                    trigger.id,
                    trigger.tenant_id,
                )

            # 2) Workspace/team match.
            if payload_team_id:
                team_match = None
                for candidate in trigger_candidates:
                    if _resolve_slack_team_id(session, candidate) == payload_team_id:
                        team_match = candidate
                        break
                if team_match:
                    trigger = team_match
                    matched_by_identity = True
                    logger.info(
                        "[SLACK_WEBHOOK] Matched trigger by team_id=%s -> trigger_id=%s tenant_id=%s",
                        payload_team_id,
                        trigger.id,
                        trigger.tenant_id,
                    )

            # 3) Channel match (trigger config + credential default channel).
            if payload_channel:
                channel_match = None
                for candidate in trigger_candidates:
                    trigger_channel = _resolve_slack_trigger_channel(candidate)
                    default_channel = _resolve_slack_default_channel(session, candidate)
                    if trigger_channel == payload_channel or default_channel == payload_channel:
                        channel_match = candidate
                        break
                if channel_match:
                    trigger = channel_match
                    matched_by_identity = True
                    logger.info(
                        "[SLACK_WEBHOOK] Matched trigger by channel=%s -> trigger_id=%s tenant_id=%s",
                        payload_channel,
                        trigger.id,
                        trigger.tenant_id,
                    )

            # 4) Avoid routing to wrong tenant when candidate resolution is ambiguous.
            if not matched_by_identity:
                logger.error(
                    "[SLACK_WEBHOOK] Ambiguous trigger mapping — %s candidates for trigger_node_id=%s, "
                    "none matched by signature/team/channel. payload_team_id=%s payload_channel=%s",
                    len(trigger_candidates), trigger_node_id, payload_team_id, payload_channel,
                )
                return jsonify({
                    "status": "error",
                    "message": "Ambiguous Slack trigger mapping across tenants; unable to safely resolve target tenant",
                }), 409

        if not trigger:
            logger.error(
                "[SLACK_WEBHOOK] No active trigger found for trigger_node_id=%s — "
                "check that the Slack app's Event Subscriptions URL matches the node id stored in the diagram. "
                "candidates_count=%s",
                trigger_node_id,
                len(trigger_candidates),
            )
            return jsonify({
                "status": "error",
                "message": f"No active trigger found for node: {trigger_node_id}",
            }), 404

        if not _has_valid_workflow_diagram(session, trigger):
            fallback = _resolve_active_trigger_with_workflow(
                session,
                trigger_node_id,
                allowed_types={"slack", "webhook"},
            )
            if not fallback:
                logger.error(
                    "[SLACK_WEBHOOK] No valid workflow diagram found for trigger_id=%s flow_id=%s trigger_node_id=%s",
                    trigger.id, trigger.flow_id, trigger_node_id,
                )
                return jsonify({
                    "status": "error",
                    "message": f"No valid workflow found for node: {trigger_node_id}",
                }), 404
            if fallback.id != trigger.id:
                logger.warning(
                    "[WORKFLOW] trigger_id=%s has invalid flow_id=%s; falling back to trigger_id=%s flow_id=%s",
                    trigger.id, trigger.flow_id, fallback.id, fallback.flow_id,
                )
                trigger = fallback

        logger.info(
            "[WORKFLOW] resolved workflow_id=%s trigger_node_id=%s trigger_id=%s",
            trigger.flow_id, trigger_node_id, trigger.id,
        )

        if trigger.trigger_type not in {"slack", "webhook"}:
            logger.error(
                "[SLACK_WEBHOOK] Trigger type mismatch: trigger_id=%s type=%s does not support Slack webhook",
                trigger.id, trigger.trigger_type,
            )
            return jsonify({
                "status": "error",
                "message": f"Trigger type {trigger.trigger_type} does not support Slack webhook.",
            }), 400

        raw_body = request.get_data(cache=True, as_text=False) or b""

        signing_secret = _resolve_slack_signing_secret(session, trigger)
        if signing_secret:
            timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
            signature = request.headers.get("X-Slack-Signature", "")
            if not _verify_slack_signature(raw_body, timestamp, signature, signing_secret):
                # Secondary resolution path for duplicate trigger_node_id across tenants:
                # find a candidate whose signing secret validates this request.
                verified_trigger = None
                for candidate in trigger_candidates:
                    candidate_secret = _resolve_slack_signing_secret(session, candidate)
                    if candidate_secret and _verify_slack_signature(
                        raw_body, timestamp, signature, candidate_secret
                    ):
                        verified_trigger = candidate
                        break

                if verified_trigger:
                    trigger = verified_trigger
                    logger.info(
                        "[SLACK_WEBHOOK] Matched trigger by signature -> trigger_id=%s tenant_id=%s",
                        trigger.id,
                        trigger.tenant_id,
                    )
                else:
                    return jsonify({
                        "status": "error",
                        "message": "Slack signature verification failed",
                    }), 403

        # 2) Inbound events
        event = payload.get("event", {})
        text = event.get("text")
        channel = event.get("channel")
        user = event.get("user")

        if event.get("bot_id"):
            logger.debug("[SLACK_WEBHOOK] Ignoring bot message bot_id=%s trigger_id=%s", event.get("bot_id"), trigger.id)
            return "Ignore bot", 200

        auth_user_id = str(
            (
                ((payload.get("authorizations") or [])[0] or {}).get("user_id")
                if isinstance(payload.get("authorizations"), list) and payload.get("authorizations")
                else ""
            )
            or ""
        ).strip()
        if auth_user_id and str(event.get("user") or "").strip() == auth_user_id:
            logger.debug("[SLACK_WEBHOOK] Ignoring self-echo from bot user_id=%s trigger_id=%s", auth_user_id, trigger.id)
            return "Ignore bot user", 200

        if not text:
            logger.info("[SLACK_WEBHOOK] Ignoring event with no text trigger_id=%s event_type=%s", trigger.id, event.get("type"))
            return "No message event", 200

        events = _format_slack_events(payload, trigger)

        # Advisory lock: acquire per-event in-flight guard before dedup read
        first_event_id = None
        for ev in events:
            eid = (ev.get("metadata") or {}).get("event_id")
            if eid:
                first_event_id = str(eid)
                break
        if first_event_id:
            if not _acquire_event_advisory_lock(session, trigger.tenant_id, trigger.id, first_event_id):
                logger.info(
                    "[SLACK_WEBHOOK] Advisory lock busy — duplicate in-flight event_id=%s trigger_id=%s",
                    first_event_id, trigger.id,
                )
                return jsonify({"status": "success", "message": "Duplicate event in-flight"}), 200

        events = _dedupe_slack_events(session, trigger, events)
        events = _filter_recent_replayed_events(
            source="slack",
            trigger=trigger,
            events=events,
            event_id_field="event_id",
        )

        if not events:
            logger.info(
                "[SLACK_WEBHOOK] All events filtered (dedup/replay guard) trigger_id=%s trigger_node_id=%s",
                trigger.id, trigger_node_id,
            )
            return jsonify({
                "status": "success",
                "message": "Slack webhook received (no new message events)",
            }), 200

        latest_event = events[0]
        latest_meta = latest_event.get("metadata") or {}
        latest_channel = str(latest_meta.get("channel") or latest_event.get("channel") or "").strip()
        latest_user = str(latest_meta.get("user") or latest_event.get("user") or "").strip()
        latest_thread_ts = str(
            latest_meta.get("thread_ts")
            or latest_event.get("thread_ts")
            or ""
        ).strip()

        wait_state = _find_waiting_slack_wait_state(
            session,
            trigger,
            latest_channel,
            latest_user,
            latest_thread_ts,
        )

        if wait_state:
            workflow_json = _load_workflow_diagram(
                session,
                int(wait_state.diagram_id),
                int(wait_state.tenant_id),
                int(wait_state.bot_id),
            )
            workflow_json.update({
                "bot_id": int(wait_state.bot_id),
                "tenant_id": int(wait_state.tenant_id),
                "diagram_id": int(wait_state.diagram_id),
                "trigger_id": trigger.id,
                "trigger_type": trigger.trigger_type,
            })

            executor = WorkflowExecutor(workflow_json)
            executor.session_ref = session

            result = executor.resume_from_wait_state(
                wait_state_id=wait_state.id,
                event_payload={
                    "slack_events": events,
                    "latest_slack_event": latest_event,
                    "channel": latest_channel,
                    "user": latest_user,
                    "thread_ts": latest_thread_ts,
                },
            )

            _mark_slack_events_processed(session, trigger, events)
            session.commit()

            if result is None:
                return jsonify({
                    "status": "success",
                    "message": "Slack webhook processed (wait state already resumed)",
                    "trigger_id": trigger.id,
                    "wait_state_id": wait_state.id,
                    "events_count": len(events),
                }), 200

            return jsonify({
                "status": "success",
                "message": "Slack webhook processed and waiting workflow resumed",
                "trigger_id": trigger.id,
                "wait_state_id": wait_state.id,
                "events_count": len(events),
                "executed_nodes": result.executed_nodes,
                "total_nodes": result.total_nodes,
            }), 200

        # 3) No wait-state matched: apply configurable unmatched reply behavior.
        unmatched_behavior = _resolve_unmatched_behavior(trigger)
        if unmatched_behavior == "ignore":
            logger.info(
                "[SLACK_WEBHOOK] Unmatched reply ignored (behavior=ignore) trigger_id=%s channel=%s user=%s",
                trigger.id, latest_channel, latest_user,
            )
            _mark_slack_events_processed(session, trigger, events)
            session.commit()
            return jsonify({"status": "success", "message": "Unmatched reply ignored"}), 200

        workflow_json = _load_workflow_diagram(
            session,
            trigger.flow_id,
            trigger.tenant_id,
            trigger.bot_id,
        )
        workflow_nodes = workflow_json.get("nodes", []) if isinstance(workflow_json, dict) else []
        generic_like_count = sum(
            1 for n in workflow_nodes
            if str((n or {}).get("type", "")).strip() in {"GenericAgentNode", "ResponseAgentNode", "GreetingAgentNode"}
        )
        logger.info(
            "[SLACK_WEBHOOK] Queue workflow node check | trigger_id=%s generic_like_nodes=%s total_nodes=%s",
            trigger.id,
            generic_like_count,
            len(workflow_nodes),
        )

        # 4) New inbound run: enqueue for background processing and return fast.
        # Do not execute LLM/workflow inline in webhook request thread.
        input_data = {
            "user_query": text,
            "message": text,
            "text": text,
            "channel": latest_channel or channel,
            "channel_id": latest_channel or channel,
            "user": latest_user or user,
            "thread_ts": latest_thread_ts,
        }

        queue_payload = {
            "trigger_id": trigger.id,
            "trigger_node_id": trigger_node_id,
            "trigger_type": "slack",
            "tenant_id": trigger.tenant_id,
            "bot_id": trigger.bot_id,
            "flow_id": trigger.flow_id,
            "prefetched_events": events,
            "input_data": input_data,
            "received_at": datetime.utcnow().isoformat() + "Z",
        }

        enqueue_trigger(queue_payload)
        logger.info(
            "[QUEUE] job queued trigger_id=%s workflow_id=%s trigger_node_id=%s",
            trigger.id,
            trigger.flow_id,
            trigger_node_id,
        )

        return jsonify({
            "status": "success",
            "message": "Slack webhook accepted and queued for background execution",
            "trigger_id": trigger.id,
            "events_count": len(events),
        }), 200

    except Exception as e:
        if session:
            session.rollback()
        logger.exception(f"[SLACK_WEBHOOK] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        if session:
            session.close()



@webhook_bp.route('/webhook/<trigger_node_id>/info', methods=['GET'])
def get_webhook_info(trigger_node_id: str):
    """Return details of a webhook trigger."""
    session = None
    try:
        session = next(db_session())
        trigger = (
            session.query(WorkflowTrigger)
            .filter_by(trigger_node_id=trigger_node_id)
            .first()
        )
        
        if not trigger:
            return jsonify({
                "status": "error",
                "message": f"No webhook trigger found for node: {trigger_node_id}"
            }), 404
        
        return jsonify({
            "status": "success",
            "trigger": {
                "id": trigger.id,
                "trigger_node_id": trigger.trigger_node_id,
                "trigger_type": trigger.trigger_type,
                "status": trigger.status,
                "bot_id": trigger.bot_id,
                "flow_id": trigger.flow_id,
                "tenant_id": trigger.tenant_id,
                "webhook_name": trigger.raw_trigger_json.get("webhook_name"),
                "event_filter": trigger.raw_trigger_json.get("event_filter", {}),
                "field_mapping": trigger.raw_trigger_json.get("field_mapping", {}),
                "created_at": trigger.created_at.isoformat() if hasattr(trigger, 'created_at') else None
            }
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
    finally:
        if session:
            session.close()



@webhook_bp.route('/webhooks/<int:bot_id>', methods=['GET'])
def get_all_webhooks_for_bot(bot_id: int):
    """List all webhook URLs belonging to a bot."""
    session = None
    try:
        session = next(db_session())
        triggers = session.query(WorkflowTrigger).filter_by(
            bot_id=bot_id,
            status='active'
        ).filter(WorkflowTrigger.trigger_type.in_(['webhook', 'whatsapp', 'slack'])).all()

        base_url = request.host_url.rstrip('/')
        webhook_list = []

        for trigger in triggers:
            if trigger.trigger_type == 'whatsapp':
                webhook_url = f"{base_url}/webhook/whatsapp/{trigger.trigger_node_id}"
            elif trigger.trigger_type == 'slack':
                webhook_url = f"{base_url}/slack/{trigger.trigger_node_id}"
            else:
                webhook_url = f"{base_url}/webhook/webhook/{trigger.trigger_node_id}"

            webhook_list.append({
                "trigger_id": trigger.id,
                "trigger_node_id": trigger.trigger_node_id,
                "webhook_name": trigger.raw_trigger_json.get('webhook_name'),
                "webhook_url": webhook_url,
                "trigger_type": trigger.trigger_type,
                "event_filter": trigger.raw_trigger_json.get('event_filter', {}),
                "field_mapping": trigger.raw_trigger_json.get('field_mapping', {}),
                "flow_id": trigger.flow_id,
                "tenant_id": trigger.tenant_id,
                "status": trigger.status
            })

        return jsonify({
            "status": "success",
            "count": len(webhook_list),
            "bot_id": bot_id,
            "webhooks": webhook_list
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
    finally:
        if session:
            session.close()
