from flask import Blueprint, request, jsonify
from app.database.DatabaseOperationPostgreSQL import db_session
from app.models import ChatHistory
from sqlalchemy.exc import SQLAlchemyError
import logging
from datetime import datetime

# Define Blueprint
chat_history_blueprint = Blueprint("chat-history", __name__)

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@chat_history_blueprint.route('/<bot_id>', methods=['GET', 'OPTIONS'])
def get_chat_history(bot_id):
    """Fetch chat history for a given bot_id."""

    try:
        session = next(db_session())
        try:
            # Query chat history for the given bot_id
            history = session.query(ChatHistory).filter_by(bot_id=bot_id).order_by(ChatHistory.created_at.asc()).all()
            history_data = [
                {
                    'query': entry.query,
                    'response': entry.response,
                    'created_at': entry.created_at.isoformat(),
                    'tenant_id': entry.tenant_id,
                    'bot_id': entry.bot_id
                }
                for entry in history
            ]
            return jsonify({'history': history_data}), 200
        finally:
            session.close()
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching chat history for bot_id {bot_id}: {e}")
        return jsonify({'error': 'Database error occurred'}), 500
    except Exception as e:
        logger.error(f"Error fetching chat history for bot_id {bot_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

