"""
agent_import_routes.py
Blueprint: /agents/import

Endpoints:
  POST /agents/import/validate  — dry-run, no DB write
  POST /agents/import/create    — full pipeline: parse → validate → create
"""

import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt

from app.services.agent_import_service import AgentImportService

logger = logging.getLogger(__name__)

agent_import_blueprint = Blueprint("agent_import", __name__)

ALLOWED_EXTENSIONS = {".json", ".zip", ".py", ".js"}


def _get_tenant_id():
    claims = get_jwt()
    return claims.get("tenant_id")


def _validate_file(request_obj):
    """Returns (file, error_response) — one of them is None."""
    file = request_obj.files.get("file")
    if not file:
        return None, jsonify({
            "status": "error",
            "message": "No file provided. Send a multipart/form-data request with key 'file'."
        }), 400

    import os
    ext = os.path.splitext((file.filename or "").lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        return None, jsonify({
            "status": "error",
            "message": (
                f"Unsupported file type '{ext}'. "
                f"Allowed: {sorted(ALLOWED_EXTENSIONS)}"
            )
        }), 400

    return file, None, None


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 1: Validate Only (dry-run, no DB write)
# POST /agents/import/validate
# ─────────────────────────────────────────────────────────────────────────────
@agent_import_blueprint.route("/validate", methods=["POST"])
@jwt_required()
def validate_agent_import():
    """
    Accepts: multipart/form-data  { file: <agent.json | agent.zip | agent_config.py> }
    Returns:
      200  { valid: true,  warnings: [...], preview: {...} }
      422  { valid: false, errors:   [...], warnings: [...] }
    """
    tenant_id = _get_tenant_id()
    if not tenant_id:
        return jsonify({"status": "error", "message": "Tenant ID not found in token"}), 401

    file, error_response, status_code = _validate_file(request)
    if error_response:
        return error_response, status_code

    logger.info(
        "agent_import /validate: tenant_id=%s file='%s'",
        tenant_id, file.filename
    )

    svc = AgentImportService(tenant_id)
    result = svc.validate(file)

    http_status = 200 if result["valid"] else 422
    return jsonify(result), http_status


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 2: Full Import — parse → validate → create agent
# POST /agents/import/create
# ─────────────────────────────────────────────────────────────────────────────
@agent_import_blueprint.route("/create", methods=["POST"])
@jwt_required()
def import_and_create_agent():
    """
    Accepts: multipart/form-data  { file: <agent.json | agent.zip | agent_config.py> }
    Returns:
      201  { status: "success", agent_id: <int>, agent: {...}, warnings: [...] }
      422  { status: "error",   errors:  [...],  warnings: [...] }
    """
    tenant_id = _get_tenant_id()
    if not tenant_id:
        return jsonify({"status": "error", "message": "Tenant ID not found in token"}), 401

    file, error_response, status_code = _validate_file(request)
    if error_response:
        return error_response, status_code

    logger.info(
        "agent_import /create: tenant_id=%s file='%s'",
        tenant_id, file.filename
    )

    svc = AgentImportService(tenant_id)
    result = svc.import_agent(file)

    if result["status"] == "success":
        return jsonify(result), 201
    else:
        return jsonify(result), 422
