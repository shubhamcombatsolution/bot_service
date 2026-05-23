from flask import Blueprint, request, jsonify
from app.models import BaseAgent
from flask_jwt_extended import jwt_required
from app.database.DatabaseOperationPostgreSQL import db_session

# Define Blueprint
base_agent_blueprint = Blueprint("base_agent", __name__)

@base_agent_blueprint.route("/decision-agent", methods=["GET", "PUT"])
@jwt_required()
def manage_decision_agent():
    session = next(db_session())
    try:
        # Fetch the Decision Agent
        decision_agent = session.query(BaseAgent).filter_by(agent_name="Decision Agent").first()
        if not decision_agent:
            return jsonify({"data": {}, "message": "Decision Agent not found", "status": "error"}), 404

        if request.method == "GET":
            agent_data = {
                "agent_id": decision_agent.agent_id,
                "agent_name": decision_agent.agent_name,
                "agent_description": decision_agent.agent_description,
                "agent_role": decision_agent.agent_role,
                "agent_instructions": decision_agent.agent_instructions,
                "Examples": decision_agent.Examples,
                "created_at": decision_agent.created_at.isoformat(),
                "updated_at": decision_agent.updated_at.isoformat(),
                "del_flg": decision_agent.del_flg
            }
            return jsonify({
                "data": agent_data,
                "message": "Decision Agent retrieved successfully",
                "status": "success"
            }), 200

        elif request.method == "PUT":
            data = request.get_json()

            # Update only the provided fields
            if "agent_description" in data:
                decision_agent.agent_description = data["agent_description"]
            if "agent_role" in data:
                decision_agent.agent_role = data["agent_role"]
            if "agent_instructions" in data:
                decision_agent.agent_instructions = data["agent_instructions"]
            if "Examples" in data:
                decision_agent.Examples = data["Examples"]

            session.commit()
            return jsonify({
                "data": {"agent_id": decision_agent.agent_id},
                "message": "Decision Agent updated successfully",
                "status": "success"
            }), 200

    except Exception as e:
        print("Error managing Decision Agent:", e)
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
    finally:
        session.close()

@base_agent_blueprint.route("/response-agent", methods=["GET", "PUT"])
@jwt_required()
def manage_response_agent():
    session = next(db_session())
    try:
        # Fetch the Response Agent
        response_agent = session.query(BaseAgent).filter_by(agent_name="Response Agent").first()
        if not response_agent:
            return jsonify({"data": {}, "message": "Response Agent not found", "status": "error"}), 404

        if request.method == "GET":
            agent_data = {
                "agent_id": response_agent.agent_id,
                "agent_name": response_agent.agent_name,
                "agent_description": response_agent.agent_description,
                "agent_role": response_agent.agent_role,
                "agent_instructions": response_agent.agent_instructions,
                "Examples": response_agent.Examples,
                "created_at": response_agent.created_at.isoformat(),
                "updated_at": response_agent.updated_at.isoformat(),
                "del_flg": response_agent.del_flg
            }
            return jsonify({
                "data": agent_data,
                "message": "Response Agent retrieved successfully",
                "status": "success"
            }), 200

        elif request.method == "PUT":
            data = request.get_json()

            # Update only the provided fields
            if "agent_description" in data:
                response_agent.agent_description = data["agent_description"]
            if "agent_role" in data:
                response_agent.agent_role = data["agent_role"]
            if "agent_instructions" in data:
                response_agent.agent_instructions = data["agent_instructions"]
            if "Examples" in data:
                response_agent.Examples = data["Examples"]

            session.commit()
            return jsonify({
                "data": {"agent_id": response_agent.agent_id},
                "message": "Response Agent updated successfully",
                "status": "success"
            }), 200

    except Exception as e:
        print("Error managing Response Agent:", e)
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
    finally:
        session.close()


@base_agent_blueprint.route("/greeting-agent", methods=["GET", "PUT"])
@jwt_required()
def manage_greeting_agent():
    session = next(db_session())
    try:
        greeting_agent = session.query(BaseAgent).filter_by(agent_name="Greeting Agent").first()
        if not greeting_agent:
            return jsonify({"data": {}, "message": "Greeting Agent not found", "status": "error"}), 404

        if request.method == "GET":
            agent_data = {
                "agent_id": greeting_agent.agent_id,
                "agent_name": greeting_agent.agent_name,
                "agent_description": greeting_agent.agent_description,
                "agent_role": greeting_agent.agent_role,
                "agent_instructions": greeting_agent.agent_instructions,
                "Examples": greeting_agent.Examples,
                "created_at": greeting_agent.created_at.isoformat(),
                "updated_at": greeting_agent.updated_at.isoformat(),
                "del_flg": greeting_agent.del_flg
            }
            return jsonify({
                "data": agent_data,
                "message": "Greeting Agent retrieved successfully",
                "status": "success"
            }), 200

        data = request.get_json() or {}
        if "agent_description" in data:
            greeting_agent.agent_description = data["agent_description"]
        if "agent_role" in data:
            greeting_agent.agent_role = data["agent_role"]
        if "agent_instructions" in data:
            greeting_agent.agent_instructions = data["agent_instructions"]
        if "Examples" in data:
            greeting_agent.Examples = data["Examples"]

        session.commit()
        return jsonify({
            "data": {"agent_id": greeting_agent.agent_id},
            "message": "Greeting Agent updated successfully",
            "status": "success"
        }), 200

    except Exception as e:
        print("Error managing Greeting Agent:", e)
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
    finally:
        session.close()
