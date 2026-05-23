from flask import Blueprint, request, jsonify
from app.models import RelatedTools, Tools
from app.database.DatabaseOperationPostgreSQL import db_session

# Define Blueprint
related_tools_blueprint = Blueprint("related_tools", __name__)

# Create a new Related Tool relationship
@related_tools_blueprint.route("/register", methods=["POST"])
def create_related_tool():
    try:
        data = request.json
        required_fields = ["tool_id", "related_tool_id", "relationship_type"]

        if not all(field in data for field in required_fields):
            return jsonify({
                "data": {},
                "message": "Missing required fields: tool_id, related_tool_id, relationship_type",
                "status": "error"
            }), 400

        session = next(db_session())
        try:
            # Verify that tool_id and related_tool_id exist in tbl_tools
            tool = session.query(Tools).filter_by(tool_id=data["tool_id"]).first()
            related_tool = session.query(Tools).filter_by(tool_id=data["related_tool_id"]).first()
            if not tool or not related_tool:
                return jsonify({
                    "data": {},
                    "message": "Invalid tool_id or related_tool_id",
                    "status": "error"
                }), 404

            new_related_tool = RelatedTools(
                tool_id=data["tool_id"],
                related_tool_id=data["related_tool_id"],
                relationship_type=data["relationship_type"],
                del_flg=False
            )
            session.add(new_related_tool)
            session.commit()

            return jsonify({
                "data": {"id": new_related_tool.id},
                "message": "Related tool created successfully",
                "status": "success"
            }), 201
        except Exception as e:
            session.rollback()
            return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500

# Get a Related Tool by ID
@related_tools_blueprint.route("/<int:id>", methods=["GET"])
def get_related_tool_by_id(id):
    try:
        session = next(db_session())
        try:
            related_tools = session.query(RelatedTools).filter_by(tool_id=id).all()

            if not related_tools:
                return jsonify({
                    "data": [],
                    "status": "error",
                    "message": "No related tools found"
                }), 404

            data = [tool.relationship_type for tool in related_tools]
            # Prepare list of related tools data
            # data = []
            # for tool in related_tools:
            #     data.append({tool.relationship_type})
            #         # "id": tool.id,
            #         # "tool_id": tool.tool_id,
            #         # "related_tool_id": tool.related_tool_id,
            #         # "relationship_type": tool.relationship_type,
            #         # "created_at": tool.created_at.isoformat() if tool.created_at else None,
            #         # "updated_at": tool.updated_at.isoformat() if tool.updated_at else None,
            #         # "del_flg": tool.del_flg
            #     # })

            return jsonify({
                "data": data,
                "status": "success",
                "message": "Related tools retrieved successfully"
            }), 200

        except Exception as e:
            return jsonify({
                "data": [],
                "status": "error",
                "message": str(e)
            }), 500

        finally:
            session.close()

    except Exception as e:
        return jsonify({
            "data": [],
            "status": "error",
            "message": str(e)
        }), 500


# Get all Related Tools for a specific tool_id
@related_tools_blueprint.route("/tool/<int:tool_id>", methods=["GET"])
def get_related_tools_by_tool_id(tool_id):
    try:
        session = next(db_session())
        try:
            # Verify that tool_id exists
            tool = session.query(Tools).filter_by(tool_id=tool_id).first()
            if not tool:
                return jsonify({"data": {}, "status": "error", "message": "Tool not found"}), 404

            related_tools = session.query(RelatedTools).filter_by(tool_id=tool_id, del_flg=False).all()
            related_tools_list = [
                {
                    "id": rt.id,
                    "tool_id": rt.tool_id,
                    "related_tool_id": rt.related_tool_id,
                    "relationship_type": rt.relationship_type,
                    "created_at": rt.created_at.isoformat(),
                    "updated_at": rt.updated_at.isoformat(),
                    "del_flg": rt.del_flg
                }
                for rt in related_tools
            ]

            return jsonify({
                "data": related_tools_list,
                "status": "success",
                "message": "Related tools retrieved successfully"
            }), 200
        except Exception as e:
            return jsonify({"data": {}, "status": "error", "message": str(e)}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"data": {}, "status": "error", "message": str(e)}), 500

# Update a Related Tool relationship
@related_tools_blueprint.route("/update/<int:id>", methods=["PUT"])
def update_related_tool(id):
    try:
        data = request.json
        session = next(db_session())
        try:
            related_tool = session.query(RelatedTools).filter_by(id=id).first()
            if not related_tool:
                return jsonify({"data": {}, "message": "Related tool not found", "status": "error"}), 404

            if "tool_id" in data:
                tool = session.query(Tools).filter_by(tool_id=data["tool_id"]).first()
                if not tool:
                    return jsonify({"data": {}, "message": "Invalid tool_id", "status": "error"}), 404
                related_tool.tool_id = data["tool_id"]
            if "related_tool_id" in data:
                related_tool_check = session.query(Tools).filter_by(tool_id=data["related_tool_id"]).first()
                if not related_tool_check:
                    return jsonify({"data": {}, "message": "Invalid related_tool_id", "status": "error"}), 404
                related_tool.related_tool_id = data["related_tool_id"]
            if "relationship_type" in data:
                related_tool.relationship_type = data["relationship_type"]
            if "del_flg" in data:
                related_tool.del_flg = data["del_flg"]

            session.commit()
            return jsonify({
                "data": {"id": related_tool.id},
                "message": "Related tool updated successfully",
                "status": "success"
            }), 200
        except Exception as e:
            session.rollback()
            return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500

# Delete a Related Tool relationship
@related_tools_blueprint.route("/delete/<int:id>", methods=["DELETE"])
def delete_related_tool(id):
    try:
        session = next(db_session())
        try:
            related_tool = session.query(RelatedTools).filter_by(id=id).first()
            if not related_tool:
                return jsonify({"data": {}, "message": "Related tool not found", "status": "error"}), 404

            session.delete(related_tool)
            session.commit()
            return jsonify({"message": "Related tool deleted successfully", "status": "success"}), 200
        except Exception as e:
            session.rollback()
            return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
