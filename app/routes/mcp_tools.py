from flask import Blueprint, request, jsonify
from app.models.mcp_tools import McpTools
from app.models.tool_authorization import ToolAuthorization
from app.models.tool import Tools
from app.database.DatabaseOperationPostgreSQL import db_session
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
mcp_blueprint = Blueprint("mcp_tools", __name__, url_prefix="/mcp_tools")
import json
import requests
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError


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
        # DETECT TYPE (NO DB STORAGE)
        # =====================================================

        if transport == "stdio":
            mcp_url = "stdio://local"

        elif transport in ["http", "sse", "streamable-http"]:
            mcp_url = config.get("url")

            if not mcp_url:
                return jsonify({
                    "status": "error",
                    "message": "url required for remote MCP",
                    "data": {}
                }), 400
        else:
            return jsonify({
                "status": "error",
                "message": f"Unsupported transport: {transport}",
                "data": {}
            }), 400

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

            message = "MCP updated successfully"
            status_code = 200

        else:
            new_mcp = McpTools(
                tenant_id=tenant_id,
                mcp_name=mcp_name,
                mcp_url=mcp_url,
                mcp_json=config,
                mcp_tools=mcp_tools,
                mcp_action_tools=mcp_action_tools
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
        # Include local tool connections for tool-config page.
        auth_rows = (
            session.query(ToolAuthorization)
            .filter_by(tenant_id=tenant_id, del_flag=False)
            .order_by(ToolAuthorization.id.asc())
            .all()
        )

        local_tool_names = []
        for row in auth_rows:
            if (row.tool_type or "local").lower() != "local":
                continue
            if row.tool_name:
                local_tool_names.append(str(row.tool_name).strip())

        # Build local catalog lookup for descriptions.
        local_catalog_rows = session.query(Tools).filter_by(del_flg=False).all()
        local_catalog = {_norm(t.tool_name): t for t in local_catalog_rows}

        unique_local_tools = []
        seen_local = set()
        for tool_name in local_tool_names:
            key = _norm(tool_name)
            if not key or key in seen_local:
                continue
            seen_local.add(key)
            unique_local_tools.append(tool_name)

        local_action_tools = {}
        for tool_name in unique_local_tools:
            key = _norm(tool_name)
            tool_meta = local_catalog.get(key)
            local_action_tools[tool_name] = [{
                "action": tool_name,
                "category": tool_name,
                "description": getattr(tool_meta, "tool_description", "") if tool_meta else "",
                "parameters": []
            }]

        auth_scope = _authorization_scope_by_mcp(session, tenant_id)
        enabled_mcp_names = set(auth_scope.keys())

        mcps = session.query(McpTools).filter_by(
            tenant_id=tenant_id,
            del_flag=False
        ).order_by(McpTools.created_at.desc()).all()

        data = []
        if unique_local_tools:
            data.append({
                "tool_type": "local",
                "mcp_name": "local",
                "mcp_tools": unique_local_tools,
                "mcp_action_tools": local_action_tools,
                "mcp_id": 0,
                "mcp_url": "local://builtin",
            })
        for mcp in mcps:
            # show only configured+enabled MCPs from tbl_tool_authorization JSON
            if _norm(mcp.mcp_name) not in enabled_mcp_names:
                continue

            selected_tools = mcp.mcp_tools or []
            all_actions = mcp.mcp_action_tools or {}
            filtered_actions = {}

            selected_tools_norm = {_norm(t) for t in selected_tools if _norm(t)}
            authorized_tools = auth_scope.get(_norm(mcp.mcp_name), set())

            # If tool names exist in authorization rows for this MCP, enforce them.
            if authorized_tools:
                selected_tools_norm = selected_tools_norm.intersection(authorized_tools)

            for tool_name, actions in all_actions.items():
                if _norm(tool_name) in selected_tools_norm:
                    filtered_actions[tool_name] = actions

            filtered_tool_names = [t for t in selected_tools if _norm(t) in selected_tools_norm]
            if not filtered_tool_names:
                continue

            data.append({
                "tool_type": "mcp",
                "mcp_name": mcp.mcp_name,
                "mcp_tools": filtered_tool_names,
                "mcp_action_tools": filtered_actions,
                "mcp_id": mcp.id,
                "mcp_url": mcp.mcp_url,
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
            if (row.tool_type or "local").lower() == "mcp":
                continue
            data.append({
                "tool_type": "local",
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
                "tool_type": "mcp",
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
