"""
superadmin_prebuilt_agent_routes.py

Flask routes for Super Admin to manage prebuilt agents.

Endpoints:
  POST   /superadmin/prebuilt-agents/import/validate
  POST   /superadmin/prebuilt-agents/import/create
  GET    /superadmin/prebuilt-agents
  GET    /superadmin/prebuilt-agents/<id>
  PUT    /superadmin/prebuilt-agents/<id>
  DELETE /superadmin/prebuilt-agents/<id>
"""

import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt

from app.services.prebuilt_agent_import_service import PrebuiltAgentImportService
from app.models.prebuilt_agent import PrebuiltAgent
from app.database.DatabaseOperationPostgreSQL import db_session

logger = logging.getLogger(__name__)

superadmin_prebuilt_blueprint = Blueprint(
    "superadmin_prebuilt",
    __name__,
    url_prefix="/superadmin/prebuilt-agents"
)


def _is_super_admin():
    """Check if current user is Super Admin"""
    claims = get_jwt()
    role = claims.get("role", "").lower()
    # Adjust this check based on your actual Super Admin role field
    return role in ["superadmin", "super_admin", "admin"]


# ══════════════════════════════════════════════════════════════════════════
# IMPORT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

@superadmin_prebuilt_blueprint.route('/import/validate', methods=['POST'])
@jwt_required()
def validate_prebuilt_import():
    """
    Validate prebuilt agent file (dry-run, no DB writes).
    
    Request: multipart/form-data with 'file'
    Response: {valid: bool, errors: [...], warnings: [...], preview: {...}}
    """
    if not _is_super_admin():
        return jsonify({"error": "Unauthorized - Super Admin only"}), 403

    file = request.files.get('file')
    if not file:
        return jsonify({"error": "No file provided"}), 400

    claims = get_jwt()
    user_id = claims.get("user_id")

    service = PrebuiltAgentImportService(created_by_user_id=user_id)
    result = service.validate(file)

    return jsonify(result), 200 if result["valid"] else 422


@superadmin_prebuilt_blueprint.route('/import/create', methods=['POST'])
@jwt_required()
def create_prebuilt_import():
    """
    Import prebuilt agent(s) to tbl_prebuilt_agents.
    
    Request: multipart/form-data with 'file'
    Response: {status: 'success', prebuilt_agent_id: int, ...}
    """
    if not _is_super_admin():
        return jsonify({"error": "Unauthorized - Super Admin only"}), 403

    file = request.files.get('file')
    if not file:
        return jsonify({"error": "No file provided"}), 400

    claims = get_jwt()
    user_id = claims.get("user_id")

    service = PrebuiltAgentImportService(created_by_user_id=user_id)
    result = service.import_prebuilt_agent(file)

    if result["status"] == "success":
        return jsonify(result), 200
    else:
        return jsonify(result), 422


# ══════════════════════════════════════════════════════════════════════════
# CRUD ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

@superadmin_prebuilt_blueprint.route('', methods=['GET'])
@jwt_required()
def get_all_prebuilt_agents():
    """
    Get all prebuilt agents (Super Admin view - includes inactive).
    
    Query params:
      - category: Filter by category
      - is_active: Filter by active status
      - is_featured: Filter by featured status
    """
    if not _is_super_admin():
        return jsonify({"error": "Unauthorized - Super Admin only"}), 403

    category = request.args.get('category')
    is_active = request.args.get('is_active')
    is_featured = request.args.get('is_featured')

    session = next(db_session())
    try:
        query = session.query(PrebuiltAgent).filter_by(del_flg=False)

        if category:
            query = query.filter_by(category=category)
        if is_active is not None:
            query = query.filter_by(is_active=is_active.lower() == 'true')
        if is_featured is not None:
            query = query.filter_by(is_featured=is_featured.lower() == 'true')

        query = query.order_by(PrebuiltAgent.display_order, PrebuiltAgent.created_at.desc())

        agents = query.all()

        return jsonify({
            "status": "success",
            "count": len(agents),
            "agents": [agent.to_dict() for agent in agents]
        }), 200

    finally:
        session.close()


@superadmin_prebuilt_blueprint.route('/<int:prebuilt_agent_id>', methods=['GET'])
@jwt_required()
def get_prebuilt_agent(prebuilt_agent_id):
    """Get single prebuilt agent by ID"""
    if not _is_super_admin():
        return jsonify({"error": "Unauthorized - Super Admin only"}), 403

    session = next(db_session())
    try:
        agent = (
            session.query(PrebuiltAgent)
            .filter_by(prebuilt_agent_id=prebuilt_agent_id, del_flg=False)
            .first()
        )

        if not agent:
            return jsonify({"error": "Prebuilt agent not found"}), 404

        return jsonify({
            "status": "success",
            "agent": agent.to_dict()
        }), 200

    finally:
        session.close()


@superadmin_prebuilt_blueprint.route('/<int:prebuilt_agent_id>', methods=['PUT'])
@jwt_required()
def update_prebuilt_agent(prebuilt_agent_id):
    """
    Update prebuilt agent.
    
    Request body: {field: value, ...}
    Updateable fields: agent_name, agent_description, category, tags,
                      is_featured, is_active, display_order, etc.
    """
    if not _is_super_admin():
        return jsonify({"error": "Unauthorized - Super Admin only"}), 403

    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    session = next(db_session())
    try:
        agent = (
            session.query(PrebuiltAgent)
            .filter_by(prebuilt_agent_id=prebuilt_agent_id, del_flg=False)
            .first()
        )

        if not agent:
            return jsonify({"error": "Prebuilt agent not found"}), 404

        # Update allowed fields
        updateable_fields = [
            "agent_name", "agent_description", "agent_role", "agent_instructions",
            "category", "tags", "is_featured", "is_active", "display_order",
            "minimum_plan_level", "is_public",
            "llm_provider", "llm_model", "temperature", "max_tokens",
            "features", "safe_ai_settings", "additional_instructions", "examples",
            "memory_type", "memory_enabled", "required_tools", "knowledge_base_config",
        ]

        for field in updateable_fields:
            if field in data:
                setattr(agent, field, data[field])

        from datetime import datetime
        agent.updated_at = datetime.utcnow()

        session.commit()
        session.refresh(agent)

        logger.info(
            "superadmin: updated prebuilt_agent_id=%d",
            prebuilt_agent_id
        )

        return jsonify({
            "status": "success",
            "message": "Prebuilt agent updated successfully",
            "agent": agent.to_dict()
        }), 200

    except Exception as e:
        session.rollback()
        logger.exception("superadmin: error updating prebuilt agent")
        return jsonify({"error": f"Update failed: {str(e)}"}), 500

    finally:
        session.close()


@superadmin_prebuilt_blueprint.route('/<int:prebuilt_agent_id>', methods=['DELETE'])
@jwt_required()
def delete_prebuilt_agent(prebuilt_agent_id):
    """Soft delete prebuilt agent"""
    if not _is_super_admin():
        return jsonify({"error": "Unauthorized - Super Admin only"}), 403

    session = next(db_session())
    try:
        agent = (
            session.query(PrebuiltAgent)
            .filter_by(prebuilt_agent_id=prebuilt_agent_id, del_flg=False)
            .first()
        )

        if not agent:
            return jsonify({"error": "Prebuilt agent not found"}), 404

        agent.del_flg = True
        session.commit()

        logger.info(
            "superadmin: deleted prebuilt_agent_id=%d",
            prebuilt_agent_id
        )

        return jsonify({
            "status": "success",
            "message": "Prebuilt agent deleted successfully"
        }), 200

    except Exception as e:
        session.rollback()
        logger.exception("superadmin: error deleting prebuilt agent")
        return jsonify({"error": f"Delete failed: {str(e)}"}), 500

    finally:
        session.close()


# ══════════════════════════════════════════════════════════════════════════
# ANALYTICS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

@superadmin_prebuilt_blueprint.route('/analytics', methods=['GET'])
@jwt_required()
def get_prebuilt_analytics():
    """Get analytics for all prebuilt agents"""
    if not _is_super_admin():
        return jsonify({"error": "Unauthorized - Super Admin only"}), 403

    session = next(db_session())
    try:
        from sqlalchemy import func
        from app.models.prebuilt_agent import TenantClonedAgent

        # Get agents with clone counts
        agents = (
            session.query(
                PrebuiltAgent.prebuilt_agent_id,
                PrebuiltAgent.agent_name,
                PrebuiltAgent.category,
                PrebuiltAgent.clone_count,
                PrebuiltAgent.average_rating,
                func.count(TenantClonedAgent.id).label('active_clones')
            )
            .outerjoin(
                TenantClonedAgent,
                PrebuiltAgent.prebuilt_agent_id == TenantClonedAgent.prebuilt_agent_id
            )
            .filter(PrebuiltAgent.del_flg == False)
            .group_by(PrebuiltAgent.prebuilt_agent_id)
            .order_by(PrebuiltAgent.clone_count.desc())
            .all()
        )

        return jsonify({
            "status": "success",
            "analytics": [
                {
                    "prebuilt_agent_id": a.prebuilt_agent_id,
                    "agent_name": a.agent_name,
                    "category": a.category,
                    "total_clones": a.clone_count or 0,
                    "active_clones": a.active_clones or 0,
                    "average_rating": float(a.average_rating) if a.average_rating else None,
                }
                for a in agents
            ]
        }), 200

    finally:
        session.close()

































# """
# superadmin_prebuilt_routes.py

# Super admin endpoints for managing prebuilt agents.
# """

# import logging
# from flask import Blueprint, request, jsonify
# from flask_jwt_extended import jwt_required, get_jwt

# from app.services.agent_parser import AgentParser
# from app.services.prebuilt_agent_validator import PrebuiltAgentValidator
# from app.services.prebuilt_agent_creator import PrebuiltAgentCreator
# from app.models.prebuilt_agent import PrebuiltAgent
# from app.models.prebuilt_agent_tools import PrebuiltAgentTools
# from app.database.DatabaseOperationPostgreSQL import db_session

# logger = logging.getLogger(__name__)

# superadmin_prebuilt_blueprint = Blueprint('superadmin_prebuilt', __name__, url_prefix='/superadmin/prebuilt')


# def is_super_admin():
#     """Check if current user is super admin"""
#     claims = get_jwt()
#     # TODO: Implement proper super admin check
#     # For now, check if user has special role or tenant_id
#     return claims.get("role") == "superadmin" or claims.get("is_superadmin") == True


# @superadmin_prebuilt_blueprint.route('/validate', methods=['POST'])
# @jwt_required()
# def validate_prebuilt_import():
#     """
#     Validate prebuilt agent file without saving.
    
#     POST /superadmin/prebuilt/validate
    
#     Form Data:
#         file: JSON or ZIP file with agent configuration
    
#     Returns:
#         {
#             "valid": true,
#             "errors": [],
#             "warnings": [
#                 "credentials should NOT be provided - they will be ignored"
#             ],
#             "preview": {
#                 "agent_name": "Email Assistant",
#                 "required_tools": ["gmail", "system"]
#             }
#         }
#     """
#     if not is_super_admin():
#         return jsonify({"error": "Super admin access required"}), 403
    
#     file = request.files.get('file')
#     if not file:
#         return jsonify({"error": "No file provided"}), 400
    
#     try:
#         # Parse
#         parser = AgentParser()
#         data = parser.parse(file)
        
#         # Validate (no credentials checked)
#         validator = PrebuiltAgentValidator()
#         result = validator.validate(data)
        
#         # Add tool requirements to preview
#         if result["valid"]:
#             tools = data.get("tools") or []
#             result["preview"] = {
#                 "agent_name": data.get("agent_name"),
#                 "agent_description": data.get("agent_description"),
#                 "agent_role": data.get("agent_role"),
#                 "llm_provider": (data.get("llm") or {}).get("provider"),
#                 "llm_model": (data.get("llm") or {}).get("model"),
#                 "required_tools": [t.get("tool_name") for t in tools if t.get("tool_name")],
#                 "tool_count": len(tools),
#             }
        
#         return jsonify(result), 200 if result["valid"] else 422
    
#     except Exception as exc:
#         logger.exception("superadmin_prebuilt: validation error")
#         return jsonify({"error": str(exc)}), 500


# @superadmin_prebuilt_blueprint.route('/import', methods=['POST'])
# @jwt_required()
# def import_prebuilt_agent():
#     """
#     Import prebuilt agent to system catalog.
    
#     POST /superadmin/prebuilt/import
    
#     Form Data:
#         file: JSON or ZIP file with agent configuration
#         category (optional): "sales", "support", "marketing", etc.
#         is_featured (optional): true/false
    
#     Returns:
#         {
#             "status": "success",
#             "prebuilt_agent_id": 1,
#             "agent": {...}
#         }
#     """
#     if not is_super_admin():
#         return jsonify({"error": "Super admin access required"}), 403
    
#     claims = get_jwt()
#     admin_user_id = claims.get("user_id")
    
#     file = request.files.get('file')
#     if not file:
#         return jsonify({"error": "No file provided"}), 400
    
#     category = request.form.get('category', 'general')
#     is_featured = request.form.get('is_featured', 'false').lower() == 'true'
    
#     try:
#         # Parse
#         parser = AgentParser()
#         data = parser.parse(file)
        
#         # Validate
#         validator = PrebuiltAgentValidator()
#         validation = validator.validate(data)
        
#         if not validation["valid"]:
#             return jsonify({
#                 "status": "error",
#                 "errors": validation["errors"],
#                 "warnings": validation["warnings"]
#             }), 422
        
#         # Add metadata
#         data["category"] = category
#         data["is_featured"] = is_featured
        
#         # Create
#         creator = PrebuiltAgentCreator()
#         result = creator.create(data, created_by=admin_user_id)
        
#         if result["status"] == "error":
#             return jsonify(result), 500
        
#         return jsonify(result), 201
    
#     except Exception as exc:
#         logger.exception("superadmin_prebuilt: import error")
#         return jsonify({"error": str(exc)}), 500


# @superadmin_prebuilt_blueprint.route('/list', methods=['GET'])
# @jwt_required()
# def list_prebuilt_agents():
#     """
#     List all prebuilt agents in the system.
    
#     GET /superadmin/prebuilt/list?category=sales&active=true
    
#     Returns:
#         {
#             "agents": [
#                 {
#                     "prebuilt_agent_id": 1,
#                     "agent_name": "Email Assistant",
#                     "category": "productivity",
#                     "is_active": true,
#                     "required_tools": ["gmail", "system"],
#                     "granted_to_tenants": 45
#                 }
#             ]
#         }
#     """
#     if not is_super_admin():
#         return jsonify({"error": "Super admin access required"}), 403
    
#     category = request.args.get('category')
#     active_only = request.args.get('active', 'true').lower() == 'true'
    
#     session = next(db_session())
#     try:
#         query = session.query(PrebuiltAgent).filter_by(del_flg=False)
        
#         if active_only:
#             query = query.filter_by(is_active=True)
        
#         if category:
#             query = query.filter_by(category=category)
        
#         prebuilt_agents = query.all()
        
#         result = []
#         for agent in prebuilt_agents:
#             # Get required tools
#             tools = (
#                 session.query(PrebuiltAgentTools)
#                 .filter_by(prebuilt_agent_id=agent.prebuilt_agent_id)
#                 .all()
#             )
            
#             # Count granted tenants
#             from app.models.tenant_prebuilt_agents import TenantPrebuiltAgents
#             granted_count = (
#                 session.query(TenantPrebuiltAgents)
#                 .filter_by(prebuilt_agent_id=agent.prebuilt_agent_id)
#                 .count()
#             )
            
#             result.append({
#                 **agent.to_dict(),
#                 "required_tools": [t.tool_name for t in tools],
#                 "granted_to_tenants": granted_count,
#             })
        
#         return jsonify({"agents": result}), 200
    
#     finally:
#         session.close()


# @superadmin_prebuilt_blueprint.route('/<int:prebuilt_agent_id>', methods=['DELETE'])
# @jwt_required()
# def delete_prebuilt_agent(prebuilt_agent_id):
#     """
#     Soft delete a prebuilt agent.
    
#     DELETE /superadmin/prebuilt/123
#     """
#     if not is_super_admin():
#         return jsonify({"error": "Super admin access required"}), 403
    
#     session = next(db_session())
#     try:
#         agent = (
#             session.query(PrebuiltAgent)
#             .filter_by(prebuilt_agent_id=prebuilt_agent_id)
#             .first()
#         )
        
#         if not agent:
#             return jsonify({"error": "Prebuilt agent not found"}), 404
        
#         agent.del_flg = True
#         session.commit()
        
#         logger.info(
#             "superadmin_prebuilt: deleted prebuilt_agent_id=%d",
#             prebuilt_agent_id
#         )
        
#         return jsonify({"status": "success"}), 200
    
#     except Exception as exc:
#         session.rollback()
#         logger.exception("superadmin_prebuilt: delete error")
#         return jsonify({"error": str(exc)}), 500
    
#     finally:
#         session.close()


# @superadmin_prebuilt_blueprint.route('/<int:prebuilt_agent_id>/toggle-active', methods=['POST'])
# @jwt_required()
# def toggle_active(prebuilt_agent_id):
#     """
#     Toggle is_active status.
    
#     POST /superadmin/prebuilt/123/toggle-active
#     """
#     if not is_super_admin():
#         return jsonify({"error": "Super admin access required"}), 403
    
#     session = next(db_session())
#     try:
#         agent = (
#             session.query(PrebuiltAgent)
#             .filter_by(prebuilt_agent_id=prebuilt_agent_id, del_flg=False)
#             .first()
#         )
        
#         if not agent:
#             return jsonify({"error": "Prebuilt agent not found"}), 404
        
#         agent.is_active = not agent.is_active
#         session.commit()
        
#         return jsonify({
#             "status": "success",
#             "is_active": agent.is_active
#         }), 200
    
#     except Exception as exc:
#         session.rollback()
#         logger.exception("superadmin_prebuilt: toggle error")
#         return jsonify({"error": str(exc)}), 500
    
#     finally:
#         session.close()