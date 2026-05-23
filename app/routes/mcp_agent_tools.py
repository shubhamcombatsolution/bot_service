
# -----------------------------
from flask import Blueprint, request, jsonify
from app.models.mcp_tools import McpTools
from app.models.tool_authorization import ToolAuthorization
from app.models.mcp_agent_tools import McpAgentTools
from app.database.DatabaseOperationPostgreSQL import db_session
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy.exc import SQLAlchemyError
mcp_agents_blueprint = Blueprint("mcp_agent_tools", __name__, url_prefix="/mcp_agent_tools")

# -----------------------------
# Add a new MCP
# -----------------------------
@mcp_agents_blueprint.route("/", methods=["POST"])
@jwt_required()
def add_or_update_mcp_agent_tool():
    session = None
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        data = request.get_json()

        tool_name = data.get("tool_name")
        mcp_url = data.get("mcp_url")
        # agent_id = data.get("agent_id")
        agent_id = data.get("agent_id")

        # Normalize invalid agent IDs
        if not agent_id or str(agent_id).strip() in ["0", "", "null", "None"]:
            agent_id = None

        mcp_id = data.get("mcp_id")
        action_tools_description = data.get("action_tools_description")
        action_tools = data.get("action_tools", [])

        # Normalize to a list safely
        if action_tools is None:
            action_tools = []
        elif isinstance(action_tools, str):
            action_tools = [action_tools]  # wrap string in a list
        elif not isinstance(action_tools, list):
            action_tools = list(action_tools)  # only if it’s a tuple/set etc
            
        if action_tools_description is None:
            action_tools_description = []
        elif isinstance(action_tools_description, str):
            action_tools_description = [action_tools_description]
        elif not isinstance(action_tools_description, list):
            action_tools_description = list(action_tools_description)
            
        session = next(db_session())

        # -------------------------------
        # Check if tool already exists
        # -------------------------------
        existing_tool = session.query(McpAgentTools).filter_by(
            tenant_id=tenant_id,
            agent_id=agent_id,
            tool_name=tool_name  # ✅ Only filter by identity
        ).first()

        if existing_tool:
            # Merge action_tools without duplicates
            existing_tool.action_tools = list(set(existing_tool.action_tools or []) | set(action_tools))
            existing_tool.mcp_id = mcp_id
            existing_tool.mcp_url = mcp_url
            old_desc = existing_tool.action_tools_description or []
            new_desc = action_tools_description or []
            existing_tool.action_tools_description = list(
                set(old_desc) | set(new_desc)
            )
            session.commit()

            return jsonify({
                "status": "success",
                "message": "MCP Agent Tool updated successfully",
                "data": {
                    "id": existing_tool.id,
                    "tool_name": existing_tool.tool_name,
                    "action_tools": existing_tool.action_tools
                }
            })
        else:
            # Add new tool
            new_tool = McpAgentTools(
                tenant_id=tenant_id,
                mcp_id=mcp_id,
                agent_id=agent_id,
                tool_name=tool_name,
                mcp_url=mcp_url,
                action_tools_description=action_tools_description,
                action_tools=action_tools
            )
            session.add(new_tool)
            session.commit()

            return jsonify({
                "status": "success",
                "message": "MCP Agent Tool added successfully",
                "data": {
                    "id": new_tool.id,
                    "tool_name": new_tool.tool_name,
                    "action_tools": new_tool.action_tools
                }
            })

    except Exception as e:
        if session:
            session.rollback()
        return jsonify({
            "status": "error",
            "message": f"Failed to add/update MCP Agent Tool: {str(e)}"
        })
    finally:
        if session:
            session.close()

@mcp_agents_blueprint.route("/<int:agent_id>", methods=["GET"])
@jwt_required()
def get_mcp_agent_tools(agent_id):
    session = None
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return jsonify({
                "status": "error",
                "message": "Tenant ID not found in token"
            }), 401

        session = next(db_session())

        # Query all MCP tools for this agent
        tools = (
            session.query(McpAgentTools)
            .filter(
                McpAgentTools.tenant_id == tenant_id,
                McpAgentTools.agent_id == agent_id,
                McpAgentTools.del_flag == False
            )
            .order_by(McpAgentTools.id.desc())
            .all()
        )

        # If no records found
        if not tools:
            return jsonify({
                "status": "success",
                "message": "No MCP tools found for this agent",
                "data": []
            }), 200

        # Format tool data
        seen_tools = set()
        tools_data = []
        for t in tools:
            key = (t.tool_name or "").strip().lower()
            if key in seen_tools:
                continue
            seen_tools.add(key)
            tools_data.append({
                "id": t.id,
                "tool_name": t.tool_name,
                "mcp_id": t.mcp_id,
                "mcp_url": t.mcp_url,
                "description": t.action_tools_description,
                "action_tools": t.action_tools or []
            })

        return jsonify({
            "status": "success",
            "message": "MCP tools fetched successfully",
            "data": tools_data
        }), 200

    except SQLAlchemyError as e:
        if session:
            session.rollback()
        return jsonify({
            "status": "error",
            "message": f"Database error occurred: {str(e.__cause__)}"
        }), 500

    except Exception as e:
        if session:
            session.rollback()
        return jsonify({
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
        }), 500

    finally:
        if session:
            session.close()

@mcp_agents_blueprint.route("/<int:agent_id>", methods=["DELETE"])
@jwt_required()
def delete_action_tool(agent_id):
    session = None
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        data = request.get_json()
        tool_name = data.get("tool_name")

        if not tool_name:
            return jsonify({
                "status": "error",
                "message": "tool_name is required"
            }), 400

        session = next(db_session())

        # Find the tool record
        mcp_tool = session.query(McpAgentTools).filter_by(
            tenant_id=tenant_id,
            agent_id=agent_id,
            tool_name=tool_name
        ).first()

        if not mcp_tool:
            return jsonify({
                "status": "error",
                "message": "MCP Agent Tool not found"
            }), 404

        # Delete the tool row entirely
        session.delete(mcp_tool)
        session.commit()

        return jsonify({
            "status": "success",
            "message": f"MCP Agent Tool '{tool_name}' deleted successfully"
        })

    except Exception as e:
        if session:
            session.rollback()
        return jsonify({
            "status": "error",
            "message": f"Failed to delete MCP Agent Tool: {str(e)}"
        }), 500

    finally:
        if session:
            session.close()


# -----------------------------
# Delete an action tool from MCP Agent Tool
# -----------------------------
# @mcp_agents_blueprint.route("/<int:agent_id>/action-tool", methods=["DELETE"])
# @jwt_required()
# def delete_action_tool(agent_id):
#     session = None
#     try:
#         claims = get_jwt()
#         tenant_id = claims.get("tenant_id")
#         data = request.get_json()
#         tool_name = data.get("tool_name")
#         action_tool_to_remove = data.get("action_tool")

#         if not tool_name or not action_tool_to_remove:
#             return jsonify({
#                 "status": "error",
#                 "message": "tool_name and action_tool are required"
#             }), 400

#         session = next(db_session())

#         # Find the tool
#         mcp_tool = session.query(McpAgentTools).filter_by(
#             tenant_id=tenant_id,
#             agent_id=agent_id,
#             tool_name=tool_name
#         ).first()

#         if not mcp_tool:
#             return jsonify({
#                 "status": "error",
#                 "message": "MCP Agent Tool not found"
#             }), 404

#         # Remove the action tool if it exists
#         current_actions = mcp_tool.action_tools or []
#         if action_tool_to_remove not in current_actions:
#             return jsonify({
#                 "status": "error",
#                 "message": f"Action tool '{action_tool_to_remove}' not found in this MCP Agent Tool"
#             }), 404

#         current_actions.remove(action_tool_to_remove)
#         mcp_tool.action_tools = current_actions
#         session.commit()

#         return jsonify({
#             "status": "success",
#             "message": f"Action tool '{action_tool_to_remove}' removed successfully",
#             "data": {
#                 "id": mcp_tool.id,
#                 "tool_name": mcp_tool.tool_name,
#                 "action_tools": mcp_tool.action_tools
#             }
#         })

#     except Exception as e:
#         if session:
#             session.rollback()
#         return jsonify({
#             "status": "error",
#             "message": f"Failed to remove action tool: {str(e)}"
#         }), 500

#     finally:
#         if session:
#             session.close()
