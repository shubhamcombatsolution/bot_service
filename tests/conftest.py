"""
Test configuration and fixtures for bb_service.

Uses an in-memory SQLite database so no real PostgreSQL connection is needed.
"""

import os
import sys
import json
import unittest
from unittest.mock import MagicMock, patch

# Set environment before any app imports
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-testing-only")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
os.environ.setdefault("LLM_ENCRYPTION_KEY", "vX3Kx5q7vT3TQqgq2YQ0nO1E7iH2F7k6Hn5s3aQbYq8=")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

# Add bb_service root to path
sys.path.insert(0, "/root/botBuilder/bb_master/bb_service")


def make_test_app():
    """Create a minimal Flask test app with SQLite in-memory DB."""
    with patch("spacy.load", return_value=MagicMock()), \
         patch("qdrant_client.QdrantClient", return_value=MagicMock()):

        from flask import Flask
        from flask_jwt_extended import JWTManager
        from flask_cors import CORS

        app = Flask(__name__)
        app.config["TESTING"] = True
        app.config["DEBUG"] = True
        app.config["JWT_SECRET_KEY"] = os.environ["JWT_SECRET_KEY"]
        app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

        from app.models import db
        db.init_app(app)

        JWTManager(app)
        CORS(app)

        return app, db


def get_jwt_token(app, role="user", tenant_id=1):
    """Generate a JWT token with given claims for testing."""
    from flask_jwt_extended import create_access_token
    with app.app_context():
        token = create_access_token(
            identity=str(tenant_id),
            additional_claims={
                "role": role,
                "tenant_id": tenant_id,
                "user_id": 1,
            }
        )
    return token
