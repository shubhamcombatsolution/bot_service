from flask import Blueprint, request, jsonify, current_app

whatsapp_bp = Blueprint('whatsapp', __name__)

# DEPRECATED: This file used a hardcoded BOT_ID and Twilio TwiML to respond to
# WhatsApp messages, completely bypassing the workflow engine. All WhatsApp
# traffic now goes through:
#   /webhook/whatsapp/<trigger_node_id>  (webhook_routes.py → WorkflowExecutor)
#
# Do NOT re-register any routes here. The blueprint is kept so app-factory
# imports don't break; remove it from app registration when convenient.