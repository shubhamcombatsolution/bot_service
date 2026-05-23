"""
tool_validation_routes.py

Validates tool credentials during external agent import.
This endpoint is called by agent_validator.

URL:
POST /tools/validate
"""

import logging
import requests
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

tool_validation_blueprint = Blueprint(
    "tool_validation",
    __name__,
    url_prefix="/tools"
)


# ============================================================
# 🔥 MAIN VALIDATION ENDPOINT
# ============================================================

@tool_validation_blueprint.route("/validate", methods=["POST"])
def validate_tool_credentials():
    """
    Expected payload:
    {
        "tool_name": "gmail",
        "credentials": {...}
    }
    """

    try:
        data = request.get_json() or {}

        tool_name = (data.get("tool_name") or "").lower()
        creds = data.get("credentials") or {}

        if not tool_name:
            return jsonify({"valid": False, "message": "tool_name missing"}), 400

        if not isinstance(creds, dict):
            return jsonify({"valid": False, "message": "credentials must be object"}), 400

        # ====================================================
        # ROUTE TO SPECIFIC VALIDATORS
        # ====================================================

        if tool_name in ("gmail", "gcalendar", "gsheets"):
            return _validate_google_token(creds)

        if tool_name == "hubspot":
            return _validate_hubspot_token(creds)

        if tool_name == "gmaps":
            return _validate_gmaps_key(creds)

        # default — unknown tool
        return jsonify({
            "valid": True,
            "message": f"No runtime validation configured for {tool_name}"
        }), 200

    except Exception as e:
        logger.exception("Tool validation failed")
        return jsonify({"valid": False, "message": str(e)}), 500


# ============================================================
# 🔥 GOOGLE TOKEN VALIDATION
# ============================================================

def _validate_google_token(creds: dict):
    access_token = creds.get("access_token")

    if not access_token:
        return jsonify({"valid": False, "message": "missing access_token"}), 200

    try:
        resp = requests.get(
            "https://www.googleapis.com/oauth2/v3/tokeninfo",
            params={"access_token": access_token},
            timeout=5,
        )

        if resp.status_code != 200:
            return jsonify({
                "valid": False,
                "message": "Google token invalid or expired"
            }), 200

        return jsonify({
            "valid": True,
            "message": "Google token valid"
        }), 200

    except Exception as e:
        return jsonify({"valid": False, "message": str(e)}), 200


# ============================================================
# 🔥 HUBSPOT VALIDATION
# ============================================================

def _validate_hubspot_token(creds: dict):
    access_token = creds.get("access_token")

    if not access_token:
        return jsonify({"valid": False, "message": "missing access_token"}), 200

    try:
        resp = requests.get(
            "https://api.hubapi.com/oauth/v1/access-tokens/" + access_token,
            timeout=5,
        )

        if resp.status_code != 200:
            return jsonify({
                "valid": False,
                "message": "HubSpot token invalid"
            }), 200

        return jsonify({
            "valid": True,
            "message": "HubSpot token valid"
        }), 200

    except Exception as e:
        return jsonify({"valid": False, "message": str(e)}), 200


# ============================================================
# 🔥 GOOGLE MAPS VALIDATION
# ============================================================

def _validate_gmaps_key(creds: dict):
    api_key = creds.get("api_key")

    if not api_key:
        return jsonify({"valid": False, "message": "missing api_key"}), 200

    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": "New York", "key": api_key},
            timeout=5,
        )

        data = resp.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            return jsonify({
                "valid": False,
                "message": f"GMaps key invalid: {data.get('status')}"
            }), 200

        return jsonify({
            "valid": True,
            "message": "GMaps key valid"
        }), 200

    except Exception as e:
        return jsonify({"valid": False, "message": str(e)}), 200
