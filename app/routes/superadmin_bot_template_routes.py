"""
superadmin_bot_template_routes.py

Super Admin endpoints for Bot Templates.

Endpoints:
  GET    /bot_template/                          – list all templates
  POST   /bot_template/                          – convert a bot → template
  GET    /bot_template/<template_id>             – get single template
  PUT    /bot_template/status/<template_id>      – toggle active / inactive
  DELETE /bot_template/<template_id>             – soft-delete a template
  GET    /bot_template/superadmin/bots           – list all bots of tenant 0001
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt

import json as _json

from app.models import db
from app.models.new_models.custom_bot import CustomBotNew
from app.models.bot_template import BotTemplate
from app.models.bot_diagram import BotDiagram
from app.database.DatabaseOperationPostgreSQL import db_session
from logging_config import setup_logging

logger = setup_logging("superadmin-bot-template", level="DEBUG")

bot_template_blueprint = Blueprint(
    "bot_template",
    __name__,
    url_prefix="/bot_template",
)

SUPER_ADMIN_TENANT_ID = 1  # Tenant whose tenant_id maps to "0001" in the system

# ── Auth helper ───────────────────────────────────────────────────────────────

def is_super_admin():
    claims = get_jwt()
    role = (claims.get("role") or "").lower()
    return role in ("superadmin", "super_admin")


# ─────────────────────────────────────────────────────────────────────────────
# GET /bot_template/superadmin/bots
# Returns LIVE bots belonging to the Super Admin tenant (tenant_id = 0001)
# Query params:
#   - status: "Live" | "Draft" | "Created" | "Paused" (optional filter, defaults to "Live")
# ─────────────────────────────────────────────────────────────────────────────
@bot_template_blueprint.route("/superadmin/bots", methods=["GET"])
@jwt_required()
def get_superadmin_bots():
    """
    List bots that belong to the Super Admin tenant (tenant_id = 0001).
    These are the bots available for conversion into templates.

    Query params:
      - status: Filter by bot status (default: "Live")
    """
    if not is_super_admin():
        return jsonify({"status": False, "message": "Super admin access required"}), 403

    # Get optional status filter, default to "Live"
    status_filter = request.args.get("status", "Live")
    logger.info(f"📥 get_superadmin_bots called with status_filter={status_filter}")

    session = next(db_session())
    try:
        # Import the enum to use for filtering
        from app.models.new_models.custom_bot import BotStatusEnum

        query = session.query(CustomBotNew).filter_by(tenant_id=SUPER_ADMIN_TENANT_ID, del_flg=False)

        # Filter by status if provided
        if status_filter:
            try:
                status_enum = BotStatusEnum[status_filter.upper()]
                query = query.filter_by(bot_status=status_enum)
                logger.info(f"🟢 Filtering for {status_filter} status bots")
            except KeyError:
                logger.warning(f"⚠️ Invalid status: {status_filter}, ignoring filter")

        bots = query.order_by(CustomBotNew.created_at.desc()).all()
        logger.info(f"📊 Found {len(bots)} bots with status={status_filter}")

        # Collect bot_ids that have already been converted to a non-deleted template
        all_bot_ids = [b.bot_id for b in bots]
        templated_bot_ids = set()
        if all_bot_ids:
            rows = (
                session.query(BotTemplate.source_bot_id)
                .filter(
                    BotTemplate.source_bot_id.in_(all_bot_ids),
                    BotTemplate.del_flg == False,
                )
                .all()
            )
            templated_bot_ids = {row.source_bot_id for row in rows}

        logger.info(f"🏷️ {len(templated_bot_ids)} bot(s) already converted to templates: {templated_bot_ids}")

        data = []
        for bot in bots:
            # Skip bots that have already been converted to a template
            if bot.bot_id in templated_bot_ids:
                logger.info(f"⏭️ Skipping bot {bot.bot_id} ({bot.bot_name}) — already a template")
                continue

            # channel is a ValueEnum — get its value safely
            channel_val = bot.channel.value if hasattr(bot.channel, 'value') else str(bot.channel or '')

            data.append({
                "bot_id":        bot.bot_id,
                "bot_name":      bot.bot_name,
                "status":        bot.bot_status.value if hasattr(bot.bot_status, 'value') else str(bot.bot_status or ''),
                "channel":       channel_val,
                "purpose":       bot.purpose,
                "avatar":        bot.avatar,
                "industry":      bot.industry.value if bot.industry else None,
                "tone_of_voice": bot.tone_of_voice.value if bot.tone_of_voice else None,
                "core_features": bot.core_features or {},
                "instructions":  bot.instructions or [],
                "completed_step":bot.completed_step,
                "created_at":    bot.created_at.isoformat() if bot.created_at else None,
                "updated_at":    bot.updated_at.isoformat() if bot.updated_at else None,
            })

        logger.info(f"✅ Returning {len(data)} bots to client ({len(templated_bot_ids)} excluded — already templates)")
        return jsonify({"status": True, "data": data, "total": len(data)}), 200

    except Exception as e:
        logger.error(f"❌ get_superadmin_bots error: {e}", exc_info=True)
        return jsonify({"status": False, "message": "Failed to fetch Super Admin bots"}), 500
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# GET /bot_template/
# List all bot templates (not deleted)
# ─────────────────────────────────────────────────────────────────────────────
@bot_template_blueprint.route("/", methods=["GET"])
@jwt_required()
def list_bot_templates():
    """
    Return all bot templates.
    Query params:
      - status: "Active" | "Inactive"  (optional filter)
    """
    status_filter = request.args.get("status")  # optional
    logger.info(f"📥 list_bot_templates called with status_filter={status_filter}")

    session = next(db_session())
    try:
        query = session.query(BotTemplate).filter_by(del_flg=False)

        logger.info(f"📊 Total non-deleted templates: {session.query(BotTemplate).filter_by(del_flg=False).count()}")

        if status_filter == "Active":
            query = query.filter_by(is_active=True)
            logger.info("🟢 Filtering for ACTIVE templates only")
        elif status_filter == "Inactive":
            query = query.filter_by(is_active=False)
            logger.info("🔴 Filtering for INACTIVE templates only")
        else:
            logger.info("📋 No status filter - returning all templates")

        templates = query.order_by(BotTemplate.created_at.desc()).all()
        logger.info(f"✅ Found {len(templates)} templates matching filter")

        return jsonify({
            "status": True,
            "data":   [t.to_dict() for t in templates],
            "total":  len(templates),
        }), 200

    except Exception as e:
        logger.error(f"list_bot_templates error: {e}", exc_info=True)
        return jsonify({"status": False, "message": "Failed to fetch bot templates"}), 500
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# POST /bot_template/
# Convert a bot into a template
# Body: { bot_id, template_name, template_description? }
# ─────────────────────────────────────────────────────────────────────────────
@bot_template_blueprint.route("/", methods=["POST"])
@jwt_required()
def create_bot_template():
    """
    Convert a Super Admin bot into a reusable bot template.
    Snapshots all bot data into tbl_bot_templates.
    """
    if not is_super_admin():
        return jsonify({"status": False, "message": "Super admin access required"}), 403

    body = request.get_json(silent=True) or {}
    bot_id           = body.get("bot_id")
    template_name    = (body.get("template_name") or "").strip()
    template_desc    = (body.get("template_description") or "").strip()

    if not bot_id:
        return jsonify({"status": False, "message": "bot_id is required"}), 400
    if not template_name:
        return jsonify({"status": False, "message": "template_name is required"}), 400

    session = next(db_session())
    try:
        # ── Fetch source bot ─────────────────────────────────────────────
        bot = (
            session.query(CustomBotNew)
            .filter_by(bot_id=bot_id, del_flg=False)
            .first()
        )
        if not bot:
            return jsonify({"status": False, "message": f"Bot {bot_id} not found"}), 404

        # ── Guard: bot must belong to the Super Admin tenant ─────────────
        if bot.tenant_id != SUPER_ADMIN_TENANT_ID:
            return jsonify({
                "status": False,
                "message": "Only Super Admin bots can be converted to templates",
            }), 400

        # ── Guard: prevent duplicate template for the same bot ───────────
        existing = (
            session.query(BotTemplate)
            .filter_by(source_bot_id=bot_id, del_flg=False)
            .first()
        )
        if existing:
            return jsonify({
                "status": False,
                "message": (
                    f"Bot '{bot.bot_name}' has already been converted to template "
                    f"'{existing.template_name}'. Delete or deactivate that template first."
                ),
                "existing_template_id": existing.template_id,
            }), 409

        # ── Fetch bot workflow/diagram + extract tool names ──────────────
        workflow_data = None
        tool_names    = []
        try:
            diagram = (
                session.query(BotDiagram)
                .filter_by(bot_id=bot_id)
                .order_by(BotDiagram.created_at.desc())
                .first()
            )
            if diagram:
                if hasattr(diagram, "diagram_data"):
                    workflow_data = diagram.diagram_data

                # parse diagram_json to collect agent_ids from nodes
                raw_json = getattr(diagram, "diagram_json", None)
                if raw_json:
                    try:
                        diag_data = _json.loads(raw_json) if isinstance(raw_json, str) else raw_json
                        nodes = diag_data.get("nodes", [])
                        agent_ids = []
                        for node in nodes:
                            aid = (
                                (node.get("data") or {}).get("agent_id") or
                                (node.get("data") or {}).get("agentId")
                            )
                            if aid:
                                agent_ids.append(int(aid))

                        # query McpTools for those agents
                        if agent_ids:
                            from app.models.mcp_agent_tools import McpAgentTools
                            mcp_rows = (
                                session.query(McpAgentTools)
                                .filter(
                                    McpAgentTools.agent_id.in_(agent_ids),
                                    McpAgentTools.del_flag == False,
                                )
                                .all()
                            )
                            tool_names = list({row.tool_name for row in mcp_rows if row.tool_name})
                    except Exception as parse_err:
                        logger.warning(f"Could not parse diagram JSON for tool names: {parse_err}")
        except Exception as diag_err:
            logger.warning(f"Could not fetch diagram for bot {bot_id}: {diag_err}")

        # ── Build template ───────────────────────────────────────────────
        channel_val = bot.channel.value if hasattr(bot.channel, 'value') else str(bot.channel or '')

        logger.info(f"📋 Building template from bot {bot_id} ({bot.bot_name})")

        template = BotTemplate(
            template_name        = template_name,
            template_description = template_desc or None,
            source_bot_id        = bot.bot_id,
            source_bot_name      = bot.bot_name,
            # snapshot bot fields
            bot_name             = bot.bot_name,
            avatar               = bot.avatar,
            purpose              = bot.purpose,
            bot_type             = channel_val,   # CustomBotNew has no bot_type; store channel instead
            channel              = channel_val,
            tone_of_voice        = bot.tone_of_voice.value if bot.tone_of_voice else None,
            industry             = bot.industry.value if bot.industry else None,
            core_features        = bot.core_features or {},
            instructions         = bot.instructions or [],
            kb_ids               = bot.kb_ids or [],
            kb_functionalities   = bot.kb_functionalities,
            theme                = bot.theme,
            disclaimer_text      = bot.disclaimer_text,
            background_image     = bot.background_image,
            colors               = bot.colors or {},
            greeting_type        = bot.greeting_type,
            greeting_message     = bot.greeting_message,
            workflow_data        = workflow_data,
            is_active            = True,
        )

        session.add(template)
        session.commit()
        session.refresh(template)

        logger.info(f"✅ Bot template created: id={template.template_id} name={template.template_name!r}")
        logger.info(f"   is_active={template.is_active} | del_flg={template.del_flg} | status={'ACTIVE' if template.is_active else 'INACTIVE'}")

        return jsonify({
            "status":  True,
            "message": "Bot template created successfully",
            "data":    template.to_dict(),
        }), 201

    except Exception as e:
        session.rollback()
        logger.error(f"create_bot_template error: {e}", exc_info=True)
        return jsonify({"status": False, "message": "Failed to create bot template"}), 500
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# GET /bot_template/<template_id>
# Get a single template by ID
# ─────────────────────────────────────────────────────────────────────────────
@bot_template_blueprint.route("/<int:template_id>", methods=["GET"])
@jwt_required()
def get_bot_template(template_id):
    """Return a single bot template by its ID."""
    session = next(db_session())
    try:
        template = (
            session.query(BotTemplate)
            .filter_by(template_id=template_id, del_flg=False)
            .first()
        )
        if not template:
            return jsonify({"status": False, "message": "Template not found"}), 404

        return jsonify({"status": True, "data": template.to_dict()}), 200

    except Exception as e:
        logger.error(f"get_bot_template error: {e}", exc_info=True)
        return jsonify({"status": False, "message": "Failed to fetch template"}), 500
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# PUT /bot_template/status/<template_id>
# Toggle Active / Inactive
# Body: { status: "Active" | "Inactive" }
# ─────────────────────────────────────────────────────────────────────────────
@bot_template_blueprint.route("/status/<int:template_id>", methods=["PUT"])
@jwt_required()
def update_bot_template_status(template_id):
    """Toggle the active/inactive status of a bot template."""
    if not is_super_admin():
        return jsonify({"status": False, "message": "Super admin access required"}), 403

    body      = request.get_json(silent=True) or {}
    new_status = (body.get("status") or "").strip()

    if new_status not in ("Active", "Inactive"):
        return jsonify({"status": False, "message": "status must be 'Active' or 'Inactive'"}), 400

    session = next(db_session())
    try:
        template = (
            session.query(BotTemplate)
            .filter_by(template_id=template_id, del_flg=False)
            .first()
        )
        if not template:
            return jsonify({"status": False, "message": "Template not found"}), 404

        template.is_active = (new_status == "Active")
        session.commit()
        session.refresh(template)

        return jsonify({
            "status":  True,
            "message": f"Template marked as {new_status}",
            "data":    template.to_dict(),
        }), 200

    except Exception as e:
        session.rollback()
        logger.error(f"update_bot_template_status error: {e}", exc_info=True)
        return jsonify({"status": False, "message": "Failed to update template status"}), 500
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /bot_template/<template_id>
# Soft-delete a template
# ─────────────────────────────────────────────────────────────────────────────
@bot_template_blueprint.route("/<int:template_id>", methods=["DELETE"])
@jwt_required()
def delete_bot_template(template_id):
    """Soft-delete a bot template (sets del_flg = True)."""
    if not is_super_admin():
        return jsonify({"status": False, "message": "Super admin access required"}), 403

    session = next(db_session())
    try:
        template = (
            session.query(BotTemplate)
            .filter_by(template_id=template_id, del_flg=False)
            .first()
        )
        if not template:
            return jsonify({"status": False, "message": "Template not found"}), 404

        template.del_flg = True
        session.commit()

        logger.info(f"Bot template soft-deleted: id={template_id}")

        return jsonify({
            "status":  True,
            "message": "Template deleted successfully",
        }), 200

    except Exception as e:
        session.rollback()
        logger.error(f"delete_bot_template error: {e}", exc_info=True)
        return jsonify({"status": False, "message": "Failed to delete template"}), 500
    finally:
        session.close()
