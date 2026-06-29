from flask import Flask
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv
from datetime import timedelta
import os
import re
from flask_cors import CORS

# Load environment variables
load_dotenv()

def create_app():
    """
    Factory function to create and configure the Flask app.
    """
    # Initialize the Flask app
    app = Flask(__name__)

    # Environment-specific configurations
    from app.config import get_config
    app.config.from_object(get_config())

    

    jwt_secret = os.getenv("JWT_SECRET_KEY")
    if not jwt_secret:
        raise RuntimeError("JWT_SECRET_KEY not set")

    app.config["JWT_SECRET_KEY"] = jwt_secret

    # Flask secret
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY is required")

    app.config["SECRET_KEY"] = secret_key

    
    # CORS configuration
    allowed_origins = [
        "http://localhost:5173",
        "http://13.200.211.217:5173",
        "https://jnanic.com",
        "https://www.jnanic.com",
        re.compile(r"^https://([a-z0-9-]+\.)?jnanic\.com$"),
    ]
    CORS(
        app,
        resources={
            r"/static/js/LaunchBot.js": {
                "origins": "*",  # Allow all origins for the chatbot widget
                "allow_headers": ["Content-Type", "X-API-Key", "x-api-key"],
                "supports_credentials": False,
            },
            r"/*": {
                "origins": allowed_origins,
                "allow_headers": [
                    "Content-Type",
                    "Authorization",
                    "X-Requested-With",
                    "X-Tenant-Id",
                    "tenant_id",
                    "X-API-Key",
                    "x-api-key",
                ],
                "supports_credentials": True,
            }
        },
    )

    # Import and register the centralized API blueprint
    from app.routes import api_blueprint
    app.register_blueprint(api_blueprint)

    return app
