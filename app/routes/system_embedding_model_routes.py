from flask import Blueprint, request, jsonify
from app.models.system_embedding_model import SystemEmbeddingModel
from app.database.DatabaseOperationPostgreSQL import db_session
import logging
from flask_jwt_extended import jwt_required

system_embedding_model_blueprint = Blueprint("system_embedding_model", __name__)

# Set up logger
logger = logging.getLogger(__name__)

@system_embedding_model_blueprint.route("/register", methods=["POST"])
# @jwt_required()
def register_or_update_system_embedding_model():
    """
    Adds or updates a system embedding model based on the provided ID or model name.
    """
    try:
        data = request.json
        embedding_id = data.get("embedding_id")  # Optional: ID for existing model
        model_name = data.get("model_name")
        api_key = data.get("api_key")
        chunk_size = data.get("chunk_size")
        chunk_overlap = data.get("chunk_overlap")

        # Validate required fields
        if not model_name or not api_key:
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Model name and API key are required"
            }), 400

        # Get session instance
        session = next(db_session())

        # Check for existing model by embedding_id (only if it is > 0)
        system_embedding_model = None
        if embedding_id and embedding_id > 0:
            system_embedding_model = session.query(SystemEmbeddingModel).filter_by(embedding_id=embedding_id).first()

        if system_embedding_model:
            # Update existing model
            system_embedding_model.api_key = api_key
            system_embedding_model.chunk_size = chunk_size
            system_embedding_model.chunk_overlap = chunk_overlap
            session.commit()
            message = "System embedding model updated successfully"
        else:
            # Insert new model
            system_embedding_model = SystemEmbeddingModel(
                model_name=model_name,
                api_key=api_key,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            session.add(system_embedding_model)
            session.commit()
            message = "System embedding model added successfully"

        return jsonify({
            "data": {
                "embedding_id": system_embedding_model.embedding_id,
                "model_name": system_embedding_model.model_name
            },
            "status": "success",
            "message": message
        }), 201 if message == "System embedding model added successfully" else 200

    except Exception as e:
        logger.exception(f"Error during register or update system embedding model: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500


@system_embedding_model_blueprint.route("/<int:embedding_id>", methods=["GET"])
# @jwt_required()
def get_system_embedding_model(embedding_id):
    """Fetches a specific system embedding model by ID."""
    try:
        session = next(db_session())
        system_embedding_model = session.query(SystemEmbeddingModel).get(embedding_id)

        if not system_embedding_model:
            return jsonify({
                "data": {},
                "status": "error",
                "message": "System embedding model not found"
            }), 404

        return jsonify({
            "data": {
                "embedding_id": system_embedding_model.embedding_id,
                "model_name": system_embedding_model.model_name,
                "chunk_size": system_embedding_model.chunk_size,
                "chunk_overlap": system_embedding_model.chunk_overlap,
                "created_at": system_embedding_model.created_at,
                "del_flg": system_embedding_model.del_flg
            },
            "status": "success",
            "message": "System embedding model fetched successfully"
        }), 200

    except Exception as e:
        logger.exception(f"Error during fetching system embedding model: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500


@system_embedding_model_blueprint.route("/", methods=["GET"])
@jwt_required()
def list_system_embedding_models():
    """Fetches all system embedding models."""
    try:
        session = next(db_session())
        system_embedding_models = session.query(SystemEmbeddingModel).all()

        return jsonify({
            "data": [
                {
                    "embedding_id": system_embedding_model.embedding_id,
                    "model_name": system_embedding_model.model_name
                } for system_embedding_model in system_embedding_models
            ],
            "status": "success",
            "message": "System embedding models fetched successfully"
        }), 200

    except Exception as e:
        logger.exception(f"Error during fetching system embedding models: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
