import os
import re
from flask import Flask, redirect, request, session, url_for,jsonify
from flask_jwt_extended import JWTManager,get_jwt_identity,jwt_required,get_jwt
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import timedelta
from flask import Flask, send_from_directory
import logging
from flask_cors import CORS
from app.middleware.api_key_auth import init_api_key_middleware
from app.models import db, LoginUser, Role, Tenant, BotPlan,tenant_payment_info, TenantSubscription, Error, SuperAdmin, CustomBot, EmbeddingModel, LLM, KnowledgeBase, SystemEmbeddingModel, SystemLLM, BaseAgent
import razorpay
from google_auth_oauthlib.flow import Flow
import google.auth.transport.requests
# Import centralized API blueprint factory that contains all routes
from app.routes import api_blueprint
# Load environment variables from .env file
load_dotenv()
# Create Flask app
app = Flask(__name__)
print(f"App root path: {app.root_path}")
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

#import os
#os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', 'postgresql+psycopg2://postgres:123@127.0.0.1:5432/db_botbuilder')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
import json
# JWT configurations
jwt_secret = os.getenv("JWT_SECRET_KEY")
if not jwt_secret:
    raise ValueError("JWT_SECRET_KEY is not set. Please check your environment variables.")
app.config["JWT_SECRET_KEY"] = jwt_secret
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=15)
app.config["JWT_TOKEN_LOCATION"] = ["headers"]
app.config["JWT_HEADER_NAME"] = "Authorization"
app.config["JWT_HEADER_TYPE"] = "Bearer"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=1)
app.config['MAX_CONTENT_LENGTH'] = None
# Base URL for generating asset URLs (avatars, backgrounds, etc.)
app.config['BASE_URL'] = os.getenv('BASE_URL', 'https://api.jnanic.com')
# Only set SERVER_NAME in production - comment out for local/Docker development
# app.config['SERVER_NAME'] = 'jnanic.com'  # Base domain
app.config.update(
    SESSION_COOKIE_SECURE=os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true',  # Only True for HTTPS
    SESSION_COOKIE_SAMESITE='Lax'
)

# Ensure critical settings are present
secret_key = os.getenv("SECRET_KEY")
if not secret_key:
    raise ValueError("SECRET_KEY is not set. Please check your environment variables.")
app.secret_key = secret_key

# Initialize extensions
db.init_app(app)
jwt = JWTManager(app)  # Initialize JWTManager here
# to migrate the changes give the command  first - set FLASK_APP=run.py
migrate = Migrate(app, db)

# Initialize API key middleware
init_api_key_middleware(app)

# CORS configuration
allowed_origins = [
    "http://localhost",
    "http://localhost:80",
    "http://localhost:5173",
    "http://127.0.0.1",
    "http://127.0.0.1:5173",
    "http://192.168.1.13:5173",
    "http://192.168.1.32:5173",
    "http://localhost:3030",
    "http://localhost:3001",
    "http://localhost:3000",
    "http://localhost:3031",
    "https://jnanic.com",
    "https://www.jnanic.com",
    "https://home.jnanic.com",
    "https://rfq.jnanic.com",
    re.compile(r"^https://([a-z0-9-]+\.)?jnanic\.com$"),
]

CORS(app, resources={
    r"/custom-bot/*": {"origins": "*"},
    r"/custom_bot_new/*": {"origins": "*"},
    r"/chat-history/*": {"origins": "*"},
    r"/multi_agents/*": {"origins": "*"},
    r"/*": {
        "origins": allowed_origins,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        "allow_headers": [
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-Tenant-Id",
            "tenant_id",
            "X-API-Key",
            "x-api-key",
        ],
        "expose_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True,
    }
})

# Register centralized API blueprint (contains all routes)
app.register_blueprint(api_blueprint)
# Configure file upload settings
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'uploads/')
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables for host and port
HOST = os.getenv("FLASK_HOST", "0.0.0.0")
PORT = int(os.getenv("FLASK_PORT", "5000"))
DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ["true", "1", "t"]

# Path to your client_secret.json
CLIENT_SECRETS_FILE = os.getenv("GOOGLE_CLIENT_SECRET_FILE", "client_secret.json")
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# Health check endpoint for Docker
@app.route("/health")
def health_check():
    return {"status": "healthy"}


# Home page
@app.route("/")
def index():
    return '<a href="/authorize">Login with Google</a>'

# Step 1: Redirect user to Google OAuth
@app.route("/authorize")
def authorize():
    oauth_redirect_uri = os.getenv('OAUTH_REDIRECT_URI', 'https://jnanic.com/Admin/Tools')
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=oauth_redirect_uri
    )

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true"
    )
    session["state"] = state
    print("Redirecting to:", authorization_url)
    return redirect(authorization_url)

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

@app.route("/oauth2callback")
def oauth2callback():
    state = session.get("state")
    if not state:
        return "State missing from session", 400

    oauth_callback_uri = os.getenv('OAUTH_CALLBACK_URI', 'https://api.jnanic.com/oauth2callback')
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=oauth_callback_uri
    )

    # Exchange the authorization code for tokens
    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials

    # Save credentials (in session or database)
    session["credentials"] = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes
    }

    return "Google OAuth successful! Tokens saved."

# Step 3: Access Google Calendar
@app.route("/calendar")
def calendar_events():
    if "credentials" not in session:
        return redirect(url_for("authorize"))

    creds = Credentials(**session["credentials"])
    service = build("calendar", "v3", credentials=creds)

    # Get next 10 events
    events_result = service.events().list(calendarId="primary", maxResults=10).execute()
    events = events_result.get("items", [])

    events_list = "<h1>Upcoming Events:</h1>"
    if not events:
        events_list += "<p>No upcoming events found.</p>"
    else:
        for event in events:
            events_list += f"<p>{event['summary']} - {event.get('start', {}).get('dateTime', event.get('start', {}).get('date'))}</p>"

    return events_list
    
# @app.route('/')
# def index():
#     return "Welcome to the Flask App!"

@app.after_request
def add_coop_coep_headers(response):
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin-allow-popups'
    response.headers['Cross-Origin-Embedder-Policy'] = 'unsafe-none'
    return response
    
# Dashboard routes for the examples
@app.route('/teams/query')
def get_teams():
    return {"message": "Teams data"}

@app.route('/sales/index')
def get_sales():
    return {"message": "Sales data"}

# Serve static media files
@app.route('/media/<path:filename>')
def serve_media(filename):
    return send_from_directory('knowledge_bases', filename)
    
# Add a new route to receive webhook requests
@app.route("/webhook/receive", methods=["POST"])
def receive_webhook():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400

        # Log the received webhook data
        print(f"Received webhook data: {data}")

        # Process the webhook data (e.g., the agent's response)
        response = data.get("response", "No response provided")
        print(f"Agent response: {response}")

        # Return a success response
        return jsonify({"status": "received", "message": "Webhook received successfully"}), 200

    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
        
# from werkzeug.middleware.dispatcher import DispatcherMiddleware
# from fastapi.middleware.wsgi import WSGIMiddleware
# from plan_langgraph import fastapi_app
# from werkzeug.serving import run_simple

# app = DispatcherMiddleware(app, {
#     '/agent': WSGIMiddleware(fastapi_app)
# })
    
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        logger.info("All tables created successfully (if they did not already exist).")
    
    logger.info(f"Starting Flask app on {HOST}:{PORT} with debug={DEBUG}")
    app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False)

# if __name__ == "__main__":
#     run_simple(HOST, PORT, app, use_reloader=True, use_debugger=True)
