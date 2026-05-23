from flask import Blueprint, request, jsonify
from app.models import SystemLLM
from app.database.DatabaseOperationPostgreSQL import db_session
import logging
from flask_jwt_extended import create_access_token, jwt_required, unset_jwt_cookies

system_llm_blueprint = Blueprint("system_llm", __name__)

# Set up logger
logger = logging.getLogger(__name__)

# SystemLLM Registration (Create New SystemLLM)
@system_llm_blueprint.route("/register", methods=["POST"])
def create_system_llm():
    try:
        data = request.json
        required_fields = ["provider", "model_name", "api_key_temp"]

        # Check for required fields
        if not all(field in data for field in required_fields):
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Missing required fields"
            }), 400

        session = next(db_session())

        try:
            # Create a new SystemLLM entry without checking for existing SystemLLM
            new_system_llm = SystemLLM(
                provider=data["provider"],
                model_name=data["model_name"],
                api_key_temp=data["api_key_temp"],
                max_output_tokens=data.get("max_output_tokens", 1024)
            )
            session.add(new_system_llm)
            session.commit()

            return jsonify({
                "data": {
                    "llm_id": new_system_llm.llm_id
                },
                "status": "success",
                "message": "SystemLLM registered successfully"
            }), 201
        except Exception as e:
            session.rollback()
            logger.exception(f"Error during SystemLLM creation: {str(e)}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Internal server error"
            }), 500
        finally:
            session.close()

    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500

# SystemLLM Update
@system_llm_blueprint.route("/update/<int:llm_id>", methods=["PUT"])
def update_system_llm(llm_id):
    try:
        data = request.json
        required_fields = ["provider", "model_name", "api_key_temp"]

        # Check for required fields
        if not all(field in data for field in required_fields):
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Missing required fields"
            }), 400

        session = next(db_session())

        try:
            # Check if SystemLLM with the given provider and model_name exists
            existing_system_llm = session.query(SystemLLM).filter_by(llm_id=llm_id, provider=data["provider"], model_name=data["model_name"]).first()
            if not existing_system_llm:
                return jsonify({
                    "data": {},
                    "status": "error",
                    "message": "SystemLLM not found"
                }), 404

            # Update the SystemLLM details
            existing_system_llm.api_key_temp = data["api_key_temp"]
            existing_system_llm.max_output_tokens = data.get("max_output_tokens", existing_system_llm.max_output_tokens)
            session.commit()

            return jsonify({
                "data": {
                    "llm_id": existing_system_llm.llm_id
                },
                "status": "success",
                "message": "SystemLLM information updated successfully"
            }), 200
        except Exception as e:
            session.rollback()
            logger.exception(f"Error during SystemLLM update: {str(e)}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Internal server error"
            }), 500
        finally:
            session.close()

    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500

# Get SystemLLM by ID
@system_llm_blueprint.route("/<int:llm_id>", methods=["GET"])
# @jwt_required()
def get_system_llm_by_id(llm_id):
    try:
        session = next(db_session())

        try:
            system_llm = session.query(SystemLLM).filter_by(llm_id=llm_id).first()
            if not system_llm:
                return jsonify({
                    "data": {},
                    "status": "error",
                    "message": "SystemLLM not found"
                }), 404

            return jsonify({
                "data": {
                    "llm_id": system_llm.llm_id,
                    "provider": system_llm.provider,
                    "model_name": system_llm.model_name,
                    "api_key_temp": system_llm.api_key_temp,
                    "max_output_tokens": system_llm.max_output_tokens
                },
                "status": "success",
                "message": "SystemLLM retrieved successfully"
            }), 200
        except Exception as e:
            logger.exception(f"Error fetching SystemLLM by ID: {str(e)}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Internal server error"
            }), 500
        finally:
            session.close()

    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500

# Get All SystemLLMs
@system_llm_blueprint.route("/", methods=["GET"])
# @jwt_required()
def list_system_llms():
    try:
        session = next(db_session())

        try:
            system_llms = session.query(SystemLLM).all()
            system_llm_list = [{
                "llm_id": system_llm.llm_id,
                "provider": system_llm.provider,
                "model_name": system_llm.model_name,
                "api_key_temp": system_llm.api_key_temp,
                "max_output_tokens": system_llm.max_output_tokens
            } for system_llm in system_llms]
        
            return jsonify({
                "data": system_llm_list,
                "status": "success",
                "message": "All SystemLLMs retrieved successfully"
            }), 200
        except Exception as e:
            logger.exception(f"Error fetching all SystemLLMs: {str(e)}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Internal server error"
            }), 500
        finally:
            session.close()

    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
