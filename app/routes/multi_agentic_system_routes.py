
from flask import Blueprint, request, jsonify, redirect, session, current_app
from datetime import datetime,timedelta
import os
from app.models import CustomBot,KnowledgeBase
from app.models import ToolAuthorization
from app.models.mcp_tools import McpTools
from app.utils import update_remaining_messages
from Tools.CalendarTool import CalendarTool
from Tools.GSheetsTool import GSheetsTool
from Tools.HubspotTool import HubSpotTool
from Tools.CommuteTimeTool import CommuteTimeTool
from Tools.NearbyFacilitiesTool import NearbyFacilitiesTool
from Tools.FinanceTool import FinanceTool
from Tools.TavilyRentalIncomeTool import TavilyRentalIncomeTool
from MultiAgentSystem import MultiAgentSystem
from app.routes.custom_bot_routes import require_valid_token
from app.database.DatabaseOperationPostgreSQL import db_session
from Tools.GmailTool import GmailTool
import time
import requests
import json
import threading
from app.utils import update_remaining_messages
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, decode_token
import random
import jwt
from qdrant_client import QdrantClient
_agent_cache: dict = {}
_agent_cache_lock = threading.Lock()
MAX_AGENT_SYSTEMS = int(os.getenv("MAX_AGENT_SYSTEMS", "50"))
AGENT_CACHE_TTL_SECS = int(os.getenv("AGENT_CACHE_TTL_SECS", "600"))

# AGENT_CACHE_TTL_SECS = 10 # 1 minute for testing

# Initialize tools globally (you can also do this per request if needed)
# calendar_tool = CalendarTool(auth_mode='manual')
from langchain_openai import ChatOpenAI
from flask_cors import cross_origin
from logging_config import setup_logging
from app.routes.helpers.tool_utils import get_enabled_tools_for_tenant
from app.routes.helpers.custom_bot_utils import resolve_bot_config
from app.models.custombot_access_restriction import CustomBotAccessRestriction

logger = setup_logging("multi-agent-system-routes", level="DEBUG")

def _normalize_chatbot_domain(value):
    if not value:
        return None
    value = str(value).strip().lower()
    value = value.replace("https://", "").replace("http://", "")
    value = value.split("/")[0].split(":")[0]
    return value[4:] if value.startswith("www.") else value


def _safe_load_json(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _extract_oauth_context(state_value, mcp_name="", tool_name=""):
    """
    Resolve MCP OAuth context from direct params and state JSON fallback.
    """
    resolved_mcp = (mcp_name or "").strip()
    resolved_tool = (tool_name or "").strip()
    state_payload = _safe_load_json(state_value)

    if not resolved_mcp:
        resolved_mcp = str(
            state_payload.get("mcp_name")
            or state_payload.get("mcpName")
            or ""
        ).strip()
    if not resolved_tool:
        resolved_tool = str(
            state_payload.get("tool_name")
            or state_payload.get("toolName")
            or ""
        ).strip()

    return resolved_mcp, resolved_tool


# Initialize OpenAI LLM (using env vars)
decision_llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    temperature=0.0,
    api_key=os.getenv("OPENAI_API_KEY")
    
)

qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
qdrant_client = QdrantClient(
    url=qdrant_url,
    timeout=120
)


# auth_url = calendar_tool.get_auth_url()calendar_tool.get_auth_url()
# print(auth_url)
facilities_tool = NearbyFacilitiesTool()  # will load API key from .env
# hubspot_tool = HubSpotTool(access_token=os.getenv("HUBSPOT_ACCESS_TOKEN"))

# Blueprint declaration
multi_agents_blueprint = Blueprint("multi_agents", __name__)

with open("client_secret.json") as f:
    CLIENT_SECRETS = json.load(f)["web"]

    CLIENT_ID = CLIENT_SECRETS["client_id"]
    CLIENT_SECRET = CLIENT_SECRETS["client_secret"]
    REDIRECT_URI = CLIENT_SECRETS["redirect_uris"][0]
    SCOPES = [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "openid",
    ]
    
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
    CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID") or CLIENT_SECRETS.get("client_id")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET") or CLIENT_SECRETS.get("client_secret")
redirect_uri = os.getenv("GOOGLE_REDIRECT_URL")  # Must match Google Cloud
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    raise RuntimeError("Google OAuth credentials are required via GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET environment variables or client_secret.json")
MAPS_SCOPES = "https://www.googleapis.com/auth/mapsengine.readonly"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# @multi_agents_blueprint.route("/auth/google")
# def google_auth():
#     try:
#         token = request.args.get("token")
#         if not token:
#             return jsonify({"error": "Missing token"}), 401

#         decoded = decode_token(token)  # from flask_jwt_extended.utils
#         tenant_id = decoded.get("tenant_id")

#         calendar_tool = CalendarTool(
#             tenant_id=tenant_id,
#             credentials_file="client_secret.json",
#             auth_mode="manual",
#             redirect_uri="https://jnanic.com/Admin/Tools"
#         )

#         auth_url, state = calendar_tool.get_auth_url()
#         session["state"] = state
#         return redirect(auth_url)

#     except Exception as e:
#         logger.error(f"OAuth auth error: {e}")
#         return jsonify({"error": str(e)}), 500

@multi_agents_blueprint.route("/auth/google")
def google_auth():
    """
    Google Calendar OAuth entry.
    Expected query params:
      - token=<JWT>
      - source=local|mcp (optional, defaults to local)
    """
    token = request.args.get("token")
    source = request.args.get("source", "local").lower()
    mcp_name = (request.args.get("mcp_name") or "").strip()
    tool_name = (request.args.get("tool_name") or "").strip()

    if not token:
        return jsonify({"error": "Missing token"}), 401

    try:
        decoded = decode_token(token)
        tenant_id = decoded.get("tenant_id")
    except Exception as e:
        return jsonify({"error": "Invalid or expired token", "details": str(e)}), 401

    redirect_uri = os.getenv("GOOGLE_REDIRECT_URL")

    calendar_tool = CalendarTool(
        tenant_id=tenant_id,
        credentials_file="client_secret.json",
        redirect_uri=redirect_uri,
        auth_mode="manual",
    )

    state_payload = {
        "source": source,
        "mcp_name": mcp_name,
        "tool_name": tool_name,
    }
    # Preserve source + MCP context in state
    auth_url, state = calendar_tool.get_auth_url(custom_state=json.dumps(state_payload))

    session["calendar_state"] = state
    session["google_oauth_context"] = state_payload
    return redirect(auth_url)

@multi_agents_blueprint.route("/auth/gsheets")
def gsheets_auth():
    """
    Google Sheets OAuth entry.
    Query params:
      - token=<JWT>
      - source=local|mcp (optional, defaults to local)
    """
    token = request.args.get("token")
    source = request.args.get("source", "local").lower()
    mcp_name = (request.args.get("mcp_name") or "").strip()
    tool_name = (request.args.get("tool_name") or "").strip()

    if not token:
        return jsonify({"error": "Missing token"}), 401

    try:
        decoded = decode_token(token)
        tenant_id = decoded.get("tenant_id")
    except Exception as e:
        return jsonify({"error": "Invalid or expired token", "details": str(e)}), 401

    redirect_uri = os.getenv("GOOGLE_REDIRECT_URL")

    sheets_tool = GSheetsTool(
        tenant_id=tenant_id,
        credentials_file="client_secret.json",
        redirect_uri=redirect_uri,
        auth_mode="manual",
    )

    state_payload = {
        "source": source,
        "mcp_name": mcp_name,
        "tool_name": tool_name,
    }
    # Preserve context in state
    auth_url, state = sheets_tool.get_auth_url(custom_state=json.dumps(state_payload))

    session["gsheets_state"] = state
    session["google_oauth_context"] = state_payload
    return redirect(auth_url)

@multi_agents_blueprint.route("/auth/hubspot")
def hubspot_auth():
    """
    HubSpot OAuth entry.
    Expected query params:
      - token=<JWT>
      - source=local|mcp (optional, defaults to local)
    """
    token = request.args.get("token")
    source = request.args.get("source", "local").lower()

    if not token:
        return jsonify({"error": "Missing token"}), 401

    # Validate JWT token
    try:
        decoded = decode_token(token)
        tenant_id = decoded.get("tenant_id")
    except Exception as e:
        return jsonify({
            "error": "Invalid or expired token",
            "details": str(e)
        }), 401

    redirect_uri = os.getenv("GOOGLE_REDIRECT_URL")

    # ✅ FIXED — Use correct parameter names (client_id, client_secret)
    hubspot_tool = HubSpotTool(
        tenant_id=tenant_id,
        client_id=os.getenv("HUBSPOT_CLIENT_ID"),
        client_secret=os.getenv("HUBSPOT_CLIENT_SECRET"),
        redirect_uri=redirect_uri,
        auth_mode="manual",
    )

    # Preserve source (for MCP/local split)
    auth_url, state = hubspot_tool.get_auth_url(custom_state=source)

    # Save state
    session["hubspot_state"] = state

    return redirect(auth_url)


@multi_agents_blueprint.route("/oauth2callback/google", methods=["GET", "POST"])
@jwt_required()
def google_callback():
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    try:
        # ✅ Support both GET and POST payloads
        if request.method == "POST":
            payload = request.get_json() or {}
            code = payload.get("code")
            scope = payload.get("scope", "")
        else:
            code = request.args.get("code")
            scope = request.args.get("scope", "")

        if not code:
            return jsonify({"error": "Missing code"}), 400
        REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URL")
        # ✅ Exchange authorization code for tokens
        token_payload = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }

        resp = requests.post(TOKEN_URL, data=token_payload, timeout=10)
        tokens = resp.json()
        logger.info(f"Google token exchange response: {tokens}")

        if resp.status_code != 200 or "error" in tokens:
            return jsonify({"error": "Token exchange failed", "details": tokens}), 400

        # ✅ Compute expiry timestamp
        expiry_iso = (datetime.utcnow() + timedelta(seconds=int(tokens.get("expires_in", 3600)))).isoformat() + "Z"

        # ✅ Store token JSON in standard format
        token_data = {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "token_uri": TOKEN_URL,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "scopes": scope.split(),
            "universe_domain": "googleapis.com",
            "account": "",
            "expiry": expiry_iso,
        }

        # ✅ Detect tools from scopes
        def detect_tools(scopes: list[str]) -> list[str]:
            tools = []
            for s in scopes:
                if "gmail" in s:
                    tools.append("Gmail")
                if "calendar" in s:
                    tools.append("Calendar")
                if "spreadsheets" in s or "drive" in s:
                    tools.append("GSheets")
            return list(set(tools))

        granted_tools = detect_tools(scope.split())

        if not granted_tools:
            granted_tools = ["google_generic"]
            logger.warning(f"No recognizable Google scopes for tenant {tenant_id}")

        # ✅ Update if exists; otherwise, create new
        Session = next(db_session())
        updated_tools = []
        created_tools = []

        try:
            for tool_name in granted_tools:
                auth = Session.query(ToolAuthorization).filter_by(
                    tenant_id=int(tenant_id),
                    tool_name=tool_name
                ).first()

                if auth:
                    # 🔄 Update existing
                    auth.token_json = token_data
                    auth.del_flag = False
                    auth.updated_at = datetime.utcnow()
                    updated_tools.append(tool_name)
                else:
                    # 🆕 Create new
                    new_auth = ToolAuthorization(
                        tenant_id=int(tenant_id),
                        tool_name=tool_name,
                        token_json=token_data,
                        del_flag=False,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    Session.add(new_auth)
                    created_tools.append(tool_name)

            Session.commit()
        finally:
            Session.close()

        return jsonify({
            "message": f"Google tools processed successfully.",
            "updated_tools": updated_tools,
            "created_tools": created_tools,
        }), 200

    except Exception as e:
        logger.exception("Google OAuth callback error")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@multi_agents_blueprint.route("/oauth2callback/hubspot", methods=["GET", "POST", "OPTIONS"])
@jwt_required(optional=True)
def hubspot_callback():
    print("HubSpot callback hit ----------------->")
    try:
        # Handle CORS preflight
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

        # Extract tenant (optional)
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        # Parse code on GET or POST
        payload = request.get_json(silent=True) or {}
        code = payload.get("code") or request.args.get("code")
        state = payload.get("state") or request.args.get("state") or "local"

        if not code:
            return jsonify({"error": "Missing code"}), 400

        # Exchange token
        token_payload = {
            "grant_type": "authorization_code",
            "client_id": os.getenv("HUBSPOT_CLIENT_ID"),
            "client_secret": os.getenv("HUBSPOT_CLIENT_SECRET"),
            "redirect_uri":redirect_uri,
            "code": code,
        }

        response = requests.post("https://api.hubapi.com/oauth/v1/token", data=token_payload)
      
        tokens = response.json()

        logger.info(f"HubSpot token exchange response: {tokens}")

        if response.status_code != 200:
            return jsonify({"error": "HubSpot token exchange failed", "details": tokens}), 400

        # Build token
        expiry_iso = (
            datetime.utcnow() + timedelta(seconds=int(tokens.get("expires_in", 3600)))
        ).isoformat() + "Z"

        token_data = {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "expires_in": tokens.get("expires_in"),
            "token_type": tokens.get("token_type"),
            "hub_id": tokens.get("hub_id"),
            "expiry": expiry_iso,
            "scopes": tokens.get("scopes", ""),
        }

        # If no tenant session → return plain token for "local tool"
        if not tenant_id:
            return jsonify({"token": token_data, "session": "no-tenant"}), 200

        # Save to DB
        Session = next(db_session())
        tool_name = "HubSpot"

        try:
            auth = (
                Session.query(ToolAuthorization)
                .filter_by(tenant_id=int(tenant_id), tool_name=tool_name)
                .first()
            )

            if auth:
                auth.token_json = token_data
                auth.del_flag = False
                auth.updated_at = datetime.utcnow()
                updated = True
                created = False
            else:
                Session.add(ToolAuthorization(
                    tenant_id=int(tenant_id),
                    tool_name=tool_name,
                    token_json=token_data,
                    del_flag=False,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                ))
                updated = False
                created = True

            Session.commit()
        finally:
            Session.close()

        return jsonify({
            "message": "HubSpot connected successfully.",
            "updated": updated,
            "created": created,
            "hub_id": tokens.get("hub_id")
        }), 200

    except Exception as e:
        logger.exception("HubSpot error")
        return jsonify({"error": str(e)}), 500



@multi_agents_blueprint.route("/mcp/oauth2callback/google", methods=["GET", "POST"])
@jwt_required()
def mcp_google():
    """
    Google OAuth2 callback handler for MCP tools.
    Handles Gmail, Calendar, and Sheets integrations.
    """
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    try:
        # ✅ Extract authorization code, scope and MCP context
        if request.method == "POST":
            payload = request.get_json() or {}
            code = payload.get("code")
            scope = payload.get("scope", "")
            mcp_name = (payload.get("mcp_name") or "").strip()
            requested_tool_name = (payload.get("tool_name") or "").strip()
            state_value = payload.get("state") or ""
        else:
            code = request.args.get("code")
            scope = request.args.get("scope", "")
            mcp_name = (request.args.get("mcp_name") or "").strip()
            requested_tool_name = (request.args.get("tool_name") or "").strip()
            state_value = request.args.get("state") or ""

        # Fallback from state/session when params are missing in callback chain
        session_ctx = session.get("google_oauth_context") or {}
        mcp_name, requested_tool_name = _extract_oauth_context(
            state_value=state_value,
            mcp_name=mcp_name or session_ctx.get("mcp_name", ""),
            tool_name=requested_tool_name or session_ctx.get("tool_name", ""),
        )

        if not code:
            return jsonify({"error": "Missing authorization code"}), 400
        
        

        # ✅ Token exchange request
        token_payload = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }


        resp = requests.post(TOKEN_URL, data=token_payload, timeout=10)
        tokens = resp.json()
        logger.info(f"[MCP] Google token exchange response: {tokens}")

        if resp.status_code != 200 or "error" in tokens:
            return jsonify({"error": "Token exchange failed", "details": tokens}), 400

        # ✅ Compute expiry timestamp
        expiry_iso = (datetime.utcnow() + timedelta(seconds=int(tokens.get("expires_in", 3600)))).isoformat() + "Z"

        # ✅ Store token JSON in standard format
        token_data = {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "token_uri": TOKEN_URL,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "scopes": scope.split(),
            "universe_domain": "googleapis.com",
            "account": "",
            "expiry": expiry_iso,
        }

        # ✅ Detect which tools user granted
        # Use the SAME names as the MCP catalog (McpTools.mcp_tools) so the
        # authorized_tools intersection in get_mcps() matches correctly.
        def detect_tools(scopes: list[str]) -> list[str]:
            tools = []
            for s in scopes:
                if "gmail" in s:
                    tools.append("Gmail")
                if "calendar" in s:
                    tools.append("Gcalendar")
                if "spreadsheets" in s or "drive" in s:
                    tools.append("Gsheets")
            return list(set(tools))

        granted_tools = detect_tools(scope.split())

        # If frontend sent explicit tool context, prioritize that tool label.
        if requested_tool_name:
            requested_norm = requested_tool_name.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
            if "gmail" in requested_norm:
                granted_tools = ["Gmail"]
            elif "calendar" in requested_norm:
                granted_tools = ["Gcalendar"]
            elif "sheet" in requested_norm or "spreadsheet" in requested_norm or "drive" in requested_norm:
                granted_tools = ["Gsheets"]

        if not granted_tools:
            granted_tools = ["MCP_Google_Generic"]
            logger.warning(f"[MCP] No recognizable scopes for tenant {tenant_id}")

        # ✅ Save or update in DB
        Session = next(db_session())
        updated_tools = []
        created_tools = []

        try:
            for tool_name in granted_tools:
                auth_query = Session.query(ToolAuthorization).filter_by(
                    tenant_id=int(tenant_id),
                    tool_name=tool_name,
                    tool_type="mcp",
                )
                auth = None
                if mcp_name:
                    auth = auth_query.filter_by(mcp_url=mcp_name).first()
                if not auth:
                    auth = auth_query.order_by(ToolAuthorization.updated_at.desc()).first()

                if auth:
                    # 🔄 Update existing
                    auth.token_json = token_data
                    auth.del_flag = False
                    auth.tool_type = "mcp"
                    if mcp_name:
                        auth.mcp_url = mcp_name
                    auth.mcp_json = {
                        "mcp_name": mcp_name,
                        "tool_name": requested_tool_name or tool_name,
                        "tgi": True,
                    } if mcp_name or requested_tool_name else auth.mcp_json
                    auth.updated_at = datetime.utcnow()
                    updated_tools.append(tool_name)
                else:
                    # 🆕 Create new
                    new_auth = ToolAuthorization(
                        tenant_id=int(tenant_id),
                        tool_name=tool_name,
                        token_json=token_data,
                        tool_type="mcp",
                        mcp_url=mcp_name or None,
                        mcp_json={
                            "mcp_name": mcp_name,
                            "tool_name": requested_tool_name or tool_name,
                            "tgi": True,
                        } if mcp_name or requested_tool_name else None,
                        del_flag=False,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    Session.add(new_auth)
                    created_tools.append(tool_name)

            Session.commit()

            # ✅ Sync granted tools into the MCP catalog (McpTools.mcp_tools)
            # Without this, /mcp_tools/tools never shows the OAuth'd tool even though
            # credentials are saved — because get_mcps() intersects catalog vs auth.
            if mcp_name:
                try:
                    mcp_record = Session.query(McpTools).filter_by(
                        tenant_id=int(tenant_id),
                        mcp_name=mcp_name
                    ).first()
                    if mcp_record:
                        current_catalog = list(mcp_record.mcp_tools or [])
                        changed = False
                        for granted in granted_tools:
                            if granted not in current_catalog:
                                current_catalog.append(granted)
                                changed = True
                                logger.info(
                                    "[MCP] Added '%s' to catalog for mcp_name='%s' tenant=%s",
                                    granted, mcp_name, tenant_id
                                )
                        if changed:
                            mcp_record.mcp_tools = current_catalog
                            Session.commit()
                    else:
                        logger.warning(
                            "[MCP] No McpTools record found for mcp_name='%s' tenant=%s — "
                            "tool will not appear until MCP server is registered.",
                            mcp_name, tenant_id
                        )
                except Exception as catalog_err:
                    logger.warning("[MCP] Could not update MCP catalog: %s", catalog_err)

        finally:
            Session.close()

        return jsonify({
            "message": f"[MCP] Google OAuth success",
            "updated_tools": updated_tools,
            "created_tools": created_tools,
        }), 200

    except Exception as e:
        logger.exception("[MCP] Google OAuth callback error")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@multi_agents_blueprint.route("/oauth2callback/MCPgoogle", methods=["GET", "POST"])
@jwt_required()
def mcp_google_callback():
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    try:
        # Get code from POST JSON or GET params
        if request.method == "POST":
            payload = request.get_json() or {}
            code = payload.get("code")
            scope = payload.get("scope")
        else:
            code = request.args.get("code")
            scope = request.args.get("scope")

        if not code or not scope:
            return jsonify({"error": "Missing code or state"}), 400

        # Exchange authorization code for tokens
        token_payload = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,  # make sure this matches your MCP redirect URI if different
            "grant_type": "authorization_code",
        }
        resp = requests.post(TOKEN_URL, data=token_payload, timeout=10)
        tokens = resp.json()
        logger.info(f"[MCP Google] Token payload: {token_payload}")

        if resp.status_code != 200 or "error" in tokens:
            return jsonify({"error": "Token exchange failed", "details": tokens}), 400

        # Build token object to store
        expiry_iso = (datetime.utcnow() + timedelta(seconds=int(tokens.get("expires_in", 3600)))).isoformat() + "Z"
        token_data = {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "token_uri": TOKEN_URL,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "scopes": [
                "https://www.googleapis.com/auth/calendar.events",
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/calendar.readonly"
            ],
            "universe_domain": "googleapis.com",
            "account": "",
            "expiry": expiry_iso
        }
        logger.info(f"[MCP Google] Token data: {token_data}")

        # ORM: insert or update token in ToolAuthorization
        Session = next(db_session())
        try:
            auth = Session.query(ToolAuthorization).filter_by(
                tenant_id=int(tenant_id),
                tool_name="jnanic.google_calendar"  # 👈 New tool name
            ).first()

            if auth:
                auth.token_json = token_data
                auth.del_flag = False
                auth.updated_at = datetime.utcnow()
            else:
                auth = ToolAuthorization(
                    tenant_id=int(tenant_id),
                    tool_name="jnanic.google_calendar",
                    token_json=token_data,
                    del_flag=False
                )
                Session.add(auth)

            Session.commit()
        finally:
            Session.close()

        return jsonify({"message": "MCP Google Calendar authorized successfully"}), 200

    except Exception as e:
        logger.exception("OAuth MCP callback error")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@multi_agents_blueprint.route("/auth/gmail")
def gmail_auth():
    """
    Gmail OAuth entry for both Local and MCP tools.
    The frontend must send:
      - token=<JWT access token>
      - source=local | mcp (optional, defaults to local)
    """
    token = request.args.get("token")
    source = request.args.get("source", "local").lower()
    mcp_name = (request.args.get("mcp_name") or "").strip()
    tool_name = (request.args.get("tool_name") or "").strip()

    if not token:
        return jsonify({"error": "Missing token"}), 401

    try:
        decoded = decode_token(token)
        tenant_id = decoded.get("tenant_id")
    except Exception as e:
        return jsonify({"error": "Invalid or expired token", "details": str(e)}), 401

    # ✅ Use a redirect URI WITHOUT query params
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URL")

    gmail_tool = GmailTool(
        tenant_id=tenant_id,
        credentials_file="client_secret.json",
        redirect_uri=redirect_uri,
        auth_mode="manual",
    )

    state_payload = {
        "source": source,
        "mcp_name": mcp_name,
        "tool_name": tool_name,
    }
    # ✅ Pass full context as state to preserve MCP mapping
    auth_url, state = gmail_tool.get_auth_url(custom_state=json.dumps(state_payload))

    # Save OAuth state to session for security
    session["gmail_state"] = state
    session["google_oauth_context"] = state_payload

    # ✅ Redirect to Google OAuth
    return redirect(auth_url)


@multi_agents_blueprint.route("/oauth2callback/gmail", methods=["GET", "POST"])
@jwt_required()
def gmail_callback():
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    try:
        # Get code from POST JSON or GET params
        if request.method == "POST":
            payload = request.get_json() or {}
            code = payload.get("code")
            scope = payload.get("scope")
        else:
            code = request.args.get("code")
            scope = request.args.get("scope")

        if not code or not scope:
            return jsonify({"error": "Missing code or state"}), 400

        # Exchange authorization code for tokens
        token_payload = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,  # same redirect_uri used in Google OAuth setup
            "grant_type": "authorization_code",
        }
        resp = requests.post(TOKEN_URL, data=token_payload, timeout=10)
        tokens = resp.json()
        logger.info(f"Token payload: {token_payload}")

        if resp.status_code != 200 or "error" in tokens:
            return jsonify({"error": "Token exchange failed", "details": tokens}), 400

        # Build token object
        expiry_iso = (datetime.utcnow() + timedelta(seconds=int(tokens.get("expires_in", 3600)))).isoformat() + "Z"
        token_data = {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "token_uri": TOKEN_URL,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "scopes": [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/gmail.compose",
                "https://www.googleapis.com/auth/gmail.modify"
            ],
            "universe_domain": "googleapis.com",
            "account": "",
            "expiry": expiry_iso
        }
        logger.info(f"Gmail token data: {token_data}")


        

        # ORM: insert or update token in ToolAuthorization
        Session = next(db_session())
        try:
            auth = Session.query(ToolAuthorization).filter_by(
                tenant_id=int(tenant_id),
                tool_name="gmail"
            ).first()

            if auth:
                auth.token_json = token_data
                auth.del_flag = False
                auth.updated_at = datetime.utcnow()
            else:
                auth = ToolAuthorization(
                    tenant_id=int(tenant_id),
                    tool_name="gmail",
                    token_json=token_data,
                    del_flag=False
                )
                Session.add(auth)

            Session.commit()
        finally:
            Session.close()

        return jsonify({"message": "Gmail authorized successfully"}), 200

    except Exception as e:
        logger.exception("Gmail OAuth callback error")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@multi_agents_blueprint.route("/gmail/list-labels")
def gmail_list_labels():
    labels = gmail_tool.list_labels()
    return jsonify({"labels": labels}), 200


@multi_agents_blueprint.route("/connect/hubspot")
def connect_hubspot():
    client_id = "7933b042-0952-4e7d-a327dab-3dc"
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URL")
    scopes = "crm.objects.contacts.read crm.objects.contacts.write"

    auth_url = (
        f"https://app.hubspot.com/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scopes}"
        f"&state=hubspot"
    )
    return redirect(auth_url)



@multi_agents_blueprint.route("/auth/google_maps")
def google_maps_auth():
    """Redirect user to Google Maps OAuth page"""
    try:
        auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={GOOGLE_CLIENT_ID}"
            f"&redirect_uri={REDIRECT_URI}"
            f"&response_type=code"
            f"&scope={MAPS_SCOPES}"
            f"&access_type=offline"
            f"&prompt=consent"
            f"&state=google_maps"
        )
        return redirect(auth_url)
    except Exception as e:
        logger.error(f"Google Maps OAuth error: {e}")
        return str(e), 500


@multi_agents_blueprint.route("/oauth2callback/maps", methods=["GET", "POST"])
def google_maps_callback():
    """Handle Google Maps OAuth callback"""
    try:
        # For GET request (redirect from Google)
        code = request.args.get("code") or request.json.get("code")
        state = request.args.get("state") or request.json.get("state")

        if not code:
            return {"error": "Missing code"}, 400

        # Exchange code for token
        payload = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }

        r = requests.post(TOKEN_URL, data=payload)
        tokens = r.json()

        # Save access token in session or DB
        session["google_maps_token"] = tokens.get("access_token")
        return jsonify({"message": "Google Maps connected", "tokens": tokens}), 200

    except Exception as e:
        logger.error(f"Google Maps callback error: {e}")
        return {"error": str(e)}, 400


@multi_agents_blueprint.route("/maps/nearby", methods=["POST"])
def maps_nearby_search():
    """
    Example endpoint: fetch nearby facilities using Google Maps API
    Expects JSON: { "location": "lat,lng", "type": "hospital" }
    """
    try:
        data = request.get_json()
        location = data.get("location")
        facility_type = data.get("type")

        if not location or not facility_type:
            return jsonify({"error": "location and type are required"}), 400

        access_token = session.get("google_maps_token")
        if not access_token:
            return jsonify({"error": "Google Maps not connected"}), 401

        # Use your existing NearbyFacilitiesTool or direct API call
        results = maps_tool.process(location, facility_type)

        return jsonify({"results": results}), 200

    except Exception as e:
        logger.error(f"Google Maps nearby search error: {e}")
        return jsonify({"error": str(e)}), 500

@multi_agents_blueprint.route('/auth')
def index():
    """Redirect to Google OAuth2 authorization."""
    try:
        return redirect(calendar_tool.get_auth_url())
    except Exception as e:
        logger.error(f"OAuth redirect error: {e}")
        return str(e), 500


@multi_agents_blueprint.route('/book-appointment', methods=['POST'])
def book_appointment():
    """Book an appointment in Google Calendar."""
    try:
        data = request.get_json()
        title = data.get('title', 'Appointment')
        location = data.get('location', '')
        description = data.get('description', '')
        start_time = data.get('start_time')
        duration = data.get('duration', 1)
        attendees = data.get('attendees', [])

        if not start_time:
            return jsonify({'error': 'Start time is required.'}), 400

        # Optional: validate datetime format (e.g., ISO 8601)
        try:
            datetime.fromisoformat(start_time)
        except Exception:
            return jsonify({'error': 'Invalid datetime format. Use YYYY-MM-DDTHH:MM:SS'}), 400

        result = calendar_tool.book_appointment(
            title, location, description, start_time, duration, attendees
        )
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Appointment booking error: {e}")
        return jsonify({'error': str(e)}), 400


@multi_agents_blueprint.route('/commute-time', methods=['POST'])
def commute_time():
    """Calculate commute time between two places."""
    try:
        data = request.get_json()
        origin = data.get('origin')
        destination = data.get('destination')
        future_date_str = data.get('future_date')

        if not origin or not destination:
            return jsonify({'error': 'Origin and destination are required.'}), 400

        result = CommuteTimeTool().process(origin, destination, future_date_str)
        return jsonify({'message': result}), 200

    except Exception as e:
        logger.error(f"Commute time error: {e}")
        return jsonify({'error': str(e)}), 400


@multi_agents_blueprint.route('/nearby-facilities', methods=['POST'])
def get_nearby_facilities():
    """Find nearby facilities like schools, hospitals."""
    try:
        data = request.get_json()
        location = data.get('location')
        facility_type = data.get('facility_type')

        if not location or not facility_type:
            return jsonify({'error': 'Location and facility_type are required.'}), 400

        result = facilities_tool.process(location, facility_type)
        return jsonify({'facilities': result}), 200

    except Exception as e:
        logger.error(f"Nearby facilities error: {e}")
        return jsonify({'error': str(e)}), 400


@multi_agents_blueprint.route('/get_loan_offers', methods=['POST'])
def get_loan_offers():
    """Fetch loan offers based on CIBIL score and salary."""
    try:
        data = request.get_json()
        cibil_score = data.get("cibil_score")
        salary = data.get("salary")

        if not cibil_score or not salary:
            return jsonify({"message": "CIBIL score and salary are required."}), 400

        finance_tool = FinanceTool(bankbazaar_api_key='your-bankbazaar-api-key')
        result = finance_tool.get_loan_offers(cibil_score, salary)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Loan offer error: {e}")
        return jsonify({"error": str(e)}), 500


@multi_agents_blueprint.route('/get_rental_income', methods=['POST'])
def get_rental_income():
    """Estimate rental income based on property info."""
    try:
        data = request.get_json()
        location = data.get('location')
        property_type = data.get('property_type')

        if not location or not property_type:
            return jsonify({"error": "Location and property type are required."}), 400

        rental_info = TavilyRentalIncomeTool().process(location, property_type)
        return jsonify({"rental_income_data": rental_info}), 200

    except Exception as e:
        logger.error(f"Rental income error: {e}")
        return jsonify({"error": str(e)}), 500


@multi_agents_blueprint.route('/hubspot/contact/create', methods=['POST'])
def create_hubspot_contact():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Missing contact data'}), 400

        result = hubspot_tool.create_contact(data)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Create contact error: {e}")
        return jsonify({'error': str(e)}), 500


@multi_agents_blueprint.route('/hubspot/contact/<contact_id>', methods=['GET'])
def get_hubspot_contact(contact_id):
    try:
        result = hubspot_tool.get_contact(contact_id)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Get contact error: {e}")
        return jsonify({'error': str(e)}), 500


@multi_agents_blueprint.route('/hubspot/contact/<contact_id>', methods=['PATCH'])
def update_hubspot_contact(contact_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Missing update data'}), 400

        result = hubspot_tool.update_contact(contact_id, data)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Update contact error: {e}")
        return jsonify({'error': str(e)}), 500


@multi_agents_blueprint.route('/hubspot/contact/<contact_id>', methods=['DELETE'])
def delete_hubspot_contact(contact_id):
    try:
        result = hubspot_tool.delete_contact(contact_id)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Delete contact error: {e}")
        return jsonify({'error': str(e)}), 500


@multi_agents_blueprint.route('/hubspot/contact/search', methods=['POST'])
def search_hubspot_contact():
    try:
        data = request.get_json()
        email = data.get("email")

        if not email:
            return jsonify({'error': 'Email is required'}), 400

        result = hubspot_tool.search_contacts(email=email)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Search contact error: {e}")
        return jsonify({'error': str(e)}), 500

def _evict_agent_cache():
    now = time.time()
    keys_to_remove = [k for k, (_, ts) in _agent_cache.items() if (now - ts) > AGENT_CACHE_TTL_SECS]
    for k in keys_to_remove:
        _agent_cache.pop(k, None)

    if len(_agent_cache) > MAX_AGENT_SYSTEMS:
        sorted_items = sorted(_agent_cache.items(), key=lambda kv: kv[1][1])
        while len(_agent_cache) > MAX_AGENT_SYSTEMS and sorted_items:
            oldest_key = sorted_items.pop(0)[0]
            _agent_cache.pop(oldest_key, None)

def get_or_create_multi_agent_system(
    tenant_id: str,
    session_id: str,
    bot_id: str = None,
    kb_ids: list = None,
    instructions: list = None,
    core_features: list = None,
    kb_functionalities: list = None,
    memory_mode: str = None
) -> MultiAgentSystem:

    cache_key = f"{tenant_id}_{bot_id or 'default'}_{session_id}_{memory_mode or 'session'}"
    logger.info(
        f"[get_or_create_mas] Request | cache_key={cache_key} | "
        f"kb_ids={kb_ids} | kb_ids_type={type(kb_ids).__name__} | "
        f"core_features_type={type(core_features).__name__}"
    )

    with _agent_cache_lock:
        _evict_agent_cache()
        cached = _agent_cache.get(cache_key)
        if cached:
            instance, created_at = cached
            age = time.time() - created_at
            cached_kb_ids = getattr(instance, "_injected_kb_ids", []) or []
            cached_instructions = getattr(instance, "_injected_instructions", []) or []
            cached_core_features = getattr(instance, "_injected_core_features", []) or []
            cached_kb_functionalities = getattr(instance, "_injected_kb_functionalities", []) or []

            incoming_kb_ids = kb_ids or []
            incoming_instructions = instructions or []
            incoming_core_features = core_features or []
            incoming_kb_functionalities = kb_functionalities or []

            if (
                cached_kb_ids == incoming_kb_ids
                and cached_instructions == incoming_instructions
                and cached_core_features == incoming_core_features
                and cached_kb_functionalities == incoming_kb_functionalities
            ):
                logger.info(f"[get_or_create_mas] Cache HIT | key={cache_key} | age={age:.1f}s")
                return instance

            logger.info(
                f"[get_or_create_mas] Cache STALE config change detected | key={cache_key} | "
                f"old_kb_ids={cached_kb_ids} | new_kb_ids={incoming_kb_ids} | recreating instance"
            )
            _agent_cache.pop(cache_key, None)
        else:
            logger.info(f"[get_or_create_mas] Cache MISS | key={cache_key} — creating new instance")

    try:
        logger.info(
            f"[get_or_create_mas] Initializing MultiAgentSystem | "
            f"tenant={tenant_id} | bot={bot_id} | "
            f"kb_ids={kb_ids} | instructions_count={len(instructions) if isinstance(instructions, list) else 'non-list'} | "
            f"core_features_type={type(core_features).__name__}"
        )
        instance = MultiAgentSystem(
            tenant_id=tenant_id,
            bot_id=bot_id,
            session_id=session_id,
            kb_ids=kb_ids or [],
            instructions=instructions or [],
            core_features=core_features or [],
            kb_functionalities=kb_functionalities or [],
            memory_mode=memory_mode
        )
    except Exception as e:
        logger.exception(f"[get_or_create_mas] Failed to initialize MultiAgentSystem for bot={bot_id}: {e}")
        raise

    with _agent_cache_lock:
        _agent_cache[cache_key] = (instance, time.time())
        logger.info(f"[get_or_create_mas] Cached | key={cache_key} | cache_size={len(_agent_cache)}")
        return instance
    
@multi_agents_blueprint.route('/get_chat', methods=['POST', 'OPTIONS'])
def get_chat():

    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    try:
     
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload."}), 400
        query      = (data.get('query') or "").strip()
        bot_id     = data.get('bot_id')
        session_id = data.get('session_id')
        if not query:
            return jsonify({"error": "Query is required."}), 400
        if not bot_id:
            return jsonify({"error": "Bot ID is required."}), 400
        if not session_id:
            return jsonify({"error": "Session ID is required."}), 400
        if len(query) > 2000:
            return jsonify({"error": "Query is too long (max 2000 characters)."}), 400

        # Ã¢â€ Â CHANGED: query CustomBotNew instead of CustomBot
        bot = CustomBotNew.query.filter_by(bot_id=bot_id, del_flg=False).first()
        logger.info("Processing query for bot_id=%s: %s", bot_id, query[:50])
        if not bot:
            return jsonify({"error": "Invalid bot_id or bot not found."}), 404

        restrictions = CustomBotAccessRestriction.query.filter_by(bot_id=bot.bot_id).all()
        has_restrictions = any(r.allowed_ip or r.allowed_domain for r in restrictions)
        if has_restrictions:
            auth_header = request.headers.get("Authorization", "")
            token = auth_header.replace("Bearer ", "").strip()
            if not token:
                return jsonify({"error": "Validation token is required"}), 401

            try:
                token_data = decode_token(token)
            except Exception as e:
                try:
                    token_data = jwt.decode(
                        token,
                        current_app.config.get("JWT_SECRET_KEY") or os.getenv("JWT_SECRET_KEY"),
                        algorithms=["HS256"],
                        options={"verify_sub": False},
                    )
                    logger.warning(
                        "Decoded legacy validation token with non-string subject | bot_id=%s | error=%s",
                        bot.bot_id,
                        str(e),
                    )
                except Exception as fallback_error:
                    logger.warning(
                        "Failed to decode validation token | bot_id=%s | error=%s | fallback_error=%s",
                        bot.bot_id,
                        str(e),
                        str(fallback_error),
                    )
                    return jsonify({"error": "Invalid token"}), 401

            if not token_data.get("client_ip") and not token_data.get("domain"):
                logger.warning(
                    "Chat request used a non-validation JWT | bot_id=%s | token_claims=%s",
                    bot.bot_id,
                    list(token_data.keys()),
                )
                return jsonify({
                    "error": "Invalid validation token. Use the token returned by /custom_bot_new/validate_client."
                }), 401

            token_bot_id = token_data.get("bot_id") or token_data.get("sub")
            if str(token_bot_id) != str(bot.bot_id):
                logger.warning(
                    "Bot mismatch in validation token | token_bot_id=%s | request_bot_id=%s",
                    token_bot_id,
                    bot.bot_id,
                )
                return jsonify({"error": "Validation token does not match this bot."}), 403

            token_tenant_id = token_data.get("tenant_id")

            # New validation tokens include tenant_id. Older cached tokens did
            # not, so allow those only after the bot_id match above succeeds.
            if token_tenant_id is not None and str(token_tenant_id) != str(bot.tenant_id):
                logger.warning(
                    f"Tenant mismatch | token_tenant_id={token_tenant_id} | bot_tenant_id={bot.tenant_id}"
                )
                return jsonify({"error": "Validation token does not match this bot tenant."}), 403
            token_ip = token_data.get("client_ip")
            token_domain = _normalize_chatbot_domain(token_data.get("domain"))
            pure_ips = {r.allowed_ip for r in restrictions if r.allowed_ip and r.allowed_domain is None}
            mapped_ips = {r.allowed_ip for r in restrictions if r.allowed_ip and r.allowed_domain}
            base_domains = {
                _normalize_chatbot_domain(r.allowed_domain)
                for r in restrictions
                if r.allowed_domain
            }

            token_still_allowed = False

            # 1. Pure IP match
            if token_ip in pure_ips:
                token_still_allowed = True

            # 2. Domain match
            elif token_domain and token_domain in base_domains:
                token_still_allowed = True

            # 3. Mapped IP + domain match (CRITICAL FIX)
            else:
                for r in restrictions:
                    db_domain = _normalize_chatbot_domain(r.allowed_domain)

                    if (
                        r.allowed_ip == token_ip and
                        db_domain == token_domain
                    ):
                        token_still_allowed = True
                        break
            if not token_still_allowed:
                logger.warning(
                    "Validation token no longer matches restrictions | bot_id=%s | token_ip=%s | token_domain=%s",
                    bot.bot_id,
                    token_ip,
                    token_domain,
                )
                return jsonify({"error": "Access denied. Your IP or domain is not allowed."}), 403

        # Ã¢â€ Â CHANGED: resolve config (handles CREATED vs LIVE)
        try:
            config = resolve_bot_config(bot)
        except PermissionError as e:
            logger.warning(str(e))
            return jsonify({"error": "Bot is not available for chat."}), 403
        except ValueError as e:
            logger.error(str(e))
            return jsonify({"error": "Bot configuration unavailable."}), 503

        is_test   = config["is_test_mode"]
        tenant_id = bot.tenant_id

        if not tenant_id:
            return jsonify({"error": "Tenant ID not found for this bot."}), 500

        # Ã¢â€ Â CHANGED: pass config fields into agent
        multi_agent = get_or_create_multi_agent_system(
            tenant_id=tenant_id,
            bot_id=bot_id,
            session_id=session_id,
            kb_ids=config.get("kb_ids", []),
            instructions=config.get("instructions", []),
            core_features=config.get("core_features", []),
            kb_functionalities=config.get("kb_functionalities", []),
            memory_mode=config.get("memory_mode")
        )

        agent_response = multi_agent.ask(query)
        # Skip message decrement in test mode
        if not is_test:
            try:
                session = next(db_session())
                result = update_remaining_messages(session, tenant_id, 1)
                if isinstance(result, tuple):
                    success, msg = result
                    if not success:
                        logger.warning(f"Message count update failed | tenant_id={tenant_id} | {msg}")
                        session.rollback()
                    else:
                        session.commit()
                else:
                    session.commit()
            except Exception as e:
                logger.warning(f"Failed to update message count | {e}")
                session.rollback()
            finally:
                session.close()

        return jsonify({
            "response":  agent_response,
            "test_mode": is_test      # useful for frontend testing banner
        }), 200

    except Exception as e:
        logger.exception(f"Unexpected error in get_chat | {e}")
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500


@multi_agents_blueprint.route("/generate-purpose", methods=["POST"])
@jwt_required()
def generate_purpose():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload."}), 400
        
        industry = data.get("industry", "General")
        bot_name = data.get("bot_name", "Chatbot")
        tone = data.get("tone", "professional")
        
        if not industry:
            return jsonify({"error": "industry is required."}), 400
        if not bot_name:
            return jsonify({"error": "bot name is required."}), 400  
        
        tool_list = data.get("tools")

        # If user did not provide tools → fetch from DB
        if not tool_list:
            tool_list = get_enabled_tools_for_tenant()

        # Ensure it's always a list (even if empty)
        if tool_list is None:
            tool_list = []
        purpose_prompt = f"""
            You are helping design a chatbot. Write a chatbot purpose in 2–3 concise sentences.
            
            Guidelines:
            - The purpose should describe how the chatbot helps users in the {industry} industry.
            - Incorporate the given bot name: {bot_name}.
            - Use a {tone} tone of voice.
            - If tools are provided, align the purpose with their potential capabilities, but do not mention tool names directly.
            - Keep the description user-facing, engaging, and outcome-driven, without being too lengthy.
            
            Example Input: Industry: Real Estate | Bot Name: HomeFinder | Tone: Friendly | Tools: [Google Maps, Gmail, Google Calendar, Tavily]  
            Example Output:  
            HomeFinder helps users explore properties with ease through personalized recommendations and interactive listings.  
            With its friendly approach, it streamlines financing, market insights, and visit scheduling for buyers, sellers, and renters.  
            
            Input: Industry: {industry} | Bot Name: {bot_name} | Tone: {tone} | Tools: [{tool_list}]  
            Output:
            """

        # Call the LLM
        routing_response = decision_llm.invoke(purpose_prompt)
        print(f"HJHJHJJJJJJ{routing_response}")
        output_text = routing_response.content.strip()
            
        return jsonify(
            {
                "industry": industry,
                "bot_name": bot_name,
                "tone": tone,
                "tools": tool_list,
                "purpose": output_text,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@multi_agents_blueprint.route("/generate-functionalities", methods=["POST"])
def generate_functionalities():
    try:
        data = request.get_json()

        industry = data.get("industry", "General")
        tools = data.get("tools", [])

        # Ensure core tools (same behavior as before)
        # if "Google Maps" not in tools:
        #     tools.append("Google Maps")
        
        

        routing_prompt = f"""
    CRITICAL RULES:
    - Return ONLY valid JSON
    - No markdown
    - No explanations
    - Use EXACT tool names from the list as JSON keys
    - Every tool MUST have exactly ONE functionality
    - Do NOT skip any tool

    Industry: {industry}
    Tools: {json.dumps(tools)}

    Output format:
    {{
    "Gmail": ["Send and manage professional emails"],
    "Calendar": ["Schedule meetings and reminders"]
    }}
    """

        response = decision_llm.invoke(routing_prompt)
        output_text = response.content.strip()

        # Parse JSON safely
        functionalities = json.loads(output_text)

        # Fallback safety (does NOT change structure)
        for tool in tools:
            if tool not in functionalities:
                functionalities[tool] = [
                    f"Perform {tool}-related actions for users"
                ]

        return jsonify({
            "industry": industry,
            "tools": tools,
            "functionalities": functionalities
        })

    except json.JSONDecodeError:
        return jsonify({
            "error": "Invalid JSON from LLM"
        }), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


MAX_DYNAMIC_INSTRUCTIONS = 3

STATIC_INSTRUCTIONS = [
    "Confirm any create, update, or delete action before executing.",
    "If a tool fails, acknowledge the issue and suggest an alternative."
]


@multi_agents_blueprint.route("/generate-instructions", methods=["POST"])
def generate_instructions():
    try:
        data = request.get_json() or {}

        bot_name = data.get("bot_name", "Chatbot")
        purpose = data.get("purpose", "")
        functionalities = data.get("functionalities", [])

        func_list = (
            "\n".join(f"- {f}" for f in functionalities)
            if functionalities
            else "none"
        )

        instructions_prompt = f"""
Generate exactly {MAX_DYNAMIC_INSTRUCTIONS} clear, actionable instructions
for the chatbot "{bot_name}".

Bot Purpose:
{purpose}

Functionalities:
{func_list}

Rules:
- Do NOT repeat generic chatbot rules
- Do NOT include confirmation, error-handling, or support escalation rules
- Focus only on domain- or use-case-specific behavior
- One instruction per line
- No numbering
- No tool names
"""

        llm_response = decision_llm.invoke(instructions_prompt)
        output_text = llm_response.content.strip()

        # ✅ ONLY dynamic instructions (exactly 3)
        dynamic_instructions = [
            {
                "id": idx + 1,
                "question": line.lstrip("-• ").strip()
            }
            for idx, line in enumerate(output_text.split("\n"))
            if line.strip()
        ][:MAX_DYNAMIC_INSTRUCTIONS]

        return jsonify({
            "instructions": dynamic_instructions
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# -------------- Kb functionalities generation ----------

# ---------------- CONFIG ----------------
MAX_CONTEXT_CHARS = 3500        # ~900 tokens
DEFAULT_CHUNK_COUNT = 2         # configurable
QDRANT_SCROLL_LIMIT = 50        # how many points to scan before random pick
MAX_KB_COUNT = 5                
MAX_CHARS_PER_KB = 800  
DEFAULT_KB_FUNCTIONALITIES_COUNT = 2
# ---------------- HLPERS -----------------------
def trim_text(text: str, max_chars: int = MAX_CONTEXT_CHARS) -> str:
    if not text:
        return ""
    return text.strip()[:max_chars]

def get_random_chunks_from_qdrant(
    collection_name: str,
    chunk_count: int = DEFAULT_CHUNK_COUNT
):
    """
    Fetch random chunks from Qdrant without assuming payload structure.
    """

    if not collection_name:
        return []

    try:
        points, _ = qdrant_client.scroll(
            collection_name=collection_name,
            limit=QDRANT_SCROLL_LIMIT,
            with_payload=True,
            with_vectors=False
        )

        texts = []

        for point in points:
            payload = point.payload or {}

            # Extract ANY string value from payload
            for value in payload.values():
                if isinstance(value, str) and len(value.strip()) > 30:
                    texts.append(value.strip())

        if not texts:
            return []

        # Randomly pick required chunks
        return random.sample(
            texts,
            min(chunk_count, len(texts))
        )

    except Exception:
        logger.exception("Failed to fetch random chunks from Qdrant")
        return []

def build_single_kb_context(kb, chunk_count=DEFAULT_CHUNK_COUNT):
    """
    Builds a bounded context for ONE KB
    """

    # 1️⃣ Summary first
    if kb.kb_summary:
        return trim_text(kb.kb_summary, MAX_CHARS_PER_KB), "summary"

    # 2️⃣ Random chunks fallback
    chunks = get_random_chunks_from_qdrant(
        collection_name=kb.collection_name,
        chunk_count=chunk_count
    )

    if chunks:
        combined = "\n\n".join(chunks)
        return trim_text(combined, MAX_CHARS_PER_KB), "random_qdrant_chunks"

    return None, None

def build_multi_kb_context(kbs, chunk_count):
    """
    Combine multiple KB contexts safely.
    """

    contexts = []
    sources = {}

    logger.info(
        "build_multi_kb_context called | kb_count=%s | chunk_count=%s",
        len(kbs),
        chunk_count
    )

    for kb in kbs:
        logger.info(
            "Processing KB for context | knowledge_base_id=%s | knowledge_base_name=%s | collection_name=%s",
            kb.knowledge_base_id,
            kb.knowledge_base_name,
            kb.collection_name
        )
        ctx, source = build_single_kb_context(kb, chunk_count)
        if ctx:
            contexts.append(f"[KB: {kb.knowledge_base_name}]\n{ctx}")
            sources[kb.knowledge_base_id] = source
            logger.info(
                "KB context added | knowledge_base_id=%s | source=%s | ctx_chars=%s",
                kb.knowledge_base_id,
                source,
                len(ctx)
            )
        else:
            logger.warning(
                "No usable context for KB | knowledge_base_id=%s | collection_name=%s",
                kb.knowledge_base_id,
                kb.collection_name
            )

    combined_context = "\n\n---\n\n".join(contexts)
    combined_context = trim_text(combined_context, MAX_CONTEXT_CHARS)

    return combined_context, sources



@multi_agents_blueprint.route("/generate-kb-functionalities", methods=["POST"])
def generate_kb_functionalities():
    try:
        data = request.get_json()
        logger.info("generate_kb_functionalities called | payload=%s", data)

        kb_ids = []

        # ---------------------------------------------
        # Backward compatibility
        # ---------------------------------------------
        if "knowledge_base_id" in data:
            kb_ids = [data["knowledge_base_id"]]
            logger.info(
                "Detected single knowledge_base_id in payload | knowledge_base_id=%s",
                data["knowledge_base_id"]
            )

        elif "knowledge_base_ids" in data:
            kb_ids = data["knowledge_base_ids"]
            logger.info(
                "Detected knowledge_base_ids list in payload | knowledge_base_ids=%s",
                kb_ids
            )

        logger.info("Resolved kb_ids after parsing request | kb_ids=%s", kb_ids)

        if not kb_ids:
            logger.warning("No kb_ids provided in request payload")
            return jsonify({
                "error": "knowledge_base_id or knowledge_base_ids is required"
            }), 400

        if len(kb_ids) > MAX_KB_COUNT:
            logger.warning(
                "Too many kb_ids provided | kb_count=%s | max_allowed=%s | kb_ids=%s",
                len(kb_ids),
                MAX_KB_COUNT,
                kb_ids
            )
            return jsonify({
                "error": f"Maximum {MAX_KB_COUNT} knowledge bases supported"
            }), 400

        num_functionalities = int(
            data.get(
                "num_functionalities",
                DEFAULT_KB_FUNCTIONALITIES_COUNT
            )
        )

        chunk_count = int(
            data.get(
                "chunk_count",
                DEFAULT_CHUNK_COUNT
            )
        )
        logger.info(
            "KB generation params | kb_ids=%s | num_functionalities=%s | chunk_count=%s",
            kb_ids,
            num_functionalities,
            chunk_count
        )

        # ---------------------------------------------
        # Fetch KBs
        # ---------------------------------------------
        kbs = KnowledgeBase.query.filter(
            KnowledgeBase.knowledge_base_id.in_(kb_ids),
            KnowledgeBase.del_flg == False
        ).all()
        logger.info(
            "KB query completed | requested_kb_ids=%s | found_kb_count=%s | found_kb_ids=%s",
            kb_ids,
            len(kbs),
            [kb.knowledge_base_id for kb in kbs]
        )

        if not kbs:
            logger.warning("No valid KBs found for requested ids | kb_ids=%s", kb_ids)
            return jsonify({"error": "No valid knowledge bases found"}), 404

        # ---------------------------------------------
        # Build combined context
        # ---------------------------------------------
        kb_context, sources = build_multi_kb_context(
            kbs,
            chunk_count=chunk_count
        )
        logger.info(
            "Combined KB context built | kb_ids=%s | sources=%s | context_chars=%s",
            kb_ids,
            sources,
            len(kb_context) if kb_context else 0
        )

        if not kb_context:
            logger.warning("KB context is empty after processing | kb_ids=%s", kb_ids)
            return jsonify({
                "error": "No usable KB content found"
            }), 400

        # ---------------------------------------------
        # Prompt
        # ---------------------------------------------
        prompt = f"""
CRITICAL RULES:
- Return ONLY valid JSON
- No markdown
- No explanations
- EXACTLY {num_functionalities} items
- User-facing capabilities only

Combined Knowledge Base Context:
\"\"\"
{kb_context}
\"\"\"

Output:
{{
  "functionalities": [
    "Capability one",
    "Capability two"
  ]
}}
"""

        response = decision_llm.invoke(prompt)
        output_text = response.content.strip()
        logger.info("LLM response received for KB functionalities | kb_ids=%s", kb_ids)

        parsed = json.loads(output_text)
        functionalities = parsed.get("functionalities", [])

        # ---------------------------------------------
        # Safety guards
        # ---------------------------------------------
        if not isinstance(functionalities, list):
            raise ValueError("Invalid response format")

        functionalities = functionalities[:num_functionalities]

        while len(functionalities) < num_functionalities:
            functionalities.append(
                "Answer user questions using the available knowledge bases"
            )

        logger.info(
            "Returning KB functionalities response | kb_ids=%s | functionality_count=%s",
            kb_ids,
            len(functionalities)
        )

        return jsonify({
            "knowledge_base_ids": kb_ids,
            "context_sources": sources,
            "num_functionalities": num_functionalities,
            "chunk_count": chunk_count,
            "functionalities": functionalities
        })

    except json.JSONDecodeError:
        logger.exception("Invalid JSON from LLM while generating KB functionalities")
        return jsonify({"error": "Invalid JSON from LLM"}), 500

    except Exception as e:
        logger.exception("KB functionality generation failed")
        return jsonify({"error": str(e)}), 500






def extract_email_body(payload) -> str:
    try:
        body = ""
        mime_type = payload.get("mimeType", "")
        if mime_type == "text/plain" and payload.get("body", {}).get("data"):
            body += base64.urlsafe_b64decode(payload["body"]["data"]).decode(errors="ignore")
        elif mime_type == "text/html" and payload.get("body", {}).get("data") and not body:
            html_body = base64.urlsafe_b64decode(payload["body"]["data"]).decode(errors="ignore")
            body += BeautifulSoup(html_body, "html.parser").get_text(separator="\n")
        elif mime_type.startswith("multipart") and "parts" in payload:
            for part in payload["parts"]:
                body += extract_email_body(part)
        return body.strip()
    except Exception as e:
        logger.error(f"Failed to extract email body: {e}")
        return ""

def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from a PDF file using pdfplumber."""
    try:
        if not pdf_path or not os.path.exists(pdf_path):
            return ""
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
            return text.strip()
    except Exception as e:
        logger.error(f"Failed to extract text from PDF {pdf_path}: {e}")
        return ""

def fetch_rfq_emails():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        print(f"AAAAAAABBBBBBBBBBBBBBBB")
        gmail_tool = GmailTool(
            tenant_id=tenant_id,
            credentials_file="client_secret.json",
            redirect_uri=redirect_uri,
            auth_mode="manual"  # Must match Google Cloud
        )
        service = gmail_tool.authenticate()
        print(f"AAAAAAAAAAAAAAAAAAAAAAAAAAA---->{service}")
        results = service.users().messages().list(
            userId="me", q='is:unread subject:"RFQ"'
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            logger.info("No unread RFQ emails found")
            return []

        fetched_folders = []

        for msg in messages:
            try:
                msg_id = msg["id"]
                logger.info(f"Processing message ID: {msg_id}")
                message = service.users().messages().get(
                    userId="me", id=msg_id, format="full"
                ).execute()

                headers = message["payload"]["headers"]
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
                sender = next((h["value"] for h in headers if h["name"] == "From"), "")
                body = extract_email_body(message["payload"])

                # Create RFQ folder and input folder for attachments
                rfq_id = str(uuid.uuid4())
                rfq_folder = os.path.join(STORAGE_DIR, rfq_id)
                input_folder = os.path.join(rfq_folder, "input")
                os.makedirs(input_folder, exist_ok=True)

                excel_path = None
                pdf_paths = []  # Store multiple PDF paths

                for part in message["payload"].get("parts", []):
                    logger.info(f"parts of message: {message['payload'].get('parts')}")
                    if part.get("filename"):
                        att_id = part["body"].get("attachmentId")
                        if att_id:
                            attachment = service.users().messages().attachments().get(
                                userId="me", messageId=msg_id, id=att_id
                            ).execute()
                            file_data = base64.urlsafe_b64decode(attachment["data"])
                            file_path = os.path.join(input_folder, part["filename"])
                            with open(file_path, "wb") as f:
                                f.write(file_data)

                            if part["filename"].endswith((".xlsx", ".xls")):
                                excel_path = file_path
                            elif part["filename"].endswith(".pdf"):
                                pdf_paths.append(file_path)

                # Extract text from all PDFs
                pdf_texts = []
                for pdf_path in pdf_paths:
                    pdf_text = extract_pdf_text(pdf_path)
                    if pdf_text:
                        pdf_texts.append({"file": pdf_path, "text": pdf_text})

                # Mark as read
                service.users().messages().modify(
                    userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
                ).execute()

                # Store RFQ metadata
                data = {
                    "rfq_id": rfq_id,
                    "subject": subject,
                    "from": sender,
                    "email_text": body,
                    "excel_path": excel_path,
                    "pdf_paths": pdf_paths,  # Store list of PDF paths
                    "pdf_text": pdf_texts  # Store list of extracted PDF texts
                }

                with open(os.path.join(rfq_folder, "rfq.json"), "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                fetched_folders.append(rfq_folder)
                logger.info(f"Fetched RFQ email from {sender} saved to folder {rfq_folder}")

            except Exception as e:
                logger.error(f"Failed processing message {msg.get('id')}: {e}")

        return fetched_folders

    except Exception as e:
        logger.error(f"Error fetching RFQ emails: {e}")
        return []



@multi_agents_blueprint.route("/rfq/process", methods=["Get"])
@jwt_required()
def process_rfq():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        
        if not tenant_id:
            return jsonify({"error": "Missing tenant_id"}), 400

        rfq_folders = fetch_rfq_emails()
        if not rfq_folders:
            return jsonify({"message": "No unread RFQ emails found"}), 404

        processed_results = []
        for folder in rfq_folders:
            try:
                if os.path.exists(folder):
                    # Instantiate RFQProcessor for the folder
                    processor = RFQProcessor(input_folder=folder)
                    # Run the workflow
                    result = processor.run()
                    processed_results.append({
                        "folder": folder,
                        "result": result.get("result", ""),
                        "emails": result.get("emails", [])
                    })
                else:
                    logger.error(f"Folder does not exist: {folder}")
                    processed_results.append({
                        "folder": folder,
                        "result": f"Folder {folder} does not exist",
                        "emails": []
                    })
            except Exception as e:
                logger.error(f"Failed processing folder {folder}: {e}")
                processed_results.append({
                    "folder": folder,
                    "result": f"Error processing folder: {str(e)}",
                    "emails": []
                })

        response = {
            "tenant_id": tenant_id,
            "processed_count": len(processed_results),
            "processed_rfqs": processed_results
        }

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"RFQ process API failed: {e}")
        return jsonify({"error": str(e)}), 500














from app.models.new_models.custom_bot import CustomBotNew
from app.models import db

from collections import defaultdict
from app.models import db, ToolAuthorization ,Tools


def normalize_tool_name(name: str) -> str:
    """
    Converts:
    - Jnanic_MCP_Gmail → gmail
    - Gmail → gmail
    - GSheets → gsheets
    """
    value = (name or "").lower().replace("jnanic_mcp_", "").strip()
    return value.replace("_", "").replace("-", "").replace(" ", "")



DEFAULT_TOOLS = {"tavily"}


def get_all_tools_with_enabled_status(tenant_id):
    """
    Returns:
        all_tool_names -> list[str]  (used for LLM generation)
        enabled_tool_names -> set[str] (used for marking selected=True)
    """

    # 1️⃣ Fetch all global tools
    all_tools = Tools.query.filter_by(del_flg=False).all()

    # 2️⃣ Fetch tenant-authorized tools
    auth_tools = ToolAuthorization.query.filter_by(
        tenant_id=tenant_id,
        del_flag=False
    ).all()

    connection_map = defaultdict(list)

    for auth in auth_tools:
        base_tool = normalize_tool_name(auth.tool_name)
        connection_map[base_tool].append(auth)

    all_tool_names = []
    enabled_tool_names = set()

    for tool in all_tools:
        base_tool = normalize_tool_name(tool.tool_name)
        all_tool_names.append(tool.tool_name.lower())

        is_default = base_tool in DEFAULT_TOOLS
        has_connection = base_tool in connection_map

        if is_default or has_connection:
            enabled_tool_names.add(tool.tool_name.lower())

    return all_tool_names, enabled_tool_names




@multi_agents_blueprint.route(
    "/bots/<int:bot_id>/generate-config",
    methods=["POST"]
)
@jwt_required()
def generate_bot_configuration(bot_id):

    try:
        # ---------------------------------------------------
        # 1. AUTH
        # ---------------------------------------------------
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return jsonify({"error": "Unauthorized"}), 401

        bot = CustomBotNew.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not bot:
            return jsonify({"error": "Bot not found"}), 404
        
        

        # ---------------------------------------------------
        # 2. PREVENT RE-GENERATION
        # ---------------------------------------------------
        if bot.core_features and bot.instructions:
            logger.info(f"Returning existing config | bot_id={bot_id}")
            return jsonify({
                "message": "Configuration already generated",
                "functionalities": bot.core_features,
                "instructions": bot.instructions
            }), 200

        # ---------------------------------------------------
        # 3. VALIDATE PERSONALIZATION
        # ---------------------------------------------------
        if not bot.industry or not bot.purpose or not bot.bot_name:
            return jsonify({
                "error": "Bot must complete personalization before generation"
            }), 400

        # ---------------------------------------------------
        # 4. FETCH TOOLS (ALL + ENABLED)
        # ---------------------------------------------------
        all_tools, enabled_tools = get_all_tools_with_enabled_status(tenant_id)

        if not all_tools:
            return jsonify({
                "error": "No tools found in catalog"
            }), 400

        logger.info(
            f"Generating config | bot_id={bot_id} | all_tools={all_tools}"
        )

        # ---------------------------------------------------
        # 5. GENERATE FUNCTIONALITIES FOR ALL TOOLS
        # ---------------------------------------------------
        routing_prompt = f"""
CRITICAL RULES:
- Return ONLY valid JSON
- No markdown
- No explanations
- Use EXACT tool names from the list as JSON keys
- Every tool MUST have exactly ONE functionality
- Do NOT skip any tool

Industry: {bot.industry.value}
Tools: {json.dumps(all_tools)}

Output format:
{{
  "gmail": ["Send and manage professional emails"],
  "calendar": ["Schedule meetings and reminders"]
}}
"""

        response = decision_llm.invoke(routing_prompt)
        raw_functionalities = json.loads(response.content.strip())

        # ---------------------------------------------------
        # 6. NORMALIZE FOR UI (selected flag logic)
        # ---------------------------------------------------
        normalized_functionalities = {}

        for tool in all_tools:

            feature_list = (
                raw_functionalities.get(tool)
                or raw_functionalities.get(tool.lower())
                or []
            )

            if not feature_list:
                feature_list = [f"Perform {tool} related actions"]

            normalized_functionalities[tool] = [
                {
                    "label": feature_list[0],
                    "selected": tool in enabled_tools
                }
            ]

        # ---------------------------------------------------
        # 7. GENERATE INSTRUCTIONS
        # ---------------------------------------------------
        func_list = "\n".join(
            f"- {v[0]['label']}" for v in normalized_functionalities.values()
        )

        instructions_prompt = f"""
Generate exactly {MAX_DYNAMIC_INSTRUCTIONS} concise, action-oriented instructions
for the chatbot "{bot.bot_name}".

Bot Purpose:
{bot.purpose}

Functionalities:
{func_list}

Rules:
- Each instruction must be ONE short sentence.
- Maximum 15 words per instruction.
- Start with an action verb.
- Be specific to the domain and use-case.
- Do NOT include confirmation, failure handling, or support escalation rules.
- Do NOT repeat generic chatbot behavior.
- No numbering.
- No explanations.
"""

        instruction_response = decision_llm.invoke(instructions_prompt)

        
        # ---------------------------
        # STATIC INSTRUCTIONS FIRST
        # ---------------------------

        static_instructions = [
            {
                "id": idx + 1,
                "question": text,
                "selected": True
            }
            for idx, text in enumerate(STATIC_INSTRUCTIONS)
        ]

        # ---------------------------
        # DYNAMIC INSTRUCTIONS
        # ---------------------------

        dynamic_instructions = [
            {
                "id": idx + len(static_instructions) + 1,
                "question": line.strip(),
                "selected": True
            }
            for idx, line in enumerate(
                instruction_response.content.strip().split("\n")
            )
            if line.strip()
        ][:MAX_DYNAMIC_INSTRUCTIONS]

        # ---------------------------
        # FINAL MERGED LIST
        # ---------------------------

        final_instructions = static_instructions + dynamic_instructions

        # ---------------------------------------------------
        # 8. SAVE TO DB
        # ---------------------------------------------------
        bot.core_features = normalized_functionalities
        bot.instructions = final_instructions

        db.session.commit()

        logger.info(f"Bot config generated | bot_id={bot_id}")

        # ---------------------------------------------------
        # 9. RESPONSE
        # ---------------------------------------------------
        return jsonify({
            "message": "Configuration generated successfully",
            "functionalities": normalized_functionalities,
            "instructions": final_instructions
        }), 200

    except json.JSONDecodeError:
        logger.error(f"Invalid JSON from LLM | bot_id={bot_id}")
        return jsonify({"error": "Invalid JSON from LLM"}), 500

    except Exception:
        db.session.rollback()
        logger.exception(f"Unexpected error | bot_id={bot_id}")
        return jsonify({"error": "Failed to generate configuration"}), 500
