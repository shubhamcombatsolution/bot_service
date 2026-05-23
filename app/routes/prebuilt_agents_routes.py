"""
prebuilt_agents_routes.py

Tenant-facing routes for browsing and cloning prebuilt agents.

Endpoints:
  GET  /prebuilt-agents              - Browse available prebuilt agents
  GET  /prebuilt-agents/<id>         - Get prebuilt agent details
  GET  /prebuilt-agents/<id>/check   - Check if tenant can clone (has tools)
  POST /prebuilt-agents/<id>/clone   - Clone prebuilt agent to tenant account
  GET  /my-cloned-agents              - Get tenant's cloned agents
"""

import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt

from app.services.agent_cloning_service import AgentCloningService
from app.models.prebuilt_agent import PrebuiltAgent, TenantClonedAgent
from app.database.DatabaseOperationPostgreSQL import db_session

logger = logging.getLogger(__name__)

prebuilt_agents_blueprint = Blueprint(
    "prebuilt_agents",
    __name__,
    url_prefix="/prebuilt-agents"
)


# ══════════════════════════════════════════════════════════════════════════
# BROWSE ENDPOINTS (Tenant View)
# ══════════════════════════════════════════════════════════════════════════

@prebuilt_agents_blueprint.route('', methods=['GET'])
@jwt_required()
def browse_prebuilt_agents():
    """
    Browse available prebuilt agents (tenant view - only active & public).
    
    Query params:
      - category: Filter by category
      - featured: Show only featured agents
      - search: Search in name/description
    
    Response:
      {
        "status": "success",
        "count": int,
        "agents": [
          {
            ...agent details...,
            "already_cloned": bool,
            "can_clone": bool,
            "missing_tools": [...]
          }
        ]
      }
    """
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    category = request.args.get('category')
    featured = request.args.get('featured')
    search = request.args.get('search')

    session = next(db_session())
    try:
        # Query active, public prebuilt agents
        query = session.query(PrebuiltAgent).filter_by(
            del_flg=False,
            is_active=True,
            is_public=True
        )

        if category:
            query = query.filter_by(category=category)
        if featured and featured.lower() == 'true':
            query = query.filter_by(is_featured=True)
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (PrebuiltAgent.agent_name.ilike(search_term)) |
                (PrebuiltAgent.agent_description.ilike(search_term))
            )

        query = query.order_by(
            PrebuiltAgent.display_order,
            PrebuiltAgent.is_featured.desc(),
            PrebuiltAgent.clone_count.desc()
        )

        agents = query.all()

        # Get tenant's cloned agents
        cloned_ids = set(
            c.prebuilt_agent_id
            for c in session.query(TenantClonedAgent.prebuilt_agent_id)
            .filter_by(tenant_id=tenant_id)
            .all()
        )

        # Check tool access for each agent
        cloning_service = AgentCloningService()
        
        result_agents = []
        for agent in agents:
            agent_dict = agent.to_dict()
            
            # Check if already cloned
            agent_dict["already_cloned"] = agent.prebuilt_agent_id in cloned_ids
            
            # Check tool access (only if not already cloned)
            if not agent_dict["already_cloned"]:
                has_access, available, missing = cloning_service.check_tool_access(
                    tenant_id, agent.prebuilt_agent_id
                )
                agent_dict["can_clone"] = has_access
                agent_dict["missing_tools"] = missing
            else:
                agent_dict["can_clone"] = False
                agent_dict["missing_tools"] = []
            
            result_agents.append(agent_dict)

        return jsonify({
            "status": "success",
            "count": len(result_agents),
            "agents": result_agents
        }), 200

    finally:
        session.close()


@prebuilt_agents_blueprint.route('/<int:prebuilt_agent_id>', methods=['GET'])
@jwt_required()
def get_prebuilt_agent_details(prebuilt_agent_id):
    """
    Get detailed info about a prebuilt agent.
    Includes tenant-specific info (can_clone, already_cloned, missing_tools).
    """
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    session = next(db_session())
    try:
        agent = (
            session.query(PrebuiltAgent)
            .filter_by(
                prebuilt_agent_id=prebuilt_agent_id,
                del_flg=False,
                is_active=True,
                is_public=True
            )
            .first()
        )

        if not agent:
            return jsonify({"error": "Prebuilt agent not found"}), 404

        agent_dict = agent.to_dict()

        # Check if already cloned
        existing = (
            session.query(TenantClonedAgent)
            .filter_by(tenant_id=tenant_id, prebuilt_agent_id=prebuilt_agent_id)
            .first()
        )
        agent_dict["already_cloned"] = existing is not None
        if existing:
            agent_dict["cloned_agent_id"] = existing.cloned_agent_id

        # Check tool access
        cloning_service = AgentCloningService()
        has_access, available, missing = cloning_service.check_tool_access(
            tenant_id, prebuilt_agent_id
        )
        agent_dict["can_clone"] = has_access and not existing
        agent_dict["missing_tools"] = missing
        agent_dict["available_tools"] = available

        return jsonify({
            "status": "success",
            "agent": agent_dict
        }), 200

    finally:
        session.close()


# ══════════════════════════════════════════════════════════════════════════
# CLONE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

@prebuilt_agents_blueprint.route('/<int:prebuilt_agent_id>/check', methods=['GET'])
@jwt_required()
def check_clone_eligibility(prebuilt_agent_id):
    """
    Check if tenant can clone this prebuilt agent.
    Returns tool access status without actually cloning.
    
    Response:
      {
        "can_clone": bool,
        "already_cloned": bool,
        "missing_tools": [...],
        "message": str
      }
    """
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    session = next(db_session())
    try:
        # Check if already cloned
        existing = (
            session.query(TenantClonedAgent)
            .filter_by(tenant_id=tenant_id, prebuilt_agent_id=prebuilt_agent_id)
            .first()
        )

        if existing:
            return jsonify({
                "can_clone": False,
                "already_cloned": True,
                "missing_tools": [],
                "message": "You have already added this agent to your account",
                "existing_agent_id": existing.cloned_agent_id
            }), 200

        # Check tool access
        cloning_service = AgentCloningService()
        has_access, available, missing = cloning_service.check_tool_access(
            tenant_id, prebuilt_agent_id
        )

        if has_access:
            message = "✅ You can clone this agent! All required tools are connected."
        else:
            message = (
                f"❌ Please connect these tools first: {', '.join(missing)}. "
                "Then you can add this agent."
            )

        return jsonify({
            "can_clone": has_access,
            "already_cloned": False,
            "missing_tools": missing,
            "available_tools": available,
            "message": message
        }), 200

    finally:
        session.close()


@prebuilt_agents_blueprint.route('/<int:prebuilt_agent_id>/clone', methods=['POST'])
@jwt_required()
def clone_prebuilt_agent(prebuilt_agent_id):
    """
    Clone prebuilt agent to tenant's account.
    
    Validates:
      - Not already cloned
      - Tenant has all required tools
      
    Response (success):
      {
        "status": "success",
        "agent_id": int,
        "agent": {...},
        "message": str
      }
      
    Response (error):
      {
        "status": "error",
        "error_code": str,
        "message": str,
        "missing_tools": [...]  # If error_code='missing_tools'
      }
    """
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    cloning_service = AgentCloningService()
    result = cloning_service.clone_to_tenant(tenant_id, prebuilt_agent_id)

    if result["status"] == "success":
        logger.info(
            "prebuilt_clone: tenant=%d cloned prebuilt=%d -> agent=%d",
            tenant_id, prebuilt_agent_id, result["agent_id"]
        )
        return jsonify(result), 200
    else:
        logger.warning(
            "prebuilt_clone: tenant=%d failed to clone prebuilt=%d - %s",
            tenant_id, prebuilt_agent_id, result.get("error_code")
        )
        return jsonify(result), 422


# ══════════════════════════════════════════════════════════════════════════
# TENANT'S CLONED AGENTS
# ══════════════════════════════════════════════════════════════════════════

@prebuilt_agents_blueprint.route('/my-cloned-agents', methods=['GET'])
@jwt_required()
def get_my_cloned_agents():
    """
    Get list of prebuilt agents this tenant has cloned.
    
    Response:
      {
        "status": "success",
        "count": int,
        "cloned_agents": [
          {
            "prebuilt_agent_id": int,
            "cloned_agent_id": int,
            "agent_name": str,
            "category": str,
            "cloned_at": str,
            "is_active": bool
          }
        ]
      }
    """
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    session = next(db_session())
    try:
        from app.models import Agent

        cloned = (
            session.query(TenantClonedAgent, PrebuiltAgent, Agent)
            .join(PrebuiltAgent, TenantClonedAgent.prebuilt_agent_id == PrebuiltAgent.prebuilt_agent_id)
            .join(Agent, TenantClonedAgent.cloned_agent_id == Agent.agent_id)
            .filter(TenantClonedAgent.tenant_id == tenant_id)
            .order_by(TenantClonedAgent.cloned_at.desc())
            .all()
        )

        result = []
        for clone_record, prebuilt, agent in cloned:
            result.append({
                "prebuilt_agent_id": prebuilt.prebuilt_agent_id,
                "cloned_agent_id": agent.agent_id,
                "agent_name": agent.agent_name,
                "category": prebuilt.category,
                "cloned_at": clone_record.cloned_at.isoformat() if clone_record.cloned_at else None,
                "is_active": clone_record.is_active,
                "user_rating": clone_record.user_rating,
            })

        return jsonify({
            "status": "success",
            "count": len(result),
            "cloned_agents": result
        }), 200

    finally:
        session.close()
