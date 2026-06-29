# app/routes/local_tool_routes.py
"""
Local tool execution endpoint.

Called by LangGraph when tools_config contains endpoint="local://..."
This bypasses MCP entirely and calls GmailTool / CalendarTool / HubSpotTool
Python classes directly using the tenant's OAuth token from tbl_tool_authorization.

POST /local_tool/call
{
    "tool_name":  "send_gmail",
    "category":   "Gmail",
    "parameters": { "to": "...", "subject": "...", "body": "..." },
    "tenant_id":  "178"
}
"""

import os
from flask import Blueprint, request, jsonify
from logging_config import setup_logging

logger = setup_logging("local_tool_routes", level="DEBUG")

local_tool_blueprint = Blueprint("local_tool", __name__)

CLIENT_SECRET_PATH = os.getenv("GOOGLE_CLIENT_SECRET_PATH", "client_secret.json")
REDIRECT_URI       = os.getenv("GOOGLE_REDIRECT_URI", "https://jnanic.com/auth/callback")


# ── Category → canonical key mapping ──────────────────────────────────────────
_CATEGORY_MAP = {
    "gmail":    "gmail",
    "gcalendar": "calendar",
    "calendar": "calendar",
    "gsheets":  "sheets",
    "sheets":   "sheets",
    "hubspot":  "hubspot",
}


def _canonical(category: str) -> str:
    raw = str(category).strip().lower()
    # If category is namespaced like "Gcalendar.create_event", extract "gcalendar"
    if "." in raw:
        raw = raw.split(".", 1)[0]
    return _CATEGORY_MAP.get(raw, raw)


# ── Lazy tool loader (one instance per tenant per request) ────────────────────
def _get_gmail_tool(tenant_id):
    from Tools.GmailTool import GmailTool
    return GmailTool(
        credentials_file=CLIENT_SECRET_PATH,
        redirect_uri=REDIRECT_URI,
        tenant_id=tenant_id,
    )


def _get_calendar_tool(tenant_id):
    from Tools.CalendarTool import CalendarTool
    return CalendarTool(
        credentials_file=CLIENT_SECRET_PATH,
        redirect_uri=REDIRECT_URI,
        auth_mode="manual",
        tenant_id=tenant_id,
    )


def _get_hubspot_tool(tenant_id):
    from Tools.HubspotTool import HubSpotTool
    return HubSpotTool(
        tenant_id=tenant_id,
        client_id=os.getenv("HUBSPOT_CLIENT_ID"),
        client_secret=os.getenv("HUBSPOT_CLIENT_SECRET"),
        redirect_uri="https://jnanic.com/Admin/Tools",
    )


# ── Main dispatch ─────────────────────────────────────────────────────────────
@local_tool_blueprint.route("/call", methods=["POST"])
def call_local_tool():
    """
    Dispatch a local tool action directly via Python tool classes.
    No MCP server involved.
    """
    try:
        data       = request.get_json(force=True) or {}
        tool_name  = str(data.get("tool_name") or "").strip()
        category   = str(data.get("category")  or "").strip()
        parameters = data.get("parameters") or {}
        tenant_id  = data.get("tenant_id")

        if not tool_name:
            return jsonify({"error": "tool_name is required"}), 400
        if not tenant_id:
            return jsonify({"error": "tenant_id is required"}), 400

        # Strip "Category." prefix if present — e.g. "Gcalendar.create_event" → "create_event"
        # LangGraph namespaces tool calls as "Category.action"
        if "." in tool_name:
            action_name = tool_name.split(".", 1)[1]
        else:
            action_name = tool_name

        logger.info(
            "[LOCAL_TOOL] call | tenant=%s category=%s tool=%s action=%s params=%s",
            tenant_id, category, tool_name, action_name,
            list(parameters.keys()) if isinstance(parameters, dict) else parameters,
        )

        canon = _canonical(category or tool_name)

        # ── Gmail ──────────────────────────────────────────────────────────
        if canon == "gmail":
            tool = _get_gmail_tool(tenant_id)
            result = _dispatch_gmail(tool, action_name, parameters)

        # ── Calendar ──────────────────────────────────────────────────────
        elif canon == "calendar":
            tool = _get_calendar_tool(tenant_id)
            result = _dispatch_calendar(tool, action_name, parameters)

        # ── HubSpot ───────────────────────────────────────────────────────
        elif canon == "hubspot":
            tool = _get_hubspot_tool(tenant_id)
            result = _dispatch_hubspot(tool, action_name, parameters)

        # ── Sheets ────────────────────────────────────────────────────────
        elif canon == "sheets":
            tool = _get_gmail_tool(tenant_id)   # GSheets uses same OAuth creds
            result = _dispatch_sheets(tool, action_name, parameters, tenant_id)

        else:
            logger.warning("[LOCAL_TOOL] Unknown category: %s", category)
            return jsonify({"error": f"Unknown local tool category: {category}"}), 400

        logger.info("[LOCAL_TOOL] success | tool=%s result_type=%s", tool_name, type(result).__name__)
        return jsonify({"result": result}), 200

    except Exception as e:
        logger.exception("[LOCAL_TOOL] Unexpected error | tool=%s | %s", tool_name, e)
        return jsonify({"error": str(e)}), 500


# ── Gmail dispatcher ──────────────────────────────────────────────────────────
def _dispatch_gmail(tool, tool_name: str, params: dict):
    action = tool_name.lower()

    if action == "send_gmail":
        return tool.send_email(
            to=params["to"],
            subject=params.get("subject", "(No Subject)"),   # default if agent omits
            body=params["body"],
            html=params.get("html", False),
            cc=params.get("cc"),
            bcc=params.get("bcc"),
        )
    elif action == "list_gmail_messages":
        return tool.list_messages(
            query=params.get("query", ""),
            max_results=params.get("max_results", 10),
        )
    elif action == "read_gmail_message":
        return tool.read_message(message_id=params["message_id"])
    elif action == "read_unread_gmail_messages":
        return tool.list_unread_messages(max_results=params.get("max_results", 10))
    elif action == "search_gmail_messages":
        return tool.search_messages(
            from_email=params.get("from_email", ""),
            after_date=params.get("after_date", ""),
            has_attachment=params.get("has_attachment", False),
            max_results=params.get("max_results", 10),
        )
    elif action == "draft_gmail":
        return tool.create_draft(
            to=params["to"],
            subject=params["subject"],
            body=params["body"],
        )
    elif action == "get_email_from_token":
        return tool.get_authenticated_email()
    elif action == "mark_as_read":
        return tool.mark_as_read(message_id=params["message_id"])
    elif action == "mark_as_unread":
        return tool.mark_as_unread(message_id=params["message_id"])
    elif action == "delete_gmail_message":
        return tool.delete_message(message_id=params["message_id"])
    else:
        raise ValueError(f"Unknown Gmail action: {tool_name}")


# ── Calendar dispatcher ───────────────────────────────────────────────────────
def _dispatch_calendar(tool, tool_name: str, params: dict):
    action = tool_name.lower()

    if action == "create_event":
        return tool.book_appointment(
            title=params["title"],
            start_time_str=params.get("start_time_str"),
            location=params.get("location", ""),
            description=params.get("description", ""),
            duration=params.get("duration", 1),
            attendees=params.get("attendees"),
            time_zone=params.get("time_zone", "Asia/Kolkata"),
            date=params.get("date"),
            time=params.get("time"),
        )
    elif action == "list_events":
        return tool.list_events(
            max_results=params.get("max_results", 10),
            time_zone=params.get("time_zone", "Asia/Kolkata"),
        )
    elif action == "update_event":
        return tool.update_event(
            event_id=params["event_id"],
            title=params.get("title"),
            start_time_str=params.get("start_time_str"),
            location=params.get("location"),
            description=params.get("description"),
            duration=params.get("duration"),
            attendees=params.get("attendees"),
        )
    elif action == "delete_event":
        return tool.delete_event(event_id=params["event_id"])
    elif action == "get_free_busy":
        return tool.get_free_busy(
            time_min=params["time_min"],
            time_max=params["time_max"],
            time_zone=params.get("time_zone", "Asia/Kolkata"),
        )
    else:
        raise ValueError(f"Unknown Calendar action: {tool_name}")


# ── HubSpot dispatcher ────────────────────────────────────────────────────────
def _dispatch_hubspot(tool, tool_name: str, params: dict):
    action = tool_name.lower()

    if action in ("create_contact", "hubspot_create_contact"):
        return tool.create_contact(**params)
    elif action in ("update_contact", "hubspot_update_contact"):
        return tool.update_contact(**params)
    elif action in ("get_contact", "hubspot_get_contact"):
        return tool.get_contact(**params)
    else:
        raise ValueError(f"Unknown HubSpot action: {tool_name}")


# ── GSheets dispatcher ────────────────────────────────────────────────────────
def _dispatch_sheets(tool, tool_name: str, params: dict, tenant_id):
    from Tools.GSheetsTool import GSheetsTool
    sheets_tool = GSheetsTool(tenant_id=tenant_id)
    action = tool_name.lower()

    if action == "read_spreadsheet":
        return sheets_tool.read(
            spreadsheet_id=params["spreadsheet_id"],
            range_name=params["range_name"],
        )
    elif action == "write_spreadsheet":
        return sheets_tool.write(
            spreadsheet_id=params["spreadsheet_id"],
            range_name=params["range_name"],
            values=params["values"],
        )
    elif action == "append_spreadsheet":
        return sheets_tool.append(
            spreadsheet_id=params["spreadsheet_id"],
            range_name=params["range_name"],
            values=params["values"],
        )
    elif action == "list_spreadsheets":
        return sheets_tool.list_spreadsheets()
    elif action == "create_sheet":
        return sheets_tool.create_sheet(
            sheet_name=params["sheet_name"],
            spreadsheet_id=params.get("spreadsheet_id"),
        )
    else:
        raise ValueError(f"Unknown Sheets action: {tool_name}")
