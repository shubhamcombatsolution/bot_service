from flask import Blueprint, request, jsonify
from app.models.basellm import BaseLLM
from app.database.DatabaseOperationPostgreSQL import db_session
import logging
from flask_jwt_extended import jwt_required

base_llm_blueprint = Blueprint("basellm", __name__)

# Set up logger
logger = logging.getLogger(__name__)

# LLM Registration (Create New LLM)
@base_llm_blueprint.route("/register", methods=["POST"])
def create_basellm():
    try:
        data = request.json
        required_fields = ["base_provider", "base_model_name", "base_model_type"]

        # Check for required fields
        if not all(field in data for field in required_fields):
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Missing required fields"
            }), 400

        session = next(db_session())
        try:
            # Create a new LLM entry
            new_basellm = BaseLLM(
                base_provider=data["base_provider"],
                base_model_name=data["base_model_name"],
                base_model_type=data["base_model_type"]
            )
            session.add(new_basellm)
            session.commit()

            return jsonify({
                "data": {
                    "base_llm_id": new_basellm.base_llm_id
                },
                "status": "success",
                "message": "BaseLLM registered successfully"
            }), 201
        except Exception as e:
            session.rollback()
            logger.exception(f"Error during BaseLLM creation: {str(e)}")
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


# Get All BaseLLMs (excluding soft deleted ones)
@base_llm_blueprint.route("/", methods=["GET"])
def get_all_basellms():
    try:
        session = next(db_session())
        try:
            basellms = session.query(BaseLLM).filter_by(del_flg=False).all()
            basellm_list = [
                {
                    "base_llm_id": b.base_llm_id,
                    "base_provider": b.base_provider,
                    "base_model_name": b.base_model_name,
                    "base_model_type": b.base_model_type,
                    "created_at": b.created_at.isoformat()
                }
                for b in basellms
            ]

            return jsonify({
                "data": basellm_list,
                "status": "success",
                "message": "BaseLLMs fetched successfully"
            }), 200
        except Exception as e:
            logger.exception(f"Error fetching BaseLLMs: {str(e)}")
            return jsonify({
                "data": [],
                "status": "error",
                "message": "Internal server error"
            }), 500
        finally:
            session.close()
    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        return jsonify({
            "data": [],
            "status": "error",
            "message": "Internal server error"
        }), 500 