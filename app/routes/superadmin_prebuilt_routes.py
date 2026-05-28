"""
superadmin_prebuilt_routes.py

Super admin endpoints for managing prebuilt agents.
Auto-syncs to external partner (monorepo bridge) on import / delete / toggle-active.
"""

import requests
import os
import json
from sqlalchemy import exists, and_

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt

from app.models.agent import Agent, AgentStatusEnum
from app.models.mcp_agent_tools import McpAgentTools
from app.services.agent_parser import AgentParser
from app.services.prebuilt_agent_validator import PrebuiltAgentValidator
from app.services.prebuilt_agent_creator import PrebuiltAgentCreator
from app.models.prebuilt_agent import PrebuiltAgent
from app.models.prebuilt_agent_tools import PrebuiltAgentTools
from app.database.DatabaseOperationPostgreSQL import db_session
from logging_config import setup_logging

logger = setup_logging("superadmin-prebuilt", level="DEBUG")
superadmin_prebuilt_blueprint = Blueprint('superadmin_prebuilt', __name__, url_prefix='/superadmin/prebuilt')   
# ── Helpers ───────────────────────────────────────────────────────────────────

def is_super_admin():
    """Check if current user is super admin."""
    claims = get_jwt()
    role = (claims.get("role") or "").lower()
    return role in ("superadmin", "super_admin")

def _trigger_monorepo_sync(
    prebuilt_agent_id: int,
    action: str = "create",
    prebuilt_agent: dict = None,
    partner_base_url: str = None,
) -> dict:
    """
    Send a sync request to the monorepo bridge and return the result.
    Called ONLY from the explicit "Send to Monorepo" endpoint — never
    automatically on import.

    action: "create" | "update" | "delete"

    Returns:
        {
            "success": bool,
            "http_status_code": int | None,
            "response_body": str | None,   # truncated to 2 000 chars
            "error_message": str | None,
            "duration_ms": float,
            "monorepo_url": str,
        }
    """
    import time

    monorepo_base = os.getenv("MONOREPO_SERVICE_URL", "https://monorepo.jnanic.com")
    endpoint_url = f"{monorepo_base}/sync/agent/{prebuilt_agent_id}"

    payload = {"action": action}
    if isinstance(prebuilt_agent, dict) and prebuilt_agent:
        payload["prebuilt_agent"] = prebuilt_agent
    if partner_base_url:
        payload["partner_base_url"] = partner_base_url

    t0 = time.monotonic()
    try:
        response = requests.post(endpoint_url, json=payload, timeout=15)
        duration_ms = (time.monotonic() - t0) * 1000
        success = 200 <= response.status_code < 300
        response_body = (response.text or "")[:2000]

        if success:
            logger.info(
                "Monorepo sync success: agent=%d action=%s status=%s",
                prebuilt_agent_id, action, response.status_code,
            )
        else:
            logger.warning(
                "Monorepo sync non-2xx: agent=%d action=%s status=%s body=%s",
                prebuilt_agent_id, action, response.status_code, response_body[:300],
            )

        return {
            "success": success,
            "http_status_code": response.status_code,
            "response_body": response_body,
            "error_message": None,
            "duration_ms": round(duration_ms, 2),
            "monorepo_url": endpoint_url,
        }

    except Exception as exc:
        duration_ms = (time.monotonic() - t0) * 1000
        logger.warning("Monorepo sync exception: agent=%d error=%s", prebuilt_agent_id, str(exc))
        return {
            "success": False,
            "http_status_code": None,
            "response_body": None,
            "error_message": str(exc),
            "duration_ms": round(duration_ms, 2),
            "monorepo_url": endpoint_url,
        }


def _build_monorepo_sync_payload(saved_agent: dict | None, source_data: dict | None = None) -> dict:
    """
    Compose payload sent to monorepo sync.
    Keeps normalized DB representation and re-attaches import-only fields
    (e.g. authenticator/input_variables) that are not persisted in tbl_prebuilt_agents.
    """
    payload = dict(saved_agent or {})
    source = source_data if isinstance(source_data, dict) else {}

    for key in ("authenticator", "input_variables", "execution", "tools"):
        value = source.get(key)
        if value is not None:
            payload[key] = value

    if not payload.get("required_tools"):
        source_tools = source.get("tools")
        if isinstance(source_tools, list):
            payload["required_tools"] = [
                {
                    "tool_name": str(tool.get("tool_name") or "").strip().lower(),
                    "action_tools": tool.get("action_tools") or [],
                }
                for tool in source_tools
                if isinstance(tool, dict) and str(tool.get("tool_name") or "").strip()
            ]

    return payload
# ── Routes ────────────────────────────────────────────────────────────────────
def _sync_to_partner(prebuilt_agent_id: int, action: str = "create"):
    """
    Direct sync to partner (NO monorepo).
    """

    partner_url = os.getenv("PARTNER_API_URL", "http://partner-api.com")

    session = next(db_session())
    try:
        # Fetch agent
        agent = (
            session.query(PrebuiltAgent)
            .filter_by(prebuilt_agent_id=prebuilt_agent_id, del_flg=False)
            .first()
        )

        if not agent:
            logger.warning("Agent not found for sync: %s", prebuilt_agent_id)
            return

        tools = (
            session.query(PrebuiltAgentTools)
            .filter_by(prebuilt_agent_id=prebuilt_agent_id)
            .all()
        )

        agent_dict = agent.to_dict()

        if tools:
            agent_dict["required_tools"] = [
                {
                    "tool_name": t.tool_name,
                    "action_tools": t.action_tools or [],
                    "is_required": t.is_required,
                }
                for t in tools
            ]

        # 🔥 Call partner API
        response = requests.post(
            f"{partner_url}/agents/sync",
            json={
                "action": action,
                "agent": agent_dict
            },
            timeout=10
        )

        logger.info(
            "Partner sync success: agent=%s action=%s status=%s",
            prebuilt_agent_id, 
            action,
            response.status_code
        )

    except Exception as e:
        logger.warning("Partner sync failed: %s", str(e))

    finally:
        session.close()
        
@superadmin_prebuilt_blueprint.route('/<int:prebuilt_agent_id>', methods=['GET'])
def get_prebuilt_agent(prebuilt_agent_id):
    """
    Get a single prebuilt agent by ID.
    Used internally by monorepo bridge — no JWT required.
    GET /superadmin/prebuilt/<id>
    """
    session = next(db_session())
    try:
        agent = (
            session.query(PrebuiltAgent)
            .filter_by(prebuilt_agent_id=prebuilt_agent_id, del_flg=False)
            .first()
        )
        if not agent:
            return jsonify({"error": "Prebuilt agent not found"}), 404

        tools = (
            session.query(PrebuiltAgentTools)
            .filter_by(prebuilt_agent_id=prebuilt_agent_id)
            .all()
        )
        agent_dict = agent.to_dict()
        if tools:
            agent_dict["required_tools"] = [
                {
                    "tool_name":    t.tool_name,
                    "action_tools": t.action_tools or [],
                    "is_required":  t.is_required,
                }
                for t in tools
            ]

        return jsonify({"agent": agent_dict}), 200

    except Exception as exc:
        logger.exception("get_prebuilt_agent: error")
        return jsonify({"error": str(exc)}), 500
    finally:
        session.close()

def _serialize_agent(agent: Agent):
    """Return a template-friendly agent payload."""
    payload = agent.to_dict()
    payload["llm"] = {
        "provider_id": agent.llm_provider_id,
        "model_id": agent.llm_model_id,
        "provider_name": payload.get("llm_provider_name"),
        "model_name": payload.get("llm_model_name"),
    }
    payload["tool"] = {
        "tool_id": agent.tool_id,
        "tool_name": payload.get("tool_name"),
        "tool_description": payload.get("tool_description"),
        "tool_type": agent.tool_type,
    }
    payload["template_source"] = "agent"
    return payload

def _json_list(value, default=None):
    if default is None:
        default = []
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return [value]
    return default

def _build_template_payload(session, agent: Agent, overrides: dict):
    tools = (
        session.query(McpAgentTools)
        .filter_by(agent_id=agent.agent_id, del_flag=False)
        .all()
    )

    tools_payload = []
    for tool in tools:
        tools_payload.append({
            "tool_name": tool.tool_name,
            "tool_type": "mcp" if tool.mcp_url else "local",
            "action_tools": tool.action_tools or [],
            "mcp_url": tool.mcp_url,
        })

    if not tools_payload and getattr(agent, "tool", None):
        tools_payload.append({
            "tool_name": getattr(agent.tool, "tool_name", None),
            "tool_type": agent.tool_type or "local",
            "action_tools": [],
            "mcp_url": None,
        })

    provider = overrides.get("llm_provider") or agent.to_dict().get("llm_provider_name")
    model = overrides.get("llm_model") or agent.to_dict().get("llm_model_name")

    return {
        "agent_name": overrides.get("agent_name") or agent.agent_name or "",
        "agent_description": overrides.get("agent_description") or agent.agent_description or "",
        "agent_role": overrides.get("agent_role") or agent.agent_role or "",
        "agent_instructions": overrides.get("agent_instructions") or agent.agent_instructions or "",
        "category": overrides.get("category") or agent.agent_type or "General",
        "tags": _json_list(overrides.get("tags"), []),
        "is_featured": bool(overrides.get("is_featured", False)),
        "llm": {
            "provider": provider or "",
            "model": model or "",
        },
        "memory": {
            "enabled": overrides.get("memory_enabled", bool(agent.memory_mode)),
            "type": overrides.get("memory_type") or agent.memory_mode,
        },
        "tools": _json_list(overrides.get("tools"), tools_payload),
        "features": overrides.get("features") or agent.features or {},
        "safe_ai_settings": overrides.get("safe_ai_settings") or agent.safe_ai_settings or {},
        "additional_instructions": overrides.get("additional_instructions") or agent.additional_instructions,
        "examples": overrides.get("examples") or agent.Examples,
        "knowledge_base_config": overrides.get("knowledge_base_config") or {
            "knowledge_base_ids": agent.knowledge_base_ids or []
        },
    }

@superadmin_prebuilt_blueprint.route('/agents', methods=['GET'])
@jwt_required()
def list_agents():
    """
    List all agents for super admin template selection.
    GET /superadmin/prebuilt/agents
    Optional query params:
      - agent_status
      - agent_type
    """
    if not is_super_admin():
        return jsonify({"error": "Super admin access required"}), 403

    agent_status = request.args.get('agent_status')
    agent_type = request.args.get('agent_type')

    session = next(db_session())
    try:
        query = session.query(Agent).filter_by(del_flg=False)

        # Show only agents that are runnable as prebuilt templates:
        # must have LLM configured and at least one attached (active) tool.
        has_active_tool = exists().where(
            and_(
                McpAgentTools.agent_id == Agent.agent_id,
                McpAgentTools.del_flag == False
            )
        )
        query = query.filter(
            Agent.llm_provider_id.isnot(None),
            Agent.llm_model_id.isnot(None),
            has_active_tool,
        )

        if agent_status:
            normalized_status = next(
                (
                    status.value
                    for status in AgentStatusEnum
                    if status.value.lower() == str(agent_status).lower()
                ),
                agent_status,
            )
            query = query.filter_by(agent_status=normalized_status)
        else:
            # Default to live agents unless caller explicitly requests a status.
            query = query.filter_by(agent_status=AgentStatusEnum.LIVE.value)
        if agent_type:
            query = query.filter_by(agent_type=agent_type)

        agents = query.order_by(Agent.agent_id.desc()).all()

        return jsonify({
            "status": "success",
            "count": len(agents),
            "agents": [_serialize_agent(agent) for agent in agents],
        }), 200

    except Exception as exc:
        logger.exception("list_agents: error")
        return jsonify({"error": str(exc)}), 500
    finally:
        session.close()

@superadmin_prebuilt_blueprint.route('/agents/<int:agent_id>', methods=['GET', 'POST'])
@jwt_required()
def get_agent(agent_id):
    """
    Fetch a single agent with all template fields.
    GET /superadmin/prebuilt/agents/<id>
    POST /superadmin/prebuilt/agents/<id>
      Creates a saved prebuilt template from the selected agent.
    """
    if not is_super_admin():
        return jsonify({"error": "Super admin access required"}), 403

    session = next(db_session())
    try:
        agent = (
            session.query(Agent)
            .filter_by(agent_id=agent_id, del_flg=False)
            .first()
        )

        if not agent:
            return jsonify({"error": "Agent not found"}), 404

        if request.method == "POST":
            claims = get_jwt()
            admin_user_id = claims.get("user_id")
            overrides = request.get_json(silent=True) or {}
            template_data = _build_template_payload(session, agent, overrides)

            if not template_data["llm"]["provider"] or not template_data["llm"]["model"]:
                return jsonify({
                    "error": "LLM provider and model are required to save this template"
                }), 400

            creator = PrebuiltAgentCreator()
            result = creator.create(template_data, created_by_user_id=admin_user_id)

            if result.get("status") != "success":
                return jsonify(result), 500

            # Monorepo sync is intentionally NOT triggered here.
            # Super Admin must use POST /superadmin/prebuilt/<id>/send-to-monorepo.

            return jsonify({
                "status": "success",
                "message": "Template saved successfully",
                "template": result.get("prebuilt_agent"),
                "prebuilt_agent_id": result.get("prebuilt_agent_id"),
            }), 201

        return jsonify({
            "status": "success",
            "agent": _serialize_agent(agent),
        }), 200

    except Exception as exc:
        logger.exception("get_agent: error")
        return jsonify({"error": str(exc)}), 500
    finally:
        session.close()
        
@superadmin_prebuilt_blueprint.route('/validate', methods=['POST'])
@jwt_required()
def validate_prebuilt_import():
    """
    Validate prebuilt agent file without saving.
    POST /superadmin/prebuilt/validate
    Form Data: file (JSON or ZIP)
    """
    if not is_super_admin():
        return jsonify({"error": "Super admin access required"}), 403

    file = request.files.get('file')
    if not file:
        return jsonify({"error": "No file provided"}), 400

    try:
        parser = AgentParser()
        data = parser.parse(file)

        validator = PrebuiltAgentValidator()
        result = validator.validate(data)

        if result["valid"]:
            tools = data.get("tools") or []
            result["preview"] = {
                "agent_name":        data.get("agent_name"),
                "agent_description": data.get("agent_description"),
                "agent_role":        data.get("agent_role"),
                "llm_provider":      (data.get("llm") or {}).get("provider"),
                "llm_model":         (data.get("llm") or {}).get("model"),
                "required_tools":    [t.get("tool_name") for t in tools if t.get("tool_name")],
                "tool_count":        len(tools),
            }

        return jsonify(result), 200 if result["valid"] else 422

    except Exception as exc:
        logger.exception("superadmin_prebuilt: validation error")
        return jsonify({"error": str(exc)}), 500

@superadmin_prebuilt_blueprint.route('/import', methods=['POST'])
@jwt_required()
def import_prebuilt_agent():
    
    if not is_super_admin():
        logger.warning("Unauthorized import attempt")
        return jsonify({"error": "Super admin access required"}), 403

    claims = get_jwt()
    admin_user_id = claims.get("user_id")

    logger.info(f"[IMPORT START] admin_user_id={admin_user_id}")

    file = request.files.get('file')
    if not file:
        logger.error("[IMPORT ERROR] No file provided")
        return jsonify({"error": "No file provided"}), 400

    logger.info(f"[FILE RECEIVED] filename={file.filename}")

    category    = request.form.get('category', 'general')
    is_featured = request.form.get('is_featured', 'false').lower() == 'true'
    partner_base_url = (
        request.form.get("partner_base_url")
        or request.form.get("parent_url")
        or request.form.get("partner_url")
    )

    logger.info(f"[FORM DATA] category={category}, is_featured={is_featured}")

    try:
        # ---------------- PARSE ----------------
        logger.info("[STEP] Parsing file started")
        parser = AgentParser()
        data = parser.parse(file)

        logger.info(f"[PARSE SUCCESS] keys={list(data.keys())}")

        # ---------------- VALIDATE ----------------
        logger.info("[STEP] Validation started")
        validator = PrebuiltAgentValidator()
        validation = validator.validate(data)

        logger.info(f"[VALIDATION RESULT] valid={validation.get('valid')}")

        if not validation["valid"]:
            logger.warning(f"[VALIDATION FAILED] errors={validation.get('errors')}")
            return jsonify({
                "status":   "error",
                "errors":   validation["errors"],
                "warnings": validation["warnings"],
            }), 422

        # ---------------- PREP DATA ----------------
        data["category"]    = category
        data["is_featured"] = is_featured

        logger.info("[STEP] Creating prebuilt agent in DB")

        # ---------------- CREATE ----------------
        creator = PrebuiltAgentCreator()
        result = creator.create(data, created_by_user_id=admin_user_id)

        logger.info(f"[CREATE RESULT] status={result.get('status')}")

        if result["status"] == "error":
            logger.error(f"[CREATE FAILED] result={result}")
            return jsonify(result), 500

        new_agent_id = result.get("prebuilt_agent_id")
        logger.info(f"[AGENT CREATED] id={new_agent_id}")
        logger.info("[IMPORT SUCCESS] monorepo sync skipped — use 'Send to Monorepo' button")

        return jsonify(result), 201 

    except Exception as exc:
        logger.exception(f"[IMPORT EXCEPTION] {str(exc)}")
        return jsonify({"error": str(exc)}), 500
    
    
@superadmin_prebuilt_blueprint.route('/list', methods=['GET'])
@jwt_required()
def list_prebuilt_agents():
    """
    List all prebuilt agents in the system.
    GET /superadmin/prebuilt/list?category=sales&active=true
    """
    if not is_super_admin():
        return jsonify({"error": "Super admin access required"}), 403

    category    = request.args.get('category')
    active_only = request.args.get('active', 'false').lower() == 'true'

    session = next(db_session())
    try:
        query = session.query(PrebuiltAgent).filter_by(del_flg=False)

        if active_only:
            query = query.filter_by(is_active=True)
        if category:
            query = query.filter_by(category=category)

        prebuilt_agents = query.order_by(PrebuiltAgent.prebuilt_agent_id.desc()).all()

        result = []
        for agent in prebuilt_agents:
            tools = (
                session.query(PrebuiltAgentTools)
                .filter_by(prebuilt_agent_id=agent.prebuilt_agent_id)
                .all()
            )

            from app.models.tenant_prebuilt_agents import TenantPrebuiltAgents
            granted_count = (
                session.query(TenantPrebuiltAgents)
                .filter_by(prebuilt_agent_id=agent.prebuilt_agent_id)
                .count()
            )

            result.append({
                **agent.to_dict(),
                "required_tools":     [t.tool_name for t in tools],
                "granted_to_tenants": granted_count,
            })

        return jsonify({"agents": result}), 200

    finally:
        session.close()

@superadmin_prebuilt_blueprint.route('/<int:prebuilt_agent_id>', methods=['DELETE'])
@jwt_required()
def delete_prebuilt_agent(prebuilt_agent_id):
    """
    Soft delete a prebuilt agent.
    DELETE /superadmin/prebuilt/<id>
    → Also notifies partner to remove the agent.
    """
    if not is_super_admin():
        return jsonify({"error": "Super admin access required"}), 403

    session = next(db_session())
    try:
        agent = (
            session.query(PrebuiltAgent)
            .filter_by(prebuilt_agent_id=prebuilt_agent_id)
            .first()
        )

        if not agent:
            return jsonify({"error": "Prebuilt agent not found"}), 404

        agent.del_flg = True
        session.commit()

        logger.info("superadmin_prebuilt: deleted prebuilt_agent_id=%d", prebuilt_agent_id)

        # ✅ Notify partner to remove agent
        _sync_to_partner(prebuilt_agent_id, action="delete")

        return jsonify({"status": "success"}), 200

    except Exception as exc:
        session.rollback()
        logger.exception("superadmin_prebuilt: delete error")
        return jsonify({"error": str(exc)}), 500
    finally:
        session.close()

@superadmin_prebuilt_blueprint.route('/<int:prebuilt_agent_id>/send-to-monorepo', methods=['POST'])
@jwt_required()
def send_to_monorepo(prebuilt_agent_id):
    """
    Manually push a prebuilt agent to the monorepo bridge.
    Called when Super Admin clicks the "Send to Monorepo" button.

    POST /superadmin/prebuilt/<id>/send-to-monorepo
    Body (JSON, all optional):
      {
        "action": "create" | "update" | "delete",   # default "create"
        "partner_base_url": "https://..."            # optional
      }

    Returns:
      {
        "status": "success" | "failed",
        "log": { ...log row... }
      }
    """
    from app.models.prebuilt_agent_monorepo_log import PrebuiltAgentMonorepoLog

    if not is_super_admin():
        return jsonify({"error": "Super admin access required"}), 403

    claims   = get_jwt()
    admin_id = claims.get("user_id")

    body             = request.get_json(silent=True) or {}
    action           = body.get("action", "create")
    partner_base_url = body.get("partner_base_url") or body.get("partner_url")

    if action not in ("create", "update", "delete"):
        return jsonify({"error": "Invalid action. Must be 'create', 'update', or 'delete'."}), 400

    # ── Fetch agent + build payload ───────────────────────────────────────────
    session = next(db_session())
    try:
        agent = (
            session.query(PrebuiltAgent)
            .filter_by(prebuilt_agent_id=prebuilt_agent_id, del_flg=False)
            .first()
        )
        if not agent:
            return jsonify({"error": "Prebuilt agent not found"}), 404

        tools = (
            session.query(PrebuiltAgentTools)
            .filter_by(prebuilt_agent_id=prebuilt_agent_id)
            .all()
        )

        agent_dict = agent.to_dict()
        if tools:
            agent_dict["required_tools"] = [
                {
                    "tool_name":    t.tool_name,
                    "action_tools": t.action_tools or [],
                    "is_required":  t.is_required,
                }
                for t in tools
            ]

        sync_payload = _build_monorepo_sync_payload(agent_dict)

    except Exception as exc:
        logger.exception("send_to_monorepo: failed to build payload")
        session.close()
        return jsonify({"error": str(exc)}), 500

    # ── Call monorepo ─────────────────────────────────────────────────────────
    result = _trigger_monorepo_sync(
        prebuilt_agent_id,
        action=action,
        prebuilt_agent=sync_payload,
        partner_base_url=partner_base_url,
    )

    # ── Write log row ─────────────────────────────────────────────────────────
    try:
        log_entry = PrebuiltAgentMonorepoLog(
            prebuilt_agent_id=prebuilt_agent_id,
            action=action,
            status="success" if result["success"] else "failed",
            triggered_by=admin_id,
            http_status_code=result["http_status_code"],
            request_payload=sync_payload,
            response_body=result["response_body"],
            error_message=result["error_message"],
            duration_ms=result["duration_ms"],
            monorepo_url=result["monorepo_url"],
        )
        session.add(log_entry)
        session.commit()
        session.refresh(log_entry)
        log_dict = log_entry.to_dict()

    except Exception as exc:
        logger.exception("send_to_monorepo: failed to write log")
        session.rollback()
        log_dict = None
    finally:
        session.close()

    return jsonify({
        "status": "success" if result["success"] else "failed",
        "monorepo_http_status": result["http_status_code"],
        "log": log_dict,
    }), 200 if result["success"] else 502


# ── Monorepo sync logs ────────────────────────────────────────────────────────

@superadmin_prebuilt_blueprint.route('/<int:prebuilt_agent_id>/monorepo-logs', methods=['GET'])
@jwt_required()
def get_monorepo_logs(prebuilt_agent_id):
    """
    Return the monorepo sync history for one prebuilt agent.
    Used by the Super Admin UI to display per-agent monorepo status.

    GET /superadmin/prebuilt/<id>/monorepo-logs
    Query params:
      limit  (int, default 20, max 100)
      offset (int, default 0)

    Returns:
      {
        "prebuilt_agent_id": <id>,
        "total": <int>,
        "logs": [ ...log rows newest-first... ]
      }
    """
    from app.models.prebuilt_agent_monorepo_log import PrebuiltAgentMonorepoLog

    if not is_super_admin():
        return jsonify({"error": "Super admin access required"}), 403

    try:
        limit  = min(int(request.args.get("limit",  20)), 100)
        offset = max(int(request.args.get("offset",  0)),   0)
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

    session = next(db_session())
    try:
        base_query = (
            session.query(PrebuiltAgentMonorepoLog)
            .filter_by(prebuilt_agent_id=prebuilt_agent_id)
        )

        total = base_query.count()

        logs = (
            base_query
            .order_by(PrebuiltAgentMonorepoLog.triggered_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

        return jsonify({
            "prebuilt_agent_id": prebuilt_agent_id,
            "total": total,
            "limit": limit,
            "offset": offset,
            "logs": [log.to_dict() for log in logs],
        }), 200

    except Exception as exc:
        logger.exception("get_monorepo_logs: error")
        return jsonify({"error": str(exc)}), 500
    finally:
        session.close()


@superadmin_prebuilt_blueprint.route('/<int:prebuilt_agent_id>/toggle-active', methods=['POST'])
@jwt_required()
def toggle_active(prebuilt_agent_id):
    """
    Toggle is_active status.
    POST /superadmin/prebuilt/<id>/toggle-active
    → Also notifies partner of updated status.
    """
    if not is_super_admin():
        return jsonify({"error": "Super admin access required"}), 403

    session = next(db_session())
    try:
        agent = (
            session.query(PrebuiltAgent)
            .filter_by(prebuilt_agent_id=prebuilt_agent_id, del_flg=False)
            .first()
        )

        if not agent:
            return jsonify({"error": "Prebuilt agent not found"}), 404

        agent.is_active = not agent.is_active
        session.commit()

        # ✅ Notify partner of status change
        _sync_to_partner(prebuilt_agent_id, action="update")

        return jsonify({
            "status":    "success",
            "is_active": agent.is_active,
        }), 200

    except Exception as exc:
        session.rollback()
        logger.exception("superadmin_prebuilt: toggle error")
        return jsonify({"error": str(exc)}), 500
    finally:
        session.close()
