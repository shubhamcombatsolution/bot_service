# from flask import Blueprint, request, jsonify
# from app.models.bot_diagram import BotDiagram
# from app.models.new_models.custom_bot import CustomBotNew as CustomBot
# from app.models import Agent,McpTools,McpAgentTools,LLM,KnowledgeBase,ToolAuthorization
# from app.database.DatabaseOperationPostgreSQL import db_session
# import json
# from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
# from langgraph.graph import StateGraph
# from pydantic import BaseModel
# from langchain_openai import ChatOpenAI
# from sqlalchemy import desc, func, or_
# from sqlalchemy.exc import SQLAlchemyError
# from app.models.workflow_trigger import WorkflowTrigger
# from app.services.channel_credentials_service import (
#     get_legacy_tool_credentials,
#     get_slack_credentials_for_bot,
#     get_whatsapp_credentials_for_bot,
# )
# from logging_config import setup_logging
# import json
# from datetime import datetime, timedelta

# logger = setup_logging("bot_diagram", level="DEBUG")

# bot_diagram_blueprint = Blueprint('bot_diagram', __name__)

# llm = ChatOpenAI(
#     model_name="gpt-3.5-turbo",
#     temperature=0.7,
#     openai_api_key="YOUR_OPENAI_API_KEY"
# )

# class ChatState(BaseModel):
#     message: str
#     response: str

# def agent_response(state: ChatState):
#     response = llm.invoke(state.message)
#     return ChatState(message=state.message, response=str(response))


# def _coerce_int(value):
#     """Best-effort integer coercion; returns None when invalid."""
#     try:
#         if value in (None, ""):
#             return None
#         return int(value)
#     except (TypeError, ValueError):
#         return None


# def _resolve_workflow_name(bot, bot_id: int) -> str:
#     """
#     Use bot name as workflow name; fallback to legacy pattern for empty names.
#     """
#     name = (getattr(bot, "bot_name", "") or "").strip()
#     return name if name else f"custom_bot_new_{bot_id}"


# def _resolve_bot_agent_name(bot, bot_id: int) -> str:
#     """
#     Build a bot-specific agent name instead of a generic "Bot Agent".
#     """
#     bot_name = (getattr(bot, "bot_name", "") or "").strip()
#     if bot_name:
#         return f"{bot_name} Agent"
#     return f"Bot {bot_id} Agent"

# def _resolve_flow_bot_id(diagram_data):
#     """
#     Resolve bot_id from workflow payload when top-level request bot_id is missing.
#     Priority:
#     1) diagram_json.flowData.bot_id
#     2) first node.data.flowData.bot_id
#     """
#     if not isinstance(diagram_data, dict):
#         return None

#     root_flow_data = diagram_data.get("flowData")
#     if isinstance(root_flow_data, dict):
#         root_bot_id = _coerce_int(root_flow_data.get("bot_id"))
#         if root_bot_id is not None:
#             return root_bot_id

#     nodes = diagram_data.get("nodes", [])
#     if isinstance(nodes, list):
#         for node in nodes:
#             if not isinstance(node, dict):
#                 continue
#             node_data = node.get("data")
#             if not isinstance(node_data, dict):
#                 continue
#             node_flow_data = node_data.get("flowData")
#             if not isinstance(node_flow_data, dict):
#                 continue
#             node_bot_id = _coerce_int(node_flow_data.get("bot_id"))
#             if node_bot_id is not None:
#                 return node_bot_id

#     return None


# def _is_legacy_bot_diagram_fk_mismatch(exc: Exception) -> bool:
#     """
#     Detects environments where tbl_bot_diagrams.bot_id FK still points to tbl_custombot.
#     """
#     err = str(exc)
#     return (
#         "tbl_bot_diagrams_bot_id_fkey" in err
#         and "tbl_custombot" in err
#     )


# def _create_bot_diagram_with_fk_compat(
#     session,
#     *,
#     bot_id,
#     tenant_id,
#     workflow_name,
#     channel,
#     status,
#     diagram_json,
# ):
#     """
#     Create a BotDiagram with compatibility fallback for legacy DB constraints.
#     In some environments, tbl_bot_diagrams.bot_id still references tbl_custombot
#     while runtime uses tbl_custombot_new IDs.
#     """
#     payload = {
#         "bot_id": bot_id,
#         "tenant_id": tenant_id,
#         "workflow_name": workflow_name,
#         "channel": channel,
#         "status": status,
#         "diagram_json": diagram_json,
#     }

#     try:
#         with session.begin_nested():
#             new_diagram = BotDiagram(**payload)
#             session.add(new_diagram)
#             session.flush()
#         return new_diagram
#     except SQLAlchemyError as exc:
#         if bot_id is not None and _is_legacy_bot_diagram_fk_mismatch(exc):
#             logger.warning(
#                 "[BOT_DIAGRAM_FK_COMPAT] Legacy FK mismatch detected. "
#                 "Retrying diagram insert with bot_id=NULL for tenant_id=%s workflow_name=%s bot_id=%s",
#                 tenant_id,
#                 workflow_name,
#                 bot_id,
#             )
#             fallback_payload = dict(payload)
#             fallback_payload["bot_id"] = None
#             with session.begin_nested():
#                 new_diagram = BotDiagram(**fallback_payload)
#                 session.add(new_diagram)
#                 session.flush()
#             return new_diagram
#         raise

# def extract_and_store_triggers(diagram_data, bot_id, tenant_id, session, flow_id):
#     """
#     Extract and store Gmail triggers from diagram.
#     """
#     logger.info(f"[TRIGGER_SYNC] Processing Gmail triggers for bot_id={bot_id}, tenant_id={tenant_id}")

#     try:
#         nodes = diagram_data.get("nodes", [])
#         if not isinstance(nodes, list):
#             logger.error("[TRIGGER_SYNC] Invalid diagram format: 'nodes' must be a list.")
#             return

#         trigger_count = 0

#         for node in nodes:
#             if node.get("type") != "GmailTriggerNode":
#                 continue

#             trigger_node_id = node.get("id")
#             gmail_data = node.get("data", {}).get("formData", {}).get("gmail", {})

#             if not gmail_data:
#                 logger.warning(f"[TRIGGER_SYNC] GmailTriggerNode '{trigger_node_id}' missing config.")
#                 continue

#             enable_mode = gmail_data.get("enableMode", False)

#             schedule = (
#                 {
#                     "mode": gmail_data.get("mode"),
#                     "hour": gmail_data.get("hour"),
#                     "minute": gmail_data.get("minute"),
#                     "weekday": gmail_data.get("weekday")
#                 }
#                 if enable_mode else None
#             )

#             filters = gmail_data.get("filters", {})

#             trigger_entry = session.query(WorkflowTrigger).filter_by(
#                 bot_id=bot_id,
#                 tenant_id=tenant_id,
#                 trigger_node_id=trigger_node_id,
#                 flow_id=flow_id
#             ).first()

#             if not trigger_entry:
#                 trigger_entry = WorkflowTrigger(
#                     bot_id=bot_id,
#                     tenant_id=tenant_id,
#                     flow_id=flow_id,
#                     trigger_node_id=trigger_node_id,
#                     trigger_type="gmail",
#                     status="active"
#                 )

#             trigger_entry.schedule_meta = schedule
#             trigger_entry.filter_meta = filters
#             trigger_entry.raw_trigger_json = gmail_data

#             session.merge(trigger_entry)
#             trigger_count += 1

#         logger.info(f"[TRIGGER_SYNC] {trigger_count} Gmail trigger(s) stored.")

#     except Exception:
#         logger.exception("[TRIGGER_SYNC] Unexpected error processing Gmail triggers")
#         raise


# def _fetch_tool_credentials(session, tenant_id: int, tool_name: str, bot_id: int | None = None) -> dict:
#     """
#     Fetch saved credentials from tbl_tool_authorization for a given tool.
#     Returns a flat dict of all credential keys, or {} if not found.
#     """
#     try:
#         if tool_name.lower() == "whatsapp":
#             bot_creds = get_whatsapp_credentials_for_bot(session, bot_id)
#             if bot_creds.get("access_token") or bot_creds.get("phone_number_id"):
#                 return bot_creds
#         if tool_name.lower() == "slack":
#             bot_creds = get_slack_credentials_for_bot(session, bot_id)
#             if bot_creds.get("bot_token") or bot_creds.get("signing_secret"):
#                 return bot_creds

#         return get_legacy_tool_credentials(session, tenant_id, tool_name)
#     except Exception as e:
#         logger.warning("[TRIGGER_SYNC] Could not fetch tool credentials for %s: %s", tool_name, e)
#         return {}


# def _normalize_whatsapp_trigger_config(node: dict) -> dict:
#     """
#     Normalize WhatsApp trigger config so both editor and runtime conventions work.
#     Supports:
#       - data.formData.whatsapp.*
#       - data.formData.* (flat)
#     """
#     node_data = node.get("data", {}) if isinstance(node, dict) else {}
#     form_data = node_data.get("formData", {}) if isinstance(node_data, dict) else {}

#     if not isinstance(form_data, dict):
#         form_data = {}

#     whatsapp_data = form_data.get("whatsapp", {})
#     if not isinstance(whatsapp_data, dict):
#         whatsapp_data = {}

#     merged = dict(whatsapp_data)
#     for key, value in form_data.items():
#         if key != "whatsapp" and key not in merged:
#             merged[key] = value

#     event_filter = (
#         merged.get("event_filter")
#         or merged.get("eventFilter")
#         or merged.get("filter")
#         or {}
#     )
#     field_mapping = (
#         merged.get("field_mapping")
#         or merged.get("fieldMapping")
#         or {}
#     )

#     return {
#         "whatsapp": whatsapp_data,
#         "webhook_name": (
#             merged.get("webhook_name")
#             or merged.get("webhookName")
#             or f"whatsapp_{node.get('id', 'trigger')}"
#         ),
#         "verify_token": (
#             merged.get("verify_token")
#             or merged.get("verifyToken")
#             or ""
#         ),
#         "include_status_updates": merged.get("include_status_updates"),
#         "event_filter": event_filter,
#         "eventFilter": event_filter,
#         "filter": event_filter,
#         "field_mapping": field_mapping,
#         "fieldMapping": field_mapping,
#         "node_data": node_data,
#     }


# def _normalize_whatsapp_trigger_node_id(diagram_data: dict) -> tuple[dict, bool]:
#     """
#     Ensure WhatsApp trigger node uses a stable id: whatsapptrigger-4.
#     This keeps Meta webhook URL stable across re-saves in the builder.
#     """
#     if not isinstance(diagram_data, dict):
#         return diagram_data, False

#     nodes = diagram_data.get("nodes", [])
#     edges = diagram_data.get("edges", [])
#     if not isinstance(nodes, list):
#         return diagram_data, False

#     whatsapp_nodes = [
#         node for node in nodes
#         if isinstance(node, dict)
#         and node.get("type") in {"WhatsAppTriggerNode", "whatsappTriggerNode"}
#     ]
#     if len(whatsapp_nodes) != 1:
#         return diagram_data, False

#     node = whatsapp_nodes[0]
#     old_id = node.get("id")
#     target_id = "whatsapptrigger-4"
#     if not old_id or old_id == target_id:
#         return diagram_data, False

#     node["id"] = target_id
#     node_data = node.get("data")
#     if isinstance(node_data, dict):
#         node_data["id"] = target_id

#     if isinstance(edges, list):
#         for edge in edges:
#             if not isinstance(edge, dict):
#                 continue
#             if edge.get("source") == old_id:
#                 edge["source"] = target_id
#             if edge.get("target") == old_id:
#                 edge["target"] = target_id

#     for key in ("trigger_data",):
#         trigger_data = diagram_data.get(key)
#         if isinstance(trigger_data, dict) and old_id in trigger_data:
#             trigger_data[target_id] = trigger_data.pop(old_id)

#     flow_data = diagram_data.get("flowData")
#     if isinstance(flow_data, dict):
#         flow_trigger_data = flow_data.get("trigger_data")
#         if isinstance(flow_trigger_data, dict) and old_id in flow_trigger_data:
#             flow_trigger_data[target_id] = flow_trigger_data.pop(old_id)

#     return diagram_data, True


# def extract_and_store_whatsapp_triggers(diagram_data, bot_id, tenant_id, session, flow_id):
#     """Extract and store WhatsApp trigger nodes from the diagram."""
#     logger.info(f"[TRIGGER_SYNC] Processing WhatsApp triggers for bot_id={bot_id}, tenant_id={tenant_id}")

#     saved_creds = _fetch_tool_credentials(session, tenant_id, "whatsapp", bot_id=bot_id)
#     cred_keys = ["access_token", "phone_number_id", "verify_token", "verifyToken"]

#     try:
#         nodes = diagram_data.get("nodes", [])
#         if not isinstance(nodes, list):
#             logger.error("[TRIGGER_SYNC] Invalid diagram format: 'nodes' must be a list.")
#             return 0

#         trigger_count = 0

#         for node in nodes:
#             if node.get("type") not in {"WhatsAppTriggerNode", "whatsappTriggerNode"}:
#                 continue

#             trigger_node_id = node.get("id")
#             if not trigger_node_id:
#                 continue

#             whatsapp_data = _normalize_whatsapp_trigger_config(node)
#             if not isinstance(whatsapp_data, dict):
#                 whatsapp_data = {}

#             for key in cred_keys:
#                 if saved_creds.get(key) and not whatsapp_data.get(key):
#                     whatsapp_data[key] = saved_creds[key]

#             trigger_entry = session.query(WorkflowTrigger).filter_by(
#                 bot_id=bot_id,
#                 tenant_id=tenant_id,
#                 trigger_node_id=trigger_node_id,
#                 flow_id=flow_id,
#             ).first()

#             if not trigger_entry:
#                 trigger_entry = WorkflowTrigger(
#                     bot_id=bot_id,
#                     tenant_id=tenant_id,
#                     flow_id=flow_id,
#                     trigger_node_id=trigger_node_id,
#                     trigger_type="whatsapp",
#                     status="active",
#                 )

#             trigger_entry.trigger_type = "whatsapp"
#             trigger_entry.status = "active"
#             trigger_entry.schedule_meta = None
#             trigger_entry.filter_meta = whatsapp_data.get("event_filter", {}) or {}
#             trigger_entry.raw_trigger_json = whatsapp_data

#             session.merge(trigger_entry)
#             trigger_count += 1

#         logger.info(f"[TRIGGER_SYNC] {trigger_count} WhatsApp trigger(s) stored.")
#         return trigger_count

#     except Exception:
#         logger.exception("[TRIGGER_SYNC] Unexpected error processing WhatsApp triggers")
#         raise


# def extract_and_store_slack_triggers(diagram_data, bot_id, tenant_id, session, flow_id):
#     """Extract and store Slack trigger nodes from the diagram."""
#     logger.info(f"[TRIGGER_SYNC] Processing Slack triggers for bot_id={bot_id}, tenant_id={tenant_id}")

#     saved_creds = _fetch_tool_credentials(session, tenant_id, "slack", bot_id=bot_id)
#     cred_keys = ["bot_token", "signing_secret", "signingSecret"]

#     try:
#         nodes = diagram_data.get("nodes", [])
#         if not isinstance(nodes, list):
#             logger.error("[TRIGGER_SYNC] Invalid diagram format: 'nodes' must be a list.")
#             return

#         trigger_count = 0

#         for node in nodes:
#             if node.get("type") not in {"SlackTriggerNode", "slackTriggerNode"}:
#                 continue

#             trigger_node_id = node.get("id")
#             form_data = node.get("data", {}).get("formData", {}) or {}
#             nested_slack = form_data.get("slack", {}) if isinstance(form_data, dict) else {}
#             if not isinstance(nested_slack, dict):
#                 nested_slack = {}
#             slack_data = dict(nested_slack)
#             # Preserve compatibility with UIs that persist trigger credentials
#             # directly on formData instead of formData.slack.
#             if isinstance(form_data, dict):
#                 for key in (
#                     "bot_token",
#                     "signing_secret",
#                     "signingSecret",
#                     "team_id",
#                     "teamId",
#                     "channel_id",
#                     "channel",
#                     "default_channel_id",
#                 ):
#                     value = form_data.get(key)
#                     if value not in (None, "") and not slack_data.get(key):
#                         slack_data[key] = value

#             if not slack_data and not saved_creds:
#                 logger.info(
#                     "[TRIGGER_SYNC] SlackTriggerNode '%s' has no config yet — registering with empty config.",
#                     trigger_node_id,
#                 )
#                 # Do NOT skip — always register the trigger so the webhook URL exists

#             for key in cred_keys:
#                 if saved_creds.get(key) and not slack_data.get(key):
#                     slack_data[key] = saved_creds[key]

#             trigger_entry = session.query(WorkflowTrigger).filter_by(
#                 bot_id=bot_id,
#                 tenant_id=tenant_id,
#                 trigger_node_id=trigger_node_id,
#                 flow_id=flow_id,
#             ).first()

#             if not trigger_entry:
#                 trigger_entry = WorkflowTrigger(
#                     bot_id=bot_id,
#                     tenant_id=tenant_id,
#                     flow_id=flow_id,
#                     trigger_node_id=trigger_node_id,
#                     trigger_type="slack",
#                     status="active",
#                 )

#             trigger_entry.trigger_type = "slack"
#             trigger_entry.status = "active"
#             trigger_entry.schedule_meta = None
#             trigger_entry.filter_meta = (
#                 slack_data.get("filter")
#                 or slack_data.get("filters")
#                 or slack_data.get("event_filter")
#                 or slack_data.get("eventFilter")
#                 or {}
#             ) if isinstance(slack_data, dict) else {}
#             trigger_entry.raw_trigger_json = slack_data

#             session.merge(trigger_entry)
#             trigger_count += 1

#         logger.info(f"[TRIGGER_SYNC] {trigger_count} Slack trigger(s) stored.")

#     except Exception:
#         logger.exception("[TRIGGER_SYNC] Unexpected error processing Slack triggers")
#         raise


# def detect_and_register_webhook_triggers(diagram_data, bot_id, tenant_id, session, flow_id):
#     """
#     Detect and register WebhookTriggerNode from diagram.
#     Returns: List of registered trigger IDs
#     """
#     logger.info(f"[WEBHOOK_SYNC] Processing webhook triggers for bot_id={bot_id}, tenant_id={tenant_id}")
    
#     registered_trigger_ids = []
    
#     try:
#         nodes = diagram_data.get("nodes", [])
#         if not isinstance(nodes, list):
#             logger.error("[WEBHOOK_SYNC] Invalid diagram format: 'nodes' must be a list.")
#             return registered_trigger_ids

#         for node in nodes:
#             node_type = node.get("type")
            
#             # Check if this is a WebhookTriggerNode
#             if node_type != "WebhookTriggerNode":
#                 continue
            
#             trigger_node_id = node.get("id")
#             node_data = node.get("data", {})
#             form_data = node_data.get("formData", {})
            
#             # Try to get webhook config from formData.webhook or directly from formData
#             webhook_data = form_data.get("webhook", {}) or form_data
            
#             # Extract webhook configuration
#             webhook_name = (
#                 webhook_data.get("webhook_name") or 
#                 webhook_data.get("webhookName") or 
#                 f"webhook_{trigger_node_id}"
#             )
#             event_filter = webhook_data.get("event_filter") or webhook_data.get("eventFilter") or {}
#             field_mapping = webhook_data.get("field_mapping") or webhook_data.get("fieldMapping") or {}
            
#             logger.info(f"[WEBHOOK_SYNC] Found WebhookTriggerNode: {trigger_node_id}, webhook_name={webhook_name}")
            
#             # Check if trigger already exists
#             trigger_entry = session.query(WorkflowTrigger).filter_by(
#                 bot_id=bot_id,
#                 tenant_id=tenant_id,
#                 trigger_node_id=trigger_node_id,
#                 flow_id=flow_id
#             ).first()
            
#             if not trigger_entry:
#                 # Create new trigger
#                 trigger_entry = WorkflowTrigger(
#                     bot_id=bot_id,
#                     tenant_id=tenant_id,
#                     flow_id=flow_id,
#                     trigger_node_id=trigger_node_id,
#                     trigger_type="webhook",
#                     status="active"
#                 )
#                 session.add(trigger_entry)
#                 logger.info(f"[WEBHOOK_SYNC] Creating new webhook trigger for node: {trigger_node_id}")
#             else:
#                 logger.info(f"[WEBHOOK_SYNC] Updating existing webhook trigger: {trigger_entry.id}")
            
#             # Update trigger configuration
#             trigger_entry.trigger_meta = {
#                 "webhook_name": webhook_name,
#                 "event_filter": event_filter,
#                 "field_mapping": field_mapping,
#                 "node_data": node_data
#             }
#             trigger_entry.schedule_meta = None  # Webhooks don't have schedules
#             trigger_entry.filter_meta = None    # Webhooks use trigger_meta for filtering
#             trigger_entry.raw_trigger_json = webhook_data
            
#             session.merge(trigger_entry)
#             session.flush()  # Flush to get the ID
            
#             registered_trigger_ids.append(trigger_entry.id)
        
#         logger.info(f"[WEBHOOK_SYNC] {len(registered_trigger_ids)} webhook trigger(s) processed.")
#         return registered_trigger_ids
        
#     except Exception:
#         logger.exception("[WEBHOOK_SYNC] Unexpected error processing webhook triggers")
#         raise


# def deactivate_removed_triggers(session, current_node_ids, tenant_id, flow_id):
#     """
#     Deactivate triggers (Gmail, WhatsApp, Webhook, etc.) that are no longer in the diagram.
#     Uses tenant_id + flow_id so cleanup works even when bot_id is missing in payload.
#     """
#     logger.info(f"[TRIGGER_CLEANUP] Checking for removed triggers in tenant_id={tenant_id}, flow_id={flow_id}")
    
#     try:
#         # Find all active triggers for this flow (across all trigger types)
#         existing_triggers = session.query(WorkflowTrigger).filter_by(
#             tenant_id=tenant_id,
#             flow_id=flow_id,
#             status="active"
#         ).all()
        
#         deactivated_count = 0
#         for trigger in existing_triggers:
#             if trigger.trigger_node_id not in current_node_ids:
#                 logger.info(
#                     f"[TRIGGER_CLEANUP] Deactivating removed {trigger.trigger_type} trigger: "
#                     f"id={trigger.id}, node_id={trigger.trigger_node_id}"
#                 )
#                 trigger.status = "inactive"
#                 deactivated_count += 1
        
#         if deactivated_count > 0:
#             logger.info(f"[TRIGGER_CLEANUP] Deactivated {deactivated_count} removed trigger(s)")
#         else:
#             logger.info("[TRIGGER_CLEANUP] No triggers to deactivate")
        
#     except Exception:
#         logger.exception("[TRIGGER_CLEANUP] Unexpected error deactivating triggers")
#         raise


# def deactivate_triggers_from_old_diagrams(session, bot_id, tenant_id, latest_flow_id):
#     updated = session.query(WorkflowTrigger).filter(
#         WorkflowTrigger.bot_id == bot_id,
#         WorkflowTrigger.tenant_id == tenant_id,
#         WorkflowTrigger.flow_id != latest_flow_id,
#         WorkflowTrigger.status == "active"
#     ).update(
#         {"status": "inactive"},
#         synchronize_session=False
#     )

#     if updated:
#         logger.info(
#             f"[TRIGGER_CLEANUP] Deactivated {updated} trigger(s) from older diagrams"
#         )

#     return updated   # ✅ REQUIRED


# @bot_diagram_blueprint.route('/save_diagram', methods=['POST'])
# @jwt_required()
# def save_diagram():
#     try:
#         claims = get_jwt()
#         jwt_tenant_id = claims.get("tenant_id")
#         logger.info(f"Saving diagram for tenant_id: {jwt_tenant_id}")
        
#         if not jwt_tenant_id:
#             logger.error("Tenant ID missing in token")
#             return jsonify({"data": {}, "status": "error", "message": "Tenant ID missing in token"}), 401

#         data = request.json or {}
#         bot_id = data.get("bot_id")
#         diagram_id = data.get("diagram_id")

#         if "diagram_json" not in data:
#             logger.error("Missing required diagram_json field in request")
#             return jsonify({"data": {}, "status": "error", "message": "Missing required fields"}), 400

#         # Validate diagram_json structure
#         try:
#             diagram_data = data["diagram_json"]
#             if isinstance(diagram_data, str):
#                 diagram_data = json.loads(diagram_data)
#             if not isinstance(diagram_data, dict) or "nodes" not in diagram_data or "edges" not in diagram_data:
#                 logger.error("Invalid diagram_json structure")
#                 return jsonify({"data": {}, "status": "error", "message": "Invalid diagram_json structure"}), 400
#             if not isinstance(diagram_data["nodes"], list) or not isinstance(diagram_data["edges"], list):
#                 logger.error("Nodes and edges must be lists")
#                 return jsonify({"data": {}, "status": "error", "message": "Nodes and edges must be lists"}), 400
#         except json.JSONDecodeError as e:
#             logger.error(f"Invalid diagram_json: {str(e)}")
#             return jsonify({"data": {}, "status": "error", "message": f"Invalid diagram_json: {str(e)}"}), 400

#         diagram_data, whatsapp_id_normalized = _normalize_whatsapp_trigger_node_id(diagram_data)
#         if whatsapp_id_normalized:
#             logger.info("[TRIGGER_SYNC] Normalized WhatsApp trigger node id to whatsapptrigger-4")

#         if bot_id is None:
#             resolved_bot_id = _resolve_flow_bot_id(diagram_data)
#             if resolved_bot_id is not None:
#                 bot_id = resolved_bot_id
#                 logger.info("Resolved bot_id=%s from diagram flowData", bot_id)

#         nodes = diagram_data.get("nodes", [])
#         edges = diagram_data.get("edges", [])

#         has_nodes = bool(nodes)
#         if not has_nodes:
#             logger.info("Saving empty diagram draft")

#         # Validate node structure only when nodes exist
#         for node in nodes:
#             if not isinstance(node, dict) or "id" not in node or "type" not in node:
#                 logger.error("Invalid node structure: missing id or type")
#                 return jsonify({"data": {}, "status": "error", "message": "Invalid node structure: missing id or type"}), 400

#         session = next(db_session())
#         try:
#             bot = None
#             workflow_name = data.get("workflow_name") or data.get("workflowId")
#             channel = data.get("channel")
#             status = data.get("status") or "Draft"
#             status_map = {
#                 "draft": "Draft",
#                 "created": "Created",
#                 "live": "Live",
#                 "paused": "Paused",
#                 "updated": "updated",
#             }
#             if isinstance(status, str):
#                 status = status_map.get(status.strip().lower(), status)

#             if bot_id is not None:
#                 bot = session.get(CustomBot, bot_id)
#                 if not bot:
#                     logger.error(f"Bot not found: {bot_id}")
#                     return jsonify({"data": {}, "status": "error", "message": "Bot not found"}), 404

#                 if str(bot.tenant_id) != str(jwt_tenant_id):
#                     logger.error(
#                         f"Unauthorized: Bot tenant_id {bot.tenant_id} does not match JWT tenant_id {jwt_tenant_id}"
#                     )
#                     return jsonify(
#                         {"data": {}, "status": "error", "message": "Unauthorized: Bot does not belong to your tenant"}
#                     ), 403

#             if not workflow_name and bot:
#                 workflow_name = _resolve_workflow_name(bot, bot.bot_id)
#             if channel is None and bot and getattr(bot, "channel", None):
#                 channel = bot.channel.value

#             existing_diagram = None
#             if diagram_id:
#                 existing_diagram = session.get(BotDiagram, diagram_id)
#                 if not existing_diagram:
#                     logger.warning(f"Diagram not found: {diagram_id}")
#                     return jsonify({"data": {}, "status": "error", "message": "No diagram found"}), 404
#                 if str(existing_diagram.tenant_id) != str(jwt_tenant_id):
#                     logger.warning(
#                         f"Unauthorized access to diagram_id={diagram_id} for tenant_id={jwt_tenant_id}"
#                     )
#                     return jsonify({"data": {}, "status": "error", "message": "No diagram found"}), 404
#             if not existing_diagram and workflow_name:
#                 existing_diagram = (
#                     session.query(BotDiagram)
#                     .filter_by(workflow_name=workflow_name, tenant_id=jwt_tenant_id, del_flg=False)
#                     .order_by(BotDiagram.diagram_id.desc())
#                     .first()
#                 )
#             if not existing_diagram and bot:
#                 existing_diagram = (
#                     session.query(BotDiagram)
#                     .filter_by(bot_id=bot.bot_id, tenant_id=jwt_tenant_id, del_flg=False)
#                     .order_by(BotDiagram.diagram_id.desc())
#                     .first()
#                 )

#             diagram_json_str = json.dumps(diagram_data)
#             diagram_owner_bot_id = bot_id if bot_id is not None else (existing_diagram.bot_id if existing_diagram else None)

#             # Keep trigger ownership as stable as possible.
#             # Some workflow-builder flows persist diagrams with bot_id=NULL.
#             # tbl_workflow_triggers.bot_id is NOT NULL, so we assign a stable
#             # internal owner id for trigger rows when no bot_id is available.
#             trigger_owner_bot_id = diagram_owner_bot_id

#             if existing_diagram:
#                 if existing_diagram.diagram_json != diagram_json_str:
#                     existing_diagram.diagram_json = diagram_json_str
#                 if workflow_name and existing_diagram.workflow_name != workflow_name:
#                     existing_diagram.workflow_name = workflow_name
#                 if status and existing_diagram.status != status:
#                     existing_diagram.status = status
#                 if bot and existing_diagram.bot_id != bot.bot_id:
#                     existing_diagram.bot_id = bot.bot_id
#                 diagram_id = existing_diagram.diagram_id
#                 logger.info(f"Using existing diagram: {diagram_id}")
#             else:
#                 new_diagram = _create_bot_diagram_with_fk_compat(
#                     session=session,
#                     bot_id=bot.bot_id if bot else None,
#                     tenant_id=jwt_tenant_id,
#                     workflow_name=workflow_name,
#                     channel=channel,
#                     status=status,
#                     diagram_json=diagram_json_str
#                 )
#                 diagram_id = new_diagram.diagram_id
#                 diagram_owner_bot_id = new_diagram.bot_id
#                 logger.info(f"Created first diagram: {diagram_id}")

#             # ═══════════════════════════════════════════════════════════════
#             # TRIGGER PROCESSING - Gmail and Webhook
#             # ═══════════════════════════════════════════════════════════════
#             # diagram_id is now FINAL (latest)
#             if trigger_owner_bot_id is None:
#                 # Use deterministic negative id to avoid collision with real bot ids.
#                 trigger_owner_bot_id = -int(diagram_id)
#                 logger.warning(
#                     "[TRIGGER_SYNC] No bot_id for diagram_id=%s; using synthetic trigger owner bot_id=%s",
#                     diagram_id,
#                     trigger_owner_bot_id,
#                 )

#             if trigger_owner_bot_id is not None:
#                 updated = deactivate_triggers_from_old_diagrams(
#                     session,
#                     trigger_owner_bot_id,
#                     jwt_tenant_id,
#                     diagram_id
#                 )
#                 if updated == 0:
#                     logger.info("[TRIGGER_CLEANUP] No old triggers to deactivate")

            
#             # Extract all current node IDs for cleanup
#             all_current_node_ids = [node['id'] for node in nodes]
            
#             # 1. Process Gmail triggers (existing functionality)
#             # Always sync trigger rows by flow_id/tenant_id, even when bot_id is missing.
#             # This enables workflow-builder Save/Save&Continue flows to become trigger-ready
#             # without requiring bot FK persistence on the diagram row.
#             extract_and_store_triggers(diagram_data, trigger_owner_bot_id, jwt_tenant_id, session, diagram_id)

#             # 1b. Process WhatsApp triggers
#             extract_and_store_whatsapp_triggers(diagram_data, trigger_owner_bot_id, jwt_tenant_id, session, diagram_id)

#             # 1c. Process Slack triggers
#             extract_and_store_slack_triggers(diagram_data, trigger_owner_bot_id, jwt_tenant_id, session, diagram_id)
            
#             # 2. Process Webhook triggers (NEW)
#             webhook_node_ids = [
#                 node['id'] for node in nodes
#                 if node.get('type') == 'WebhookTriggerNode'
#             ]
            
#             webhook_count = 0
#             if webhook_node_ids:
#                 registered_webhook_ids = detect_and_register_webhook_triggers(
#                     diagram_data, trigger_owner_bot_id, jwt_tenant_id, session, diagram_id
#                 )
#                 webhook_count = len(registered_webhook_ids)
#                 logger.info(f"✅ Registered {webhook_count} webhook trigger(s): {registered_webhook_ids}")
#             else:
#                 logger.info("ℹ️ No webhook triggers found in diagram")
            
#             # 3. Deactivate removed triggers (including WhatsApp) for this flow
#             deactivate_removed_triggers(session, all_current_node_ids, jwt_tenant_id, diagram_id)
            
#             # Commit all trigger changes
#             session.commit()
            
#             # ═══════════════════════════════════════════════════════════════
#             # WORKFLOW GRAPH BUILDING
#             # ═══════════════════════════════════════════════════════════════
#             if has_nodes:
#                 workflow = StateGraph(ChatState)
#                 added_nodes = set()
#                 entry_nodes, exit_nodes = [], []

#                 for node in nodes:
#                     node_id = node.get("id")
#                     node_data = node.get("data", {})
#                     form_data = node_data.get("formData", {})
#                     node_type = form_data.get("type", "").strip() or node.get("type", "")

#                     if not node_id:
#                         continue

#                     # Include WebhookTriggerNode as entry point
#                     if node["type"] in [
#                         "ChatTriggerNode",
#                         "ManualTriggerNode",
#                         "GmailTriggerNode",
#                         "WebhookTriggerNode",
#                         "WhatsAppTriggerNode",
#                         "whatsappTriggerNode",
#                     ]:
#                         entry_nodes.append(node_id)
                    
#                     if node["type"] in ["GenralOutputNode"]:
#                         exit_nodes.append(node_id)

#                     if node_id not in added_nodes:
#                         workflow.add_node(node_id, agent_response)
#                         added_nodes.add(node_id)

#                 # Add edges
#                 for edge in edges:
#                     source = edge.get("source")
#                     target = edge.get("target")
#                     if source in added_nodes and target in added_nodes:
#                         workflow.add_edge(source, target)

#                 # Set entry point
#                 if not entry_nodes and nodes:
#                     entry_nodes.append(nodes[0]["id"])

#                 workflow.set_entry_point(entry_nodes[0])
                
#                 # Set finish point
#                 if exit_nodes:
#                     workflow.set_finish_point(exit_nodes[0])

#                 # Compile graph
#                 graph = workflow.compile()

#                 # Generate graph visualization (optional)
#                 try:
#                     graph_image = graph.get_graph().draw_mermaid_png()
#                     graph_bot_id = diagram_owner_bot_id if diagram_owner_bot_id is not None else "diagram"
#                     with open(f"workflow_graph_bot_{graph_bot_id}_diagram_{diagram_id}.png", "wb") as f:
#                         f.write(graph_image)
#                     logger.info(f"📊 Generated workflow graph image for diagram {diagram_id}")
#                 except Exception as e:
#                     logger.warning(f"⚠️ Could not generate workflow graph image: {e}")
#             else:
#                 logger.info(f"Skipping graph build for empty draft diagram {diagram_id}")

#             logger.info(f"✅ Diagram saved successfully: diagram_id={diagram_id}")
            
#             return jsonify({
#                 "data": {
#                     "diagram_id": diagram_id,
#                     "message": "Diagram saved and converted successfully!",
#                     "webhook_triggers_count": webhook_count
#                 },
#                 "status": "success"
#             }), 200 if existing_diagram else 201

#         except Exception as e:
#             session.rollback()
#             logger.exception(f"Error saving diagram for bot_id: {bot_id}")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": f"Internal server error: {str(e)}"
#             }), 500
#         finally:
#             session.close()

#     except Exception as e:
#         logger.exception("Unexpected error in save_diagram")
#         return jsonify({
#             "data": {},
#             "status": "error",
#             "message": f"Internal server error: {str(e)}"
#         }), 500

# @bot_diagram_blueprint.route('/get_diagram/<int:bot_id>', methods=['GET'])
# @jwt_required()
# def get_diagram(bot_id):
#     try:
#         claims = get_jwt()
#         jwt_tenant_id = claims.get("tenant_id")
#         logger.info(f"Fetching diagram for bot_id: {bot_id}, tenant_id: {jwt_tenant_id}")
        
#         if not jwt_tenant_id:
#             logger.error("Tenant ID missing in token")
#             return jsonify({"data": {}, "status": "error", "message": "Tenant ID missing in token"}), 401

#         session = next(db_session())
#         try:
#             bot = session.get(CustomBot, bot_id)
#             if not bot:
#                 logger.error(f"Bot not found: {bot_id}")
#                 return jsonify({"data": {}, "status": "error", "message": "Bot not found"}), 404
            
#             if str(bot.tenant_id) != str(jwt_tenant_id):
#                 logger.error(f"Unauthorized: Bot tenant_id {bot.tenant_id} does not match JWT tenant_id {jwt_tenant_id}")
#                 return jsonify({"data": {}, "status": "error", "message": "Unauthorized: Bot does not belong to your tenant"}), 403

#             workflow_name = _resolve_workflow_name(bot, bot_id)
#             legacy_workflow_name = f"custom_bot_new_{bot_id}"
#             diagram = (
#                 session.query(BotDiagram)
#                 .filter(
#                     BotDiagram.tenant_id == jwt_tenant_id,
#                     BotDiagram.del_flg == False,
#                     (
#                         (BotDiagram.workflow_name == workflow_name)
#                         | (BotDiagram.workflow_name == legacy_workflow_name)
#                         | (BotDiagram.bot_id == bot_id)
#                     )
#                 )
#                 .order_by(desc(BotDiagram.diagram_id))
#                 .first()
#             )
            
#             if not diagram:
#                 logger.warning(f"No diagram found for bot_id: {bot_id}")
#                 return jsonify({"data": {}, "status": "error", "message": "No diagram found for this bot"}), 404

#             logger.info(f"Diagram retrieved successfully: diagram_id={diagram.diagram_id}")
#             return jsonify({
#                 "data": {
#                     "diagram_id": diagram.diagram_id,
#                     "workflow_name": diagram.workflow_name or workflow_name,
#                     "channel": diagram.channel,
#                     "diagram_json": diagram.diagram_json
#                 },
#                 "status": "success",
#                 "message": "Diagram retrieved successfully"
#             }), 200

#         except Exception as e:
#             session.rollback()
#             logger.exception(f"Error retrieving diagram for bot_id: {bot_id}")
#             return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500
#         finally:
#             session.close()

#     except Exception as e:
#         logger.exception(f"Unexpected error in get_diagram for bot_id: {bot_id}")
#         return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500


# @bot_diagram_blueprint.route('/diagram/<int:diagram_id>', methods=['GET'])
# @jwt_required()
# def get_diagram_by_id(diagram_id):
#     try:
#         claims = get_jwt()
#         jwt_tenant_id = claims.get("tenant_id")
#         logger.info(f"Fetching diagram by diagram_id: {diagram_id}, tenant_id: {jwt_tenant_id}")

#         if not jwt_tenant_id:
#             logger.error("Tenant ID missing in token")
#             return jsonify({"data": {}, "status": "error", "message": "Tenant ID missing in token"}), 401

#         session = next(db_session())
#         try:
#             diagram = (
#                 session.query(BotDiagram)
#                 .filter(
#                     BotDiagram.diagram_id == diagram_id,
#                     BotDiagram.tenant_id == jwt_tenant_id,
#                     BotDiagram.del_flg == False
#                 )
#                 .first()
#             )

#             if not diagram:
#                 logger.warning(f"No diagram found for diagram_id: {diagram_id}")
#                 return jsonify({"data": {}, "status": "error", "message": "No diagram found"}), 404

#             logger.info(f"Diagram retrieved successfully by diagram_id={diagram.diagram_id}")
#             return jsonify({
#                 "data": {
#                     "diagram_id": diagram.diagram_id,
#                     "bot_id": diagram.bot_id,
#                     "workflow_name": diagram.workflow_name,
#                     "channel": diagram.channel,
#                     "diagram_json": diagram.diagram_json
#                 },
#                 "status": "success",
#                 "message": "Diagram retrieved successfully"
#             }), 200

#         except Exception as e:
#             session.rollback()
#             logger.exception(f"Error retrieving diagram for diagram_id: {diagram_id}")
#             return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500
#         finally:
#             session.close()

#     except Exception as e:
#         logger.exception(f"Unexpected error in get_diagram_by_id for diagram_id: {diagram_id}")
#         return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500


# @bot_diagram_blueprint.route('/diagram/<int:diagram_id>', methods=['DELETE'])
# @jwt_required()
# def delete_diagram(diagram_id):
#     try:
#         claims = get_jwt()
#         jwt_tenant_id = claims.get("tenant_id")

#         if not jwt_tenant_id:
#             logger.error("Tenant ID missing in token")
#             return jsonify({"data": {}, "status": "error", "message": "Tenant ID missing in token"}), 401

#         session = next(db_session())
#         try:
#             diagram = (
#                 session.query(BotDiagram)
#                 .filter(
#                     BotDiagram.diagram_id == diagram_id,
#                     BotDiagram.tenant_id == jwt_tenant_id,
#                     BotDiagram.del_flg == False
#                 )
#                 .first()
#             )

#             if not diagram:
#                 logger.warning(f"No active diagram found for deletion: diagram_id={diagram_id}")
#                 return jsonify({"data": {}, "status": "error", "message": "No diagram found"}), 404

#             diagram.del_flg = True
#             diagram.status = "deleted"

#             session.query(WorkflowTrigger).filter(
#                 WorkflowTrigger.tenant_id == jwt_tenant_id,
#                 WorkflowTrigger.flow_id == diagram_id
#             ).update(
#                 {"status": "deleted"},
#                 synchronize_session=False
#             )

#             session.commit()

#             logger.info(
#                 f"Soft deleted diagram_id={diagram_id}, tenant_id={jwt_tenant_id}"
#             )

#             return jsonify({
#                 "data": {
#                     "diagram_id": diagram_id,
#                     "deleted": True
#                 },
#                 "status": "success",
#                 "message": "Diagram deleted successfully"
#             }), 200

#         except Exception as e:
#             session.rollback()
#             logger.exception(f"Error deleting diagram for diagram_id: {diagram_id}")
#             return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500
#         finally:
#             session.close()

#     except Exception as e:
#         logger.exception(f"Unexpected error in delete_diagram for diagram_id: {diagram_id}")
#         return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500


# @bot_diagram_blueprint.route('/update_diagram_name/<int:diagram_id>', methods=['PUT', 'PATCH'])
# @jwt_required()
# def update_diagram_name(diagram_id):
#     try:
#         claims = get_jwt()
#         jwt_tenant_id = claims.get("tenant_id")

#         if not jwt_tenant_id:
#             logger.error("Tenant ID missing in token")
#             return jsonify({"data": {}, "status": "error", "message": "Tenant ID missing in token"}), 401

#         data = request.get_json(silent=True) or {}
#         workflow_name = data.get("workflow_name")

#         if not workflow_name:
#             return jsonify(
#                 {"data": {}, "status": "error", "message": "workflow_name is required"}
#             ), 400

#         session = next(db_session())
#         try:
#             diagram = (
#                 session.query(BotDiagram)
#                 .filter(
#                     BotDiagram.diagram_id == diagram_id,
#                     BotDiagram.tenant_id == jwt_tenant_id,
#                     BotDiagram.del_flg == False
#                 )
#                 .first()
#             )

#             if not diagram:
#                 return jsonify({"data": {}, "status": "error", "message": "No diagram found"}), 404

#             diagram.workflow_name = workflow_name
#             session.commit()

#             logger.info(
#                 f"Updated workflow_name for diagram_id={diagram_id}, tenant_id={jwt_tenant_id}"
#             )

#             return jsonify({
#                 "data": {
#                     "diagram_id": diagram.diagram_id,
#                     "workflow_name": diagram.workflow_name
#                 },
#                 "status": "success",
#                 "message": "Diagram name updated successfully"
#             }), 200

#         except Exception as e:
#             session.rollback()
#             logger.exception(f"Error updating workflow name for diagram_id: {diagram_id}")
#             return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500
#         finally:
#             session.close()

#     except Exception as e:
#         logger.exception(f"Unexpected error in update_diagram_name for diagram_id: {diagram_id}")
#         return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500


# @bot_diagram_blueprint.route('/diagrams', methods=['GET'])
# @jwt_required()
# def get_all_diagrams():
#     try:
#         claims = get_jwt()
#         jwt_tenant_id = claims.get("tenant_id")

#         if not jwt_tenant_id:
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "Tenant ID missing in token"
#             }), 401

#         # -----------------------------
#         # Pagination Params
#         # -----------------------------
#         page = request.args.get("page", 1, type=int)
#         limit = request.args.get("limit", 10, type=int)

#         page = max(page, 1)
#         limit = max(limit, 1)

#         # -----------------------------
#         # Filter Params
#         # -----------------------------
#         date_filter = request.args.get("date")
#         channel = request.args.get("channel")
#         status = request.args.get("status")
#         workflow_name = request.args.get("workflow_name")
#         bot_id = request.args.get("bot_id", type=int)

#         session = next(db_session())

#         try:
#             # -----------------------------
#             # Base Query (IMPORTANT: FIRST)
#             # -----------------------------
#             query = (
#                 session.query(BotDiagram)
#                 .filter(
#                     BotDiagram.tenant_id == jwt_tenant_id,
#                     BotDiagram.del_flg == False
#                 )
#             )

#             # -----------------------------
#             # Apply Filters
#             # -----------------------------

#             # Channel filter
#             if channel:
#                 query = query.filter(BotDiagram.channel == channel)

#             # Status filter
#             if status:
#                 query = query.filter(BotDiagram.status == status)

#             # Workflow name search
#             if workflow_name:
#                 query = query.filter(
#                     func.lower(BotDiagram.workflow_name).like(f"%{workflow_name.lower()}%")
#                 )

#             # Bot ID filter
#             if bot_id:
#                 query = query.filter(BotDiagram.bot_id == bot_id)

#             # -----------------------------
#             # ✅ Date Filter (FIXED)
#             # -----------------------------
#             if date_filter:
#                 now = datetime.utcnow()

#                 if date_filter == "today":
#                     start = now.replace(hour=0, minute=0, second=0, microsecond=0)
#                     query = query.filter(BotDiagram.created_at >= start)

#                 elif date_filter == "7days":
#                     start = now - timedelta(days=7)
#                     query = query.filter(BotDiagram.created_at >= start)

#                 elif date_filter == "30days":
#                     start = now - timedelta(days=30)
#                     query = query.filter(BotDiagram.created_at >= start)

#             # -----------------------------
#             # Total Count (AFTER filters)
#             # -----------------------------
#             total_records = query.count()

#             # -----------------------------
#             # Pagination + Sorting
#             # -----------------------------
#             diagrams = (
#                 query.order_by(
#                     desc(BotDiagram.updated_at),
#                     desc(BotDiagram.diagram_id)
#                 )
#                 .offset((page - 1) * limit)
#                 .limit(limit)
#                 .all()
#             )

#             total_pages = (total_records + limit - 1) // limit if limit else 0

#             # -----------------------------
#             # Response Data
#             # -----------------------------
#             items = []

#             for diagram in diagrams:
#                 bot = None
#                 if diagram.bot_id:
#                     bot = session.get(CustomBot, diagram.bot_id)

#                 items.append({
#                     "diagram_id": diagram.diagram_id,
#                     "bot_id": diagram.bot_id,
#                     "workflow_name": diagram.workflow_name,
#                     "channel": diagram.channel,
#                     "status": diagram.status,
#                     "diagram_json": diagram.diagram_json,
#                     "bot_details": serialize_custom_bot_new(bot) if bot else None,
#                     "created_at": diagram.created_at.isoformat() if diagram.created_at else None,
#                     "updated_at": diagram.updated_at.isoformat() if diagram.updated_at else None,
#                 })

#             # -----------------------------
#             # Final Response
#             # -----------------------------
#             return jsonify({
#                 "data": items,
#                 "pagination": {
#                     "page": page,
#                     "per_page": limit,
#                     "total_records": total_records,
#                     "total_pages": total_pages,
#                     "has_next": page < total_pages,
#                     "has_prev": page > 1,
#                 },
#                 "filters_applied": {
#                     "channel": channel,
#                     "status": status,
#                     "workflow_name": workflow_name,
#                     "bot_id": bot_id,
#                     "date": date_filter,   # ✅ added
#                 },
#                 "status": "success",
#                 "message": "Diagrams fetched successfully"
#             }), 200

#         except Exception as e:
#             session.rollback()
#             logger.exception("Error fetching diagrams")

#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": f"Internal server error: {str(e)}"
#             }), 500

#         finally:
#             session.close()

#     except Exception as e:
#         logger.exception("Unexpected error in get_all_diagrams")

#         return jsonify({
#             "data": {},
#             "status": "error",
#             "message": f"Internal server error: {str(e)}"
#         }), 500
    
# USER_MCP_TOOLS = {
#     "Gcalendar",
#     "Gmail",
#     "Gmaps",
#     "Gsheets",
#     "HubSpot",
#     "Tavily",
# }

# def normalize_tool_name_for_db(name: str) -> str:
#     """
#     Normalizes tool names to match existing MCPAgentTools.tool_name values.
#     Examples:
#       "hubspot"        -> "HubSpot"
#       "HubSpot"        -> "HubSpot"
#       "google maps"    -> "Gmaps"
#       "gmaps"          -> "Gmaps"
#     """
#     if not name:
#         return ""

#     key = name.strip().lower().replace(" ", "")

#     TOOL_CANONICAL_MAP = {
#         "hubspot": "HubSpot",
#         "gmaps": "Gmaps",
#         "googlemaps": "Gmaps",
#         "googlemap": "Gmaps",
#         "calendar": "Gcalendar",
#         "gmail": "Gmail",
#         "gsheets": "Gsheets",
#     }

#     return TOOL_CANONICAL_MAP.get(key, name.strip().title())

# def resolve_feature_to_mcp_tool(feature_name: str) -> str:
#     """
#     Convert a user-facing feature label into the MCP tool category used in DB.
#     """
#     if not feature_name:
#         return ""

#     raw = str(feature_name).strip()
#     key = raw.lower()

#     direct_map = {
#         "schedule meetings and reminders": "Gcalendar",
#         "send and manage professional emails": "Gmail",
#         "navigate and find locations": "Gmaps",
#         "find and navigate to fishing locations": "Gmaps",
#         "manage customer relationships and sales": "HubSpot",
#         "manage customer relationships and track interactions": "HubSpot",
#         "organize and analyze data in spreadsheets": "Gsheets",
#         "store and analyze fishing data": "Gsheets",
#         "plan and organize fishing trips": "Tavily",
#     }

#     if key in direct_map:
#         return direct_map[key]

#     keyword_map = [
#         ("Gcalendar", ["calendar", "meeting", "reminder", "schedule"]),
#         ("Gmail", ["gmail", "email", "mail"]),
#         ("Gmaps", ["map", "maps", "location", "navigate", "directions"]),
#         ("HubSpot", ["hubspot", "customer", "sales", "relationship", "interaction"]),
#         ("Gsheets", ["sheet", "sheets", "spreadsheet", "data", "analyze"]),
#         ("Tavily", ["tavily", "research", "search", "browse"]),
#     ]   

#     for tool_name, keywords in keyword_map:
#         if any(word in key for word in keywords):
#             return tool_name

#     return normalize_tool_name_for_db(raw)

# def extract_selected_core_tools(core_features) -> set:
#     # ✅ FIX: deserialize if string
#     if isinstance(core_features, str):
#         try:
#             core_features = json.loads(core_features)
#         except Exception as e:
#             logger.error(
#                 "❌ [EXTRACT] Failed to parse core_features JSON: %s",
#                 e
#             )
#             return set()

#     logger.info(
#         "🧩 [EXTRACT] core_features type=%s value=%s",
#         type(core_features),
#         core_features
#     )

#     selected = set()

#     if not core_features:
#         logger.warning("⚠️ [EXTRACT] core_features invalid or empty")
#         return selected

#     if isinstance(core_features, list):
#         for entry in core_features:
#             if isinstance(entry, str) and entry.strip():
#                 selected.add(resolve_feature_to_mcp_tool(entry))
#                 continue
#             if not isinstance(entry, dict):
#                 continue
#             tool_name = entry.get("tool_name") or entry.get("name") or entry.get("label") or entry.get("tool")
#             if not tool_name:
#                 continue
#             selected_flag = entry.get("selected")
#             if isinstance(selected_flag, str):
#                 selected_flag = selected_flag.strip().lower() in {"1", "true", "yes", "on"}
#             if selected_flag is None:
#                 selected_flag = True
#             if bool(selected_flag):
#                 selected.add(resolve_feature_to_mcp_tool(tool_name))
#         return selected

#     if not isinstance(core_features, dict):
#         logger.warning("⚠️ [EXTRACT] core_features invalid type=%s", type(core_features))
#         return selected

#     if "tools" in core_features and isinstance(core_features.get("tools"), list):
#         return extract_selected_core_tools(core_features.get("tools"))

#     for tool_name, entries in core_features.items():
#         if str(tool_name).lower() == "tavily":
#             continue

#         if not isinstance(entries, list):
#             continue

#         for entry in entries:
#             if not isinstance(entry, dict):
#                 continue
#             selected_flag = entry.get("selected")
#             if isinstance(selected_flag, str):
#                 selected_flag = selected_flag.strip().lower() in {"1", "true", "yes", "on"}
#             if selected_flag is None:
#                 selected_flag = True
#             if bool(selected_flag):
#                 selected.add(resolve_feature_to_mcp_tool(tool_name))
#                 break

#     return selected
# DEFAULT_MCP_URL = "https://mcp.jnanic.com/connect_mcp"


# def attach_mcp_tools_to_agent(session, tenant_id: int, agent_id: int, bot: CustomBot, core_features=None):
#     logger.info("🔧 [MCP_ATTACH] Starting tool attachment")
#     logger.info("🔧 [MCP_ATTACH] tenant_id=%s agent_id=%s", tenant_id, agent_id)

#     def _norm(value) -> str:
#         return "".join(ch for ch in str(value).lower() if ch.isalnum())

#     def _action_names_from_payload(payload):
#         if isinstance(payload, list):
#             names = []
#             for item in payload:
#                 if isinstance(item, dict) and item.get("action"):
#                     names.append(item["action"])
#                 elif isinstance(item, str) and item.strip():
#                     names.append(item.strip())
#             return names
#         return []

#     def _extract_tool_names_from_mcp_payload(payload):
#         names = []
#         if isinstance(payload, list):
#             for item in payload:
#                 if isinstance(item, str) and item.strip():
#                     names.append(item.strip())
#                 elif isinstance(item, dict):
#                     candidate = (
#                         item.get("tool_name")
#                         or item.get("name")
#                         or item.get("category")
#                         or item.get("label")
#                     )
#                     if isinstance(candidate, str) and candidate.strip():
#                         names.append(candidate.strip())
#         elif isinstance(payload, dict):
#             for key in payload.keys():
#                 if isinstance(key, str) and key.strip():
#                     names.append(key.strip())
#         return names

#     # ─────────────────────────────────────────────
#     # 1️⃣ RAW core_features from DB
#     # ─────────────────────────────────────────────
#     effective_core_features = bot.core_features if core_features is None else core_features
#     logger.info(
#         "🧩 [CORE_FEATURES_RAW] type=%s value=%s",
#         type(effective_core_features),
#         effective_core_features
#     )

#     allowed_tools = extract_selected_core_tools(effective_core_features)

#     # ─────────────────────────────────────────────
#     # 2️⃣ Extracted allowed tools
#     # ─────────────────────────────────────────────
#     logger.info(
#         "✅ [ALLOWED_TOOLS] extracted=%s count=%d",
#         sorted(list(allowed_tools)),
#         len(allowed_tools)
#     )
#     allowed_tool_norms = {_norm(name) for name in allowed_tools}

#     tool_auth_rows = session.query(ToolAuthorization).filter_by(
#         tenant_id=tenant_id,
#         del_flag=False
#     ).all()
#     tool_auth_by_norm = {
#         _norm(auth.tool_name): auth
#         for auth in tool_auth_rows
#         if auth.tool_name
#     }

#     session.query(McpAgentTools).filter_by(
#         tenant_id=tenant_id,
#         agent_id=agent_id,
#         del_flag=False
#     ).update({"del_flag": True})
#     session.flush()

#     if not allowed_tools:
#         logger.warning(
#             "⚠️ [MCP_ATTACH_ABORT] No allowed tools found from core_features"
#         )
#         return

#     # ─────────────────────────────────────────────
#     # 3️⃣ Load MCP tools
#     # ─────────────────────────────────────────────
#     mcp_tools = session.query(McpTools).filter(
#         McpTools.tenant_id == tenant_id,
#         McpTools.del_flag == False
#     ).all()
#     mcp_tools_by_norm = {
#         _norm(tool.mcp_name): tool
#         for tool in mcp_tools
#         if tool.mcp_name
#     }
#     mcp_tools_by_selected_norm = {}
#     for tool in mcp_tools:
#         for entry_name in _extract_tool_names_from_mcp_payload(tool.mcp_tools):
#             entry_norm = _norm(entry_name)
#             if entry_norm and entry_norm not in mcp_tools_by_selected_norm:
#                 mcp_tools_by_selected_norm[entry_norm] = tool

#     logger.info(
#         "📦 [MCP_TOOLS] tenant_id=%s found=%d",
#         tenant_id,
#         len(mcp_tools)
#     )
#     logger.info(
#         "📦 [TOOL_AUTH] tenant_id=%s found=%d names=%s",
#         tenant_id,
#         len(tool_auth_rows),
#         [auth.tool_name for auth in tool_auth_rows]
#     )
#     attached_count = 0

#     # ─────────────────────────────────────────────
#     # 4️⃣ Iterate selected tools
#     # ─────────────────────────────────────────────
#     for selected_tool in sorted(list(allowed_tools)):
#         selected_norm = _norm(selected_tool)
#         tool = mcp_tools_by_norm.get(selected_norm) or mcp_tools_by_selected_norm.get(selected_norm)
#         tool_auth = tool_auth_by_norm.get(selected_norm)

#         logger.info(
#             "🔌 [SELECTED_TOOL] name=%s norm=%s has_mcp=%s has_auth=%s",
#             selected_tool,
#             selected_norm,
#             bool(tool),
#             bool(tool_auth)
#         )

#         if not tool and not tool_auth:
#             logger.warning(
#                 "⚠️ [SELECTED_TOOL_SKIP] name=%s has no MCP config and no authorized tool row; skipping attachment",
#                 selected_tool,
#             )
#             continue

#         actions_map = tool.mcp_action_tools if tool else None
#         action_names = []
#         if tool and actions_map:
#             logger.info(
#                 "🗂️ [MCP_ACTION_MAP] tool_id=%s type=%s",
#                 tool.id,
#                 type(actions_map)
#             )

#             if isinstance(actions_map, list):
#                 action_entries = []
#                 for entry in actions_map:
#                     if not isinstance(entry, dict):
#                         continue
#                     category = (
#                         entry.get("tool_name")
#                         or entry.get("category")
#                         or entry.get("name")
#                         or tool.mcp_name
#                     )
#                     actions = (
#                         entry.get("action_tools")
#                         or entry.get("actions")
#                         or entry.get("tools")
#                         or []
#                     )
#                     action_entries.append((category, actions))
#             elif isinstance(actions_map, dict):
#                 action_entries = list(actions_map.items())
#             else:
#                 action_entries = []

#             logger.info(
#                 "🧠 [MCP_ACTION_KEYS] tool_id=%s keys=%s",
#                 tool.id,
#                 [item[0] for item in action_entries]
#             )

#             for category, actions in action_entries:
#                 canonical_category = normalize_tool_name_for_db(category)
#                 category_norm = _norm(category)
#                 tool_name_norm = _norm(tool.mcp_name)

#                 if category_norm not in allowed_tool_norms and tool_name_norm not in allowed_tool_norms:
#                     continue

#                 action_names = _action_names_from_payload(actions)
#                 if action_names:
#                     break

#         if tool and _norm(getattr(tool, "mcp_name", "")) != selected_norm:
#             canonical_tool_source = selected_tool
#         else:
#             canonical_tool_source = tool.mcp_name if tool else (tool_auth.tool_name if tool_auth else selected_tool)

#         canonical_tool_name = normalize_tool_name_for_db(canonical_tool_source)
#         mcp_url = tool.mcp_url if tool else (tool_auth.mcp_url if tool_auth else None)
#         tool_type = (tool_auth.tool_type if tool_auth else ("mcp" if tool else "local")).lower()
#         tool_config = {
#             "source": "mcp" if tool else "tool_authorization",
#             "tool_type": tool_type,
#             "selected_tool": selected_tool,
#         }

#         existing = session.query(McpAgentTools).filter_by(
#             tenant_id=tenant_id,
#             agent_id=agent_id,
#             tool_name=canonical_tool_name,
#             del_flag=False
#         ).first()

#         if existing:
#             logger.info(
#                 "♻️ [UPDATE_TOOL] agent_id=%s tool='%s' type=%s actions=%d",
#                 agent_id,
#                 canonical_tool_name,
#                 tool_type,
#                 len(action_names)
#             )
#             existing.mcp_id = tool.id if tool else None
#             existing.mcp_url = mcp_url
#             existing.action_tools = action_names
#             existing.tool_config = tool_config
#         else:
#             logger.info(
#                 "➕ [INSERT_TOOL] agent_id=%s tool='%s' type=%s actions=%d",
#                 agent_id,
#                 canonical_tool_name,
#                 tool_type,
#                 len(action_names)
#             )
#             session.add(McpAgentTools(
#                 tenant_id=tenant_id,
#                 agent_id=agent_id,
#                 mcp_id=tool.id if tool else None,
#                 tool_name=canonical_tool_name,
#                 mcp_url=mcp_url,
#                 tool_config=tool_config,
#                 action_tools=action_names,
#                 action_tools_description=[],
#                 del_flag=False
#             ))
#         attached_count += 1

#     # ─────────────────────────────────────────────
#     # 6️⃣ Flush + verification log
#     # ─────────────────────────────────────────────
#     session.flush()

#     final_tools = session.query(McpAgentTools).filter_by(
#         tenant_id=tenant_id,
#         agent_id=agent_id,
#         del_flag=False
#     ).all()

#     logger.info(
#         "✅ [MCP_ATTACH_DONE] agent_id=%s attached_count=%d tools=%s",
#         agent_id,
#         len(final_tools),
#         [t.tool_name for t in final_tools]
#     )
#     return attached_count

# def get_default_llm(session, tenant_id):
#     """
#     Returns default LLM identifiers for agent creation.
#     Does NOT create anything.
#     """

#     llm = session.query(LLM).filter(
#         LLM.tenant_id == tenant_id,
#         LLM.del_flg == False
#     ).order_by(LLM.llm_id.desc()).first()

#     if llm:
#         return {
#             "llm_id": llm.llm_id,
#             "provider": llm.provider,
#             "model_name": llm.model_name
#         }

#     # 🔁 Pure fallback (NO DB WRITE)
#     return {
#         "llm_id": None,
#         "provider": "openai",
#         "model_name": "gpt-4"
#     }

# def serialize_custom_bot_new(bot: CustomBot) -> dict:
#     """
#     Return a JSON-safe snapshot of the new bot record.
#     """
#     def enum_value(value):
#         return value.value if hasattr(value, "value") else value

#     return {
#         "bot_id": bot.bot_id,
#         "tenant_id": bot.tenant_id,
#         "instance_id": bot.instance_id,
#         "channel": enum_value(bot.channel),
#         "bot_name": bot.bot_name,
#         "tone_of_voice": enum_value(bot.tone_of_voice),
#         "industry": enum_value(bot.industry),
#         "purpose": bot.purpose,
#         "avatar": bot.avatar,
#         "core_features": bot.core_features or {},
#         "instructions": bot.instructions or [],
#         "kb_ids": bot.kb_ids or [],
#         "kb_functionalities": bot.kb_functionalities or [],
#         "bot_status": enum_value(bot.bot_status),
#         "position": bot.position,
#         "page_config": bot.page_config,
#         "specific_pages": bot.specific_pages or [],
#         "theme": bot.theme,
#         "colors": bot.colors or {},
#         "background_image": bot.background_image,
#         "background_color": bot.background_color,
#         "disclaimer_text": bot.disclaimer_text,
#         "greeting_type": bot.greeting_type,
#         "greeting_message": bot.greeting_message,
#         "published_version_id": bot.published_version_id,
#         "last_published_at": bot.last_published_at.isoformat() if bot.last_published_at else None,
#         "access_restriction_type": bot.access_restriction_type,
#         "created_at": bot.created_at.isoformat() if bot.created_at else None,
#         "updated_at": bot.updated_at.isoformat() if bot.updated_at else None,
#         "del_flg": bot.del_flg,
#     }

# #------------------------------------------------------------

# def build_multi_agent_chat_workflow(
#     bot_id: int,
#     tenant_id: int,
#     router_agent_id: int,
#     greeting_agent_id: int,
#     kb_agent_id: int = None,
#     tool_agent_id: int = None,
#     response_agent_id: int = None,
#     channel: str = "website",
#     kb_ids: list | None = None,
#     tool_names: list | None = None,
# ) -> dict:
#     """
#     UI + Runtime compatible multi-agent workflow.
#     Produces diagram structure exactly as expected by UI.
#     """
#     normalized_channel = str(channel or "website").strip().lower()

#     # ====================== CHANNEL SPECIFIC CONFIG ======================
#     if normalized_channel == "whatsapp":
#         trigger_node_id = "whatsapptrigger-4"
#         trigger_type = "WhatsAppTriggerNode"
#         trigger_label = "WhatsApp Trigger"
#         greeting_node_id = "genericagent-1"
#         greeting_node_type = "GenericAgentNode"
#         response_node_type = "GenericAgentNode"
#         final_node = {
#             "id": "whatsappsendmessage-1",
#             "type": "whatsappSendMessageNode",
#             "label": "WhatsApp Send Message",
#             "formData": {
#                 "to": "{{whatsapptrigger-4.phone || whatsapptrigger-4.from}}",
#                 "body": "{{WH_bot.output || genericagent-4.output || 'Sorry, something went wrong.'}}",
#                 "recipient_number": "{{whatsapptrigger-4.phone || whatsapptrigger-4.from}}",
#             },
#         }
#         decision_data_mapping = {"message": [f"{trigger_node_id}.0.message", f"{trigger_node_id}.0.user_query"]}
#         source_handle_for_trigger = "drag-output"

#     elif normalized_channel == "slack":
#         trigger_node_id = "slacktrigger-1"
#         trigger_type = "SlackTriggerNode"
#         trigger_label = "Slack Trigger"
#         greeting_node_id = "greetingagent-7"          # Important: matches your JSON
#         greeting_node_type = "GreetingAgentNode"
#         response_node_type = "ResponseAgentNode"      # Important for Slack
#         final_node = {
#             "id": "slacksendmessage-1",
#             "type": "slackSendMessageNode",
#             "label": "Slack Send Message",
#             "formData": {
#                 "channel": "{{slacktrigger-1.channel}}",
#                 "text": "{{genericagent-4.output || genericagent-4.output.llm_response || 'Sorry, something went wrong.'}}",
#             },
#         }
#         decision_data_mapping = {"message": ["slacktrigger-1.message"]}
#         source_handle_for_trigger = None

#     else:  # website / default
#         trigger_node_id = "chattrigger-1"
#         trigger_type = "ChatTriggerNode"
#         trigger_label = "On Chat Message"
#         greeting_node_id = "genericagent-1"
#         greeting_node_type = "GreetingAgentNode"
#         response_node_type = "GenericAgentNode"
#         final_node = None
#         decision_data_mapping = {"user_query": [f"{trigger_node_id}.user_query", "user_query", "message"]}
#         source_handle_for_trigger = None

#     # Common configurations
#     user_query_paths = [f"{trigger_node_id}.user_query", "user_query", "message"]
#     user_query_static_parameter = json.dumps(user_query_paths)

#     agent_input_form_data = {
#         "data_mapping": {"user_query": user_query_paths}
#     }

#     response_data_mapping = {
#         "user_query": user_query_paths,
#         "greeting_response": f"{greeting_node_id}.output",
#     }

#     include_kb_node = bool(kb_agent_id) and bool(kb_ids)
#     include_tool_node = bool(tool_agent_id) and bool(tool_names)

#     if include_kb_node:
#         response_data_mapping["kb_response"] = "genericagent-2.output"
#     if include_tool_node:
#         response_data_mapping["tool_response"] = "genericagent-3.output"

#     flow_data = {
#         "bot_id": bot_id,
#         "tenant_id": tenant_id,
#         "execution_mode": "BOT",
#         "trigger_data": {
#             trigger_node_id: {"inputs": {"user_query": "hi"}}
#         },
#     }
#     # ====================== NODES ======================
#     nodes = [
#         # Trigger
#         {
#             "id": trigger_node_id,
#             "type": trigger_type,
#             "position": {"x": -80, "y": 280},
#             "data": {
#                 "label": trigger_label,
#                 "id": trigger_node_id,
#                 "formData": {},
#                 "details": {},
#                 "flowData": flow_data,
#                 "executionData": {},
#             },
#             "width": 182 if normalized_channel == "slack" else 220,
#             "height": 70 if normalized_channel == "slack" else 106,
#         },
#         # Decision Router
#         {
#             "id": "decisionrouter-1",
#             "type": "DecisionRouterNode",
#             "position": {"x": 220, "y": 220},
#             "data": {
#                 "label": "Decision Router",
#                 "id": "decisionrouter-1",
#                 "formData": {
#                     "agent_id": router_agent_id,
#                     "use_temp_llm": True,
#                     "task": f"Classify the user's {normalized_channel} message as GREETING, INFORMATION, or ACTION and return ONLY the label; if the intent is unclear, return INFORMATION.",
#                     "data_mapping": decision_data_mapping,
#                     "static_parameters": {},
#                     "conditions": [],
#                     "defaultTarget": "genericagent-4",
#                     "default_target": "genericagent-4",
#                 },
#                 "details": {},
#                 "flowData": flow_data,
#                 "executionData": {},
#             },
#             "width": 292,
#             "height": 101,
#         },
#         # Greeting Agent
#         {
#             "id": greeting_node_id,
#             "type": greeting_node_type,
#             "position": {"x": 680, "y": 480} if normalized_channel == "slack" else {"x": 745.32, "y": 54.25},
#             "data": {
#                 "label": "Greeting Agent",
#                 "id": greeting_node_id,
#                 "formData": {
#                     "agent_id": greeting_agent_id,
#                     "agent_name": "Greeting Agent",
#                     "use_temp_llm": True,
#                     "task": "Respond warmly to greetings. Keep responses friendly and concise.",
#                     **agent_input_form_data,
#                 },
#                 "details": {},
#                 "flowData": flow_data,
#                 "executionData": {},
#             },
#             "width": 292 if normalized_channel == "slack" else 320,
#             "height": 101 if normalized_channel == "slack" else 130,
#         },
#         # Response Agent
#         {
#             "id": "genericagent-4",
#             "type": response_node_type,
#             "position": {"x": 1166.04, "y": 188.40},
#             "data": {
#                 "label": "Response Agent",
#                 "id": "genericagent-4",
#                 "formData": {
#                     "agent_id": response_agent_id,
#                     "agent_name": "Response Agent",
#                     "use_temp_llm": True,
#                     "task": "Format and summarize the final response for the user.",
#                     "data_mapping": response_data_mapping,
#                     "label": "Response Agent",
#                 },
#                 "details": {},
#                 "flowData": flow_data,
#                 "executionData": {},
#             },
#             "width": 292 if normalized_channel == "slack" else 320,
#             "height": 125 if normalized_channel == "slack" else 130,
#         },
#     ]

#     # Knowledge Base Agent
#     if include_kb_node:
#         nodes.append({
#             "id": "genericagent-2",
#             "type": "GenericAgentNode",
#             "position": {"x": 700, "y": 40} if normalized_channel == "slack" else {"x": 748, "y": 194},
#             "data": {
#                 "label": "Knowledge Base Agent",
#                 "id": "genericagent-2",
#                 "formData": {
#                     "agent_id": kb_agent_id,
#                     "agent_name": "Knowledge Base Agent",
#                     "use_temp_llm": True,
#                     "task": "Retrieve and answer from knowledge base. No tool execution.",
#                     "data_mapping": {"user_query": user_query_paths},
#                     "knowledge_base_ids": kb_ids or [],
#                 },
#                 "details": {"knowledge_base_ids": kb_ids or []},
#                 "flowData": flow_data,
#                 "executionData": {},
#             },
#             "width": 320,
#             "height": 114,
#         })

#     # Tool Agent
#     if include_tool_node:
#         nodes.append({
#             "id": "genericagent-3",
#             "type": "GenericAgentNode",
#             "position": {"x": 660, "y": 280} if normalized_channel == "slack" else {"x": 754, "y": 340},
#             "data": {
#                 "label": "Tool Agent",
#                 "id": "genericagent-3",
#                 "formData": {
#                     "agent_id": tool_agent_id,
#                     "agent_name": "Tool Agent",
#                     "use_temp_llm": True,
#                     "task": "Execute user-requested actions using available tools.",
#                     "data_mapping": {"user_query": user_query_paths},
#                     "tool_names": tool_names or [],
#                 },
#                 "details": {"tool_names": tool_names or []},
#                 "flowData": flow_data,
#                 "executionData": {},
#             },
#             "width": 320,
#             "height": 114,
#         })

#     # Final Send Message Node (Slack / WhatsApp)
#     if final_node:
#         nodes.append({
#             "id": final_node["id"],
#             "type": final_node["type"],
#             "position": {"x": 1580, "y": 240} if normalized_channel == "slack" else {"x": 1530, "y": 180},
#             "data": {
#                 "label": final_node["label"],
#                 "id": final_node["id"],
#                 "formData": final_node["formData"],
#                 "details": {},
#                 "flowData": flow_data,
#                 "executionData": {},
#             },
#             "width": 213 if normalized_channel == "slack" else 250,
#             "height": 70 if normalized_channel == "slack" else 120,
#         })

#     # ====================== EDGES ======================
#     edges = [
#         {
#             "source": trigger_node_id,
#             "sourceHandle": source_handle_for_trigger,
#             "target": "decisionrouter-1",
#             "targetHandle": None,
#             "type": "bezier",
#         },
#         {
#             "source": "decisionrouter-1",
#             "sourceHandle": None,
#             "target": greeting_node_id,
#             "targetHandle": None,
#             "type": "bezier",
#         },
#         {
#             "source": greeting_node_id,
#             "sourceHandle": "drag-output" if normalized_channel == "slack" else "response",
#             "target": "genericagent-4",
#             "targetHandle": None,
#             "type": "bezier",
#         },
#     ]

#     if include_kb_node:
#         edges.append({"source": "decisionrouter-1", "target": "genericagent-2", "type": "bezier"})
#         edges.append({"source": "genericagent-2", "sourceHandle": "response", "target": "genericagent-4", "type": "bezier"})

#     if include_tool_node:
#         edges.append({"source": "decisionrouter-1", "target": "genericagent-3", "type": "bezier"})
#         edges.append({"source": "genericagent-3", "sourceHandle": "response", "target": "genericagent-4", "type": "bezier"})

#     if final_node:
#         edges.append({
#             "source": "genericagent-4",
#             "sourceHandle": "response",
#             "target": final_node["id"],
#             "type": "bezier"
#         })

#     return {
#         "nodes": nodes,
#         "edges": edges,
#         "flowData": flow_data,
#     }


# def create_unified_bot_agent(session, tenant_id: int, bot_id: int, bot, core_features=None) -> dict:
#     """
#     Create/update a single Bot Agent that can use both KBs and tools.
#     Used for channel flows where hidden specialized agents are not desired.
#     """
#     llm = get_default_llm(session, tenant_id)
#     kb_ids = bot.kb_ids or []
#     if isinstance(kb_ids, str):
#         try:
#             kb_ids = json.loads(kb_ids)
#         except Exception:
#             kb_ids = []
#     if not isinstance(kb_ids, list):
#         kb_ids = []
#     kb_ids = [int(kb_id) for kb_id in kb_ids if str(kb_id).isdigit()]

#     effective_core_features = bot.core_features if core_features is None else core_features
#     selected_tools = extract_selected_core_tools(effective_core_features)
#     has_tools = len(selected_tools) > 0

#     bot_agent_key = f"bot-{bot_id}-agent"
#     bot_agent_name = _resolve_bot_agent_name(bot, bot_id)
#     bot_agent_description = f"Primary bot agent for '{(getattr(bot, 'bot_name', '') or f'Bot {bot_id}').strip()}' workflows"
#     bot_agent = session.query(Agent).filter_by(
#         tenant_id=tenant_id,
#         agent_key=bot_agent_key,
#         del_flg=False
#     ).first()

#     if not bot_agent:
#         bot_agent = Agent(
#             tenant_id=tenant_id,
#             agent_name=bot_agent_name,
#             agent_description=bot_agent_description,
#             agent_role="bot_agent",
#             llm_provider_id=llm["llm_id"],
#             llm_model_id=llm["llm_id"],
#             tool_type="mcp" if has_tools else None,
#             tool_id=None,
#             knowledge_base_ids=kb_ids,
#             agent_key=bot_agent_key,
#             deployment_method="local",
#             del_flg=False
#         )
#         session.add(bot_agent)
#         session.flush()
#     else:
#         bot_agent.agent_name = bot_agent_name
#         bot_agent.agent_description = bot_agent_description
#         bot_agent.knowledge_base_ids = kb_ids
#         bot_agent.tool_type = "mcp" if has_tools else None
#         session.flush()

#     attached_count = 0
#     if has_tools:
#         attached_count = attach_mcp_tools_to_agent(
#             session,
#             tenant_id,
#             bot_agent.agent_id,
#             bot,
#             core_features=effective_core_features
#         ) or 0
#     else:
#         session.query(McpAgentTools).filter_by(
#             tenant_id=tenant_id,
#             agent_id=bot_agent.agent_id,
#             del_flag=False
#         ).update({"del_flag": True})
#         session.flush()

#     return {
#         "agent_id": bot_agent.agent_id,
#         "kb_ids": kb_ids,
#         "tool_names": sorted(list(selected_tools)),
#         "attached_count": attached_count,
#     }


# def build_single_bot_agent_workflow(
#     bot_id: int,
#     tenant_id: int,
#     bot_agent_id: int,
#     channel: str = "website",
#     kb_ids: list | None = None,
#     tool_names: list | None = None,
#     bot_agent_name: str | None = None,
# ) -> dict:
#     """
#     Build a simple trigger -> Bot Agent -> send-message flow.
#     """
#     normalized_channel = str(channel or "website").strip().lower()

#     if normalized_channel == "whatsapp":
#         trigger_node_id = "whatsapptrigger-4"
#         trigger_type = "WhatsAppTriggerNode"
#         trigger_label = "WhatsApp Trigger"
#         trigger_source_handle = "drag-output"
#         user_query_paths = [f"{trigger_node_id}.message", f"{trigger_node_id}.user_query", "message", "user_query"]
#         final_node = {
#             "id": "whatsappsendmessage-1",
#             "type": "whatsappSendMessageNode",
#             "label": "WhatsApp Send Message",
#             "formData": {
#                 "to": "{{whatsapptrigger-4.phone || whatsapptrigger-4.from}}",
#                 "body": "{{genericagent-1.output || genericagent-1.output.llm_response || 'Sorry, something went wrong.'}}",
#                 "recipient_number": "{{whatsapptrigger-4.phone || whatsapptrigger-4.from}}",
#             },
#         }
#     elif normalized_channel == "slack":
#         trigger_node_id = "slacktrigger-1"
#         trigger_type = "SlackTriggerNode"
#         trigger_label = "Slack Trigger"
#         trigger_source_handle = None
#         user_query_paths = [f"{trigger_node_id}.message", "message", "user_query"]
#         final_node = {
#             "id": "slacksendmessage-1",
#             "type": "slackSendMessageNode",
#             "label": "Slack Send Message",
#             "formData": {
#                 "channel": "{{slacktrigger-1.channel}}",
#                 "text": "{{genericagent-1.output || genericagent-1.output.llm_response || 'Sorry, something went wrong.'}}",
#             },
#         }
#     else:
#         trigger_node_id = "chattrigger-1"
#         trigger_type = "ChatTriggerNode"
#         trigger_label = "On Chat Message"
#         trigger_source_handle = None
#         user_query_paths = [f"{trigger_node_id}.user_query", "user_query", "message"]
#         final_node = None

#     effective_bot_agent_name = (bot_agent_name or "Bot Agent").strip() or "Bot Agent"

#     flow_data = {
#         "bot_id": bot_id,
#         "tenant_id": tenant_id,
#         "execution_mode": "BOT",
#         "trigger_data": {
#             trigger_node_id: {"inputs": {"user_query": "hi"}}
#         },
#     }

#     nodes = [
#         {
#             "id": trigger_node_id,
#             "type": trigger_type,
#             "position": {"x": -20, "y": 300},
#             "data": {
#                 "label": trigger_label,
#                 "id": trigger_node_id,
#                 "formData": {},
#                 "details": {},
#                 "flowData": flow_data,
#                 "executionData": {},
#             },
#             "width": 220,
#             "height": 106,
#         },
#         {
#             "id": "genericagent-1",
#             "type": "GenericAgentNode",
#             "position": {"x": 320, "y": 320},
#             "data": {
#                 "label": effective_bot_agent_name,
#                 "id": "genericagent-1",
#                 "formData": {
#                     "agent_id": str(bot_agent_id),
#                     "agent_name": effective_bot_agent_name,
#                     "agent_description": "Primary bot agent for this workflow",
#                     "task": (
#                         "You are an intelligent assistant that handles greetings, knowledge base answers, and tool-based actions.\n\n"
#                         "Guidelines:\n"
#                         "- Reply naturally and conversationally.\n"
#                         "- Answer only using relevant knowledge base content or approved tool results.\n"
#                         "- Do not generate information outside the provided knowledge base or tool output.\n"
#                         "- Use tools only when necessary to complete the request.\n"
#                         "- Keep responses direct, accurate, and concise.\n"
#                         "- Do not mention knowledge base, tools, sources, browsing, or limitations.\n"
#                         "- Avoid phrases like \"Based on\", \"According to\", or \"I would need access\".\n"
#                         "- If no relevant information is available, reply exactly:\n"
#                         "I could not find this in the selected knowledge base."
#                     ),
#                     "data_mapping": {"user_query": user_query_paths},
#                     "static_parameters": {"message": f"{trigger_node_id}.message"},
#                     "knowledge_base_ids": kb_ids or [],
#                     "tool_names": tool_names or [],
#                     "label": effective_bot_agent_name,
#                 },
#                 "details": {
#                     "agent_id": bot_agent_id,
#                     "knowledge_base_ids": kb_ids or [],
#                     "tool_names": tool_names or [],
#                 },
#                 "flowData": flow_data,
#                 "executionData": {},
#             },
#             "width": 320,
#             "height": 114,
#         },
#     ]

#     edges = [
#         {
#             "source": trigger_node_id,
#             "sourceHandle": trigger_source_handle,
#             "target": "genericagent-1",
#             "targetHandle": None,
#             "type": "bezier",
#         }
#     ]

#     if final_node:
#         nodes.append({
#             "id": final_node["id"],
#             "type": final_node["type"],
#             "position": {"x": 760, "y": 300},
#             "data": {
#                 "label": final_node["label"],
#                 "id": final_node["id"],
#                 "formData": final_node["formData"],
#                 "details": {},
#                 "flowData": flow_data,
#                 "executionData": {},
#             },
#             "width": 250,
#             "height": 120,
#         })
#         edges.append({
#             "source": "genericagent-1",
#             "sourceHandle": "response",
#             "target": final_node["id"],
#             "type": "bezier",
#         })

#     return {
#         "nodes": nodes,
#         "edges": edges,
#         "flowData": flow_data,
#     }


# def verify_agent_mappings(session, tenant_id: int, agent_ids: dict) -> dict:
#     """
#     Verifies that KBs and tools are correctly assigned to respective agents.
    
#     Returns:
#         {
#             "valid": bool,
#             "errors": list,
#             "summary": dict
#         }
#     """
#     errors = []
#     summary = {}
    
#     # Check each agent type
#     for agent_type, agent_id in agent_ids.items():
#         agent = session.query(Agent).filter_by(
#             agent_id=agent_id,
#             tenant_id=tenant_id,
#             del_flg=False
#         ).first()
        
#         if not agent:
#             errors.append(f"{agent_type} agent not found (ID: {agent_id})")
#             continue
        
#         # Check MCP tools assignment
#         mcp_tools = session.query(McpAgentTools).filter_by(
#             agent_id=agent_id,
#             tenant_id=tenant_id,
#             del_flag=False
#         ).all()
        
#         tool_count = len(mcp_tools)
#         kb_count = len(agent.knowledge_base_ids or [])
        
#         summary[agent_type] = {
#             "agent_id": agent_id,
#             "has_tools": tool_count > 0,
#             "tool_count": tool_count,
#             "has_kb": kb_count > 0,
#             "kb_count": kb_count,
#             "tool_type": agent.tool_type
#         }
        
#         # ✅ VALIDATION RULES
#         if agent_type == "router":
#             if tool_count > 0:
#                 errors.append(f"Router agent should NOT have tools (has {tool_count})")
#             if kb_count > 0:
#                 errors.append(f"Router agent should NOT have KBs (has {kb_count})")
        
#         elif agent_type == "greeting":
#             if tool_count > 0:
#                 errors.append(f"Greeting agent should NOT have tools (has {tool_count})")
#             if kb_count > 0:
#                 errors.append(f"Greeting agent should NOT have KBs (has {kb_count})")
        
#         elif agent_type == "kb":
#             if tool_count > 0:
#                 errors.append(f"KB agent should NOT have tools (has {tool_count})")
#             if kb_count == 0:
#                 errors.append(f"KB agent MUST have at least one KB (has {kb_count})")
#             if agent.tool_type is not None:
#                 errors.append(f"KB agent tool_type should be NULL (is '{agent.tool_type}')")
        
#         elif agent_type == "tool":
#             if tool_count == 0:
#                 errors.append(f"Tool agent MUST have tools (has {tool_count})")
#             if agent.tool_type != "mcp":
#                 errors.append(f"Tool agent tool_type should be 'mcp' (is '{agent.tool_type}')")
#             # Tool agent can optionally have KB for context
        
#         elif agent_type == "response":
#             if tool_count > 0:
#                 errors.append(f"Response agent should NOT have tools (has {tool_count})")
#             if kb_count > 0:
#                 errors.append(f"Response agent should NOT have KBs (has {kb_count})")
    
#     return {
#         "valid": len(errors) == 0,
#         "errors": errors,
#         "summary": summary
#     }



# def create_specialized_agents(session, tenant_id: int, bot_id: int, bot, core_features=None) -> dict:
#     """
#     Creates specialized agents only when their backing data exists:
#     1. Router (decision maker, no tools)
#     2. Greeting (no tools, no KB)
#     3. KB Agent (KB only, no tools)
#     4. Tool Agent (tools only, minimal KB)
#     5. Response Agent (formatting only)
#     """
    
#     llm = get_default_llm(session, tenant_id)
#     kb_ids = bot.kb_ids or []
#     if isinstance(kb_ids, str):
#         try:
#             kb_ids = json.loads(kb_ids)
#         except Exception:
#             kb_ids = []
#     if not isinstance(kb_ids, list):
#         kb_ids = []
#     kb_ids = [int(kb_id) for kb_id in kb_ids if str(kb_id).isdigit()]
#     has_kb = len(kb_ids) > 0
#     effective_core_features = bot.core_features if core_features is None else core_features
#     selected_tools = extract_selected_core_tools(effective_core_features)
#     has_tools = len(selected_tools) > 0

#     logger.info(
#         "🧩 [SPECIALIZED_AGENTS] bot_id=%s tenant_id=%s has_kb=%s has_tools=%s selected_tools=%s",
#         bot_id,
#         tenant_id,
#         has_kb,
#         has_tools,
#         sorted(list(selected_tools))
#     )
#     logger.info(
#         "🧩 [SPECIALIZED_AGENTS] core_features_type=%s core_features=%s",
#         type(effective_core_features),
#         effective_core_features
#     )
    
#     agents = {}
    
#     # 1. ROUTER AGENT (lightweight classification)
#     router_key = f"bot-{bot_id}-router"
#     router = session.query(Agent).filter_by(
#         tenant_id=tenant_id,
#         agent_key=router_key,
#         del_flg=False
#     ).first()
    
#     if not router:
#         router = Agent(
#             tenant_id=tenant_id,
#             agent_name="Intent Router",
#             agent_description="Classifies user intent (greeting/info/action)",
#             agent_role="router",
#             llm_provider_id=llm["llm_id"],
#             llm_model_id=llm["llm_id"],
#             tool_type=None,  # NO TOOLS
#             tool_id=None,
#             knowledge_base_ids=[],
#             agent_key=router_key,
#             deployment_method="local",
#             del_flg=False
#         )
#         session.add(router)
#         session.flush()
    
#     agents["router"] = router.agent_id
    
#     # 2. GREETING AGENT (simple responses)
#     greeting_key = f"bot-{bot_id}-greeting"
#     greeting = session.query(Agent).filter_by(
#         tenant_id=tenant_id,
#         agent_key=greeting_key,
#         del_flg=False
#     ).first()
    
#     if not greeting:
#         greeting = Agent(
#             tenant_id=tenant_id,
#             agent_name="Greeting Agent",
#             agent_description="Handles greetings and small talk",
#             agent_role="greeting",
#             llm_provider_id=llm["llm_id"],
#             llm_model_id=llm["llm_id"],
#             tool_type=None,
#             tool_id=None,
#             knowledge_base_ids=[],
#             agent_key=greeting_key,
#             deployment_method="local",
#             del_flg=False
#         )
#         session.add(greeting)
#         session.flush()
    
#     agents["greeting"] = greeting.agent_id
    
#     # 3. KB AGENT (knowledge retrieval only)
#     if has_kb:
#         kb_key = f"bot-{bot_id}-kb"
#         kb_agent = session.query(Agent).filter_by(
#             tenant_id=tenant_id,
#             agent_key=kb_key,
#             del_flg=False
#         ).first()
        
#         if not kb_agent:
#             kb_agent = Agent(
#                 tenant_id=tenant_id,
#                 agent_name="Knowledge Base Agent",
#                 agent_description="Answers questions from knowledge base",
#                 agent_role="knowledge_retrieval",
#                 llm_provider_id=llm["llm_id"],
#                 llm_model_id=llm["llm_id"],
#                 tool_type=None,
#                 tool_id=None,
#                 knowledge_base_ids=kb_ids,
#                 agent_key=kb_key,
#                 deployment_method="local",
#                 del_flg=False
#             )
#             session.add(kb_agent)
#             session.flush()
#         elif kb_agent.knowledge_base_ids != kb_ids:
#             kb_agent.knowledge_base_ids = kb_ids
#             session.flush()
        
#         agents["kb"] = kb_agent.agent_id
    
#     # 4. TOOL AGENT (action execution)
#     if has_tools:
#         tool_key = f"bot-{bot_id}-tools"
#         tool_agent = session.query(Agent).filter_by(
#             tenant_id=tenant_id,
#             agent_key=tool_key,
#             del_flg=False
#         ).first()
        
#         if not tool_agent:
#             tool_agent = Agent(
#                 tenant_id=tenant_id,
#                 agent_name="Tool Execution Agent",
#                 agent_description="Executes actions using tools",
#                 agent_role="tool_executor",
#                 llm_provider_id=llm["llm_id"],
#                 llm_model_id=llm["llm_id"],
#                 tool_type="mcp",
#                 tool_id=None,
#                 knowledge_base_ids=[],
#                 agent_key=tool_key,
#                 deployment_method="local",
#                 del_flg=False
#             )
#             session.add(tool_agent)
#             session.flush()
        
#         attached_count = attach_mcp_tools_to_agent(
#             session,
#             tenant_id,
#             tool_agent.agent_id,
#             bot,
#             core_features=effective_core_features
#         )
#         logger.info(
#             "🧩 [SPECIALIZED_AGENTS] tool_agent_id=%s attached_count=%s",
#             tool_agent.agent_id,
#             attached_count
#         )
#         if attached_count > 0:
#             agents["tool"] = tool_agent.agent_id
#         else:
#             logger.warning(
#                 "⚠️ [TOOL_AGENT_SKIPPED] tool agent created but no MCP tools attached for bot_id=%s",
#                 bot_id
#             )
#     else:
#         # Ensure removed tools are reflected by soft-deleting previously attached MCP tools.
#         tool_key = f"bot-{bot_id}-tools"
#         existing_tool_agent = session.query(Agent).filter_by(
#             tenant_id=tenant_id,
#             agent_key=tool_key,
#             del_flg=False
#         ).first()
#         if existing_tool_agent:
#             session.query(McpAgentTools).filter_by(
#                 tenant_id=tenant_id,
#                 agent_id=existing_tool_agent.agent_id,
#                 del_flag=False
#             ).update({"del_flag": True})
#             session.flush()
#             logger.info(
#                 "🧹 [TOOL_CLEANUP] Cleared MCP tools for bot_id=%s tool_agent_id=%s",
#                 bot_id,
#                 existing_tool_agent.agent_id
#             )
    
#     # 5. RESPONSE AGENT (formatting/summarization)
#     response_key = f"bot-{bot_id}-response"
#     response_agent = session.query(Agent).filter_by(
#         tenant_id=tenant_id,
#         agent_key=response_key,
#         del_flg=False
#     ).first()
    
#     if not response_agent:
#         response_agent = Agent(
#             tenant_id=tenant_id,
#             agent_name="Response Formatter",
#             agent_description="Formats and summarizes final responses",
#             agent_role="response_formatter",
#             llm_provider_id=llm["llm_id"],
#             llm_model_id=llm["llm_id"],
#             tool_type=None,
#             tool_id=None,
#             knowledge_base_ids=[],
#             agent_key=response_key,
#             deployment_method="local",
#             del_flg=False
#         )
#         session.add(response_agent)
#         session.flush()
    
#     agents["response"] = response_agent.agent_id
    
#     return {
#         "agents": agents,
#         "kb_ids": kb_ids,
#         "tool_names": sorted(list(selected_tools)),
#     }

# @bot_diagram_blueprint.route("/<int:bot_id>/initialize-workflow", methods=["POST"])
# @jwt_required()
# def initialize_bot_workflow_v2(bot_id):
#     """
#     Updated endpoint using multi-agent router architecture.
#     Creates a workflow diagram when missing, otherwise regenerates and updates
#     the existing diagram.
#     """
#     session = None

#     try:
#         jwt_claims = get_jwt() or {}
#         tenant_id = _coerce_int(jwt_claims.get("tenant_id"))
#         if tenant_id is None:
#             tenant_id = _coerce_int(get_jwt_identity())
#         if tenant_id is None:
#             return jsonify({
#                 "status": "error",
#                 "message": "tenant_id missing in JWT claims/identity"
#             }), 401

#         session = next(db_session())
#         request_data = request.get_json(silent=True) or {}
#         logger.info(
#             "🚀 [INIT_WORKFLOW] bot_id=%s tenant_id=%s request_data=%s",
#             bot_id,
#             tenant_id,
#             request_data
#         )
#         bot = session.query(CustomBot).filter_by(
#             bot_id=bot_id,
#             tenant_id=tenant_id,
#             del_flg=False
#         ).first()
        
#         if not bot:
#             return jsonify({"error": "Bot not found"}), 404

#         bot_details = serialize_custom_bot_new(bot)
#         workflow_name = _resolve_workflow_name(bot, bot_id)
#         legacy_workflow_name = f"custom_bot_new_{bot_id}"
#         requested_channel = (
#             request_data.get("channel")
#             or request_data.get("channels")
#             or getattr(bot.channel, "value", None)
#             or "website"
#         )
#         has_core_features_in_request = (
#             "core_features" in request_data or "tools" in request_data
#         )
#         if "core_features" in request_data:
#             requested_core_features = request_data.get("core_features")
#         elif "tools" in request_data:
#             requested_core_features = request_data.get("tools")
#         else:
#             requested_core_features = bot.core_features

#         # If caller explicitly sends null, treat as empty selection.
#         if has_core_features_in_request and requested_core_features is None:
#             requested_core_features = []
#         logger.info(
#             "🚀 [INIT_WORKFLOW] workflow_name=%s requested_core_features_type=%s requested_core_features=%s",
#             workflow_name,
#             type(requested_core_features),
#             requested_core_features
#         )
        
#         # Check whether a workflow diagram already exists for this bot.
#         existing_diagram = (
#             session.query(BotDiagram)
#             .filter(
#                 BotDiagram.tenant_id == tenant_id,
#                 BotDiagram.workflow_name.in_([workflow_name, legacy_workflow_name]),
#                 BotDiagram.del_flg == False,
#                 or_(BotDiagram.bot_id == bot_id, BotDiagram.bot_id.is_(None))
#             )
#             .order_by(desc(BotDiagram.diagram_id))
#             .first()
#         )

#         channel_key = str(requested_channel or "").strip().lower()
#         architecture = "multi_agent_router"

#         unified = create_unified_bot_agent(
#             session=session,
#             tenant_id=tenant_id,
#             bot_id=bot_id,
#             bot=bot,
#             core_features=requested_core_features
#         )
#         agent_ids = {"bot": unified["agent_id"]}
#         verification = {
#             "valid": True,
#             "errors": [],
#             "summary": {
#                 "bot": {
#                     "agent_id": unified["agent_id"],
#                     "kb_count": len(unified.get("kb_ids") or []),
#                     "tool_count": len(unified.get("tool_names") or []),
#                 }
#             }
#         }
#         diagram = build_single_bot_agent_workflow(
#             bot_id=bot_id,
#             tenant_id=tenant_id,
#             bot_agent_id=unified["agent_id"],
#             channel=requested_channel,
#             kb_ids=unified.get("kb_ids"),
#             tool_names=unified.get("tool_names"),
#             bot_agent_name=_resolve_bot_agent_name(bot, bot_id),
#         )
#         architecture = "single_bot_agent"
        
#         if existing_diagram:
#             existing_diagram.diagram_json = json.dumps(diagram)
#             existing_diagram.channel = requested_channel
#             existing_diagram.status = "updated"
#             channel_key = str(requested_channel or "").strip().lower()
#             if channel_key == "whatsapp":
#                 extract_and_store_whatsapp_triggers(
#                     diagram,
#                     bot_id,
#                     tenant_id,
#                     session,
#                     existing_diagram.diagram_id,
#                 )
#             elif channel_key == "slack":
#                 extract_and_store_slack_triggers(
#                     diagram,
#                     bot_id,
#                     tenant_id,
#                     session,
#                     existing_diagram.diagram_id,
#                 )
#             session.commit()

#             return jsonify({
#                 "status": "updated",
#                 "architecture": architecture,
#                 "message": "Existing workflow diagram has been regenerated",
#                 "bot_details": bot_details,
#                 "workflow_id": existing_diagram.diagram_id,
#                 "workflow_name": existing_diagram.workflow_name or workflow_name,
#                 "diagram_id": existing_diagram.diagram_id,
#                 "channel": existing_diagram.channel,
#                 "agents": agent_ids,
#                 "verification": verification,
#                 "diagram": diagram
#             }), 200

#         new_diagram = _create_bot_diagram_with_fk_compat(
#             session=session,
#             bot_id=bot_id,
#             tenant_id=tenant_id,
#             workflow_name=workflow_name,
#             channel=requested_channel,
#             status="created",
#             diagram_json=json.dumps(diagram)
#         )

#         if channel_key == "whatsapp":
#             extract_and_store_whatsapp_triggers(
#                 diagram,
#                 bot_id,
#                 tenant_id,
#                 session,
#                 new_diagram.diagram_id,
#             )
#         elif channel_key == "slack":
#             extract_and_store_slack_triggers(
#                 diagram,
#                 bot_id,
#                 tenant_id,
#                 session,
#                 new_diagram.diagram_id,
#             )

#         session.commit()

#         return jsonify({
#             "status": "created",
#             "architecture": architecture,
#             "bot_details": bot_details,
#             "workflow_id": new_diagram.diagram_id,
#             "workflow_name": workflow_name,
#             "diagram_id": new_diagram.diagram_id,
#             "channel": new_diagram.channel,
#             "agents": agent_ids,
#             "verification": verification,
#             "diagram": diagram
#         }), 201
        
#     except Exception as e:
#         if session is not None:
#             session.rollback()
#         logger.exception("❌ [INIT_WORKFLOW_ERROR]")
#         return jsonify({
#             "status": "error",
#             "message": str(e)
#         }), 500
#     finally:
#         if session is not None:
#             session.close()





from flask import Blueprint, request, jsonify
from app.models.bot_diagram import BotDiagram
from app.models.new_models.custom_bot import CustomBotNew as CustomBot
from app.models import Agent,McpTools,McpAgentTools,LLM,KnowledgeBase,ToolAuthorization
from app.models.tool import Tools
from app.models.agent import AgentStatusEnum
from app.database.DatabaseOperationPostgreSQL import db_session
import json
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from langgraph.graph import StateGraph
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from sqlalchemy import desc, func, or_
from sqlalchemy.exc import SQLAlchemyError
from app.models.workflow_trigger import WorkflowTrigger
from app.services.channel_credentials_service import (
    get_legacy_tool_credentials,
    get_slack_credentials_for_bot,
    get_whatsapp_credentials_for_bot,
)
from logging_config import setup_logging
import json
from datetime import datetime, timedelta

logger = setup_logging("bot_diagram", level="DEBUG")

bot_diagram_blueprint = Blueprint('bot_diagram', __name__)

llm = ChatOpenAI(
    model_name="gpt-3.5-turbo",
    temperature=0.7,
    openai_api_key="YOUR_OPENAI_API_KEY"
)

class ChatState(BaseModel):
    message: str
    response: str

def agent_response(state: ChatState):
    response = llm.invoke(state.message)
    return ChatState(message=state.message, response=str(response))


def _coerce_int(value):
    """Best-effort integer coercion; returns None when invalid."""
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_workflow_name(bot, bot_id: int) -> str:
    """
    Use bot name as workflow name; fallback to legacy pattern for empty names.
    """
    name = (getattr(bot, "bot_name", "") or "").strip()
    return name if name else f"custom_bot_new_{bot_id}"

def _resolve_flow_bot_id(diagram_data):
    """
    Resolve bot_id from workflow payload when top-level request bot_id is missing.
    Priority:
    1) diagram_json.flowData.bot_id
    2) first node.data.flowData.bot_id
    """
    if not isinstance(diagram_data, dict):
        return None

    root_flow_data = diagram_data.get("flowData")
    if isinstance(root_flow_data, dict):
        root_bot_id = _coerce_int(root_flow_data.get("bot_id"))
        if root_bot_id is not None:
            return root_bot_id

    nodes = diagram_data.get("nodes", [])
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_data = node.get("data")
            if not isinstance(node_data, dict):
                continue
            node_flow_data = node_data.get("flowData")
            if not isinstance(node_flow_data, dict):
                continue
            node_bot_id = _coerce_int(node_flow_data.get("bot_id"))
            if node_bot_id is not None:
                return node_bot_id

    return None


def _is_legacy_bot_diagram_fk_mismatch(exc: Exception) -> bool:
    """
    Detects environments where tbl_bot_diagrams.bot_id FK still points to tbl_custombot.
    """
    err = str(exc)
    return (
        "tbl_bot_diagrams_bot_id_fkey" in err
        and "tbl_custombot" in err
    )


def _create_bot_diagram_with_fk_compat(
    session,
    *,
    bot_id,
    tenant_id,
    workflow_name,
    channel,
    status,
    diagram_json,
):
    """
    Create a BotDiagram with compatibility fallback for legacy DB constraints.
    In some environments, tbl_bot_diagrams.bot_id still references tbl_custombot
    while runtime uses tbl_custombot_new IDs.
    """
    payload = {
        "bot_id": bot_id,
        "tenant_id": tenant_id,
        "workflow_name": workflow_name,
        "channel": channel,
        "status": status,
        "diagram_json": diagram_json,
    }

    try:
        with session.begin_nested():
            new_diagram = BotDiagram(**payload)
            session.add(new_diagram)
            session.flush()
        return new_diagram
    except SQLAlchemyError as exc:
        if bot_id is not None and _is_legacy_bot_diagram_fk_mismatch(exc):
            logger.warning(
                "[BOT_DIAGRAM_FK_COMPAT] Legacy FK mismatch detected. "
                "Retrying diagram insert with bot_id=NULL for tenant_id=%s workflow_name=%s bot_id=%s",
                tenant_id,
                workflow_name,
                bot_id,
            )
            fallback_payload = dict(payload)
            fallback_payload["bot_id"] = None
            with session.begin_nested():
                new_diagram = BotDiagram(**fallback_payload)
                session.add(new_diagram)
                session.flush()
            return new_diagram
        raise

def _assign_existing_diagram_bot_id_with_fk_compat(
    session,
    *,
    diagram,
    bot_id,
    tenant_id,
):
    """
    Update diagram.bot_id with compatibility fallback for legacy FK constraints.
    """
    try:
        with session.begin_nested():
            diagram.bot_id = bot_id
            session.flush()
    except SQLAlchemyError as exc:
        if bot_id is not None and _is_legacy_bot_diagram_fk_mismatch(exc):
            logger.warning(
                "[BOT_DIAGRAM_FK_COMPAT] Legacy FK mismatch detected on update. "
                "Retrying diagram update with bot_id=NULL for tenant_id=%s diagram_id=%s bot_id=%s",
                tenant_id,
                diagram.diagram_id,
                bot_id,
            )
            with session.begin_nested():
                diagram.bot_id = None
                session.flush()
            return
        raise

def extract_and_store_triggers(diagram_data, bot_id, tenant_id, session, flow_id):
    """
    Extract and store Gmail triggers from diagram.
    """
    logger.info(f"[TRIGGER_SYNC] Processing Gmail triggers for bot_id={bot_id}, tenant_id={tenant_id}")

    try:
        nodes = diagram_data.get("nodes", [])
        if not isinstance(nodes, list):
            logger.error("[TRIGGER_SYNC] Invalid diagram format: 'nodes' must be a list.")
            return

        trigger_count = 0

        for node in nodes:
            if node.get("type") != "GmailTriggerNode":
                continue

            trigger_node_id = node.get("id")
            gmail_data = node.get("data", {}).get("formData", {}).get("gmail", {})

            if not gmail_data:
                logger.warning(f"[TRIGGER_SYNC] GmailTriggerNode '{trigger_node_id}' missing config.")
                continue

            enable_mode = gmail_data.get("enableMode", False)

            schedule = (
                {
                    "mode": gmail_data.get("mode"),
                    "hour": gmail_data.get("hour"),
                    "minute": gmail_data.get("minute"),
                    "weekday": gmail_data.get("weekday")
                }
                if enable_mode else None
            )

            filters = gmail_data.get("filters", {})

            trigger_entry = session.query(WorkflowTrigger).filter_by(
                bot_id=bot_id,
                tenant_id=tenant_id,
                trigger_node_id=trigger_node_id,
                flow_id=flow_id
            ).first()

            if not trigger_entry:
                trigger_entry = WorkflowTrigger(
                    bot_id=bot_id,
                    tenant_id=tenant_id,
                    flow_id=flow_id,
                    trigger_node_id=trigger_node_id,
                    trigger_type="gmail",
                    status="active"
                )

            trigger_entry.schedule_meta = schedule
            trigger_entry.filter_meta = filters
            trigger_entry.raw_trigger_json = gmail_data

            session.merge(trigger_entry)
            trigger_count += 1

        logger.info(f"[TRIGGER_SYNC] {trigger_count} Gmail trigger(s) stored.")

    except Exception:
        logger.exception("[TRIGGER_SYNC] Unexpected error processing Gmail triggers")
        raise


def _fetch_tool_credentials(session, tenant_id: int, tool_name: str, bot_id: int | None = None) -> dict:
    """
    Fetch saved credentials from tbl_tool_authorization for a given tool.
    Returns a flat dict of all credential keys, or {} if not found.
    """
    try:
        if tool_name.lower() == "whatsapp":
            bot_creds = get_whatsapp_credentials_for_bot(session, bot_id)
            if bot_creds.get("access_token") or bot_creds.get("phone_number_id"):
                return bot_creds
        if tool_name.lower() == "slack":
            bot_creds = get_slack_credentials_for_bot(session, bot_id)
            if bot_creds.get("bot_token") or bot_creds.get("signing_secret"):
                return bot_creds

        return get_legacy_tool_credentials(session, tenant_id, tool_name)
    except Exception as e:
        logger.warning("[TRIGGER_SYNC] Could not fetch tool credentials for %s: %s", tool_name, e)
        return {}


def _hydrate_trigger_credentials_in_diagram(
    diagram_data: dict,
    session,
    tenant_id: int,
    bot_id: int,
    channel: str | None = None,
) -> dict:
    """
    Inject saved Slack/WhatsApp credentials into trigger node formData so workflow
    editor settings are prefilled on initialize/edit flows.
    """
    if not isinstance(diagram_data, dict):
        return diagram_data

    nodes = diagram_data.get("nodes")
    if not isinstance(nodes, list):
        return diagram_data

    channel_key = str(channel or "").strip().lower()
    inject_whatsapp = channel_key in {"", "whatsapp"}
    inject_slack = channel_key in {"", "slack"}

    whatsapp_creds = _fetch_tool_credentials(session, tenant_id, "whatsapp", bot_id=bot_id) if inject_whatsapp else {}
    slack_creds = _fetch_tool_credentials(session, tenant_id, "slack", bot_id=bot_id) if inject_slack else {}

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = node.get("type")
        node_data = node.get("data")
        if not isinstance(node_data, dict):
            node_data = {}
            node["data"] = node_data
        form_data = node_data.get("formData")
        if not isinstance(form_data, dict):
            form_data = {}
            node_data["formData"] = form_data

        if node_type in {"WhatsAppTriggerNode", "whatsappTriggerNode"} and whatsapp_creds:
            if not form_data.get("access_token") and whatsapp_creds.get("access_token"):
                form_data["access_token"] = whatsapp_creds["access_token"]
            if not form_data.get("phone_number_id") and whatsapp_creds.get("phone_number_id"):
                form_data["phone_number_id"] = whatsapp_creds["phone_number_id"]
            if not form_data.get("verify_token") and whatsapp_creds.get("verify_token"):
                form_data["verify_token"] = whatsapp_creds["verify_token"]

            nested_whatsapp = form_data.get("whatsapp")
            if not isinstance(nested_whatsapp, dict):
                nested_whatsapp = {}
                form_data["whatsapp"] = nested_whatsapp

            if not nested_whatsapp.get("access_token") and whatsapp_creds.get("access_token"):
                nested_whatsapp["access_token"] = whatsapp_creds["access_token"]
            if not nested_whatsapp.get("phone_number_id") and whatsapp_creds.get("phone_number_id"):
                nested_whatsapp["phone_number_id"] = whatsapp_creds["phone_number_id"]
            if not nested_whatsapp.get("verify_token") and whatsapp_creds.get("verify_token"):
                nested_whatsapp["verify_token"] = whatsapp_creds["verify_token"]

        if node_type in {"SlackTriggerNode", "slackTriggerNode"} and slack_creds:
            if not form_data.get("bot_token") and slack_creds.get("bot_token"):
                form_data["bot_token"] = slack_creds["bot_token"]
            if not form_data.get("signing_secret") and slack_creds.get("signing_secret"):
                form_data["signing_secret"] = slack_creds["signing_secret"]
            if not form_data.get("channel_id") and slack_creds.get("channel_id"):
                form_data["channel_id"] = slack_creds["channel_id"]

            nested_slack = form_data.get("slack")
            if not isinstance(nested_slack, dict):
                nested_slack = {}
                form_data["slack"] = nested_slack

            if not nested_slack.get("bot_token") and slack_creds.get("bot_token"):
                nested_slack["bot_token"] = slack_creds["bot_token"]
            if not nested_slack.get("signing_secret") and slack_creds.get("signing_secret"):
                nested_slack["signing_secret"] = slack_creds["signing_secret"]
            if not nested_slack.get("channel_id") and slack_creds.get("channel_id"):
                nested_slack["channel_id"] = slack_creds["channel_id"]

    return diagram_data


def _normalize_whatsapp_trigger_config(node: dict) -> dict:
    """
    Normalize WhatsApp trigger config so both editor and runtime conventions work.
    Supports:
      - data.formData.whatsapp.*
      - data.formData.* (flat)
    """
    node_data = node.get("data", {}) if isinstance(node, dict) else {}
    form_data = node_data.get("formData", {}) if isinstance(node_data, dict) else {}

    if not isinstance(form_data, dict):
        form_data = {}

    whatsapp_data = form_data.get("whatsapp", {})
    if not isinstance(whatsapp_data, dict):
        whatsapp_data = {}

    merged = dict(whatsapp_data)
    for key, value in form_data.items():
        if key != "whatsapp" and key not in merged:
            merged[key] = value

    event_filter = (
        merged.get("event_filter")
        or merged.get("eventFilter")
        or merged.get("filter")
        or {}
    )
    field_mapping = (
        merged.get("field_mapping")
        or merged.get("fieldMapping")
        or {}
    )

    return {
        "whatsapp": whatsapp_data,
        "webhook_name": (
            merged.get("webhook_name")
            or merged.get("webhookName")
            or f"whatsapp_{node.get('id', 'trigger')}"
        ),
        "verify_token": (
            merged.get("verify_token")
            or merged.get("verifyToken")
            or ""
        ),
        "include_status_updates": merged.get("include_status_updates"),
        "event_filter": event_filter,
        "eventFilter": event_filter,
        "filter": event_filter,
        "field_mapping": field_mapping,
        "fieldMapping": field_mapping,
        "node_data": node_data,
    }


def _normalize_whatsapp_trigger_node_id(diagram_data: dict) -> tuple[dict, bool]:
    """
    Ensure WhatsApp trigger node uses a stable id: whatsapptrigger-4.
    This keeps Meta webhook URL stable across re-saves in the builder.
    """
    if not isinstance(diagram_data, dict):
        return diagram_data, False

    nodes = diagram_data.get("nodes", [])
    edges = diagram_data.get("edges", [])
    if not isinstance(nodes, list):
        return diagram_data, False

    whatsapp_nodes = [
        node for node in nodes
        if isinstance(node, dict)
        and node.get("type") in {"WhatsAppTriggerNode", "whatsappTriggerNode"}
    ]
    if len(whatsapp_nodes) != 1:
        return diagram_data, False

    node = whatsapp_nodes[0]
    old_id = node.get("id")
    target_id = "whatsapptrigger-4"
    if not old_id or old_id == target_id:
        return diagram_data, False

    node["id"] = target_id
    node_data = node.get("data")
    if isinstance(node_data, dict):
        node_data["id"] = target_id

    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            if edge.get("source") == old_id:
                edge["source"] = target_id
            if edge.get("target") == old_id:
                edge["target"] = target_id

    for key in ("trigger_data",):
        trigger_data = diagram_data.get(key)
        if isinstance(trigger_data, dict) and old_id in trigger_data:
            trigger_data[target_id] = trigger_data.pop(old_id)

    flow_data = diagram_data.get("flowData")
    if isinstance(flow_data, dict):
        flow_trigger_data = flow_data.get("trigger_data")
        if isinstance(flow_trigger_data, dict) and old_id in flow_trigger_data:
            flow_trigger_data[target_id] = flow_trigger_data.pop(old_id)

    return diagram_data, True


def _normalize_slack_trigger_node_id(diagram_data: dict) -> tuple[dict, bool]:
    """
    Ensure Slack trigger node uses a stable id: slacktrigger-1.
    This keeps the Slack Event Subscriptions webhook URL stable across re-saves
    in the builder, so users don't have to re-configure Slack every time they
    edit the workflow and replace the trigger node.
    """
    if not isinstance(diagram_data, dict):
        return diagram_data, False

    nodes = diagram_data.get("nodes", [])
    edges = diagram_data.get("edges", [])
    if not isinstance(nodes, list):
        return diagram_data, False

    slack_nodes = [
        node for node in nodes
        if isinstance(node, dict)
        and node.get("type") in {"SlackTriggerNode", "slackTriggerNode"}
    ]
    if len(slack_nodes) != 1:
        return diagram_data, False

    node = slack_nodes[0]
    old_id = node.get("id")
    target_id = "slacktrigger-1"
    if not old_id or old_id == target_id:
        return diagram_data, False

    node["id"] = target_id
    node_data = node.get("data")
    if isinstance(node_data, dict):
        node_data["id"] = target_id

    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            if edge.get("source") == old_id:
                edge["source"] = target_id
            if edge.get("target") == old_id:
                edge["target"] = target_id

    for key in ("trigger_data",):
        trigger_data = diagram_data.get(key)
        if isinstance(trigger_data, dict) and old_id in trigger_data:
            trigger_data[target_id] = trigger_data.pop(old_id)

    flow_data = diagram_data.get("flowData")
    if isinstance(flow_data, dict):
        flow_trigger_data = flow_data.get("trigger_data")
        if isinstance(flow_trigger_data, dict) and old_id in flow_trigger_data:
            flow_trigger_data[target_id] = flow_trigger_data.pop(old_id)

    return diagram_data, True


def extract_and_store_whatsapp_triggers(diagram_data, bot_id, tenant_id, session, flow_id):
    """Extract and store WhatsApp trigger nodes from the diagram."""
    logger.info(f"[TRIGGER_SYNC] Processing WhatsApp triggers for bot_id={bot_id}, tenant_id={tenant_id}")

    saved_creds = _fetch_tool_credentials(session, tenant_id, "whatsapp", bot_id=bot_id)
    cred_keys = ["access_token", "phone_number_id", "verify_token", "verifyToken"]

    try:
        nodes = diagram_data.get("nodes", [])
        if not isinstance(nodes, list):
            logger.error("[TRIGGER_SYNC] Invalid diagram format: 'nodes' must be a list.")
            return 0

        trigger_count = 0

        for node in nodes:
            if node.get("type") not in {"WhatsAppTriggerNode", "whatsappTriggerNode"}:
                continue

            trigger_node_id = node.get("id")
            if not trigger_node_id:
                continue

            whatsapp_data = _normalize_whatsapp_trigger_config(node)
            if not isinstance(whatsapp_data, dict):
                whatsapp_data = {}

            for key in cred_keys:
                if saved_creds.get(key) and not whatsapp_data.get(key):
                    whatsapp_data[key] = saved_creds[key]

            trigger_entry = session.query(WorkflowTrigger).filter_by(
                bot_id=bot_id,
                tenant_id=tenant_id,
                trigger_node_id=trigger_node_id,
                flow_id=flow_id,
            ).first()

            if not trigger_entry:
                trigger_entry = WorkflowTrigger(
                    bot_id=bot_id,
                    tenant_id=tenant_id,
                    flow_id=flow_id,
                    trigger_node_id=trigger_node_id,
                    trigger_type="whatsapp",
                    status="active",
                )

            trigger_entry.trigger_type = "whatsapp"
            trigger_entry.status = "active"
            trigger_entry.schedule_meta = None
            trigger_entry.filter_meta = whatsapp_data.get("event_filter", {}) or {}
            trigger_entry.raw_trigger_json = whatsapp_data

            session.merge(trigger_entry)
            trigger_count += 1

        logger.info(f"[TRIGGER_SYNC] {trigger_count} WhatsApp trigger(s) stored.")
        return trigger_count

    except Exception:
        logger.exception("[TRIGGER_SYNC] Unexpected error processing WhatsApp triggers")
        raise


def extract_and_store_slack_triggers(diagram_data, bot_id, tenant_id, session, flow_id):
    """Extract and store Slack trigger nodes from the diagram."""
    logger.info(f"[TRIGGER_SYNC] Processing Slack triggers for bot_id={bot_id}, tenant_id={tenant_id}")

    saved_creds = _fetch_tool_credentials(session, tenant_id, "slack", bot_id=bot_id)
    cred_keys = ["bot_token", "signing_secret", "signingSecret"]

    try:
        nodes = diagram_data.get("nodes", [])
        if not isinstance(nodes, list):
            logger.error("[TRIGGER_SYNC] Invalid diagram format: 'nodes' must be a list.")
            return

        trigger_count = 0

        for node in nodes:
            if node.get("type") not in {"SlackTriggerNode", "slackTriggerNode"}:
                continue

            trigger_node_id = node.get("id")
            form_data = node.get("data", {}).get("formData", {}) or {}
            nested_slack = form_data.get("slack", {}) if isinstance(form_data, dict) else {}
            if not isinstance(nested_slack, dict):
                nested_slack = {}
            slack_data = dict(nested_slack)
            # Preserve compatibility with UIs that persist trigger credentials
            # directly on formData instead of formData.slack.
            if isinstance(form_data, dict):
                for key in (
                    "bot_token",
                    "signing_secret",
                    "signingSecret",
                    "team_id",
                    "teamId",
                    "channel_id",
                    "channel",
                    "default_channel_id",
                ):
                    value = form_data.get(key)
                    if value not in (None, "") and not slack_data.get(key):
                        slack_data[key] = value

            if not slack_data and not saved_creds:
                logger.info(
                    "[TRIGGER_SYNC] SlackTriggerNode '%s' has no config yet — registering with empty config.",
                    trigger_node_id,
                )
                # Do NOT skip — always register the trigger so the webhook URL exists

            for key in cred_keys:
                if saved_creds.get(key) and not slack_data.get(key):
                    slack_data[key] = saved_creds[key]

            trigger_entry = session.query(WorkflowTrigger).filter_by(
                bot_id=bot_id,
                tenant_id=tenant_id,
                trigger_node_id=trigger_node_id,
                flow_id=flow_id,
            ).first()

            if not trigger_entry:
                trigger_entry = WorkflowTrigger(
                    bot_id=bot_id,
                    tenant_id=tenant_id,
                    flow_id=flow_id,
                    trigger_node_id=trigger_node_id,
                    trigger_type="slack",
                    status="active",
                )

            trigger_entry.trigger_type = "slack"
            trigger_entry.status = "active"
            trigger_entry.schedule_meta = None
            trigger_entry.filter_meta = (
                slack_data.get("filter")
                or slack_data.get("filters")
                or slack_data.get("event_filter")
                or slack_data.get("eventFilter")
                or {}
            ) if isinstance(slack_data, dict) else {}
            trigger_entry.raw_trigger_json = slack_data

            session.merge(trigger_entry)
            trigger_count += 1
            logger.info(
                "[TRIGGER_SYNC] Slack trigger registered: trigger_node_id=%s flow_id=%s bot_id=%s "
                "| Slack webhook URL path: /webhook/slack/%s",
                trigger_node_id, flow_id, bot_id, trigger_node_id,
            )

        logger.info(f"[TRIGGER_SYNC] {trigger_count} Slack trigger(s) stored.")

    except Exception:
        logger.exception("[TRIGGER_SYNC] Unexpected error processing Slack triggers")
        raise


def detect_and_register_webhook_triggers(diagram_data, bot_id, tenant_id, session, flow_id):
    """
    Detect and register WebhookTriggerNode from diagram.
    Returns: List of registered trigger IDs
    """
    logger.info(f"[WEBHOOK_SYNC] Processing webhook triggers for bot_id={bot_id}, tenant_id={tenant_id}")
    
    registered_trigger_ids = []
    
    try:
        nodes = diagram_data.get("nodes", [])
        if not isinstance(nodes, list):
            logger.error("[WEBHOOK_SYNC] Invalid diagram format: 'nodes' must be a list.")
            return registered_trigger_ids

        for node in nodes:
            node_type = node.get("type")
            
            # Check if this is a WebhookTriggerNode
            if node_type != "WebhookTriggerNode":
                continue
            
            trigger_node_id = node.get("id")
            node_data = node.get("data", {})
            form_data = node_data.get("formData", {})
            
            # Try to get webhook config from formData.webhook or directly from formData
            webhook_data = form_data.get("webhook", {}) or form_data
            
            # Extract webhook configuration
            webhook_name = (
                webhook_data.get("webhook_name") or 
                webhook_data.get("webhookName") or 
                f"webhook_{trigger_node_id}"
            )
            event_filter = webhook_data.get("event_filter") or webhook_data.get("eventFilter") or {}
            field_mapping = webhook_data.get("field_mapping") or webhook_data.get("fieldMapping") or {}
            
            logger.info(f"[WEBHOOK_SYNC] Found WebhookTriggerNode: {trigger_node_id}, webhook_name={webhook_name}")
            
            # Check if trigger already exists
            trigger_entry = session.query(WorkflowTrigger).filter_by(
                bot_id=bot_id,
                tenant_id=tenant_id,
                trigger_node_id=trigger_node_id,
                flow_id=flow_id
            ).first()
            
            if not trigger_entry:
                # Create new trigger
                trigger_entry = WorkflowTrigger(
                    bot_id=bot_id,
                    tenant_id=tenant_id,
                    flow_id=flow_id,
                    trigger_node_id=trigger_node_id,
                    trigger_type="webhook",
                    status="active"
                )
                session.add(trigger_entry)
                logger.info(f"[WEBHOOK_SYNC] Creating new webhook trigger for node: {trigger_node_id}")
            else:
                logger.info(f"[WEBHOOK_SYNC] Updating existing webhook trigger: {trigger_entry.id}")
            
            # Update trigger configuration
            trigger_entry.trigger_meta = {
                "webhook_name": webhook_name,
                "event_filter": event_filter,
                "field_mapping": field_mapping,
                "node_data": node_data
            }
            trigger_entry.schedule_meta = None  # Webhooks don't have schedules
            trigger_entry.filter_meta = None    # Webhooks use trigger_meta for filtering
            trigger_entry.raw_trigger_json = webhook_data
            
            session.merge(trigger_entry)
            session.flush()  # Flush to get the ID
            
            registered_trigger_ids.append(trigger_entry.id)
        
        logger.info(f"[WEBHOOK_SYNC] {len(registered_trigger_ids)} webhook trigger(s) processed.")
        return registered_trigger_ids
        
    except Exception:
        logger.exception("[WEBHOOK_SYNC] Unexpected error processing webhook triggers")
        raise


def deactivate_removed_triggers(session, current_node_ids, tenant_id, flow_id):
    """
    Deactivate triggers (Gmail, WhatsApp, Webhook, etc.) that are no longer in the diagram.
    Uses tenant_id + flow_id so cleanup works even when bot_id is missing in payload.
    """
    logger.info(f"[TRIGGER_CLEANUP] Checking for removed triggers in tenant_id={tenant_id}, flow_id={flow_id}")
    
    try:
        # Find all active triggers for this flow (across all trigger types)
        existing_triggers = session.query(WorkflowTrigger).filter_by(
            tenant_id=tenant_id,
            flow_id=flow_id,
            status="active"
        ).all()
        
        deactivated_count = 0
        logger.info(
            "[TRIGGER_CLEANUP] Active triggers for flow_id=%s: %s",
            flow_id,
            [(t.trigger_node_id, t.trigger_type) for t in existing_triggers],
        )
        for trigger in existing_triggers:
            if trigger.trigger_node_id not in current_node_ids:
                logger.info(
                    f"[TRIGGER_CLEANUP] Deactivating removed {trigger.trigger_type} trigger: "
                    f"id={trigger.id}, node_id={trigger.trigger_node_id}"
                )
                trigger.status = "inactive"
                deactivated_count += 1

        if deactivated_count > 0:
            logger.info(f"[TRIGGER_CLEANUP] Deactivated {deactivated_count} removed trigger(s)")
        else:
            logger.info("[TRIGGER_CLEANUP] No triggers to deactivate")
        
    except Exception:
        logger.exception("[TRIGGER_CLEANUP] Unexpected error deactivating triggers")
        raise


def deactivate_triggers_from_old_diagrams(session, bot_id, tenant_id, latest_flow_id):
    updated = session.query(WorkflowTrigger).filter(
        WorkflowTrigger.bot_id == bot_id,
        WorkflowTrigger.tenant_id == tenant_id,
        WorkflowTrigger.flow_id != latest_flow_id,
        WorkflowTrigger.status == "active"
    ).update(
        {"status": "inactive"},
        synchronize_session=False
    )

    if updated:
        logger.info(
            f"[TRIGGER_CLEANUP] Deactivated {updated} trigger(s) from older diagrams"
        )

    return updated   # ✅ REQUIRED


@bot_diagram_blueprint.route('/save_diagram', methods=['POST'])
@jwt_required()
def save_diagram():
    try:
        claims = get_jwt()
        jwt_tenant_id = claims.get("tenant_id")
        logger.info(f"Saving diagram for tenant_id: {jwt_tenant_id}")
        
        if not jwt_tenant_id:
            logger.error("Tenant ID missing in token")
            return jsonify({"data": {}, "status": "error", "message": "Tenant ID missing in token"}), 401

        data = request.json or {}
        bot_id = data.get("bot_id")
        diagram_id = data.get("diagram_id")

        if "diagram_json" not in data:
            logger.error("Missing required diagram_json field in request")
            return jsonify({"data": {}, "status": "error", "message": "Missing required fields"}), 400

        # Validate diagram_json structure
        try:
            diagram_data = data["diagram_json"]
            if isinstance(diagram_data, str):
                diagram_data = json.loads(diagram_data)
            if not isinstance(diagram_data, dict) or "nodes" not in diagram_data or "edges" not in diagram_data:
                logger.error("Invalid diagram_json structure")
                return jsonify({"data": {}, "status": "error", "message": "Invalid diagram_json structure"}), 400
            if not isinstance(diagram_data["nodes"], list) or not isinstance(diagram_data["edges"], list):
                logger.error("Nodes and edges must be lists")
                return jsonify({"data": {}, "status": "error", "message": "Nodes and edges must be lists"}), 400
        except json.JSONDecodeError as e:
            logger.error(f"Invalid diagram_json: {str(e)}")
            return jsonify({"data": {}, "status": "error", "message": f"Invalid diagram_json: {str(e)}"}), 400

        diagram_data, whatsapp_id_normalized = _normalize_whatsapp_trigger_node_id(diagram_data)
        if whatsapp_id_normalized:
            logger.info("[TRIGGER_SYNC] Normalized WhatsApp trigger node id to whatsapptrigger-4")

        diagram_data, slack_id_normalized = _normalize_slack_trigger_node_id(diagram_data)
        if slack_id_normalized:
            logger.info("[TRIGGER_SYNC] Normalized Slack trigger node id to slacktrigger-1")

        if bot_id is None:
            resolved_bot_id = _resolve_flow_bot_id(diagram_data)
            if resolved_bot_id is not None:
                bot_id = resolved_bot_id
                logger.info("Resolved bot_id=%s from diagram flowData", bot_id)

        # 🆕 Fallback: if no bot_id was sent in the request and none was found
        # in the diagram payload, look up a bot in this tenant by name matching
        # workflow_name (case-insensitive, whitespace-trimmed) or by the legacy
        # workflow_name pattern `custom_bot_new_{bot_id}`. Prevents the diagram
        # from ever being saved detached (which previously produced synthetic
        # bot_id=-N triggers and broke MAS overlay of formData edits).
        if bot_id is None:
            candidate_name = (data.get("workflow_name") or data.get("workflowId") or "").strip()
            if candidate_name:
                _bot_lookup_session = next(db_session())
                try:
                    # Legacy pattern: workflow_name == "custom_bot_new_{bot_id}"
                    import re as _re
                    legacy_match = _re.match(r"^custom_bot_new_(\d+)$", candidate_name)
                    if legacy_match:
                        try:
                            candidate_id = int(legacy_match.group(1))
                        except (TypeError, ValueError):
                            candidate_id = None
                        if candidate_id is not None:
                            matched_bot = (
                                _bot_lookup_session.query(CustomBot)
                                .filter(
                                    CustomBot.bot_id == candidate_id,
                                    CustomBot.tenant_id == jwt_tenant_id,
                                    CustomBot.del_flg == False,
                                )
                                .first()
                            )
                            if matched_bot:
                                bot_id = matched_bot.bot_id
                                logger.info(
                                    "Resolved bot_id=%s by legacy workflow_name='%s'",
                                    bot_id, candidate_name,
                                )

                    # Case-insensitive / whitespace-tolerant bot_name match,
                    # performed in Python to stay portable across DB backends.
                    if bot_id is None:
                        cand_norm = candidate_name.strip().lower()
                        all_bots = (
                            _bot_lookup_session.query(CustomBot)
                            .filter(
                                CustomBot.tenant_id == jwt_tenant_id,
                                CustomBot.del_flg == False,
                            )
                            .order_by(CustomBot.bot_id.desc())
                            .all()
                        )
                        for b in all_bots:
                            name_norm = (getattr(b, "bot_name", "") or "").strip().lower()
                            if name_norm == cand_norm:
                                bot_id = b.bot_id
                                logger.info(
                                    "Resolved bot_id=%s by case-insensitive workflow_name='%s' fallback",
                                    bot_id, candidate_name,
                                )
                                break
                finally:
                    _bot_lookup_session.close()

        nodes = diagram_data.get("nodes", [])
        edges = diagram_data.get("edges", [])

        has_nodes = bool(nodes)
        if not has_nodes:
            logger.info("Saving empty diagram draft")

        # Validate node structure only when nodes exist
        for node in nodes:
            if not isinstance(node, dict) or "id" not in node or "type" not in node:
                logger.error("Invalid node structure: missing id or type")
                return jsonify({"data": {}, "status": "error", "message": "Invalid node structure: missing id or type"}), 400

        session = next(db_session())
        try:
            bot = None
            workflow_name = data.get("workflow_name") or data.get("workflowId")
            channel = data.get("channel")
            status = data.get("status") or "Draft"
            status_map = {
                "draft": "Draft",
                "created": "Created",
                "live": "Live",
                "paused": "Paused",
                "updated": "updated",
            }
            if isinstance(status, str):
                status = status_map.get(status.strip().lower(), status)

            if bot_id is not None:
                bot = session.get(CustomBot, bot_id)
                if not bot:
                    logger.error(f"Bot not found: {bot_id}")
                    return jsonify({"data": {}, "status": "error", "message": "Bot not found"}), 404

                if str(bot.tenant_id) != str(jwt_tenant_id):
                    logger.error(
                        f"Unauthorized: Bot tenant_id {bot.tenant_id} does not match JWT tenant_id {jwt_tenant_id}"
                    )
                    return jsonify(
                        {"data": {}, "status": "error", "message": "Unauthorized: Bot does not belong to your tenant"}
                    ), 403

            if not workflow_name and bot:
                workflow_name = _resolve_workflow_name(bot, bot.bot_id)
            if channel is None and bot and getattr(bot, "channel", None):
                channel = bot.channel.value

            existing_diagram = None
            if diagram_id:
                existing_diagram = session.get(BotDiagram, diagram_id)
                if not existing_diagram:
                    logger.warning(f"Diagram not found: {diagram_id}")
                    return jsonify({"data": {}, "status": "error", "message": "No diagram found"}), 404
                if str(existing_diagram.tenant_id) != str(jwt_tenant_id):
                    logger.warning(
                        f"Unauthorized access to diagram_id={diagram_id} for tenant_id={jwt_tenant_id}"
                    )
                    return jsonify({"data": {}, "status": "error", "message": "No diagram found"}), 404
            if not existing_diagram and workflow_name:
                existing_diagram = (
                    session.query(BotDiagram)
                    .filter_by(workflow_name=workflow_name, tenant_id=jwt_tenant_id, del_flg=False)
                    .order_by(BotDiagram.diagram_id.desc())
                    .first()
                )
            if not existing_diagram and bot:
                existing_diagram = (
                    session.query(BotDiagram)
                    .filter_by(bot_id=bot.bot_id, tenant_id=jwt_tenant_id, del_flg=False)
                    .order_by(BotDiagram.diagram_id.desc())
                    .first()
                )

            diagram_json_str = json.dumps(diagram_data)
            diagram_owner_bot_id = bot_id if bot_id is not None else (existing_diagram.bot_id if existing_diagram else None)

            # Keep trigger ownership as stable as possible.
            # Some workflow-builder flows persist diagrams with bot_id=NULL.
            # tbl_workflow_triggers.bot_id is NOT NULL, so we assign a stable
            # internal owner id for trigger rows when no bot_id is available.
            trigger_owner_bot_id = diagram_owner_bot_id

            if existing_diagram:
                if existing_diagram.diagram_json != diagram_json_str:
                    existing_diagram.diagram_json = diagram_json_str
                if workflow_name and existing_diagram.workflow_name != workflow_name:
                    existing_diagram.workflow_name = workflow_name
                if status and existing_diagram.status != status:
                    existing_diagram.status = status
                if bot and existing_diagram.bot_id != bot.bot_id:
                    _assign_existing_diagram_bot_id_with_fk_compat(
                        session,
                        diagram=existing_diagram,
                        bot_id=bot.bot_id,
                        tenant_id=jwt_tenant_id,
                    )
                    diagram_owner_bot_id = existing_diagram.bot_id
                elif not bot and existing_diagram.bot_id is not None:
                    orphan_bot = session.get(CustomBot, existing_diagram.bot_id)
                    if not orphan_bot:
                        logger.warning(
                            "Diagram %s references deleted bot_id=%s; clearing to NULL",
                            existing_diagram.diagram_id,
                            existing_diagram.bot_id,
                        )
                        existing_diagram.bot_id = None
                        diagram_owner_bot_id = None
                diagram_id = existing_diagram.diagram_id
                logger.info(f"Using existing diagram: {diagram_id}")
            else:
                new_diagram = _create_bot_diagram_with_fk_compat(
                    session=session,
                    bot_id=bot.bot_id if bot else None,
                    tenant_id=jwt_tenant_id,
                    workflow_name=workflow_name,
                    channel=channel,
                    status=status,
                    diagram_json=diagram_json_str
                )
                diagram_id = new_diagram.diagram_id
                diagram_owner_bot_id = new_diagram.bot_id
                logger.info(f"Created first diagram: {diagram_id}")

            # ═══════════════════════════════════════════════════════════════
            # TRIGGER PROCESSING - Gmail and Webhook
            # ═══════════════════════════════════════════════════════════════
            # diagram_id is now FINAL (latest)
            if trigger_owner_bot_id is None:
                # Use deterministic negative id to avoid collision with real bot ids.
                trigger_owner_bot_id = -int(diagram_id)
                logger.warning(
                    "[TRIGGER_SYNC] No bot_id for diagram_id=%s; using synthetic trigger owner bot_id=%s",
                    diagram_id,
                    trigger_owner_bot_id,
                )

            if trigger_owner_bot_id is not None:
                updated = deactivate_triggers_from_old_diagrams(
                    session,
                    trigger_owner_bot_id,
                    jwt_tenant_id,
                    diagram_id
                )
                if updated == 0:
                    logger.info("[TRIGGER_CLEANUP] No old triggers to deactivate")

            
            # Extract all current node IDs for cleanup
            all_current_node_ids = [node['id'] for node in nodes]
            
            # 1. Process Gmail triggers (existing functionality)
            # Always sync trigger rows by flow_id/tenant_id, even when bot_id is missing.
            # This enables workflow-builder Save/Save&Continue flows to become trigger-ready
            # without requiring bot FK persistence on the diagram row.
            extract_and_store_triggers(diagram_data, trigger_owner_bot_id, jwt_tenant_id, session, diagram_id)

            # 1b. Process WhatsApp triggers
            extract_and_store_whatsapp_triggers(diagram_data, trigger_owner_bot_id, jwt_tenant_id, session, diagram_id)

            # 1c. Process Slack triggers
            extract_and_store_slack_triggers(diagram_data, trigger_owner_bot_id, jwt_tenant_id, session, diagram_id)
            
            # 2. Process Webhook triggers (NEW)
            webhook_node_ids = [
                node['id'] for node in nodes
                if node.get('type') == 'WebhookTriggerNode'
            ]
            
            webhook_count = 0
            if webhook_node_ids:
                registered_webhook_ids = detect_and_register_webhook_triggers(
                    diagram_data, trigger_owner_bot_id, jwt_tenant_id, session, diagram_id
                )
                webhook_count = len(registered_webhook_ids)
                logger.info(f"✅ Registered {webhook_count} webhook trigger(s): {registered_webhook_ids}")
            else:
                logger.info("ℹ️ No webhook triggers found in diagram")
            
            # 3. Deactivate removed triggers (including WhatsApp) for this flow
            deactivate_removed_triggers(session, all_current_node_ids, jwt_tenant_id, diagram_id)
            
            # Commit all trigger changes
            session.commit()
            
            # ═══════════════════════════════════════════════════════════════
            # WORKFLOW GRAPH BUILDING
            # ═══════════════════════════════════════════════════════════════
            if has_nodes:
                workflow = StateGraph(ChatState)
                added_nodes = set()
                entry_nodes, exit_nodes = [], []

                for node in nodes:
                    node_id = node.get("id")
                    node_data = node.get("data", {})
                    form_data = node_data.get("formData", {})
                    node_type = form_data.get("type", "").strip() or node.get("type", "")

                    if not node_id:
                        continue

                    # Include WebhookTriggerNode as entry point
                    if node["type"] in [
                        "ChatTriggerNode",
                        "ManualTriggerNode",
                        "GmailTriggerNode",
                        "WebhookTriggerNode",
                        "WhatsAppTriggerNode",
                        "whatsappTriggerNode",
                    ]:
                        entry_nodes.append(node_id)
                    
                    if node["type"] in ["GenralOutputNode"]:
                        exit_nodes.append(node_id)

                    if node_id not in added_nodes:
                        workflow.add_node(node_id, agent_response)
                        added_nodes.add(node_id)

                # Add edges
                for edge in edges:
                    source = edge.get("source")
                    target = edge.get("target")
                    if source in added_nodes and target in added_nodes:
                        workflow.add_edge(source, target)

                # Set entry point
                if not entry_nodes and nodes:
                    entry_nodes.append(nodes[0]["id"])

                workflow.set_entry_point(entry_nodes[0])
                
                # Set finish point
                if exit_nodes:
                    workflow.set_finish_point(exit_nodes[0])

                # Compile graph
                graph = workflow.compile()

                # Generate graph visualization (optional)
                try:
                    graph_image = graph.get_graph().draw_mermaid_png()
                    graph_bot_id = diagram_owner_bot_id if diagram_owner_bot_id is not None else "diagram"
                    with open(f"workflow_graph_bot_{graph_bot_id}_diagram_{diagram_id}.png", "wb") as f:
                        f.write(graph_image)
                    logger.info(f"📊 Generated workflow graph image for diagram {diagram_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not generate workflow graph image: {e}")
            else:
                logger.info(f"Skipping graph build for empty draft diagram {diagram_id}")

            logger.info(f"✅ Diagram saved successfully: diagram_id={diagram_id}")
            
            return jsonify({
                "data": {
                    "diagram_id": diagram_id,
                    "message": "Diagram saved and converted successfully!",
                    "webhook_triggers_count": webhook_count
                },
                "status": "success"
            }), 200 if existing_diagram else 201

        except Exception as e:
            session.rollback()
            logger.exception(f"Error saving diagram for bot_id: {bot_id}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": f"Internal server error: {str(e)}"
            }), 500
        finally:
            session.close()

    except Exception as e:
        logger.exception("Unexpected error in save_diagram")
        return jsonify({
            "data": {},
            "status": "error",
            "message": f"Internal server error: {str(e)}"
        }), 500

@bot_diagram_blueprint.route('/get_diagram/<int:bot_id>', methods=['GET'])
@jwt_required()
def get_diagram(bot_id):
    try:
        claims = get_jwt()
        jwt_tenant_id = claims.get("tenant_id")
        logger.info(f"Fetching diagram for bot_id: {bot_id}, tenant_id: {jwt_tenant_id}")
        
        if not jwt_tenant_id:
            logger.error("Tenant ID missing in token")
            return jsonify({"data": {}, "status": "error", "message": "Tenant ID missing in token"}), 401

        session = next(db_session())
        try:
            bot = session.get(CustomBot, bot_id)
            if not bot:
                logger.error(f"Bot not found: {bot_id}")
                return jsonify({"data": {}, "status": "error", "message": "Bot not found"}), 404
            
            if str(bot.tenant_id) != str(jwt_tenant_id):
                logger.error(f"Unauthorized: Bot tenant_id {bot.tenant_id} does not match JWT tenant_id {jwt_tenant_id}")
                return jsonify({"data": {}, "status": "error", "message": "Unauthorized: Bot does not belong to your tenant"}), 403

            workflow_name = _resolve_workflow_name(bot, bot_id)
            legacy_workflow_name = f"custom_bot_new_{bot_id}"
            diagram = (
                session.query(BotDiagram)
                .filter(
                    BotDiagram.tenant_id == jwt_tenant_id,
                    BotDiagram.del_flg == False,
                    (
                        (BotDiagram.workflow_name == workflow_name)
                        | (BotDiagram.workflow_name == legacy_workflow_name)
                        | (BotDiagram.bot_id == bot_id)
                    )
                )
                .order_by(desc(BotDiagram.diagram_id))
                .first()
            )
            
            if not diagram:
                logger.warning(f"No diagram found for bot_id: {bot_id}")
                return jsonify({"data": {}, "status": "error", "message": "No diagram found for this bot"}), 404

            # Enrich diagram: inject memory_mode into GenericAgentNode formData if missing
            diagram_json_str = diagram.diagram_json
            try:
                _bot_memory_mode = getattr(bot, "memory_mode", None)
                if not _bot_memory_mode:
                    _agent_cfg = getattr(bot, "agent_config", {}) or {}
                    if isinstance(_agent_cfg, str):
                        try: _agent_cfg = json.loads(_agent_cfg)
                        except Exception: _agent_cfg = {}
                    _bot_memory_mode = _agent_cfg.get("memory_mode")
                if _bot_memory_mode:
                    _diagram_data = json.loads(diagram_json_str)
                    _changed = False
                    for _node in _diagram_data.get("nodes", []):
                        if _node.get("type") == "GenericAgentNode":
                            _fd = _node.get("data", {}).get("formData", {})
                            if not _fd.get("memory_mode"):
                                _fd["memory_mode"] = _bot_memory_mode
                                _node.setdefault("data", {})["formData"] = _fd
                                _changed = True
                    if _changed:
                        diagram_json_str = json.dumps(_diagram_data)
            except Exception:
                pass  # Return original JSON on any error

            logger.info(f"Diagram retrieved successfully: diagram_id={diagram.diagram_id}")
            return jsonify({
                "data": {
                    "diagram_id": diagram.diagram_id,
                    "workflow_name": diagram.workflow_name or workflow_name,
                    "channel": diagram.channel,
                    "diagram_json": diagram_json_str
                },
                "status": "success",
                "message": "Diagram retrieved successfully"
            }), 200

        except Exception as e:
            session.rollback()
            logger.exception(f"Error retrieving diagram for bot_id: {bot_id}")
            return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500
        finally:
            session.close()

    except Exception as e:
        logger.exception(f"Unexpected error in get_diagram for bot_id: {bot_id}")
        return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500


@bot_diagram_blueprint.route('/diagram/<int:diagram_id>', methods=['GET'])
@jwt_required()
def get_diagram_by_id(diagram_id):
    try:
        claims = get_jwt()
        jwt_tenant_id = claims.get("tenant_id")
        logger.info(f"Fetching diagram by diagram_id: {diagram_id}, tenant_id: {jwt_tenant_id}")

        if not jwt_tenant_id:
            logger.error("Tenant ID missing in token")
            return jsonify({"data": {}, "status": "error", "message": "Tenant ID missing in token"}), 401

        session = next(db_session())
        try:
            diagram = (
                session.query(BotDiagram)
                .filter(
                    BotDiagram.diagram_id == diagram_id,
                    BotDiagram.tenant_id == jwt_tenant_id,
                    BotDiagram.del_flg == False
                )
                .first()
            )

            if not diagram:
                logger.warning(f"No diagram found for diagram_id: {diagram_id}")
                return jsonify({"data": {}, "status": "error", "message": "No diagram found"}), 404

            # Enrich diagram: inject memory_mode into GenericAgentNode formData if missing
            diagram_json_str = diagram.diagram_json
            try:
                _bot_memory_mode = None
                if diagram.bot_id:
                    _bot = session.get(CustomBot, diagram.bot_id)
                    if _bot:
                        _bot_memory_mode = getattr(_bot, "memory_mode", None)
                        if not _bot_memory_mode:
                            _agent_cfg = getattr(_bot, "agent_config", {}) or {}
                            if isinstance(_agent_cfg, str):
                                try: _agent_cfg = json.loads(_agent_cfg)
                                except Exception: _agent_cfg = {}
                            _bot_memory_mode = _agent_cfg.get("memory_mode")
                if _bot_memory_mode:
                    _diagram_data = json.loads(diagram_json_str)
                    _changed = False
                    for _node in _diagram_data.get("nodes", []):
                        if _node.get("type") == "GenericAgentNode":
                            _fd = _node.get("data", {}).get("formData", {})
                            if not _fd.get("memory_mode"):
                                _fd["memory_mode"] = _bot_memory_mode
                                _node.setdefault("data", {})["formData"] = _fd
                                _changed = True
                    if _changed:
                        diagram_json_str = json.dumps(_diagram_data)
            except Exception:
                pass  # Return original JSON on any error

            logger.info(f"Diagram retrieved successfully by diagram_id={diagram.diagram_id}")
            return jsonify({
                "data": {
                    "diagram_id": diagram.diagram_id,
                    "bot_id": diagram.bot_id,
                    "workflow_name": diagram.workflow_name,
                    "channel": diagram.channel,
                    "diagram_json": diagram_json_str
                },
                "status": "success",
                "message": "Diagram retrieved successfully"
            }), 200

        except Exception as e:
            session.rollback()
            logger.exception(f"Error retrieving diagram for diagram_id: {diagram_id}")
            return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500
        finally:
            session.close()

    except Exception as e:
        logger.exception(f"Unexpected error in get_diagram_by_id for diagram_id: {diagram_id}")
        return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500


@bot_diagram_blueprint.route('/diagram/<int:diagram_id>', methods=['DELETE'])
@jwt_required()
def delete_diagram(diagram_id):
    try:
        claims = get_jwt()
        jwt_tenant_id = claims.get("tenant_id")

        if not jwt_tenant_id:
            logger.error("Tenant ID missing in token")
            return jsonify({"data": {}, "status": "error", "message": "Tenant ID missing in token"}), 401

        session = next(db_session())
        try:
            diagram = (
                session.query(BotDiagram)
                .filter(
                    BotDiagram.diagram_id == diagram_id,
                    BotDiagram.tenant_id == jwt_tenant_id,
                    BotDiagram.del_flg == False
                )
                .first()
            )

            if not diagram:
                logger.warning(f"No active diagram found for deletion: diagram_id={diagram_id}")
                return jsonify({"data": {}, "status": "error", "message": "No diagram found"}), 404

            diagram.del_flg = True
            diagram.status = "deleted"

            session.query(WorkflowTrigger).filter(
                WorkflowTrigger.tenant_id == jwt_tenant_id,
                WorkflowTrigger.flow_id == diagram_id
            ).update(
                {"status": "deleted"},
                synchronize_session=False
            )

            session.commit()

            logger.info(
                f"Soft deleted diagram_id={diagram_id}, tenant_id={jwt_tenant_id}"
            )

            return jsonify({
                "data": {
                    "diagram_id": diagram_id,
                    "deleted": True
                },
                "status": "success",
                "message": "Diagram deleted successfully"
            }), 200

        except Exception as e:
            session.rollback()
            logger.exception(f"Error deleting diagram for diagram_id: {diagram_id}")
            return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500
        finally:
            session.close()

    except Exception as e:
        logger.exception(f"Unexpected error in delete_diagram for diagram_id: {diagram_id}")
        return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500


@bot_diagram_blueprint.route('/update_diagram_name/<int:diagram_id>', methods=['PUT', 'PATCH'])
@jwt_required()
def update_diagram_name(diagram_id):
    try:
        claims = get_jwt()
        jwt_tenant_id = claims.get("tenant_id")

        if not jwt_tenant_id:
            logger.error("Tenant ID missing in token")
            return jsonify({"data": {}, "status": "error", "message": "Tenant ID missing in token"}), 401

        data = request.get_json(silent=True) or {}
        workflow_name = data.get("workflow_name")

        if not workflow_name:
            return jsonify(
                {"data": {}, "status": "error", "message": "workflow_name is required"}
            ), 400

        session = next(db_session())
        try:
            diagram = (
                session.query(BotDiagram)
                .filter(
                    BotDiagram.diagram_id == diagram_id,
                    BotDiagram.tenant_id == jwt_tenant_id,
                    BotDiagram.del_flg == False
                )
                .first()
            )

            if not diagram:
                return jsonify({"data": {}, "status": "error", "message": "No diagram found"}), 404

            diagram.workflow_name = workflow_name
            session.commit()

            logger.info(
                f"Updated workflow_name for diagram_id={diagram_id}, tenant_id={jwt_tenant_id}"
            )

            return jsonify({
                "data": {
                    "diagram_id": diagram.diagram_id,
                    "workflow_name": diagram.workflow_name
                },
                "status": "success",
                "message": "Diagram name updated successfully"
            }), 200

        except Exception as e:
            session.rollback()
            logger.exception(f"Error updating workflow name for diagram_id: {diagram_id}")
            return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500
        finally:
            session.close()

    except Exception as e:
        logger.exception(f"Unexpected error in update_diagram_name for diagram_id: {diagram_id}")
        return jsonify({"data": {}, "status": "error", "message": f"Internal server error: {str(e)}"}), 500


@bot_diagram_blueprint.route('/diagrams', methods=['GET'])
@jwt_required()
def get_all_diagrams():
    try:
        claims = get_jwt()
        jwt_tenant_id = claims.get("tenant_id")

        if not jwt_tenant_id:
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Tenant ID missing in token"
            }), 401

        # -----------------------------
        # Pagination Params
        # -----------------------------
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)

        page = max(page, 1)
        limit = max(limit, 1)

        # -----------------------------
        # Filter Params
        # -----------------------------
        date_filter = request.args.get("date")
        channel = request.args.get("channel")
        status = request.args.get("status")
        workflow_name = request.args.get("workflow_name")
        bot_id = request.args.get("bot_id", type=int)

        session = next(db_session())

        try:
            # -----------------------------
            # Base Query (IMPORTANT: FIRST)
            # -----------------------------
            query = (
                session.query(BotDiagram)
                .filter(
                    BotDiagram.tenant_id == jwt_tenant_id,
                    BotDiagram.del_flg == False
                )
            )

            # -----------------------------
            # Apply Filters
            # -----------------------------

            # Channel filter
            if channel:
                query = query.filter(BotDiagram.channel == channel)

            # Status filter
            if status:
                query = query.filter(BotDiagram.status == status)

            # Workflow name search
            if workflow_name:
                query = query.filter(
                    func.lower(BotDiagram.workflow_name).like(f"%{workflow_name.lower()}%")
                )

            # Bot ID filter
            if bot_id:
                query = query.filter(BotDiagram.bot_id == bot_id)

            # -----------------------------
            # ✅ Date Filter (FIXED)
            # -----------------------------
            if date_filter:
                now = datetime.utcnow()

                if date_filter == "today":
                    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    query = query.filter(BotDiagram.created_at >= start)

                elif date_filter == "7days":
                    start = now - timedelta(days=7)
                    query = query.filter(BotDiagram.created_at >= start)

                elif date_filter == "30days":
                    start = now - timedelta(days=30)
                    query = query.filter(BotDiagram.created_at >= start)

            # -----------------------------
            # Total Count (AFTER filters)
            # -----------------------------
            total_records = query.count()

            # -----------------------------
            # Pagination + Sorting
            # -----------------------------
            diagrams = (
                query.order_by(
                    desc(BotDiagram.updated_at),
                    desc(BotDiagram.diagram_id)
                )
                .offset((page - 1) * limit)
                .limit(limit)
                .all()
            )

            total_pages = (total_records + limit - 1) // limit if limit else 0

            # -----------------------------
            # Response Data
            # -----------------------------
            items = []

            for diagram in diagrams:
                bot = None
                if diagram.bot_id:
                    bot = session.get(CustomBot, diagram.bot_id)

                items.append({
                    "diagram_id": diagram.diagram_id,
                    "bot_id": diagram.bot_id,
                    "workflow_name": diagram.workflow_name,
                    "channel": diagram.channel,
                    "status": diagram.status,
                    "diagram_json": diagram.diagram_json,
                    "bot_details": serialize_custom_bot_new(bot) if bot else None,
                    "created_at": diagram.created_at.isoformat() if diagram.created_at else None,
                    "updated_at": diagram.updated_at.isoformat() if diagram.updated_at else None,
                })

            # -----------------------------
            # Final Response
            # -----------------------------
            return jsonify({
                "data": items,
                "pagination": {
                    "page": page,
                    "per_page": limit,
                    "total_records": total_records,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                },
                "filters_applied": {
                    "channel": channel,
                    "status": status,
                    "workflow_name": workflow_name,
                    "bot_id": bot_id,
                    "date": date_filter,   # ✅ added
                },
                "status": "success",
                "message": "Diagrams fetched successfully"
            }), 200

        except Exception as e:
            session.rollback()
            logger.exception("Error fetching diagrams")

            return jsonify({
                "data": {},
                "status": "error",
                "message": f"Internal server error: {str(e)}"
            }), 500

        finally:
            session.close()

    except Exception as e:
        logger.exception("Unexpected error in get_all_diagrams")

        return jsonify({
            "data": {},
            "status": "error",
            "message": f"Internal server error: {str(e)}"
        }), 500
    
USER_MCP_TOOLS = {
    "Gcalendar",
    "Gmail",
    "Gmaps",
    "Gsheets",
    "HubSpot",
    "Tavily",
}

def normalize_tool_name_for_db(name: str) -> str:
    """
    Normalizes tool names to match existing MCPAgentTools.tool_name values.
    Examples:
      "hubspot"        -> "HubSpot"
      "HubSpot"        -> "HubSpot"
      "google maps"    -> "Gmaps"
      "gmaps"          -> "Gmaps"
    """
    if not name:
        return ""

    key = name.strip().lower().replace(" ", "")

    TOOL_CANONICAL_MAP = {
        "hubspot": "HubSpot",
        "gmaps": "Gmaps",
        "googlemaps": "Gmaps",
        "googlemap": "Gmaps",
        "calendar": "Gcalendar",
        "gmail": "Gmail",
        "gsheets": "Gsheets",
    }

    return TOOL_CANONICAL_MAP.get(key, name.strip().title())

def resolve_feature_to_mcp_tool(feature_name: str) -> str:
    """
    Convert a user-facing feature label into the MCP tool category used in DB.
    """
    if not feature_name:
        return ""

    raw = str(feature_name).strip()
    key = raw.lower()

    direct_map = {
        "schedule meetings and reminders": "Gcalendar",
        "send and manage professional emails": "Gmail",
        "navigate and find locations": "Gmaps",
        "find and navigate to fishing locations": "Gmaps",
        "manage customer relationships and sales": "HubSpot",
        "manage customer relationships and track interactions": "HubSpot",
        "organize and analyze data in spreadsheets": "Gsheets",
        "store and analyze fishing data": "Gsheets",
        "plan and organize fishing trips": "Tavily",
    }

    if key in direct_map:
        return direct_map[key]

    keyword_map = [
        ("Gcalendar", ["calendar", "meeting", "reminder", "schedule"]),
        ("Gmail", ["gmail", "email", "mail"]),
        ("Gmaps", ["map", "maps", "location", "navigate", "directions"]),
        ("HubSpot", ["hubspot", "customer", "sales", "relationship", "interaction"]),
        ("Gsheets", ["sheet", "sheets", "spreadsheet", "data", "analyze"]),
        ("Tavily", ["tavily", "research", "search", "browse"]),
    ]   

    for tool_name, keywords in keyword_map:
        if any(word in key for word in keywords):
            return tool_name

    return normalize_tool_name_for_db(raw)

def extract_selected_core_tools(core_features) -> set:
    # ✅ FIX: deserialize if string
    if isinstance(core_features, str):
        try:
            core_features = json.loads(core_features)
        except Exception as e:
            logger.error(
                "❌ [EXTRACT] Failed to parse core_features JSON: %s",
                e
            )
            return set()

    logger.info(
        "🧩 [EXTRACT] core_features type=%s value=%s",
        type(core_features),
        core_features
    )

    selected = set()

    if not core_features:
        logger.warning("⚠️ [EXTRACT] core_features invalid or empty")
        return selected

    if isinstance(core_features, list):
        for entry in core_features:
            if isinstance(entry, str) and entry.strip():
                selected.add(resolve_feature_to_mcp_tool(entry))
                continue
            if not isinstance(entry, dict):
                continue
            tool_name = entry.get("tool_name") or entry.get("name") or entry.get("label") or entry.get("tool")
            if not tool_name:
                continue
            selected_flag = entry.get("selected")
            if isinstance(selected_flag, str):
                selected_flag = selected_flag.strip().lower() in {"1", "true", "yes", "on"}
            if selected_flag is None:
                selected_flag = True
            if bool(selected_flag):
                selected.add(resolve_feature_to_mcp_tool(tool_name))
        return selected

    if not isinstance(core_features, dict):
        logger.warning("⚠️ [EXTRACT] core_features invalid type=%s", type(core_features))
        return selected

    if "tools" in core_features and isinstance(core_features.get("tools"), list):
        return extract_selected_core_tools(core_features.get("tools"))

    for tool_name, entries in core_features.items():
        if not isinstance(entries, list):
            continue

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            selected_flag = entry.get("selected")
            if isinstance(selected_flag, str):
                selected_flag = selected_flag.strip().lower() in {"1", "true", "yes", "on"}
            if selected_flag is None:
                selected_flag = True
            if bool(selected_flag):
                selected.add(resolve_feature_to_mcp_tool(tool_name))
                break

    return selected
DEFAULT_MCP_URL = "https://mcp.jnanic.com/connect_mcp"

# Actions supported by each local tool category (mirrors local_tool_routes.py dispatchers)
_LOCAL_TOOL_ACTIONS = {
    "gmail": [
        "send_gmail", "list_gmail_messages", "read_gmail_message",
        "read_unread_gmail_messages", "search_gmail_messages",
        "draft_gmail", "get_email_from_token", "mark_as_read",
        "mark_as_unread", "delete_gmail_message",
    ],
    "gcalendar": [
        "create_event", "list_events", "update_event",
        "delete_event", "get_free_busy",
    ],
    "hubspot": [
        "create_contact", "update_contact", "get_contact",
    ],
    "gsheets": [
        "read_spreadsheet", "write_spreadsheet", "append_spreadsheet",
        "list_spreadsheets", "create_sheet",
    ],
}

def _get_local_tool_actions(tool_name: str) -> list:
    """Return the known action list for a local tool, matched by normalized name."""
    key = "".join(c for c in str(tool_name).lower() if c.isalnum())
    for canonical, actions in _LOCAL_TOOL_ACTIONS.items():
        if key == canonical or key in canonical or canonical in key:
            return list(actions)
    return []

def _get_local_tool_url() -> str:
    import os
    base = os.getenv("BB_SERVICE_URL", "http://bot-builder-service:5000").rstrip("/")
    return f"{base}/local_tool/call"


def attach_mcp_tools_to_agent(session, tenant_id: int, agent_id: int, bot: CustomBot, core_features=None):
    """
    Attach only the locally-configured tools (ToolAuthorization) to the agent.
    MCP tools are not used in the bot flow — only tools the tenant has explicitly
    configured (Gmail, Calendar, HubSpot, Sheets, etc.) are attached.
    """
    logger.info("🔧 [TOOL_ATTACH] Starting local-tool attachment | agent_id=%s", agent_id)

    def _norm(value) -> str:
        return "".join(ch for ch in str(value).lower() if ch.isalnum())

    # Canonical backend name → all name variants the frontend may store in ToolAuthorization
    _ALIASES = {
        "gcalendar": ["gcalendar", "calendar", "googlecalendar", "google calendar"],
        "gmail":     ["gmail", "googlemail", "google mail"],
        "gmaps":     ["gmaps", "googlemaps", "google maps", "maps"],
        "hubspot":   ["hubspot", "hub spot"],
        "gsheets":   ["gsheets", "googlesheets", "google sheets", "sheets"],
    }

    def _find_tool_auth(tool_auth_by_norm, canonical_norm):
        """Alias-aware lookup: "gcalendar" finds "calendar" stored by the frontend."""
        if canonical_norm in tool_auth_by_norm:
            return tool_auth_by_norm[canonical_norm]
        for aliases in _ALIASES.values():
            norms = [_norm(a) for a in aliases]
            if canonical_norm in norms:
                for alias_norm in norms:
                    if alias_norm in tool_auth_by_norm:
                        return tool_auth_by_norm[alias_norm]
        # Fuzzy substring fallback
        for stored_norm, auth in tool_auth_by_norm.items():
            if stored_norm in canonical_norm or canonical_norm in stored_norm:
                return auth
        return None

    # ── 1. Resolve selected tools from core_features ──────────────────────────
    effective_core_features = bot.core_features if core_features is None else core_features
    allowed_tools = extract_selected_core_tools(effective_core_features)

    logger.info(
        "✅ [TOOL_ATTACH] selected tools from core_features=%s",
        sorted(list(allowed_tools)),
    )

    # ── 2. Soft-delete existing tool rows for this agent ──────────────────────
    session.query(McpAgentTools).filter_by(
        tenant_id=tenant_id,
        agent_id=agent_id,
        del_flag=False,
    ).update({"del_flag": True})
    session.flush()

    if not allowed_tools:
        logger.warning("⚠️ [TOOL_ATTACH] No tools selected — nothing to attach")
        return 0

    # ── 3. Load all ToolAuthorization rows for this tenant ────────────────────
    tool_auth_rows = session.query(ToolAuthorization).filter_by(
        tenant_id=tenant_id,
        del_flag=False,
    ).all()
    tool_auth_by_norm = {
        _norm(auth.tool_name): auth
        for auth in tool_auth_rows
        if auth.tool_name
    }
    logger.info(
        "📦 [TOOL_ATTACH] configured local tools=%s",
        [auth.tool_name for auth in tool_auth_rows],
    )

    attached_count = 0

    # ── 4. Attach only tools that are configured in ToolAuthorization ─────────
    for selected_tool in sorted(allowed_tools):
        selected_norm = _norm(selected_tool)
        tool_auth = _find_tool_auth(tool_auth_by_norm, selected_norm)

        if not tool_auth:
            logger.warning(
                "⚠️ [TOOL_ATTACH] '%s' not configured in ToolAuthorization — skipping",
                selected_tool,
            )
            continue

        # Always "local" — bot flow tools (Gmail, Calendar, HubSpot, Sheets)
        # are always dispatched through the bb_service local tool endpoint.
        # ToolAuthorization.tool_type may contain stale values like "jnanic_mcp".
        tool_type    = "local"
        action_names = _get_local_tool_actions(selected_tool)
        mcp_url      = _get_local_tool_url()
        canonical_tool_name = normalize_tool_name_for_db(tool_auth.tool_name)
        tool_config = {
            "source": "tool_authorization",
            "tool_type": "local",
            "selected_tool": selected_tool,
        }

        existing = session.query(McpAgentTools).filter_by(
            tenant_id=tenant_id,
            agent_id=agent_id,
            tool_name=canonical_tool_name,
            del_flag=False,
        ).first()

        if existing:
            existing.tool_type   = tool_type
            existing.mcp_id      = None
            existing.mcp_url     = mcp_url
            existing.action_tools = action_names
            existing.tool_config = tool_config
            logger.info(
                "♻️ [TOOL_ATTACH] updated agent_id=%s tool='%s' type=%s actions=%d",
                agent_id, canonical_tool_name, tool_type, len(action_names),
            )
        else:
            session.add(McpAgentTools(
                tenant_id=tenant_id,
                agent_id=agent_id,
                mcp_id=None,
                tool_name=canonical_tool_name,
                mcp_url=mcp_url,
                tool_type=tool_type,
                tool_config=tool_config,
                action_tools=action_names,
                action_tools_description=[],
                del_flag=False,
            ))
            logger.info(
                "➕ [TOOL_ATTACH] inserted agent_id=%s tool='%s' type=%s actions=%d",
                agent_id, canonical_tool_name, tool_type, len(action_names),
            )

        attached_count += 1

    session.flush()

    final_tools = session.query(McpAgentTools).filter_by(
        tenant_id=tenant_id, agent_id=agent_id, del_flag=False,
    ).all()
    logger.info(
        "✅ [TOOL_ATTACH] done agent_id=%s attached=%d tools=%s",
        agent_id, len(final_tools), [t.tool_name for t in final_tools],
    )
    return attached_count

def get_default_llm(session, tenant_id):
    """
    Returns default LLM identifiers for agent creation.
    Does NOT create anything.
    """

    llm = session.query(LLM).filter(
        LLM.tenant_id == tenant_id,
        LLM.del_flg == False
    ).first()

    if llm:
        return {
            "llm_id": llm.llm_id,
            "provider": llm.provider,
            "model_name": llm.model_name
        }

    # 🔁 Pure fallback (NO DB WRITE)
    return {
        "llm_id": None,
        "provider": "openai",
        "model_name": "gpt-4"
    }

def serialize_custom_bot_new(bot: CustomBot) -> dict:
    """
    Return a JSON-safe snapshot of the new bot record.
    """
    def enum_value(value):
        return value.value if hasattr(value, "value") else value

    return {
        "bot_id": bot.bot_id,
        "tenant_id": bot.tenant_id,
        "instance_id": bot.instance_id,
        "channel": enum_value(bot.channel),
        "bot_name": bot.bot_name,
        "tone_of_voice": enum_value(bot.tone_of_voice),
        "industry": enum_value(bot.industry),
        "purpose": bot.purpose,
        "avatar": bot.avatar,
        "core_features": bot.core_features or {},
        "instructions": bot.instructions or [],
        "kb_ids": bot.kb_ids or [],
        "kb_functionalities": bot.kb_functionalities or [],
        "bot_status": enum_value(bot.bot_status),
        "position": bot.position,
        "page_config": bot.page_config,
        "specific_pages": bot.specific_pages or [],
        "theme": bot.theme,
        "colors": bot.colors or {},
        "background_image": bot.background_image,
        "background_color": bot.background_color,
        "disclaimer_text": bot.disclaimer_text,
        "greeting_type": bot.greeting_type,
        "greeting_message": bot.greeting_message,
        "published_version_id": bot.published_version_id,
        "last_published_at": bot.last_published_at.isoformat() if bot.last_published_at else None,
        "access_restriction_type": bot.access_restriction_type,
        "created_at": bot.created_at.isoformat() if bot.created_at else None,
        "updated_at": bot.updated_at.isoformat() if bot.updated_at else None,
        "del_flg": bot.del_flg,
    }

#------------------------------------------------------------

def build_multi_agent_chat_workflow(
    bot_id: int,
    tenant_id: int,
    router_agent_id: int,
    greeting_agent_id: int,
    kb_agent_id: int = None,
    tool_agent_id: int = None,
    response_agent_id: int = None,
    channel: str = "website",
    kb_ids: list | None = None,
    tool_names: list | None = None,
) -> dict:
    """
    UI + Runtime compatible multi-agent workflow.
    Produces diagram structure exactly as expected by UI.
    """
    normalized_channel = str(channel or "website").strip().lower()

    # ====================== CHANNEL SPECIFIC CONFIG ======================
    if normalized_channel == "whatsapp":
        trigger_node_id = "whatsapptrigger-4"
        trigger_type = "WhatsAppTriggerNode"
        trigger_label = "WhatsApp Trigger"
        greeting_node_id = "genericagent-1"
        greeting_node_type = "GenericAgentNode"
        response_node_type = "GenericAgentNode"
        final_node = {
            "id": "whatsappsendmessage-1",
            "type": "whatsappSendMessageNode",
            "label": "WhatsApp Send Message",
            "formData": {
                "to": "{{whatsapptrigger-4.phone || whatsapptrigger-4.from}}",
                "body": "{{WH_bot.output || genericagent-4.output || 'Sorry, something went wrong.'}}",
                "recipient_number": "{{whatsapptrigger-4.phone || whatsapptrigger-4.from}}",
            },
        }
        decision_data_mapping = {"message": [f"{trigger_node_id}.0.message", f"{trigger_node_id}.0.user_query"]}
        source_handle_for_trigger = "drag-output"

    elif normalized_channel == "slack":
        trigger_node_id = "slacktrigger-1"
        trigger_type = "SlackTriggerNode"
        trigger_label = "Slack Trigger"
        greeting_node_id = "greetingagent-7"          # Important: matches your JSON
        greeting_node_type = "GreetingAgentNode"
        response_node_type = "ResponseAgentNode"      # Important for Slack
        final_node = {
            "id": "slacksendmessage-1",
            "type": "slackSendMessageNode",
            "label": "Slack Send Message",
            "formData": {
                "channel": "{{slacktrigger-1.channel}}",
                "text": "{{genericagent-4.output || genericagent-4.output.llm_response || 'Sorry, something went wrong.'}}",
            },
        }
        decision_data_mapping = {"message": ["slacktrigger-1.message"]}
        source_handle_for_trigger = None

    else:  # website / default
        trigger_node_id = "chattrigger-1"
        trigger_type = "ChatTriggerNode"
        trigger_label = "On Chat Message"
        greeting_node_id = "genericagent-1"
        greeting_node_type = "GreetingAgentNode"
        response_node_type = "GenericAgentNode"
        final_node = None
        decision_data_mapping = {"user_query": [f"{trigger_node_id}.user_query", "user_query", "message"]}
        source_handle_for_trigger = None

    # Common configurations
    user_query_paths = [f"{trigger_node_id}.user_query", "user_query", "message"]
    user_query_static_parameter = json.dumps(user_query_paths)

    agent_input_form_data = {
        "data_mapping": {"user_query": user_query_paths}
    }

    response_data_mapping = {
        "user_query": user_query_paths,
        "greeting_response": f"{greeting_node_id}.output",
    }

    include_kb_node = bool(kb_agent_id) and bool(kb_ids)
    include_tool_node = bool(tool_agent_id) and bool(tool_names)

    if include_kb_node:
        response_data_mapping["kb_response"] = "genericagent-2.output"
    if include_tool_node:
        response_data_mapping["tool_response"] = "genericagent-3.output"

    flow_data = {
        "bot_id": bot_id,
        "tenant_id": tenant_id,
        "execution_mode": "BOT",
        "trigger_data": {
            trigger_node_id: {"inputs": {"user_query": "hi"}}
        },
    }
    # ====================== NODES ======================
    nodes = [
        # Trigger
        {
            "id": trigger_node_id,
            "type": trigger_type,
            "position": {"x": -80, "y": 280},
            "data": {
                "label": trigger_label,
                "id": trigger_node_id,
                "formData": {},
                "details": {},
                "flowData": flow_data,
                "executionData": {},
            },
            "width": 182 if normalized_channel == "slack" else 220,
            "height": 70 if normalized_channel == "slack" else 106,
        },
        # Decision Router
        {
            "id": "decisionrouter-1",
            "type": "DecisionRouterNode",
            "position": {"x": 220, "y": 220},
            "data": {
                "label": "Decision Router",
                "id": "decisionrouter-1",
                "formData": {
                    "agent_id": router_agent_id,
                    "use_temp_llm": True,
                    "task": f"Classify the user's {normalized_channel} message as GREETING, INFORMATION, or ACTION and return ONLY the label; if the intent is unclear, return INFORMATION.",
                    "data_mapping": decision_data_mapping,
                    "static_parameters": {},
                    "conditions": [],
                    "defaultTarget": "genericagent-4",
                    "default_target": "genericagent-4",
                },
                "details": {},
                "flowData": flow_data,
                "executionData": {},
            },
            "width": 292,
            "height": 101,
        },
        # Greeting Agent
        {
            "id": greeting_node_id,
            "type": greeting_node_type,
            "position": {"x": 680, "y": 480} if normalized_channel == "slack" else {"x": 745.32, "y": 54.25},
            "data": {
                "label": "Greeting Agent",
                "id": greeting_node_id,
                "formData": {
                    "agent_id": greeting_agent_id,
                    "agent_name": "Greeting Agent",
                    "use_temp_llm": True,
                    "task": "Respond warmly to greetings. Keep responses friendly and concise.",
                    **agent_input_form_data,
                },
                "details": {},
                "flowData": flow_data,
                "executionData": {},
            },
            "width": 292 if normalized_channel == "slack" else 320,
            "height": 101 if normalized_channel == "slack" else 130,
        },
        # Response Agent
        {
            "id": "genericagent-4",
            "type": response_node_type,
            "position": {"x": 1166.04, "y": 188.40},
            "data": {
                "label": "Response Agent",
                "id": "genericagent-4",
                "formData": {
                    "agent_id": response_agent_id,
                    "agent_name": "Response Agent",
                    "use_temp_llm": True,
                    "task": "Format and summarize the final response for the user.",
                    "data_mapping": response_data_mapping,
                    "label": "Response Agent",
                },
                "details": {},
                "flowData": flow_data,
                "executionData": {},
            },
            "width": 292 if normalized_channel == "slack" else 320,
            "height": 125 if normalized_channel == "slack" else 130,
        },
    ]

    # Knowledge Base Agent
    if include_kb_node:
        nodes.append({
            "id": "genericagent-2",
            "type": "GenericAgentNode",
            "position": {"x": 700, "y": 40} if normalized_channel == "slack" else {"x": 748, "y": 194},
            "data": {
                "label": "Knowledge Base Agent",
                "id": "genericagent-2",
                "formData": {
                    "agent_id": kb_agent_id,
                    "agent_name": "Knowledge Base Agent",
                    "use_temp_llm": True,
                    "task": "Retrieve and answer from knowledge base. No tool execution.",
                    "data_mapping": {"user_query": user_query_paths},
                    "knowledge_base_ids": kb_ids or [],
                },
                "details": {"knowledge_base_ids": kb_ids or []},
                "flowData": flow_data,
                "executionData": {},
            },
            "width": 320,
            "height": 114,
        })

    # Tool Agent
    if include_tool_node:
        nodes.append({
            "id": "genericagent-3",
            "type": "GenericAgentNode",
            "position": {"x": 660, "y": 280} if normalized_channel == "slack" else {"x": 754, "y": 340},
            "data": {
                "label": "Tool Agent",
                "id": "genericagent-3",
                "formData": {
                    "agent_id": tool_agent_id,
                    "agent_name": "Tool Agent",
                    "use_temp_llm": True,
                    "task": "Execute user-requested actions using available tools.",
                    "data_mapping": {"user_query": user_query_paths},
                    "tool_names": tool_names or [],
                },
                "details": {"tool_names": tool_names or []},
                "flowData": flow_data,
                "executionData": {},
            },
            "width": 320,
            "height": 114,
        })

    # Final Send Message Node (Slack / WhatsApp)
    if final_node:
        nodes.append({
            "id": final_node["id"],
            "type": final_node["type"],
            "position": {"x": 1580, "y": 240} if normalized_channel == "slack" else {"x": 1530, "y": 180},
            "data": {
                "label": final_node["label"],
                "id": final_node["id"],
                "formData": final_node["formData"],
                "details": {},
                "flowData": flow_data,
                "executionData": {},
            },
            "width": 213 if normalized_channel == "slack" else 250,
            "height": 70 if normalized_channel == "slack" else 120,
        })

    # ====================== EDGES ======================
    edges = [
        {
            "source": trigger_node_id,
            "sourceHandle": source_handle_for_trigger,
            "target": "decisionrouter-1",
            "targetHandle": None,
            "type": "bezier",
        },
        {
            "source": "decisionrouter-1",
            "sourceHandle": None,
            "target": greeting_node_id,
            "targetHandle": None,
            "type": "bezier",
        },
        {
            "source": greeting_node_id,
            "sourceHandle": "drag-output" if normalized_channel == "slack" else "response",
            "target": "genericagent-4",
            "targetHandle": None,
            "type": "bezier",
        },
    ]

    if include_kb_node:
        edges.append({"source": "decisionrouter-1", "target": "genericagent-2", "type": "bezier"})
        edges.append({"source": "genericagent-2", "sourceHandle": "response", "target": "genericagent-4", "type": "bezier"})

    if include_tool_node:
        edges.append({"source": "decisionrouter-1", "target": "genericagent-3", "type": "bezier"})
        edges.append({"source": "genericagent-3", "sourceHandle": "response", "target": "genericagent-4", "type": "bezier"})

    if final_node:
        edges.append({
            "source": "genericagent-4",
            "sourceHandle": "response",
            "target": final_node["id"],
            "type": "bezier"
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "flowData": flow_data,
    }


def _resolve_agent_tool_id_and_type(session, tenant_id: int, selected_tools: set) -> tuple:
    """
    Resolve Agent.tool_id (NOT NULL FK) and Agent.tool_type.
    Only ToolAuthorization (local tools) is considered — no MCP lookup.

    Returns (tool_id: int, tool_type: str).
    """
    def _norm(v):
        return "".join(c for c in str(v).lower() if c.isalnum())

    _ALIASES = {
        "gcalendar": ["gcalendar", "calendar", "googlecalendar", "google calendar"],
        "gmail":     ["gmail", "googlemail", "google mail"],
        "gmaps":     ["gmaps", "googlemaps", "google maps", "maps"],
        "hubspot":   ["hubspot", "hub spot"],
        "gsheets":   ["gsheets", "googlesheets", "google sheets", "sheets"],
    }

    def _find_auth_for(canonical):
        candidate_norms = [_norm(canonical)]
        for aliases in _ALIASES.values():
            if _norm(canonical) in [_norm(a) for a in aliases]:
                candidate_norms = [_norm(a) for a in aliases]
                break
        for cn in candidate_norms:
            auth = session.query(ToolAuthorization).filter(
                ToolAuthorization.tenant_id == tenant_id,
                ToolAuthorization.del_flag == False,
                ToolAuthorization.tool_name.ilike(cn),
            ).first()
            if auth:
                return auth
        # Fuzzy fallback
        for auth in session.query(ToolAuthorization).filter_by(
            tenant_id=tenant_id, del_flag=False
        ).all():
            stored = _norm(auth.tool_name or "")
            if stored in _norm(canonical) or _norm(canonical) in stored:
                return auth
        return None

    # tool_type: always "local" for bot flow agents —
    # ToolAuthorization.tool_type can be "jnanic_mcp" or stale; ignore it.
    resolved_type = "local"

    # tool_id: satisfy the NOT NULL FK on tbl_agents.tool_id
    resolved_id = None
    for tool_name in (selected_tools or []):
        row = session.query(Tools).filter(
            Tools.tool_name.ilike(tool_name),
            Tools.del_flg == False,
        ).first()
        if row:
            resolved_id = row.tool_id
            break
    if resolved_id is None:
        fallback = session.query(Tools).filter(Tools.del_flg == False).first()
        resolved_id = fallback.tool_id if fallback else 1

    return resolved_id, resolved_type


def create_unified_bot_agent(session, tenant_id: int, bot_id: int, bot, core_features=None) -> dict:
    """
    Create/update a single Bot Agent that can use both KBs and tools.
    Used for channel flows where hidden specialized agents are not desired.
    """
    # Prefer the LLM the user selected in the AI Config wizard step.
    # Fall back to the tenant's default only if nothing was saved.
    _agent_cfg = getattr(bot, "agent_config", {}) or {}
    if isinstance(_agent_cfg, str):
        try:
            _agent_cfg = json.loads(_agent_cfg)
        except Exception:
            _agent_cfg = {}

    _saved_llm_id = _agent_cfg.get("llm_model_id")
    llm = None
    if _saved_llm_id:
        _saved_llm = session.query(LLM).filter_by(
            llm_id=int(_saved_llm_id),
            tenant_id=tenant_id,
            del_flg=False
        ).first()
        if _saved_llm:
            llm = {
                "llm_id": _saved_llm.llm_id,
                "provider": _saved_llm.provider,
                "model_name": _saved_llm.model_name,
            }

    if not llm:
        llm = get_default_llm(session, tenant_id)
    kb_ids = bot.kb_ids or []
    if isinstance(kb_ids, str):
        try:
            kb_ids = json.loads(kb_ids)
        except Exception:
            kb_ids = []
    if not isinstance(kb_ids, list):
        kb_ids = []
    kb_ids = [int(kb_id) for kb_id in kb_ids if str(kb_id).isdigit()]

    effective_core_features = bot.core_features if core_features is None else core_features
    selected_tools = extract_selected_core_tools(effective_core_features)
    has_tools = len(selected_tools) > 0

    resolved_tool_id, resolved_tool_type = _resolve_agent_tool_id_and_type(
        session, tenant_id, selected_tools
    )

    bot_agent_key = f"bot-{bot_id}-agent"
    bot_name = (getattr(bot, "bot_name", None) or "").strip() or f"Bot {bot_id}"
    bot_agent_description = f"Primary bot agent for '{bot_name}'"

    bot_agent = session.query(Agent).filter_by(
        tenant_id=tenant_id,
        agent_key=bot_agent_key,
        del_flg=False
    ).first()

    # Extract instructions from bot
    bot_instructions = None
    raw_instructions = getattr(bot, "instructions", None)
    if isinstance(raw_instructions, list) and raw_instructions:
        bot_instructions = "\n".join(
            i.get("text", "") if isinstance(i, dict) else str(i)
            for i in raw_instructions
            if i
        ) or None
    elif isinstance(raw_instructions, str) and raw_instructions.strip():
        bot_instructions = raw_instructions.strip()

    # Extract agent config from bot (if available)
    agent_config = getattr(bot, "agent_config", {}) or {}
    if isinstance(agent_config, str):
        try:
            agent_config = json.loads(agent_config)
        except Exception:
            agent_config = {}

    # ✅ Set default values for all agent fields
    agent_defaults = {
        "temperature": agent_config.get("temperature", 0.7),
        "max_tokens": agent_config.get("max_tokens", 5000),
        "greeting_message": agent_config.get("greeting_message", f"Hello! I'm {bot_name}. How can I help you today?"),
        "language": agent_config.get("language", "English"),
        "timezone": agent_config.get("timezone", "UTC"),
        "tone": agent_config.get("tone", "friendly"),
        "emoji_mode": agent_config.get("emoji_mode", "enabled"),
        "availability_mode": agent_config.get("availability_mode", "always"),
        "instruction_mode": agent_config.get("instruction_mode", "structured"),
        "agent_type": agent_config.get("agent_type", "react_agent"),
        "persona_style": agent_config.get("persona_style", "professional"),
        "memory_mode": agent_config.get("memory_mode", "persistent"),
        "guardrails": agent_config.get("guardrails", {}),
        "completed_step": agent_config.get("completed_step", 6),
    }

    if not bot_agent:
        bot_agent = Agent(
            tenant_id=tenant_id,
            agent_name=bot_name,
            agent_description=bot_agent_description,
            agent_role="bot_agent",
            llm_provider_id=llm["llm_id"],
            llm_model_id=llm["llm_id"],
            tool_type=resolved_tool_type if has_tools else "local",
            tool_id=resolved_tool_id,
            knowledge_base_ids=kb_ids,
            agent_key=bot_agent_key,
            deployment_method="local",
            agent_instructions=bot_instructions,
            agent_status=AgentStatusEnum.LIVE,
            del_flg=False,
            # ✅ NEW: Set all agent configuration fields
            temperature=agent_defaults["temperature"],
            max_tokens=agent_defaults["max_tokens"],
            greeting_message=agent_defaults["greeting_message"],
            language=agent_defaults["language"],
            timezone=agent_defaults["timezone"],
            tone=agent_defaults["tone"],
            emoji_mode=agent_defaults["emoji_mode"],
            availability_mode=agent_defaults["availability_mode"],
            instruction_mode=agent_defaults["instruction_mode"],
            agent_type=agent_defaults["agent_type"],
            persona_style=agent_defaults["persona_style"],
            memory_mode=agent_defaults["memory_mode"],
            guardrails=agent_defaults["guardrails"],
            completed_step=agent_defaults["completed_step"],
        )
        session.add(bot_agent)
        session.flush()
        logger.info(
            f"✅ [Agent] Created new agent | agent_id={bot_agent.agent_id} | "
            f"completed_step={bot_agent.completed_step} | "
            f"instructions_len={len(bot_instructions or '')} | "
            f"temperature={bot_agent.temperature}"
        )
    else:
        # Update existing agent with new values
        bot_agent.agent_name = bot_name
        bot_agent.agent_description = bot_agent_description
        bot_agent.knowledge_base_ids = kb_ids
        bot_agent.tool_type = resolved_tool_type if has_tools else "local"
        bot_agent.tool_id = resolved_tool_id
        if bot_instructions is not None:
            bot_agent.agent_instructions = bot_instructions
        bot_agent.agent_status = AgentStatusEnum.LIVE
        # ✅ NEW: Update all agent configuration fields
        bot_agent.temperature = agent_defaults["temperature"]
        bot_agent.max_tokens = agent_defaults["max_tokens"]
        bot_agent.greeting_message = agent_defaults["greeting_message"]
        bot_agent.language = agent_defaults["language"]
        bot_agent.timezone = agent_defaults["timezone"]
        bot_agent.tone = agent_defaults["tone"]
        bot_agent.emoji_mode = agent_defaults["emoji_mode"]
        bot_agent.availability_mode = agent_defaults["availability_mode"]
        bot_agent.instruction_mode = agent_defaults["instruction_mode"]
        bot_agent.agent_type = agent_defaults["agent_type"]
        bot_agent.persona_style = agent_defaults["persona_style"]
        bot_agent.memory_mode = agent_defaults["memory_mode"]
        bot_agent.guardrails = agent_defaults["guardrails"]
        bot_agent.completed_step = agent_defaults["completed_step"]
        session.flush()
        logger.info(
            f"✅ [Agent] Updated existing agent | agent_id={bot_agent.agent_id} | "
            f"completed_step={bot_agent.completed_step} | "
            f"instructions_len={len(bot_instructions or '')} | "
            f"temperature={bot_agent.temperature}"
        )

    attached_count = 0
    if has_tools:
        attached_count = attach_mcp_tools_to_agent(
            session,
            tenant_id,
            bot_agent.agent_id,
            bot,
            core_features=effective_core_features
        ) or 0
    else:
        session.query(McpAgentTools).filter_by(
            tenant_id=tenant_id,
            agent_id=bot_agent.agent_id,
            del_flag=False
        ).update({"del_flag": True})
        session.flush()

    return {
        "agent_id": bot_agent.agent_id,
        "kb_ids": kb_ids,
        "tool_names": sorted(list(selected_tools)),
        "attached_count": attached_count,
    }


def build_single_bot_agent_workflow(
    bot_id: int,
    tenant_id: int,
    bot_agent_id: int,
    channel: str = "website",
    kb_ids: list | None = None,
    tool_names: list | None = None,
    bot_name: str | None = None,
    memory_mode: str | None = None,
) -> dict:
    """
    Build a simple trigger -> Bot Agent -> send-message flow.
    """
    normalized_channel = str(channel or "website").strip().lower()
    agent_label = (bot_name or "").strip() or "Bot Agent"

    if normalized_channel == "whatsapp":
        trigger_node_id = "whatsapptrigger-4"
        trigger_type = "WhatsAppTriggerNode"
        trigger_label = "WhatsApp Trigger"
        trigger_source_handle = "drag-output"
        user_query_paths = [f"{trigger_node_id}.message", f"{trigger_node_id}.user_query", "message", "user_query"]
        final_node = {
            "id": "whatsappsendmessage-1",
            "type": "whatsappSendMessageNode",
            "label": "WhatsApp Send Message",
            "formData": {
                "to": "{{whatsapptrigger-4.phone || whatsapptrigger-4.from}}",
                "body": "{{genericagent-1.output || genericagent-1.output.llm_response || 'Sorry, something went wrong.'}}",
                "recipient_number": "{{whatsapptrigger-4.phone || whatsapptrigger-4.from}}",
            },
        }
    elif normalized_channel == "slack":
        trigger_node_id = "slacktrigger-1"
        trigger_type = "SlackTriggerNode"
        trigger_label = "Slack Trigger"
        trigger_source_handle = None
        user_query_paths = [f"{trigger_node_id}.message", "message", "user_query"]
        final_node = {
            "id": "slacksendmessage-1",
            "type": "slackSendMessageNode",
            "label": "Slack Send Message",
            "formData": {
                "channel": "{{slacktrigger-1.channel}}",
                "text": "{{genericagent-1.output || genericagent-1.output.llm_response || 'Sorry, something went wrong.'}}",
            },
        }
    else:
        trigger_node_id = "chattrigger-1"
        trigger_type = "ChatTriggerNode"
        trigger_label = "On Chat Message"
        trigger_source_handle = None
        user_query_paths = [f"{trigger_node_id}.user_query", "user_query", "message"]
        final_node = None

    flow_data = {
        "bot_id": bot_id,
        "tenant_id": tenant_id,
        "execution_mode": "BOT",
        "trigger_data": {
            trigger_node_id: {"inputs": {"user_query": "hi"}}
        },
    }

    nodes = [
        {
            "id": trigger_node_id,
            "type": trigger_type,
            "position": {"x": -20, "y": 300},
            "data": {
                "label": trigger_label,
                "id": trigger_node_id,
                "formData": {},
                "details": {},
                "flowData": flow_data,
                "executionData": {},
            },
            "width": 220,
            "height": 106,
        },
        {
            "id": "genericagent-1",
            "type": "GenericAgentNode",
            "position": {"x": 320, "y": 320},
            "data": {
                "label": agent_label,
                "id": "genericagent-1",
                "formData": {
                    "agent_id": str(bot_agent_id),
                    "agent_name": agent_label,
                    "agent_description": f"Primary bot agent for {agent_label}",
                    "task": (
                        "You are an intelligent assistant that handles greetings, knowledge base answers, and tool-based actions.\n\n"
                        "Guidelines:\n"
                        "- Reply naturally and conversationally.\n"
                        "- Answer only using relevant knowledge base content or approved tool results.\n"
                        "- Do not generate information outside the provided knowledge base or tool output.\n"
                        "- Use tools only when necessary to complete the request.\n"
                        "- Keep responses direct, accurate, and concise.\n"
                        "- Do not mention knowledge base, tools, sources, browsing, or limitations.\n"
                        "- Avoid phrases like \"Based on\", \"According to\", or \"I would need access\".\n"
                        "- If no relevant information is available, reply exactly:\n"
                        "I could not find this in the selected knowledge base."
                    ),
                    "data_mapping": {"user_query": user_query_paths},
                    "static_parameters": {"message": f"{trigger_node_id}.message"},
                    "knowledge_base_ids": kb_ids or [],
                    "tool_names": tool_names or [],
                    "memory_mode": memory_mode or "session",
                    "label": agent_label,
                },
                "details": {
                    "agent_id": bot_agent_id,
                    "knowledge_base_ids": kb_ids or [],
                    "tool_names": tool_names or [],
                },
                "flowData": flow_data,
                "executionData": {},
            },
            "width": 320,
            "height": 114,
        },
    ]

    edges = [
        {
            "source": trigger_node_id,
            "sourceHandle": trigger_source_handle,
            "target": "genericagent-1",
            "targetHandle": None,
            "type": "bezier",
        }
    ]

    if final_node:
        nodes.append({
            "id": final_node["id"],
            "type": final_node["type"],
            "position": {"x": 760, "y": 300},
            "data": {
                "label": final_node["label"],
                "id": final_node["id"],
                "formData": final_node["formData"],
                "details": {},
                "flowData": flow_data,
                "executionData": {},
            },
            "width": 250,
            "height": 120,
        })
        edges.append({
            "source": "genericagent-1",
            "sourceHandle": "response",
            "target": final_node["id"],
            "type": "bezier",
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "flowData": flow_data,
    }


def verify_agent_mappings(session, tenant_id: int, agent_ids: dict) -> dict:
    """
    Verifies that KBs and tools are correctly assigned to respective agents.
    
    Returns:
        {
            "valid": bool,
            "errors": list,
            "summary": dict
        }
    """
    errors = []
    summary = {}
    
    # Check each agent type
    for agent_type, agent_id in agent_ids.items():
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()
        
        if not agent:
            errors.append(f"{agent_type} agent not found (ID: {agent_id})")
            continue
        
        # Check MCP tools assignment
        mcp_tools = session.query(McpAgentTools).filter_by(
            agent_id=agent_id,
            tenant_id=tenant_id,
            del_flag=False
        ).all()
        
        tool_count = len(mcp_tools)
        kb_count = len(agent.knowledge_base_ids or [])
        
        summary[agent_type] = {
            "agent_id": agent_id,
            "has_tools": tool_count > 0,
            "tool_count": tool_count,
            "has_kb": kb_count > 0,
            "kb_count": kb_count,
            "tool_type": agent.tool_type
        }
        
        # ✅ VALIDATION RULES
        if agent_type == "router":
            if tool_count > 0:
                errors.append(f"Router agent should NOT have tools (has {tool_count})")
            if kb_count > 0:
                errors.append(f"Router agent should NOT have KBs (has {kb_count})")
        
        elif agent_type == "greeting":
            if tool_count > 0:
                errors.append(f"Greeting agent should NOT have tools (has {tool_count})")
            if kb_count > 0:
                errors.append(f"Greeting agent should NOT have KBs (has {kb_count})")
        
        elif agent_type == "kb":
            if tool_count > 0:
                errors.append(f"KB agent should NOT have tools (has {tool_count})")
            if kb_count == 0:
                errors.append(f"KB agent MUST have at least one KB (has {kb_count})")
            if agent.tool_type is not None:
                errors.append(f"KB agent tool_type should be NULL (is '{agent.tool_type}')")
        
        elif agent_type == "tool":
            if tool_count == 0:
                errors.append(f"Tool agent MUST have tools (has {tool_count})")
            if agent.tool_type != "mcp":
                errors.append(f"Tool agent tool_type should be 'mcp' (is '{agent.tool_type}')")
            # Tool agent can optionally have KB for context
        
        elif agent_type == "response":
            if tool_count > 0:
                errors.append(f"Response agent should NOT have tools (has {tool_count})")
            if kb_count > 0:
                errors.append(f"Response agent should NOT have KBs (has {kb_count})")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "summary": summary
    }



def create_specialized_agents(session, tenant_id: int, bot_id: int, bot, core_features=None) -> dict:
    """
    Creates specialized agents only when their backing data exists:
    1. Router (decision maker, no tools)
    2. Greeting (no tools, no KB)
    3. KB Agent (KB only, no tools)
    4. Tool Agent (tools only, minimal KB)
    5. Response Agent (formatting only)
    """
    # Prefer the LLM the user selected in the AI Config wizard step.
    _agent_cfg = getattr(bot, "agent_config", {}) or {}
    if isinstance(_agent_cfg, str):
        try:
            _agent_cfg = json.loads(_agent_cfg)
        except Exception:
            _agent_cfg = {}

    _saved_llm_id = _agent_cfg.get("llm_model_id")
    llm = None
    if _saved_llm_id:
        _saved_llm = session.query(LLM).filter_by(
            llm_id=int(_saved_llm_id),
            tenant_id=tenant_id,
            del_flg=False
        ).first()
        if _saved_llm:
            llm = {
                "llm_id": _saved_llm.llm_id,
                "provider": _saved_llm.provider,
                "model_name": _saved_llm.model_name,
            }

    if not llm:
        llm = get_default_llm(session, tenant_id)
    kb_ids = bot.kb_ids or []
    if isinstance(kb_ids, str):
        try:
            kb_ids = json.loads(kb_ids)
        except Exception:
            kb_ids = []
    if not isinstance(kb_ids, list):
        kb_ids = []
    kb_ids = [int(kb_id) for kb_id in kb_ids if str(kb_id).isdigit()]
    has_kb = len(kb_ids) > 0
    effective_core_features = bot.core_features if core_features is None else core_features
    selected_tools = extract_selected_core_tools(effective_core_features)
    has_tools = len(selected_tools) > 0

    resolved_tool_id, resolved_tool_type = _resolve_agent_tool_id_and_type(
        session, tenant_id, selected_tools
    )

    logger.info(
        "🧩 [SPECIALIZED_AGENTS] bot_id=%s tenant_id=%s has_kb=%s has_tools=%s selected_tools=%s",
        bot_id,
        tenant_id,
        has_kb,
        has_tools,
        sorted(list(selected_tools))
    )
    logger.info(
        "🧩 [SPECIALIZED_AGENTS] core_features_type=%s core_features=%s",
        type(effective_core_features),
        effective_core_features
    )
    
    agents = {}
    
    # 1. ROUTER AGENT (lightweight classification)
    router_key = f"bot-{bot_id}-router"
    router = session.query(Agent).filter_by(
        tenant_id=tenant_id,
        agent_key=router_key,
        del_flg=False
    ).first()
    
    if not router:
        router = Agent(
            tenant_id=tenant_id,
            agent_name="Intent Router",
            agent_description="Classifies user intent (greeting/info/action)",
            agent_role="router",
            llm_provider_id=llm["llm_id"],
            llm_model_id=llm["llm_id"],
            tool_type="local",
            tool_id=resolved_tool_id,
            knowledge_base_ids=[],
            agent_key=router_key,
            deployment_method="local",
            agent_status=AgentStatusEnum.LIVE,
            del_flg=False
        )
        session.add(router)
        session.flush()
    else:
        router.tool_id = resolved_tool_id
        router.agent_status = AgentStatusEnum.LIVE
        session.flush()

    agents["router"] = router.agent_id

    # 2. GREETING AGENT (simple responses)
    greeting_key = f"bot-{bot_id}-greeting"
    greeting = session.query(Agent).filter_by(
        tenant_id=tenant_id,
        agent_key=greeting_key,
        del_flg=False
    ).first()

    if not greeting:
        greeting = Agent(
            tenant_id=tenant_id,
            agent_name="Greeting Agent",
            agent_description="Handles greetings and small talk",
            agent_role="greeting",
            llm_provider_id=llm["llm_id"],
            llm_model_id=llm["llm_id"],
            tool_type="local",
            tool_id=resolved_tool_id,
            knowledge_base_ids=[],
            agent_key=greeting_key,
            deployment_method="local",
            agent_status=AgentStatusEnum.LIVE,
            del_flg=False
        )
        session.add(greeting)
        session.flush()
    else:
        greeting.tool_id = resolved_tool_id
        greeting.agent_status = AgentStatusEnum.LIVE
        session.flush()

    agents["greeting"] = greeting.agent_id

    # 3. KB AGENT (knowledge retrieval only)
    if has_kb:
        kb_key = f"bot-{bot_id}-kb"
        kb_agent = session.query(Agent).filter_by(
            tenant_id=tenant_id,
            agent_key=kb_key,
            del_flg=False
        ).first()

        if not kb_agent:
            kb_agent = Agent(
                tenant_id=tenant_id,
                agent_name="Knowledge Base Agent",
                agent_description="Answers questions from knowledge base",
                agent_role="knowledge_retrieval",
                llm_provider_id=llm["llm_id"],
                llm_model_id=llm["llm_id"],
                tool_type="local",
                tool_id=resolved_tool_id,
                knowledge_base_ids=kb_ids,
                agent_key=kb_key,
                deployment_method="local",
                agent_status=AgentStatusEnum.LIVE,
                del_flg=False
            )
            session.add(kb_agent)
            session.flush()
        else:
            kb_agent.knowledge_base_ids = kb_ids
            kb_agent.tool_id = resolved_tool_id
            kb_agent.agent_status = AgentStatusEnum.LIVE
            session.flush()

        agents["kb"] = kb_agent.agent_id

    # 4. TOOL AGENT (action execution)
    if has_tools:
        tool_key = f"bot-{bot_id}-tools"
        tool_agent = session.query(Agent).filter_by(
            tenant_id=tenant_id,
            agent_key=tool_key,
            del_flg=False
        ).first()

        if not tool_agent:
            tool_agent = Agent(
                tenant_id=tenant_id,
                agent_name="Tool Execution Agent",
                agent_description="Executes actions using tools",
                agent_role="tool_executor",
                llm_provider_id=llm["llm_id"],
                llm_model_id=llm["llm_id"],
                tool_type=resolved_tool_type,
                tool_id=resolved_tool_id,
                knowledge_base_ids=[],
                agent_key=tool_key,
                deployment_method="local",
                agent_status=AgentStatusEnum.LIVE,
                del_flg=False
            )
            session.add(tool_agent)
            session.flush()
        else:
            tool_agent.tool_type = resolved_tool_type
            tool_agent.tool_id = resolved_tool_id
            tool_agent.agent_status = AgentStatusEnum.LIVE
            session.flush()

        attached_count = attach_mcp_tools_to_agent(
            session,
            tenant_id,
            tool_agent.agent_id,
            bot,
            core_features=effective_core_features
        )
        logger.info(
            "🧩 [SPECIALIZED_AGENTS] tool_agent_id=%s attached_count=%s",
            tool_agent.agent_id,
            attached_count
        )
        if attached_count > 0:
            agents["tool"] = tool_agent.agent_id
        else:
            logger.warning(
                "⚠️ [TOOL_AGENT_SKIPPED] tool agent created but no MCP tools attached for bot_id=%s",
                bot_id
            )
    else:
        # Ensure removed tools are reflected by soft-deleting previously attached MCP tools.
        tool_key = f"bot-{bot_id}-tools"
        existing_tool_agent = session.query(Agent).filter_by(
            tenant_id=tenant_id,
            agent_key=tool_key,
            del_flg=False
        ).first()
        if existing_tool_agent:
            session.query(McpAgentTools).filter_by(
                tenant_id=tenant_id,
                agent_id=existing_tool_agent.agent_id,
                del_flag=False
            ).update({"del_flag": True})
            session.flush()
            logger.info(
                "🧹 [TOOL_CLEANUP] Cleared MCP tools for bot_id=%s tool_agent_id=%s",
                bot_id,
                existing_tool_agent.agent_id
            )
    
    # 5. RESPONSE AGENT (formatting/summarization)
    response_key = f"bot-{bot_id}-response"
    response_agent = session.query(Agent).filter_by(
        tenant_id=tenant_id,
        agent_key=response_key,
        del_flg=False
    ).first()
    
    if not response_agent:
        response_agent = Agent(
            tenant_id=tenant_id,
            agent_name="Response Formatter",
            agent_description="Formats and summarizes final responses",
            agent_role="response_formatter",
            llm_provider_id=llm["llm_id"],
            llm_model_id=llm["llm_id"],
            tool_type="local",
            tool_id=resolved_tool_id,
            knowledge_base_ids=[],
            agent_key=response_key,
            deployment_method="local",
            agent_status=AgentStatusEnum.LIVE,
            del_flg=False
        )
        session.add(response_agent)
        session.flush()
    else:
        response_agent.tool_id = resolved_tool_id
        response_agent.agent_status = AgentStatusEnum.LIVE
        session.flush()

    agents["response"] = response_agent.agent_id
    
    return {
        "agents": agents,
        "kb_ids": kb_ids,
        "tool_names": sorted(list(selected_tools)),
    }


def _initialize_workflow_for_bot(bot, tenant_id: int) -> dict:
    """
    Creates or regenerates the workflow diagram for a bot without requiring
    an HTTP request context. Intended to be called after configure-and-publish.
    Returns dict with diagram_id, status, and architecture.
    """
    session = None
    bot_id = bot.bot_id
    try:
        session = next(db_session())

        # Re-fetch bot from this session to avoid DetachedInstanceError
        bot = session.query(CustomBot).filter_by(bot_id=bot_id, del_flg=False).first()
        if not bot:
            raise ValueError(f"Bot {bot_id} not found when initializing workflow")

        workflow_name = _resolve_workflow_name(bot, bot_id)
        legacy_workflow_name = f"custom_bot_new_{bot_id}"
        requested_channel = getattr(bot.channel, "value", None) or "website"
        requested_core_features = bot.core_features

        existing_diagram = (
            session.query(BotDiagram)
            .filter(
                BotDiagram.tenant_id == tenant_id,
                BotDiagram.workflow_name.in_([workflow_name, legacy_workflow_name]),
                BotDiagram.del_flg == False,
                or_(BotDiagram.bot_id == bot_id, BotDiagram.bot_id.is_(None))
            )
            .order_by(desc(BotDiagram.diagram_id))
            .first()
        )

        channel_key = str(requested_channel or "").strip().lower()
        architecture = "single_bot_agent"

        if channel_key in {"whatsapp", "slack", "website"}:
            unified = create_unified_bot_agent(
                session=session,
                tenant_id=tenant_id,
                bot_id=bot_id,
                bot=bot,
                core_features=requested_core_features,
            )
            agent_ids = {"bot": unified["agent_id"]}
            diagram = build_single_bot_agent_workflow(
                bot_id=bot_id,
                tenant_id=tenant_id,
                bot_agent_id=unified["agent_id"],
                channel=requested_channel,
                kb_ids=unified.get("kb_ids"),
                tool_names=unified.get("tool_names"),
                bot_name=(getattr(bot, "bot_name", None) or "").strip() or None,
                memory_mode=getattr(bot, "memory_mode", None),
            )
        else:
            specialized = create_specialized_agents(
                session=session,
                tenant_id=tenant_id,
                bot_id=bot_id,
                bot=bot,
                core_features=requested_core_features,
            )
            agent_ids = specialized["agents"]
            architecture = "multi_agent_router"
            diagram = build_multi_agent_chat_workflow(
                bot_id=bot_id,
                tenant_id=tenant_id,
                router_agent_id=agent_ids["router"],
                greeting_agent_id=agent_ids["greeting"],
                kb_agent_id=agent_ids.get("kb"),
                tool_agent_id=agent_ids.get("tool"),
                response_agent_id=agent_ids.get("response"),
                channel=requested_channel,
                kb_ids=specialized.get("kb_ids"),
                tool_names=specialized.get("tool_names"),
            )

        diagram = _hydrate_trigger_credentials_in_diagram(
            diagram_data=diagram,
            session=session,
            tenant_id=tenant_id,
            bot_id=bot_id,
            channel=requested_channel,
        )

        if existing_diagram:
            existing_diagram.diagram_json = json.dumps(diagram)
            existing_diagram.channel = requested_channel
            existing_diagram.status = "Live"
            if channel_key == "whatsapp":
                extract_and_store_whatsapp_triggers(
                    diagram, bot_id, tenant_id, session, existing_diagram.diagram_id
                )
            elif channel_key == "slack":
                extract_and_store_slack_triggers(
                    diagram, bot_id, tenant_id, session, existing_diagram.diagram_id
                )
            session.commit()
            return {
                "diagram_id": existing_diagram.diagram_id,
                "status": "Live",
                "architecture": architecture,
            }

        new_diagram = _create_bot_diagram_with_fk_compat(
            session=session,
            bot_id=bot_id,
            tenant_id=tenant_id,
            workflow_name=workflow_name,
            channel=requested_channel,
            status="Live",
            diagram_json=json.dumps(diagram),
        )
        if channel_key == "whatsapp":
            extract_and_store_whatsapp_triggers(
                diagram, bot_id, tenant_id, session, new_diagram.diagram_id
            )
        elif channel_key == "slack":
            extract_and_store_slack_triggers(
                diagram, bot_id, tenant_id, session, new_diagram.diagram_id
            )
        session.commit()
        return {
            "diagram_id": new_diagram.diagram_id,
            "status": "Live",
            "architecture": architecture,
        }

    except Exception:
        if session is not None:
            session.rollback()
        raise
    finally:
        if session is not None:
            session.close()


@bot_diagram_blueprint.route("/<int:bot_id>/initialize-workflow", methods=["POST"])
@jwt_required()
def initialize_bot_workflow_v2(bot_id):
    """
    Updated endpoint using multi-agent router architecture.
    Creates a workflow diagram when missing, otherwise regenerates and updates
    the existing diagram.
    """
    session = None

    try:
        jwt_claims = get_jwt() or {}
        tenant_id = _coerce_int(jwt_claims.get("tenant_id"))
        if tenant_id is None:
            tenant_id = _coerce_int(get_jwt_identity())
        if tenant_id is None:
            return jsonify({
                "status": "error",
                "message": "tenant_id missing in JWT claims/identity"
            }), 401

        session = next(db_session())
        request_data = request.get_json(silent=True) or {}
        logger.info(
            "🚀 [INIT_WORKFLOW] bot_id=%s tenant_id=%s request_data=%s",
            bot_id,
            tenant_id,
            request_data
        )
        bot = session.query(CustomBot).filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()
        
        if not bot:
            return jsonify({"error": "Bot not found"}), 404

        bot_details = serialize_custom_bot_new(bot)
        workflow_name = _resolve_workflow_name(bot, bot_id)
        legacy_workflow_name = f"custom_bot_new_{bot_id}"
        requested_channel = (
            request_data.get("channel")
            or request_data.get("channels")
            or getattr(bot.channel, "value", None)
            or "website"
        )
        has_core_features_in_request = (
            "core_features" in request_data or "tools" in request_data
        )
        if "core_features" in request_data:
            requested_core_features = request_data.get("core_features")
        elif "tools" in request_data:
            requested_core_features = request_data.get("tools")
        else:
            requested_core_features = bot.core_features

        # If caller explicitly sends null, treat as empty selection.
        if has_core_features_in_request and requested_core_features is None:
            requested_core_features = []
        logger.info(
            "🚀 [INIT_WORKFLOW] workflow_name=%s requested_core_features_type=%s requested_core_features=%s",
            workflow_name,
            type(requested_core_features),
            requested_core_features
        )
        
        # Check whether a workflow diagram already exists for this bot.
        existing_diagram = (
            session.query(BotDiagram)
            .filter(
                BotDiagram.tenant_id == tenant_id,
                BotDiagram.workflow_name.in_([workflow_name, legacy_workflow_name]),
                BotDiagram.del_flg == False,
                or_(BotDiagram.bot_id == bot_id, BotDiagram.bot_id.is_(None))
            )
            .order_by(desc(BotDiagram.diagram_id))
            .first()
        )

        channel_key = str(requested_channel or "").strip().lower()
        architecture = "multi_agent_router"

        if channel_key in {"whatsapp", "slack", "website"}:
            unified = create_unified_bot_agent(
                session=session,
                tenant_id=tenant_id,
                bot_id=bot_id,
                bot=bot,
                core_features=requested_core_features
            )
            agent_ids = {"bot": unified["agent_id"]}
            verification = {
                "valid": True,
                "errors": [],
                "summary": {
                    "bot": {
                        "agent_id": unified["agent_id"],
                        "kb_count": len(unified.get("kb_ids") or []),
                        "tool_count": len(unified.get("tool_names") or []),
                    }
                }
            }
            diagram = build_single_bot_agent_workflow(
                bot_id=bot_id,
                tenant_id=tenant_id,
                bot_agent_id=unified["agent_id"],
                channel=requested_channel,
                kb_ids=unified.get("kb_ids"),
                tool_names=unified.get("tool_names"),
                bot_name=(getattr(bot, "bot_name", None) or "").strip() or None,
                memory_mode=getattr(bot, "memory_mode", None),
            )
            architecture = "single_bot_agent"
        else:
            # Create all specialized agents
            specialized = create_specialized_agents(
                session=session,
                tenant_id=tenant_id,
                bot_id=bot_id,
                bot=bot,
                core_features=requested_core_features
            )
            agent_ids = specialized["agents"]
            logger.info(
                "🚀 [INIT_WORKFLOW] created agent_ids=%s",
                agent_ids
            )
            
            # ✅ VERIFICATION: Ensure correct mappings
            verification = verify_agent_mappings(session, tenant_id, agent_ids)
            logger.info(
                "🚀 [INIT_WORKFLOW] verification=%s",
                verification
            )
            
            if not verification["valid"]:
                return jsonify({
                    "error": "Agent configuration invalid",
                    "details": verification["errors"]
                }), 500
            
            # Build multi-agent workflow
            diagram = build_multi_agent_chat_workflow(
                bot_id=bot_id,
                tenant_id=tenant_id,
                router_agent_id=agent_ids["router"],
                greeting_agent_id=agent_ids["greeting"],
                kb_agent_id=agent_ids.get("kb"),
                tool_agent_id=agent_ids.get("tool"),
                response_agent_id=agent_ids.get("response"),
                channel=requested_channel,
                kb_ids=specialized.get("kb_ids"),
                tool_names=specialized.get("tool_names"),
            )
        
        if existing_diagram:
            diagram = _hydrate_trigger_credentials_in_diagram(
                diagram_data=diagram,
                session=session,
                tenant_id=tenant_id,
                bot_id=bot_id,
                channel=requested_channel,
            )
            existing_diagram.diagram_json = json.dumps(diagram)
            existing_diagram.channel = requested_channel
            existing_diagram.status = "Live"
            channel_key = str(requested_channel or "").strip().lower()
            if channel_key == "whatsapp":
                extract_and_store_whatsapp_triggers(
                    diagram,
                    bot_id,
                    tenant_id,
                    session,
                    existing_diagram.diagram_id,
                )
            elif channel_key == "slack":
                extract_and_store_slack_triggers(
                    diagram,
                    bot_id,
                    tenant_id,
                    session,
                    existing_diagram.diagram_id,
                )
            session.commit()

            return jsonify({
                "status": "Live",
                "architecture": architecture,
                "message": "Existing workflow diagram has been regenerated",
                "bot_details": bot_details,
                "workflow_id": existing_diagram.diagram_id,
                "workflow_name": existing_diagram.workflow_name or workflow_name,
                "diagram_id": existing_diagram.diagram_id,
                "channel": existing_diagram.channel,
                "agents": agent_ids,
                "verification": verification,
                "diagram": diagram
            }), 200

        diagram = _hydrate_trigger_credentials_in_diagram(
            diagram_data=diagram,
            session=session,
            tenant_id=tenant_id,
            bot_id=bot_id,
            channel=requested_channel,
        )

        new_diagram = _create_bot_diagram_with_fk_compat(
            session=session,
            bot_id=bot_id,
            tenant_id=tenant_id,
            workflow_name=workflow_name,
            channel=requested_channel,
            status="Live",
            diagram_json=json.dumps(diagram)
        )

        if channel_key == "whatsapp":
            extract_and_store_whatsapp_triggers(
                diagram,
                bot_id,
                tenant_id,
                session,
                new_diagram.diagram_id,
            )
        elif channel_key == "slack":
            extract_and_store_slack_triggers(
                diagram,
                bot_id,
                tenant_id,
                session,
                new_diagram.diagram_id,
            )

        session.commit()

        return jsonify({
            "status": "Live",
            "architecture": architecture,
            "bot_details": bot_details,
            "workflow_id": new_diagram.diagram_id,
            "workflow_name": workflow_name,
            "diagram_id": new_diagram.diagram_id,
            "channel": new_diagram.channel,
            "agents": agent_ids,
            "verification": verification,
            "diagram": diagram
        }), 201
        
    except Exception as e:
        if session is not None:
            session.rollback()
        logger.exception("❌ [INIT_WORKFLOW_ERROR]")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    finally:
        if session is not None:
            session.close()
