"""
tenant_prebuilt_routes.py

Tenant-facing endpoints for the prebuilt agents system.
(New approach — matches README architecture with tbl_tenant_prebuilt_agents)

Endpoints:
  GET  /agents/prebuilt/available           - Get all prebuilt agents granted to tenant
  POST /agents/prebuilt/grant-to-tenant     - Manually grant prebuilt agents (or called on registration)
  GET  /agents/prebuilt/<id>/check-tools    - Check tool authorization status
  POST /agents/prebuilt/<id>/activate       - Activate a prebuilt agent (clone with user credentials)
"""

import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt

from app.services.prebuilt_agent_service import PrebuiltAgentService

logger = logging.getLogger(__name__)

tenant_prebuilt_blueprint = Blueprint(
    "tenant_prebuilt",
    __name__,
    url_prefix="/agents/prebuilt"
)


def _get_tenant_id():
    """Extract tenant_id from JWT claims."""
    claims = get_jwt()
    return claims.get("tenant_id")


# ══════════════════════════════════════════════════════════════════════════
# 1. GET AVAILABLE PREBUILT AGENTS
# ══════════════════════════════════════════════════════════════════════════

@tenant_prebuilt_blueprint.route("/available", methods=["GET"])
@jwt_required()
def get_available_prebuilt_agents():
    """
    Get all prebuilt agents granted to the current tenant.
    Includes status: pending_tools / ready / active.

    GET /agents/prebuilt/available

    Response:
        {
            "agents": [
                {
                    "prebuilt_agent_id": 1,
                    "agent_name": "Email Assistant",
                    "agent_description": "...",
                    "status": "pending_tools",
                    "required_tools": ["gmail", "system"],
                    "missing_tools": ["gmail"],
                    "agent_id": null,
                    "activated_at": null
                }
            ]
        }
    """
    tenant_id = _get_tenant_id()
    if not tenant_id:
        return jsonify({"error": "Tenant ID not found in token"}), 401

    service = PrebuiltAgentService()
    result = service.get_available_prebuilt_agents(tenant_id)

    if "error" in result:
        logger.error("get_available_prebuilt_agents: tenant=%d error=%s", tenant_id, result["error"])
        return jsonify({"error": result["error"]}), 500

    return jsonify(result), 200


# ══════════════════════════════════════════════════════════════════════════
# 2. GRANT PREBUILT AGENTS (Manual trigger / registration hook)
# ══════════════════════════════════════════════════════════════════════════

@tenant_prebuilt_blueprint.route("/grant-to-tenant", methods=["POST"])
@jwt_required()
def grant_prebuilt_agents():
    """
    Grant all active prebuilt agents to current tenant.
    Normally called automatically on registration.
    Can also be called manually to pick up newly added prebuilt agents.

    POST /agents/prebuilt/grant-to-tenant

    Body (optional):
        {"plan": "basic"}

    Response:
        {
            "status": "success",
            "granted_count": 3,
            "already_had": 1
        }
    """
    tenant_id = _get_tenant_id()
    if not tenant_id:
        return jsonify({"error": "Tenant ID not found in token"}), 401

    body = request.get_json(silent=True) or {}
    plan = body.get("plan")

    service = PrebuiltAgentService()
    result = service.grant_prebuilt_agents_to_tenant(tenant_id, plan)

    logger.info(
        "grant_prebuilt_agents: tenant=%d granted=%d already_had=%d",
        tenant_id,
        result.get("granted_count", 0),
        result.get("already_had", 0)
    )

    return jsonify({
        "status": "success",
        "granted_count": result.get("granted_count", 0),
        "already_had": result.get("already_had", 0),
        "agents": result.get("agents", []),
    }), 200


# ══════════════════════════════════════════════════════════════════════════
# 3. CHECK TOOL STATUS FOR A PREBUILT AGENT
# ══════════════════════════════════════════════════════════════════════════

@tenant_prebuilt_blueprint.route("/<int:prebuilt_agent_id>/check-tools", methods=["GET"])
@jwt_required()
def check_tool_status(prebuilt_agent_id):
    """
    Check current tool authorization status for a prebuilt agent.
    Refreshes the missing_tools list from live tool authorization data.

    GET /agents/prebuilt/<id>/check-tools

    Response:
        {
            "status": "ready",          // or "pending_tools"
            "can_activate": true,
            "required_tools": ["gmail"],
            "missing_tools": [],
        }
    """
    tenant_id = _get_tenant_id()
    if not tenant_id:
        return jsonify({"error": "Tenant ID not found in token"}), 401

    service = PrebuiltAgentService()
    result = service.check_and_update_tool_status(tenant_id, prebuilt_agent_id)

    if result.get("status") == "not_found":
        return jsonify({"error": result.get("error", "Not found")}), 404

    if result.get("status") == "error":
        return jsonify({"error": result.get("error", "Internal error")}), 500

    return jsonify(result), 200


# ══════════════════════════════════════════════════════════════════════════
# 4. ACTIVATE PREBUILT AGENT
# ══════════════════════════════════════════════════════════════════════════

@tenant_prebuilt_blueprint.route("/<int:prebuilt_agent_id>/activate", methods=["POST"])
@jwt_required()
def activate_prebuilt_agent(prebuilt_agent_id):
    """
    Activate a prebuilt agent for the current tenant.
    Clones the agent to tbl_agents using tenant's own credentials.
    Updates tbl_tenant_prebuilt_agents status to 'active'.

    POST /agents/prebuilt/<id>/activate

    Response (success):
        {
            "status": "success",
            "agent_id": 123,
            "agent": {...},
            "message": "Agent activated and ready to use!"
        }

    Response (error - missing tools):
        {
            "status": "error",
            "error": "Connect these tools first: gmail",
            "missing_tools": ["gmail"]
        }
    """
    tenant_id = _get_tenant_id()
    if not tenant_id:
        return jsonify({"error": "Tenant ID not found in token"}), 401

    service = PrebuiltAgentService()
    result = service.activate_prebuilt_agent(tenant_id, prebuilt_agent_id)

    if result.get("status") == "success":
        logger.info(
            "activate_prebuilt_agent: SUCCESS tenant=%d prebuilt=%d agent=%d",
            tenant_id, prebuilt_agent_id, result.get("agent_id")
        )
        return jsonify(result), 200
    else:
        logger.warning(
            "activate_prebuilt_agent: FAILED tenant=%d prebuilt=%d error=%s",
            tenant_id, prebuilt_agent_id, result.get("error")
        )
        # 409 for already active, 422 for missing tools or config errors
        status_code = 422
        if "already activated" in (result.get("error") or ""):
            status_code = 409
        return jsonify(result), status_code
