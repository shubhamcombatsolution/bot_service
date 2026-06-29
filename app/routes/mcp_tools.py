import os
import json
import requests
from flask import Blueprint, request, jsonify
from app.models.mcp_tools import McpTools
from app.models.tool_authorization import ToolAuthorization
from app.models.tool import Tools
from app.models.related_tools import RelatedTools
from app.database.DatabaseOperationPostgreSQL import db_session
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
mcp_blueprint = Blueprint("mcp_tools", __name__, url_prefix="/mcp_tools")


def _norm(value):
    return str(value or "").strip().lower()


def _as_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _authorization_scope_by_mcp(session, tenant_id):
    """
    Build authorization scope from tbl_tool_authorization.
    Returns: {normalized_mcp_name: set(normalized_tool_names)}
    """
    rows = (
        session.query(ToolAuthorization)
        .filter_by(tenant_id=tenant_id, del_flag=False)
        .all()
    )

    scope = {}
    for row in rows:
        mcp_json = _as_dict(row.mcp_json)
        if not mcp_json:
            continue

        mcp_name = _norm(mcp_json.get("mcp_name"))
        is_enabled = bool(mcp_json.get("tgi"))
        if not (mcp_name and is_enabled):
            continue

        if mcp_name not in scope:
            scope[mcp_name] = set()

        tool_name = _norm(getattr(row, "tool_name", None))
        if tool_name:
            scope[mcp_name].add(tool_name)

    return scope


def _enabled_mcp_names_from_authorization(session, tenant_id):
    """
    Read enabled MCP names from tbl_tool_authorization.mcp_json.
    Expected JSON shape: {"mcp_name": "jnanic.com", "tgi": true}
    """
    return set(_authorization_scope_by_mcp(session, tenant_id).keys())
# -----------------------------
# Add a new MCP
# -----------------------------
@mcp_blueprint.route("/", methods=["POST"])
@jwt_required()
def add_or_update_mcp():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return jsonify({
                "status": "error",
                "message": "Tenant ID missing in JWT",
                "data": {}
            }), 401

        data = request.get_json() or {}

        # =====================================================
        # SUPPORT BOTH OLD + NEW FORMAT
        # =====================================================

        mcp = data.get("mcp")

        if mcp:
            mcp_name = mcp.get("name")
            config = mcp.get("config", {})

            mcp_tools = data.get("tools", [])
            mcp_action_tools = data.get("action_tools", {})

        else:
            mcp_name = data.get("mcp_name")
            mcp_json = data.get("mcp_json", {})

            mcp_tools = data.get("mcp_tools", [])
            mcp_action_tools = data.get("mcp_action_tools", {})

            if mcp_json and isinstance(mcp_json, dict):
                mcp_servers = mcp_json.get("mcpServers", {})

                if mcp_servers:
                    first_name = list(mcp_servers.keys())[0]
                    first_server = mcp_servers[first_name]

                    # 🔥 auto-fix external name
                    if mcp_name == "external" or not mcp_name:
                        mcp_name = first_name

                    config = first_server
                else:
                    config = mcp_json
            else:
                config = {}

        # =====================================================
        # VALIDATION
        # =====================================================

        if not mcp_name:
            return jsonify({
                "status": "error",
                "message": "mcp_name is required",
                "data": {}
            }), 400

        if not config:
            return jsonify({
                "status": "error",
                "message": "MCP config is required",
                "data": {}
            }), 400

        transport = config.get("transport")

        # =====================================================
        # DETECT TYPE + URL
        # =====================================================

        # Allow caller to explicitly pass tool_type ("jnanic_mcp" | "external")
        # Otherwise derive it from the transport/url
        explicit_tool_type = str(data.get("tool_type") or "").strip().lower()

        if transport == "stdio":
            mcp_url = "stdio://local"
            inferred_tool_type = "jnanic_mcp"

        elif transport in ["http", "sse", "streamable-http"]:
            mcp_url = config.get("url")

            if not mcp_url:
                return jsonify({
                    "status": "error",
                    "message": "url required for remote MCP",
                    "data": {}
                }), 400

            # jnanic-hosted public gateway stays as jnanic_mcp
            if "mcp.jnanic.com" in mcp_url:
                inferred_tool_type = "jnanic_mcp"
            else:
                inferred_tool_type = "external"
        else:
            return jsonify({
                "status": "error",
                "message": f"Unsupported transport: {transport}",
                "data": {}
            }), 400

        # Explicit caller value takes priority over inferred
        final_tool_type = explicit_tool_type if explicit_tool_type in ("jnanic_mcp", "external", "mcp") else inferred_tool_type

        # =====================================================
        # DB OPERATIONS
        # =====================================================

        session = next(db_session())

        existing_mcp = (
            session.query(McpTools)
            .filter_by(tenant_id=tenant_id, mcp_name=mcp_name)
            .first()
        )

        if existing_mcp:
            existing_mcp.mcp_url = mcp_url
            existing_mcp.mcp_json = config
            existing_mcp.mcp_tools = mcp_tools
            existing_mcp.mcp_action_tools = mcp_action_tools
            existing_mcp.tool_type = final_tool_type

            message = "MCP updated successfully"
            status_code = 200

        else:
            new_mcp = McpTools(
                tenant_id=tenant_id,
                mcp_name=mcp_name,
                mcp_url=mcp_url,
                mcp_json=config,
                mcp_tools=mcp_tools,
                mcp_action_tools=mcp_action_tools,
                tool_type=final_tool_type,
            )
            session.add(new_mcp)

            message = "MCP created successfully"
            status_code = 201

        session.commit()

        return jsonify({
            "status": "success",
            "message": message,
            "data": {
                "mcp_name": mcp_name,
                "mcp_url": mcp_url
            }
        }), status_code

    except Exception as e:
        if "session" in locals():
            session.rollback()

        return jsonify({
            "status": "error",
            "message": str(e),
            "data": {}
        }), 500

    finally:
        if "session" in locals():
            session.close()         

@mcp_blueprint.route("/connect", methods=["POST"])
@jwt_required()
def connect_mcp_proxy():
    """
    Proxy MCP connection through the backend so the browser never calls the MCP
    service directly. This avoids CORS and localhost/origin issues.
    """
    try:
        data = request.get_json() or {}
        mcp_url = (data.get("mcp_url") or "https://mcp.jnanic.com/connect_mcp").strip()
        payload = data.get("payload") or {}
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not payload:
            return jsonify({
                "status": "error",
                "message": "payload is required",
                "data": {}
            }), 400

        if not tenant_id:
            return jsonify({
                "status": "error",
                "message": "tenant_id missing in JWT",
                "data": {}
            }), 401

        gmail_token_json = None
        gmail_token_found = False
        try:
            token_service_url = (
                "https://api.jnanic.com/tool/fetch_token_json"
            )
            token_resp = requests.post(
                token_service_url,
                json={
                    "tenant_id": tenant_id,
                    "tool_name": "gmail",
                },
                timeout=20,
            )
            if token_resp.status_code == 200:
                token_body = token_resp.json() or {}
                gmail_token_json = token_body.get("token_json")
                gmail_token_found = bool(gmail_token_json)
        except Exception:
            gmail_token_json = None
            gmail_token_found = False

        if gmail_token_json:
            mcp_servers = payload.get("mcpServers") or {}
            if mcp_servers:
                server_name, server_params = next(iter(mcp_servers.items()))
                server_env = server_params.setdefault("env", {})
                server_env.pop("GMAIL_ACCESS_TOKEN", None)
                server_env["GMAIL_TOKEN_FILE"] = json.dumps(gmail_token_json)
                server_env.setdefault(
                    "MONGO_URI",
                    "mongodb://demo_admin:demo_admin_pass@mongo:27017/?authSource=admin",
                )
                server_env.setdefault("MONGO_DB_NAME", "banking_demo")
                payload["mcpServers"][server_name] = server_params
        else:
            mcp_servers = payload.get("mcpServers") or {}
            if mcp_servers:
                server_name, server_params = next(iter(mcp_servers.items()))
                server_env = server_params.setdefault("env", {})
                server_env.setdefault(
                    "MONGO_URI",
                    "mongodb://demo_admin:demo_admin_pass@mongo:27017/?authSource=admin",
                )
                server_env.setdefault("MONGO_DB_NAME", "banking_demo")
                payload["mcpServers"][server_name] = server_params

        response = requests.post(mcp_url, json=payload, timeout=70)

        try:
            body = response.json()
        except Exception:
            body = {
                "status": "error" if response.status_code >= 400 else "success",
                "message": response.text,
                "data": {}
            }

        warnings = []
        tools = body.get("tools") if isinstance(body, dict) else None
        if gmail_token_found and isinstance(tools, dict) and "Gmail" not in tools:
            warnings.append(
                "Gmail token exists, but Gmail tools were not registered. Reconnect Gmail OAuth."
            )

        if warnings:
            body["warnings"] = warnings
            if "message" in body and isinstance(body["message"], str):
                body["message"] = f"{body['message']} Gmail reconnect required."

        return jsonify(body), response.status_code

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Failed to proxy MCP connection: {str(e)}",
            "data": {}
        }), 500

@mcp_blueprint.route("/connect_external", methods=["POST"])
@jwt_required()
def connect_external_mcp():
    """
    Proxy external MCP JSON (HTTP/SSE) without modifying payload.
    """

    try:
        data = request.get_json() or {}

        mcp_url = (
            data.get("mcp_url") or "https://mcp.jnanic.com/connect_mcp"
        ).strip()

        payload = data.get("payload")

        if not payload:
            # fallback: treat entire body as payload
            payload = data

        if not payload:
            return jsonify({
                "status": "error",
                "message": "payload or valid MCP body is required",
                "data": {}
            }), 400

        mcp_servers = payload.get("mcpServers")
        if not isinstance(mcp_servers, dict) or not mcp_servers:
            return jsonify({
                "status": "error",
                "message": "payload must contain valid 'mcpServers'",
                "data": {}
            }), 400

        # 🔹 Validate each server (important for external)
        for name, server in mcp_servers.items():

            if not isinstance(server, dict):
                return jsonify({
                    "status": "error",
                    "message": f"Invalid config for server '{name}'",
                    "data": {}
                }), 400

            # Must have URL for external MCP
            if not server.get("url"):
                return jsonify({
                    "status": "error",
                    "message": f"'url' is required for server '{name}'",
                    "data": {}
                }), 400

            transport = server.get("transport")
            if not transport:
                return jsonify({
                    "status": "error",
                    "message": f"'transport' is required for server '{name}'",
                    "data": {}
                }), 400 

            # Ensure headers is dict if present
            if "headers" in server and not isinstance(server["headers"], dict):
                return jsonify({
                    "status": "error",
                    "message": f"'headers' must be an object for server '{name}'",
                    "data": {}
                }), 400

        # 🚀 Forward request WITHOUT modifying payload
        response = requests.post(
            mcp_url,
            json=payload,
            timeout=70
        )

        # 🔹 Safe response parsing
        try:
            body = response.json()
        except Exception:
            body = {
                "status": "error" if response.status_code >= 400 else "success",
                "message": response.text,
                "data": {}
            }

        return jsonify(body), response.status_code

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"External MCP connection failed: {str(e)}",
            "data": {}
        }), 500
     
@mcp_blueprint.route("/tools", methods=["GET"], endpoint="get_mcps_v2")
@jwt_required()
def get_mcps():
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")
    session = next(db_session())
    try:
        # ── 1. Build connected-tool set from tbl_tool_authorization ──────────
        auth_rows = (
            session.query(ToolAuthorization)
            .filter_by(tenant_id=tenant_id, del_flag=False)
            .order_by(ToolAuthorization.id.asc())
            .all()
        )

        # Normalised set of tool names the tenant has connected
        connected_local_norms = {
            _norm(row.tool_name)
            for row in auth_rows
            if row.tool_name and (row.tool_type or "local").lower() == "local"
        }

        # ── 2. Load FULL local catalog (ALL tools, configured or not) ─────────
        local_catalog_rows = session.query(Tools).filter_by(del_flg=False).all()
        # Build list of ALL catalog tools with connected flag
        all_local_tools = []
        seen_local = set()
        for tool in local_catalog_rows:
            key = _norm(tool.tool_name)
            if not key or key in seen_local:
                continue
            seen_local.add(key)
            all_local_tools.append({
                "tool_name":        tool.tool_name,
                "tool_description": tool.tool_description or "",
                "tool_logo":        tool.tool_logo or "",
                "connected":        key in connected_local_norms,
            })

        # Build action map for local tools using tbl_related_tools
        related_rows = (
            session.query(RelatedTools, Tools)
            .join(Tools, RelatedTools.tool_id == Tools.tool_id)
            .filter(RelatedTools.del_flg == False)
            .all()
        )
        tool_action_map = {}
        for related, tool in related_rows:
            tool_action_map.setdefault(tool.tool_name, []).append(related.relationship_type)

        local_action_tools = {}
        for t in all_local_tools:
            actions = tool_action_map.get(t["tool_name"], [])
            if actions:
                local_action_tools[t["tool_name"]] = [
                    {
                        "action":      action,
                        "category":    t["tool_name"],
                        "description": t["tool_description"],
                        "parameters":  [],
                    }
                    for action in actions
                ]
            else:
                local_action_tools[t["tool_name"]] = [{
                    "action":      t["tool_name"],
                    "category":    t["tool_name"],
                    "description": t["tool_description"],
                    "parameters":  [],
                }]

        # ── 3. Legacy tgi-based scope (used only for MCP tool-name filtering) ─
        auth_scope = _authorization_scope_by_mcp(session, tenant_id)

        # Connected MCP tool names (for marking MCP tools as connected)
        connected_mcp_norms = {
            _norm(row.tool_name)
            for row in auth_rows
            if row.tool_name and (row.tool_type or "local").lower() == "mcp"
        }

        mcps = session.query(McpTools).filter_by(
            tenant_id=tenant_id,
            del_flag=False
        ).order_by(McpTools.created_at.desc()).all()

        data = []

        # Tools that run through local MCP server (not local_tool/call route)
        _mcp_native_tools = {"zoom"}

        builtin_tools = [t for t in all_local_tools if _norm(t["tool_name"]) not in _mcp_native_tools]
        mcp_native_tools = [t for t in all_local_tools if _norm(t["tool_name"]) in _mcp_native_tools]

        mcp_service_url = os.environ.get("MCP_BASE_URL", "http://mcp-service:5006")

        # ── Local tools group — builtin tools only ────────────────────────────
        if builtin_tools:
            builtin_action_tools = {k: v for k, v in local_action_tools.items()
                                    if _norm(k) not in _mcp_native_tools}
            data.append({
                "tool_type":        "local",
                "mcp_name":         "local",
                "mcp_tools":        [t["tool_name"] for t in builtin_tools],
                "mcp_action_tools": builtin_action_tools,
                "mcp_id":           0,
                "mcp_url":          "local://builtin",
                "tools_detail":     builtin_tools,
            })

        # ── MCP-native local tools group (e.g. Zoom) ─────────────────────────
        if mcp_native_tools:
            mcp_native_action_tools = {k: v for k, v in local_action_tools.items()
                                       if _norm(k) in _mcp_native_tools}
            data.append({
                "tool_type":        "local_mcp",
                "mcp_name":         "local_mcp",
                "mcp_tools":        [t["tool_name"] for t in mcp_native_tools],
                "mcp_action_tools": mcp_native_action_tools,
                "mcp_id":           -1,
                "mcp_url":          f"{mcp_service_url}/call_tool",
                "tools_detail":     mcp_native_tools,
            })

        for mcp in mcps:
            all_tools  = mcp.mcp_tools or []
            all_actions = mcp.mcp_action_tools or {}

            # Mark each tool as connected based on tbl_tool_authorization
            mcp_tool_type = str(getattr(mcp, "tool_type", None) or "jnanic_mcp").strip().lower()

            # No filtering — show ALL tools in this MCP catalog
            # connected flag is informational only
            tools_detail = [
                {
                    "tool_name": t,
                    "connected": _norm(t) in connected_mcp_norms,
                }
                for t in all_tools
            ]

            if not all_tools:
                continue

            data.append({
                "tool_type":        mcp_tool_type,
                "mcp_name":         mcp.mcp_name,
                "mcp_tools":        all_tools,          # ALL tools, no filter
                "mcp_action_tools": all_actions,        # ALL actions
                "mcp_id":           mcp.id,
                "mcp_url":          mcp.mcp_url,
                "tools_detail":     tools_detail,       # per-tool connected flag
            })

        return jsonify({
            "status": "success",
            "message": "Configured MCP tools retrieved successfully",
            "data": data
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Failed to retrieve MCP Tools: {str(e)}",
            "data": []
        })
    finally:
        session.close()

# -----------------------------
# Update MCP Tools
# -----------------------------
@mcp_blueprint.route("/<int:mcp_id>", methods=["PUT"])
@jwt_required()
def update_mcp_tools(mcp_id):
    try:
        data = request.json
        session = next(db_session())
        try:
            mcp = session.query(McpTools).get(mcp_id)
            if not mcp:
                return jsonify({"status": "error", "message": "MCP not found"}), 404

            # Ensure tool_id is a single integer
            tool_id = data.get("tool_id")
            if tool_id is not None:
                tool_id = int(tool_id)
                mcp.tool_id = tool_id

            # action_tools can still be a list of strings
            action_tools = data.get("action_tools")
            if action_tools:
                if isinstance(action_tools, str):
                    action_tools = [action_tools]
                mcp.action_tools = action_tools

            session.commit()

            return jsonify({
                "status": "success",
                "message": "MCP tools updated successfully",
                "data": {
                    "tool_id": mcp.tool_id,
                    "action_tools": mcp.action_tools
                }
            }), 200
        except Exception as e:
            session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# -----------------------------
# Get MCP Details
# -----------------------------
@mcp_blueprint.route("/", methods=["GET"])
@jwt_required()
def get_mcp_tools():
    session = None
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return jsonify({
                "status": "error",
                "message": "Tenant ID missing in JWT",
                "data": {}
            }), 401

        session = next(db_session())

        # 1) Local + MCP authorization rows (single-tool connections)
        auth_rows = (
            session.query(ToolAuthorization)
            .filter_by(tenant_id=tenant_id, del_flag=False)
            .order_by(ToolAuthorization.id.asc())
            .all()
        )

        # 2) MCP configuration rows (grouped tool bundles)
        mcps = (
            session.query(McpTools)
            .filter_by(tenant_id=tenant_id, del_flag=False)
            .order_by(McpTools.mcp_name.asc())
            .all()
        )

        data = []

        # Local tools showcase
        for row in auth_rows:
            row_tool_type = str(row.tool_type or "local").strip().lower()
            if row_tool_type == "mcp":
                continue
            data.append({
                "tool_type": row_tool_type,   # ← from DB, not hardcoded
                "tool_id": row.id,
                "tool_name": row.tool_name,
                "tools": [
                    {
                        "tool_id": row.id,
                        "tool_name": row.tool_name,
                        "tool_description": "",
                        "tool_logo": ""
                    }
                ]
            })

        # MCP tools showcase
        for mcp in mcps:
            tools = []
            selected_tools = mcp.mcp_tools or []
            action_tools = mcp.mcp_action_tools or {}
            selected_tools_set = {_norm(t) for t in selected_tools if _norm(t)}

            for tool_name, actions in action_tools.items():
                if selected_tools_set and _norm(tool_name) not in selected_tools_set:
                    continue
                first_action = actions[0] if actions else {}
                tools.append({
                    "tool_id": f"{mcp.id}-{tool_name}",
                    "tool_name": tool_name,
                    "tool_description": first_action.get("description", ""),
                    "tool_logo": ""
                })

            # If no action map available, still expose selected tool names.
            if not tools:
                for tool_name in selected_tools:
                    tools.append({
                        "tool_id": f"{mcp.id}-{tool_name}",
                        "tool_name": tool_name,
                        "tool_description": "",
                        "tool_logo": ""
                    })

            data.append({
                "tool_type": str(getattr(mcp, "tool_type", None) or "jnanic_mcp").strip().lower(),
                "mcp_id": mcp.id,
                "mcp_name": mcp.mcp_name,
                "tool_name": mcp.mcp_name,
                "mcp_url": mcp.mcp_url,
                "tools": tools
            })

        return jsonify({
            "status": True,
            "message": "MCP configurations fetched successfully",
            "data": data
        }), 200

    except Exception as e:
        if session:
            session.rollback()

        return jsonify({
            "status": "error",
            "message": str(e),
            "data": []
        }), 500

    finally:
        if session:
            session.close()
