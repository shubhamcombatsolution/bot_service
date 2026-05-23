from flask import Blueprint, request, jsonify
from datetime import datetime
from app.models.role import Role
from app.database.DatabaseOperationPostgreSQL import db_session
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt,jwt_required
from app.models import db, ToolAuthorization ,Tools
authTool_blueprint = Blueprint("auth_tools", __name__)

from flask_jwt_extended import jwt_required, get_jwt
from flask import jsonify, current_app
from collections import defaultdict

@authTool_blueprint.route("/user/tools", methods=["GET"])
@jwt_required()
def get_user_tools():
    try:
        claims = get_jwt()  # Get full JWT payload
        tenant_id = claims.get("tenant_id")  # Extract tenant_id claim

        if not tenant_id:
            return jsonify({"status": "error", "message": "Missing tenant_id in token"}), 400

        tools = ToolAuthorization.query.filter_by(
            tenant_id=tenant_id, del_flag=False
        ).all()

        data = []
        for t in tools:
            mcp_name = ""
            if t.tool_type == "mcp":
                mcp_name = (t.mcp_url or "")
                if not mcp_name and isinstance(t.mcp_json, dict):
                    mcp_name = str(t.mcp_json.get("mcp_name") or "")

            data.append({
                "tool_name": t.tool_name,
                "tool_id": t.id,
                "tool_type": t.tool_type,
                "mcp_name": mcp_name,
            })

        return jsonify({
            "status": "success",
            "tenant_id": tenant_id,
            "count": len(data),
            "data": data
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error fetching tools for tenant: {e}")
        return jsonify({
            "status": "error",
            "message": "Unable to retrieve tools"
        }), 500


def normalize_tool_name(name: str) -> str:
    """
    Converts:
    - Jnanic_MCP_Gmail → gmail
    - Gmail → gmail
    - GSheets → gsheets
    """
    value = (name or "").lower().replace("jnanic_mcp_", "").strip()
    return value.replace("_", "").replace("-", "").replace(" ", "")



DEFAULT_TOOLS = {"tavily"}

@authTool_blueprint.route("/catalog", methods=["GET"])
@jwt_required()
def get_tool_catalog():
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    if not tenant_id:
        return jsonify({
            "status": "error",
            "message": "Missing tenant_id"
        }), 400

    # 1️⃣ Fetch all catalog tools (GLOBAL)
    all_tools = Tools.query.filter_by(del_flg=False).all()

    # 2️⃣ Fetch tenant-authorized tools (LOCAL + MCP)
    auth_tools = ToolAuthorization.query.filter_by(
        tenant_id=tenant_id,
        del_flag=False
    ).all()

    # 3️⃣ Group connections by base tool
    connection_map = defaultdict(list)

    for auth in auth_tools:
        base_tool = normalize_tool_name(auth.tool_name)

        connection_map[base_tool].append({
            "auth_id": auth.id,
            "connection_name": auth.tool_name,   # Gmail / Jnanic_MCP_Gmail
            "connection_type": auth.tool_type,   # local / mcp
            "has_mcp_url": bool(auth.mcp_url)
        })

    # 4️⃣ Build catalog response
    response = []

    for tool in all_tools:
        base_tool = normalize_tool_name(tool.tool_name)
        is_default_tool = base_tool in DEFAULT_TOOLS
        connections = connection_map.get(base_tool, [])

        response.append({
            "tool_id": tool.tool_id,
            "tool_name": tool.tool_name,          # GENERAL NAME
            "description": tool.tool_description,
            "logo": tool.tool_logo,
            "tool_class": tool.tool_class,

            # Enabled if at least one connection exists
            "enabled": is_default_tool or len(connections) > 0,

            # NEW (non-breaking addition)
            "connections": connections
        })

    return jsonify({
        "status": "success",
        "tools": response
    }), 200



@authTool_blueprint.route("/tool_type", methods=["POST"])
@jwt_required()
def add_or_update_tool_type():
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}

        # STEP 1: Ensure tool_type is provided, fallback to 'local'
        tool_type = data.get("tool_type", "local").lower()
        print(f"ssssssssssssss---------------------->{tool_type}")
        if tool_type not in ["local", "mcp"]:
            return jsonify({
                "status": "error",
                "message": "Invalid tool type. Must be 'local' or 'mcp'."
            }), 400

        # STEP 2: Fetch existing record for this user
        existing_tool = ToolAuthorization.query.filter_by(
            tenant_id=user_id,
            del_flag=False
        ).order_by(ToolAuthorization.created_at.desc()).first()

        if existing_tool:
            # Update existing record
            existing_tool.tool_type = tool_type
            existing_tool.updated_at = datetime.utcnow()
            db.session.commit()
            return jsonify({
                "status": "success",
                "message": f"Tool type updated to '{tool_type}'",
                "data": {
                    "id": existing_tool.id,
                    "tool_type": existing_tool.tool_type
                }
            }), 200

        # STEP 3: Create new record if none exists
        new_tool = ToolAuthorization(
            tenant_id=user_id,
            tool_type=tool_type,
            del_flag=False,
            created_at=datetime.utcnow()
        )
        db.session.add(new_tool)
        db.session.commit()

        return jsonify({
            "status": "success",
            "message": f"Tool type '{tool_type}' added successfully",
            "data": {
                "id": new_tool.id,
                "tool_type": new_tool.tool_type
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(e),
            "data": {}
        }), 500

@authTool_blueprint.route("/tool_type", methods=["GET"])
@jwt_required()
def get_tool_type():
    try:
        user_id = get_jwt_identity()
        tool = ToolAuthorization.query.filter_by(
            tenant_id=user_id,
            del_flag=False
        ).first()

        if not tool:
            return jsonify({
                "status": "success",
                "message": "Defaulting to local",
                "data": {"tool_type": "local"}
            }), 200

        return jsonify({
            "status": "success",
            "message": "Tool type fetched successfully",
            "data": {"tool_type": tool.tool_type}
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "data": {}}), 500
