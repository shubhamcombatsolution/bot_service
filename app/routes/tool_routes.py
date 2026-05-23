from flask import Blueprint, request, jsonify
from app.models import Tools ,McpTool
from app.database.DatabaseOperationPostgreSQL import db_session
import base64
import os
# Define Blueprint
tools_blueprint = Blueprint("tools", __name__)

# Create a new Tool
@tools_blueprint.route("/register", methods=["POST"])
def create_tool():
    try:
        data = request.json
        required_fields = ["tool_name", "tool_description"]

        if not all(field in data for field in required_fields):
            return jsonify({
                "data": {},
                "message": "Missing required fields",
                "status": "error"
            }), 400

        session = next(db_session())
        try:
            new_tool = Tools(
                tool_name=data["tool_name"],
                tool_description=data["tool_description"],
                tool_logo=data.get("tool_logo", None)
            )
            session.add(new_tool)
            session.commit()

            return jsonify({
                "data": {"tool_id": new_tool.tool_id},
                "message": "Tool created successfully",
                "status": "success"
            }), 201
        except Exception as e:
            session.rollback()
            return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500

# Update an existing Tool
@tools_blueprint.route("/update/<int:tool_id>", methods=["PUT"])
def update_tool(tool_id):
    try:
        data = request.json
        session = next(db_session())
        try:
            tool = session.query(Tools).filter_by(tool_id=tool_id).first()
            if not tool:
                return jsonify({"data": {}, "message": "Tool not found", "status": "error"}), 404

            if "tool_name" in data:
                tool.tool_name = data["tool_name"]
            if "tool_description" in data:
                tool.tool_description = data["tool_description"]
            if "tool_logo" in data:
                tool.tool_logo = data["tool_logo"]
            if "del_flg" in data:
                tool.del_flg = data["del_flg"]

            session.commit()
            return jsonify({"data": {"tool_id": tool.tool_id}, "message": "Tool updated successfully", "status": "success"}), 200
        except Exception as e:
            session.rollback()
            return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500

@tools_blueprint.route("/save_tool_type", methods=["POST"])
def save_tool_type():
    try:
        data = request.get_json()
        tool_type = data.get("tool_type")

        if tool_type not in ["local", "mcp"]:
            return jsonify({
                "status": "error",
                "message": "Invalid tool_type. Must be 'local' or 'mcp'.",
                "data": {}
            }), 400

        session = next(db_session())

        # Fetch the latest tool record (or create a new one if none exists)
        tool = session.query(Tools).order_by(Tools.tool_id.desc()).first()

        if tool:
            tool.tool_type = tool_type
            message = "Tool type updated successfully"
        else:
            tool = Tools(
                tool_name="Default Tool",
                tool_description="Auto-created record for tool type selection",
                tool_type=tool_type
            )
            session.add(tool)
            message = "Tool type created successfully"

        session.commit()

        return jsonify({
            "status": "success",
            "message": message,
            "data": {"tool_type": tool_type}
        }), 200

    except Exception as e:
        if "session" in locals():
            session.rollback()
        return jsonify({
            "status": "error",
            "message": str(e),
            "data": {}
        }), 500
    finally:
        if "session" in locals():
            session.close()
# Get a Tool by ID
@tools_blueprint.route("/<int:tool_id>", methods=["GET"])
def get_tool_by_id(tool_id):
    try:
        session = next(db_session())
        try:
            tool = session.query(Tools).filter_by(tool_id=tool_id).first()
            if not tool:
                return jsonify({"data": {}, "status": "error", "message": "Tool not found"}), 404

            return jsonify({
                "data": {
                    "tool_id": tool.tool_id,
                    "tool_name": tool.tool_name,
                    "tool_description": tool.tool_description,
                    "tool_logo": tool.tool_logo,
                    "created_at": tool.created_at.isoformat(),
                    "updated_at": tool.updated_at.isoformat()
                },
                "status": "success",
                "message": "Tool retrieved successfully"
            }), 200
        except Exception as e:
            return jsonify({"data": {}, "status": "error", "message": str(e)}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"data": {}, "status": "error", "message": str(e)}), 500

# Get all Tools
@tools_blueprint.route("/", methods=["GET"])
def get_all_tools():
    try:
        session = next(db_session())
        try:
            tools = session.query(Tools).order_by(Tools.tool_id.asc()).all()
            tools_list = []
            for tool in tools:
                tool_path = tool.tool_logo
                try:
                    with open(tool_path, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                    tool_logo = f"data:image/jpeg;base64,{encoded_string}"
                except Exception as e:
                    tool_logo = ""

                tools_list.append({
                    "tool_id": tool.tool_id,
                    "tool_name": tool.tool_name,
                    "tool_description": tool.tool_description,
                    "tool_logo": tool.tool_logo,  # Send base64 instead of path
                    "created_at": tool.created_at.isoformat(),
                    "updated_at": tool.updated_at.isoformat()
                })

            return jsonify({"data": tools_list, "status": "success", "message": "All tools retrieved successfully"}), 200
        except Exception as e:
            return jsonify({"data": {}, "status": "error", "message": str(e)}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"data": {}, "status": "error", "message": str(e)}), 500


# Delete a Tool
@tools_blueprint.route("/delete/<int:tool_id>", methods=["DELETE"])
def delete_tool(tool_id):
    try:
        session = next(db_session())
        try:
            tool = session.query(Tools).filter_by(tool_id=tool_id).first()
            if not tool:
                return jsonify({"data": {}, "message": "Tool not found", "status": "error"}), 404

            session.delete(tool)
            session.commit()
            return jsonify({"message": "Tool deleted successfully", "status": "success"}), 200
        except Exception as e:
            session.rollback()
            return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500

@tools_blueprint.route("/mcptools", methods=["GET"])
def get_all_mcp_tools():
    try:
        session = next(db_session())
        try:
            tools = session.query(McpTool).order_by(McpTool.tool_id.asc()).all()
            tools_list = []

            for tool in tools:
                if (tool.tool_name or "").strip().lower() in {"whatsapp", "slack"}:
                    continue

                tool_path = tool.tool_logo
                tool_logo = ""

                # ✅ Convert logo file to base64 if path exists
                if tool_path and os.path.exists(tool_path):
                    try:
                        with open(tool_path, "rb") as image_file:
                            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
                            tool_logo = f"data:image/jpeg;base64,{encoded_string}"
                    except Exception:
                        tool_logo = ""

                tools_list.append({
                    "tool_id": tool.tool_id,
                    "tool_name": tool.tool_name,
                    "tool_description": tool.tool_description,
                    "tool_logo": tool.tool_logo,  # ✅ Send base64-encoded image
                    "created_at": tool.created_at.isoformat() if tool.created_at else None,
                    "updated_at": tool.updated_at.isoformat() if tool.updated_at else None
                })

            return jsonify({
                "data": tools_list,
                "status": "success",
                "message": "All MCP tools retrieved successfully"
            }), 200

        except Exception as e:
            session.rollback()
            return jsonify({
                "data": {},
                "status": "error",
                "message": str(e)
            }), 500

        finally:
            session.close()

    except Exception as e:
        return jsonify({
            "data": {},
            "status": "error",
            "message": str(e)
        }), 500
