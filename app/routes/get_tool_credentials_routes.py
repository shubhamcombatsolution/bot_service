from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, verify_jwt_in_request
from sqlalchemy import func

from app.database.DatabaseOperationPostgreSQL import db_session
from app.models.tool_authorization import ToolAuthorization
from app.services.channel_credentials_service import get_legacy_tool_credentials


# Compatibility placeholder blueprint.
# Some environments still import and register this module even though
# credential APIs are handled elsewhere.
tool_blueprint = Blueprint("tool_credential_legacy", __name__)


@tool_blueprint.route("/health", methods=["GET"])
def tool_credential_health():
    return jsonify({
        "status": "success",
        "message": "tool credential legacy routes active",
    }), 200


@tool_blueprint.route("/<tool_name>/credentials", methods=["GET"])
def get_tool_credentials(tool_name: str):
    tenant_id = _resolve_tenant_id()
    if not tenant_id:
        return jsonify({
            "status": "error",
            "message": "tenant_id missing. Pass ?tenant_id=<id> or use JWT with tenant_id claim.",
            "data": {},
        }), 400

    session = next(db_session())
    try:
        credentials = get_legacy_tool_credentials(session, int(tenant_id), tool_name)
        if not credentials:
            auth = (
                session.query(ToolAuthorization)
                .filter(
                    ToolAuthorization.tenant_id == int(tenant_id),
                    func.lower(ToolAuthorization.tool_name) == tool_name.lower(),
                    ToolAuthorization.del_flag.is_(False),
                )
                .order_by(ToolAuthorization.updated_at.desc())
                .first()
            )
            credentials = auth.token_json if auth and isinstance(auth.token_json, dict) else {}

        if not credentials:
            return jsonify({
                "status": "error",
                "message": f"No credentials found for tool '{tool_name}' and tenant_id={tenant_id}",
                "credentials": {},
            }), 404

        return jsonify({
            "status": "success",
            "message": "Credentials fetched successfully",
            "credentials": credentials,
        }), 200
        
    finally:
        session.close()


@tool_blueprint.route("/<tool_name>/credentials", methods=["PUT", "POST"])
def upsert_tool_credentials(tool_name: str):
    tenant_id = _resolve_tenant_id()
    if not tenant_id:
        return jsonify({
            "status": "error",
            "message": "tenant_id missing. Pass ?tenant_id=<id> or use JWT with tenant_id claim.",
            "data": {},
        }), 400

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({
            "status": "error",
            "message": "Payload must be a JSON object",
            "data": {},
        }), 400

    incoming_creds = body.get("credentials", body)
    if not isinstance(incoming_creds, dict):
        return jsonify({
            "status": "error",
            "message": "credentials must be an object",
            "data": {},
        }), 400

    # Avoid storing meta keys as credential fields when caller sends raw body.
    credentials = dict(incoming_creds)
    credentials.pop("tool_type", None)
    credentials.pop("mcp_url", None)
    credentials.pop("mcp_json", None)
    credentials.pop("mcp_name", None)
    credentials.pop("tgi", None)

    session = next(db_session())
    try:
        auth = (
            session.query(ToolAuthorization)
            .filter(
                ToolAuthorization.tenant_id == int(tenant_id),
                func.lower(ToolAuthorization.tool_name) == tool_name.lower(),
                ToolAuthorization.del_flag.is_(False),
            )
            .order_by(ToolAuthorization.updated_at.desc())
            .first()
        )

        tool_type = body.get("tool_type")
        mcp_url = body.get("mcp_url")
        mcp_json = body.get("mcp_json")
        mcp_name = body.get("mcp_name")
        tgi = body.get("tgi")

        existing_mcp_json = auth.mcp_json if auth and isinstance(auth.mcp_json, dict) else {}
        incoming_mcp_json = mcp_json if isinstance(mcp_json, dict) else {}
        merged_mcp_json = {**existing_mcp_json, **incoming_mcp_json}
        if mcp_name is not None:
            merged_mcp_json["mcp_name"] = mcp_name
        if tgi is not None:
            merged_mcp_json["tgi"] = bool(tgi)

        if auth:
            auth.token_json = credentials
            if isinstance(tool_type, str) and tool_type.strip():
                auth.tool_type = tool_type.strip().lower()
            if mcp_url is not None:
                auth.mcp_url = mcp_url
            if merged_mcp_json:
                auth.mcp_json = merged_mcp_json
            elif mcp_json is not None:
                auth.mcp_json = None
            message = "Credentials updated successfully"
        else:
            auth = ToolAuthorization(
                tenant_id=int(tenant_id),
                tool_name=tool_name,
                token_json=credentials,
                tool_type=(tool_type.strip().lower() if isinstance(tool_type, str) and tool_type.strip() else "local"),
                mcp_url=mcp_url,
                mcp_json=(merged_mcp_json if merged_mcp_json else None),
                del_flag=False,
            )
            session.add(auth)
            message = "Credentials saved successfully"

        session.commit()

        return jsonify({
            "status": "success",
            "message": message,
            "tool_name": tool_name,
            "tenant_id": int(tenant_id),
            "credentials": auth.token_json or {},
        }), 200
    except Exception as e:
        session.rollback()
        return jsonify({
            "status": "error",
            "message": str(e),
            "data": {},
        }), 500
    finally:
        session.close()


def _resolve_tenant_id():
    tenant_id = request.args.get("tenant_id")
    if tenant_id and str(tenant_id).isdigit():
        return int(tenant_id)

    try:
        verify_jwt_in_request(optional=True)
        claims = get_jwt()
        jwt_tenant_id = claims.get("tenant_id")
        if jwt_tenant_id and str(jwt_tenant_id).isdigit():
            return int(jwt_tenant_id)
    except Exception:
        pass

    return None
