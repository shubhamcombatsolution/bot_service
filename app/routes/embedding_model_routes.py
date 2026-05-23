from flask import Blueprint, request, jsonify
from app.models.embedding_model import EmbeddingModel
from app.database.DatabaseOperationPostgreSQL import db_session
import logging
from flask_jwt_extended import create_access_token, jwt_required, unset_jwt_cookies
embedding_model_blueprint = Blueprint("embedding_model", __name__)

# Set up logger
logger = logging.getLogger(__name__)

 

@embedding_model_blueprint.route("/register", methods=["POST"])
# @jwt_required()
def register_or_update_embedding_model():
    """
    Adds or updates an embedding model based on the provided ID or model name.
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
        embedding_model = None
        if embedding_id and embedding_id > 0:
            embedding_model = session.query(EmbeddingModel).filter_by(embedding_id=embedding_id).first()

       

        if embedding_model:
            # Update existing model
            embedding_model.api_key = api_key
            embedding_model.chunk_size = chunk_size
            embedding_model.chunk_overlap = chunk_overlap
            session.commit()
            message = "Embedding model updated successfully"
        else:
            # Insert new model
            embedding_model = EmbeddingModel(
                model_name=model_name,
                api_key=api_key,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            session.add(embedding_model)
            session.commit()
            message = "Embedding model added successfully"

        return jsonify({
            "data": {
                "embedding_id": embedding_model.embedding_id,
                "model_name": embedding_model.model_name
            },
            "status": "success",
            "message": message
        }), 201 if message == "Embedding model added successfully" else 200

    except Exception as e:
        logger.exception(f"Error during register or update embedding model: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500


@embedding_model_blueprint.route("/<int:embedding_id>", methods=["GET"])
# @jwt_required()
def get_embedding_model(embedding_id):
    """Fetches a specific embedding model by ID."""
    try:
        session = next(db_session())
        embedding_model = session.query(EmbeddingModel).get(embedding_id)

        if not embedding_model:
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Embedding model not found"
            }), 404

        return jsonify({
            "data": {
                "embedding_id": embedding_model.embedding_id,
                "model_name": embedding_model.model_name,
                "chunk_size": embedding_model.chunk_size,
                "chunk_overlap": embedding_model.chunk_overlap
            },
            "status": "success",
            "message": "Embedding model fetched successfully"
        }), 200

    except Exception as e:
        logger.exception(f"Error during fetching embedding model: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500

 
@embedding_model_blueprint.route("/", methods=["GET"])
# @jwt_required()
def list_embedding_models():
    """Fetches all embedding models."""
    try:
        print("asdf")
        session = next(db_session())
        embedding_models = session.query(EmbeddingModel).all()

        return jsonify({
            "data": [
                {
                    "embedding_id": embedding_model.embedding_id,
                    "model_name": embedding_model.model_name
                } for embedding_model in embedding_models
            ],
            "status": "success",
            "message": "Embedding models fetched successfully"
        }), 200

    except Exception as e:
        logger.exception(f"Error during fetching embedding models: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
