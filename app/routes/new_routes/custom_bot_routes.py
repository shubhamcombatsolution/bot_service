from flask import Blueprint, request, jsonify, current_app, render_template, send_from_directory, abort, g
from werkzeug.utils import secure_filename
from app.models import db, CustomBotNew, Tenant, BaseAgent, Agent, LLM, ChatHistory, LoginUser
from app.models.whatsapp_cred import WhatsAppCred
from app.models.slack_cred import SlackCred
from app.models.new_models.custom_bot import ChannelEnum, ToneOfVoiceEnum, IndustryEnum, BotStatusEnum
from app.database.DatabaseOperationPostgreSQL import db_session
from MultiAgentSystem import MultiAgentSystem
import os
import json
import re
from datetime import datetime, timedelta
from os.path import basename
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
import ipaddress
from app.models.custombot_access_restriction import CustomBotAccessRestriction
from app.models.tenant_subscription import TenantSubscription
from functools import wraps
from flask_jwt_extended import (
    create_access_token,
    verify_jwt_in_request,
    jwt_required,
    get_jwt,
    get_jwt_identity
)

import socket
from app.models.knowledge_base import KnowledgeBase
from logging_config import setup_logging
from app.routes.helpers.custom_bot_utils import (
    validate_bot_access,  
    process_kb_functionalities,
    process_instructions,
    process_kb_ids,
    process_core_features,
    clean_enum_input,
    validate_customization_fields,
    handle_file_upload,
    process_access_restrictions,
    parse_enum,
    build_snapshot,
    resolve_bot_config
    
)
from app.routes.helpers.custom_bot_utils import ALLOWED_EXTENSIONS,UPLOAD_FOLDER,allowed_file
from app.routes.helpers.response_utils import success_response, error_response
from app.models.new_models.bot_versions import BotVersion
from app.routes.helpers.common_utils import compute_snapshot_hash,make_json_safe

CustomBotNewAccessRestriction = CustomBotAccessRestriction


# Define blueprint
custom_bot_blueprint_new = Blueprint('custom-bot-new', __name__)

logger = setup_logging("custom-bot-new", level="DEBUG")



@custom_bot_blueprint_new.route("/dropdown-data", methods=["GET"])
def get_dropdown_data():
    try:
        tones = [{"value": tone.value, "label": tone.value} for tone in ToneOfVoiceEnum]
        industries = [{"value": industry.value, "label": industry.value} for industry in IndustryEnum]
        return success_response(message = "Success", data = {"tones": tones, "industries": industries}, code = 200)
    except Exception as e:
        logger.error(f"Error fetching dropdown data: {str(e)}")
        return error_response(message = str(e), data = None, code = 500)



@custom_bot_blueprint_new.route("/suggest-bot-name", methods=["POST"])
@jwt_required()
def suggest_bot_name():
    """
    API to generate sequential bot names for a tenant.
    
    Request body:
    {
        "bot_name": "suraj"
    }
    
    Response:
    {
        "suggested_name": "suraj_01",
        "next_number": 1,
        "existing_variations": ["suraj_01", "suraj_02"]
    }
    """
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            logger.warning("Tenant ID missing in JWT")
            return error_response(message = "Tenant ID missing", data = None, code = 401)

        tenant = Tenant.query.filter_by(
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not tenant:
            logger.warning(f"Invalid tenant access | tenant_id={tenant_id}")
            return error_response(message = "Invalid tenant", data = None, code = 401)

        data = request.get_json() or {}
        base_bot_name = data.get("bot_name", "").strip()

        if not base_bot_name:
            logger.warning(f"Bot name missing | tenant_id={tenant_id}")
            return error_response(message = "bot_name is required", data = None, code = 400)

        if len(base_bot_name) < 2:
            logger.warning(f"Bot name too short | tenant_id={tenant_id}")
            return error_response(message = "bot_name must be at least 2 characters", data = None, code = 400)

        # Query existing bot names that match the pattern (exact match or with sequential suffix)
        # We'll use LIKE pattern to find names like "suraj", "suraj_01", "suraj_02", etc.
        search_pattern = f"{base_bot_name}%"
        
        existing_bots = CustomBotNew.query.filter(
            CustomBotNew.tenant_id == tenant_id,
            CustomBotNew.bot_name.ilike(search_pattern),
            CustomBotNew.del_flg == False
        ).all()

        logger.info(
            f"Found {len(existing_bots)} existing bots with similar name | "
            f"tenant_id={tenant_id} | base_name={base_bot_name}"
        )

        # Extract numbers from existing bot names
        existing_numbers = []
        existing_names = []
        
        for bot in existing_bots:
            existing_names.append(bot.bot_name)
            
            # Check if it's an exact match
            if bot.bot_name.lower() == base_bot_name.lower():
                existing_numbers.append(0)
            else:
                # Try to extract sequential number (e.g., "suraj_01" -> 1)
                remainder = bot.bot_name.lower()[len(base_bot_name):].lower()
                
                # Check if it matches the pattern _NN or -NN or NN
                if remainder.startswith("_") or remainder.startswith("-"):
                    try:
                        num = int(remainder[1:])
                        existing_numbers.append(num)
                    except ValueError:
                        pass
                else:
                    try:
                        # Direct number match (e.g., "suraj01")
                        num = int(remainder)
                        existing_numbers.append(num)
                    except ValueError:
                        pass

        # Check if exact name exists
        exact_exists = any(bot.bot_name.lower() == base_bot_name.lower() for bot in existing_bots)
        
        if not existing_numbers and not exact_exists:
            # No similar names found - can use the base name
            suggested_name = base_bot_name
            next_number = None
            message = f"Bot name '{suggested_name}' is available"
        else:
            # Find next available number
            if existing_numbers:
                max_number = max(existing_numbers)
                next_number = max_number + 1 if max_number > 0 else 1
            else:
                next_number = 1
            
            suggested_name = f"{base_bot_name}_{next_number:02d}"
            message = f"Suggested name: '{suggested_name}'"

        logger.info(
            f"Bot name suggestion | tenant_id={tenant_id} | "
            f"base_name={base_bot_name} | suggested={suggested_name}"
        )

        return success_response(
            message = "Success",
            data = {
                "suggested_name": suggested_name,
                "next_number": next_number,
                "existing_variations": sorted(existing_names),
                "message": message
            },
            code = 200
        )

    except Exception as e:
        logger.exception(f"Error suggesting bot name: {str(e)}")
        return error_response(message = f"Error: {str(e)}", data = None, code = 500)



@custom_bot_blueprint_new.route("/create", methods=["POST"])
@jwt_required()
def create_custombot():

    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            logger.warning("Tenant ID missing in JWT")
            return error_response(message = "Tenant ID missing", data = None, code = 401)

        tenant = Tenant.query.filter_by(
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not tenant:
            logger.warning(f"Invalid tenant access | tenant_id={tenant_id}")
            return error_response(message = "Invalid tenant", data = None, code = 401)

        data = request.get_json() or {}
        channel_value = data.get("channel")

        if not channel_value:
            logger.warning(f"Channel missing | tenant_id={tenant_id}")
            return error_response(message = "Channel is required", data = None, code = 400)

        try:
            channel_enum = ChannelEnum[channel_value.upper()]
        except KeyError:
            logger.warning(
                f"Invalid channel | tenant_id={tenant_id} | value={channel_value}"
            )
            return error_response(message = "Invalid channel", data = None, code = 400)

        new_bot = CustomBotNew(
            tenant_id=tenant_id,
            channel=channel_enum,
            bot_status=BotStatusEnum.DRAFT
        )

        db.session.add(new_bot)
        db.session.commit()

        logger.info(
            f"Bot created | bot_id={new_bot.bot_id} | tenant_id={tenant_id}"
        )

        return success_response(message = "Success", data = {
            "message": "Bot initialized successfully",
            "bot_id": new_bot.bot_id,
            "instance_id": new_bot.instance_id,
            "status": new_bot.bot_status.value
        }, code = 201)

    except Exception as e:
        db.session.rollback()
        logger.exception("Unexpected error while creating bot")
        return error_response(message = "Unexpected error occurred", data = None, code = 500)

@custom_bot_blueprint_new.route(
    "/<int:bot_id>/channel",
    methods=["PATCH"]
)
@jwt_required()
@validate_bot_access(
    allowed_status=[BotStatusEnum.DRAFT,BotStatusEnum.LIVE,BotStatusEnum.CREATED]  # Only editable in step 1 phase
)
def update_channel(bot_id):

    bot = g.bot
    logger.info(
        f"Channel update started | bot_id={bot.bot_id} | tenant_id={g.tenant.tenant_id}"
    )

    try:
        data = request.get_json() or {}

        channel_value = clean_enum_input(data.get("channel"))

        if not channel_value:
            logger.warning(
                f"Channel missing | bot_id={bot.bot_id}"
            )
            return error_response(message = "Channel is required", data = None, code = 400)

        try:
            channel_enum = ChannelEnum[channel_value.upper()]
        except KeyError:
            logger.warning(
                f"Invalid channel | bot_id={bot.bot_id} | value={channel_value}"
            )
            return error_response(message = "Invalid channel value", data = None, code = 400)

        # Prevent unnecessary update
        if bot.channel == channel_enum:
            logger.info(
                f"Channel unchanged | bot_id={bot.bot_id}"
            )
            return success_response(message = "Success", data = {
                "message": "Channel already set",
                "channel": bot.channel.value
            }, code = 200)

        bot.channel = channel_enum
        db.session.commit()

        logger.info(
            f"Channel updated successfully | bot_id={bot.bot_id} | channel={bot.channel.value}"
        )

        return success_response(message = "Success", data = {
            "message": "Channel updated successfully",
            "bot_id": bot.bot_id,
            "channel": bot.channel.value,
            "status": bot.bot_status.value
        }, code = 200)

    except Exception:
        db.session.rollback()
        logger.exception(
            f"Unexpected error while updating channel | bot_id={bot.bot_id}"
        )
        return error_response(message = "Unexpected error occurred", data = None, code = 500)


@custom_bot_blueprint_new.route(
    "/<int:bot_id>/personalization",
    methods=["POST", "PATCH"]
)
@jwt_required()
@validate_bot_access(
    allowed_status=[BotStatusEnum.DRAFT, BotStatusEnum.CREATED, BotStatusEnum.LIVE]
)
def personalization(bot_id):

    bot = g.bot
    logger.info(f"Personalization update started | bot_id={bot.bot_id}")

    try:
        # ----------------------------------------
        # Get Form Data (multipart/form-data)
        # ----------------------------------------
        data = request.form
        avatar_file = request.files.get("avatar")

        name = data.get("bot_name")
        tone = data.get("tone_of_voice")
        industry = data.get("industry")
        purpose = data.get("purpose")

        if isinstance(name, str):
            name = name.strip()

        if isinstance(purpose, str):
            purpose = purpose.strip()

        # ----------------------------------------
        # POST Required Validation
        # ----------------------------------------
        if request.method == "POST":

            required_fields = {
                "bot_name": name,
                "tone_of_voice": tone,
                "industry": industry,
                "purpose": purpose
            }

            for field, value in required_fields.items():
                if not value:
                    logger.warning(
                        f"Missing required field | bot_id={bot.bot_id} | field={field}"
                    )
                    return error_response(message = f"{field} is required", data = None, code = 400)


        # ----------------------------------------
        # BOT NAME VALIDATION
        # ----------------------------------------
        if name is not None:

            if not name:
                return error_response(message = "Bot name cannot be empty", data = None, code = 400)

            if len(name) < 3:
                return error_response(message = "Bot name must be at least 3 characters", data = None, code = 400)

            existing_bot = CustomBotNew.query.filter(
                CustomBotNew.tenant_id.in_(g.allowed_tenant_ids),
                CustomBotNew.bot_name.ilike(name),
                CustomBotNew.bot_id != bot.bot_id,
                CustomBotNew.del_flg == False
            ).first()

            if existing_bot:
                return error_response(message = "Bot name already exists", data = None, code = 400)

            bot.bot_name = name

        # ----------------------------------------
        # ENUM VALIDATION
        # ----------------------------------------
        try:
            if tone:
                bot.tone_of_voice = parse_enum(ToneOfVoiceEnum, tone, "tone_of_voice")

            if industry:
                bot.industry = parse_enum(IndustryEnum, industry, "industry")

        except ValueError as e:
            return error_response(message = str(e), data = None, code = 400)
        # ----------------------------------------
        # PURPOSE
        # ----------------------------------------
        if purpose is not None:
            if not purpose:
                return error_response(message = "Purpose cannot be empty", data = None, code = 400)
            bot.purpose = purpose

        # ----------------------------------------
        # AVATAR FILE HANDLING
        # ----------------------------------------
        if avatar_file:

            if avatar_file.filename == "":
                return error_response(message = "No selected file", data = None, code = 400)

            if not allowed_file(avatar_file.filename):
                return error_response(message = "Invalid file type", data = None, code = 400)

            os.makedirs(UPLOAD_FOLDER, exist_ok=True)

            filename = secure_filename(avatar_file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)

            avatar_file.save(file_path)

            bot.avatar = file_path

            logger.info(
                f"Avatar uploaded | bot_id={bot.bot_id} | filename={filename}"
            )

        db.session.commit()

        logger.info(f"Personalization saved | bot_id={bot.bot_id}")

        return success_response(message = "Success", data = {
            "message": "Personalization saved successfully",
            "status": bot.bot_status.value
        }, code = 200)

    except Exception:
        db.session.rollback()
        logger.exception(
            f"Unexpected error in personalization | bot_id={bot.bot_id}"
        )
        return error_response(message = "Unexpected error occurred", data = None, code = 500)





@custom_bot_blueprint_new.route(
    "/<int:bot_id>/knowledge-base",
    methods=["POST", "PATCH"]
)
@jwt_required()
@validate_bot_access(
    allowed_status=[BotStatusEnum.DRAFT, BotStatusEnum.CREATED,BotStatusEnum.LIVE]
)
def upsert_knowledge_base_step(bot_id):

    bot = g.bot
    data = request.get_json() or {}

    logger.info(
        f"KB step upsert started | bot_id={bot.bot_id} | method={request.method}"
    )

    try:

        # -------------------------
        # For POST → require kb_ids
        # -------------------------
        if request.method == "POST" and "kb_ids" not in data:
            return error_response(
                message="kb_ids is required",
                data=None,
                code=400
            )

        if request.method == "POST" and isinstance(data.get("kb_ids"), list) and len(data.get("kb_ids")) == 0:
            return error_response(
                message="kb_ids cannot be empty",
                data=None,
                code=400
            )

        # -------------------------
        # KB IDs
        # -------------------------
        if "kb_ids" in data:

            # Handle empty array explicitly (remove all KBs)
            if isinstance(data.get("kb_ids"), list) and len(data.get("kb_ids")) == 0:
                logger.info(
                    f"Clearing all KBs for bot | bot_id={bot.bot_id}"
                )
                bot.kb_ids = []

            else:
                kb_ids, error = process_kb_ids(
                    bot,
                    data.get("kb_ids"),
                    g.allowed_tenant_ids
                )

                if error:
                    return error_response(
                        message=error,
                        data=None,
                        code=400
                    )

                bot.kb_ids = kb_ids  # Replace, do NOT merge

        # -------------------------
        # KB Functionalities
        # -------------------------
        if "kb_functionalities" in data:
            functionalities, error = process_kb_functionalities(
                data.get("kb_functionalities")
            )

            if error:
                return error_response(
                    message=error,
                    data=None,
                    code=400
                )

            bot.kb_functionalities = functionalities

        db.session.commit()

        logger.info(f"KB step saved successfully | bot_id={bot.bot_id}")

        return success_response(
            message="Success",
            data={
                "message": "Knowledge base saved successfully",
                "bot_id": bot.bot_id,
                "kb_ids": bot.kb_ids or [],
                "kb_functionalities": bot.kb_functionalities or []
            },
            code=200
        )

    except Exception:
        db.session.rollback()
        logger.exception(
            f"Unexpected error updating KB | bot_id={bot.bot_id}"
        )
        return error_response(
            message="Unexpected error occurred",
            data=None,
            code=500
        )

@custom_bot_blueprint_new.route(
    "/<int:bot_id>/functionality",
    methods=["PATCH"]
)
@jwt_required()
@validate_bot_access(
    allowed_status=[BotStatusEnum.DRAFT, BotStatusEnum.CREATED,BotStatusEnum.LIVE]
)
def update_functionality(bot_id):

    bot = g.bot
    logger.info(
        f"Updating functionality | bot_id={bot.bot_id} | tenant_id={g.tenant.tenant_id}"
    )

    try:
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return error_response(
                message="Invalid JSON payload",
                data=None,
                code=400
            )

        updated_fields = []

        if "instructions" in data:
            cleaned, error = process_instructions(
                data.get("instructions")
            )
            if error:
                logger.warning(f"Instruction validation failed | bot_id={bot.bot_id}")
                return error_response(message = error, data = None, code = 400)
            bot.instructions = cleaned
            updated_fields.append("instructions")

        core_features_payload = None
        if "core_features" in data:
            core_features_payload = data.get("core_features")
        elif "core_feature" in data:
            core_features_payload = data.get("core_feature")
        elif "core_functionalities" in data:
            core_features_payload = data.get("core_functionalities")
        elif "fullFunctionalities" in data:
            # Backward-compatible payload support:
            # {
            #   "selectedFeatures": {...},
            #   "fullFunctionalities": {...}
            # }
            selected_features = data.get("selectedFeatures") or {}
            full_features = data.get("fullFunctionalities") or {}
            if not isinstance(full_features, dict):
                return error_response(
                    message="fullFunctionalities must be a dictionary",
                    data=None,
                    code=400
                )

            merged = {}
            for tool, all_feats in full_features.items():
                if not isinstance(all_feats, list):
                    continue

                selected_labels = {
                    f.get("label")
                    for f in (selected_features.get(tool, []) if isinstance(selected_features, dict) else [])
                    if isinstance(f, dict) and f.get("selected") is True
                }

                merged[tool] = [
                    {
                        "label": feat.get("label"),
                        "selected": feat.get("label") in selected_labels
                    }
                    for feat in all_feats
                    if isinstance(feat, dict) and feat.get("label")
                ]

            core_features_payload = merged

        if core_features_payload is not None:
            normalized, error = process_core_features(core_features_payload)

            if error:
                logger.warning(
                    f"Core feature validation failed | bot_id={bot.bot_id}"
                )
                return error_response(message = error, data = None, code = 400)

            bot.core_features = normalized
            updated_fields.append("core_features")

            logger.debug(
                f"Core features updated | bot_id={bot.bot_id}"
            )

        if not updated_fields:
            return error_response(
                message="At least one of instructions or core_features is required",
                data=None,
                code=400
            )
        
        # ---------------------------------------
        # STATUS TRANSITION
        # ---------------------------------------
        if bot.bot_status == BotStatusEnum.DRAFT:
            bot.bot_status = BotStatusEnum.CREATED
            logger.info(
                f"Bot status updated to CREATED | bot_id={bot.bot_id}"
            )


        db.session.commit()

        logger.info(f"Functionality update successful | bot_id={bot.bot_id}")

        return success_response(message = "Success", data = {
            "message": "Functionality updated successfully",
            "bot_id": bot.bot_id,
            "kb_functionalities": bot.kb_functionalities,
            "instructions": bot.instructions,
            "kb_ids": bot.kb_ids,
            "core_features": bot.core_features
        }, code = 200)

    except Exception:
        db.session.rollback()
        logger.exception(
            f"Unexpected error updating functionality | bot_id={bot.bot_id}"
        )
        return error_response(message = "Unexpected error occurred", data = None, code = 500)

    
@custom_bot_blueprint_new.route(
    "/bots/<int:bot_id>/configure-and-publish",
    methods=["POST"]
)
@jwt_required()
@validate_bot_access(
    allowed_status=[BotStatusEnum.CREATED, BotStatusEnum.LIVE]
)
def configure_bot(bot_id):

    bot = g.bot
    tenant = g.tenant

    try:
        logger.info(
            f"Configuring bot | bot_id={bot.bot_id} | tenant_id={tenant.tenant_id}"
        )

        # ---------------------------------------
        # FORM DATA
        # ---------------------------------------
        data = request.form
        files = request.files
        channel_value = clean_enum_input(data.get("channel"))
        whatsapp_credentials_raw = data.get("whatsapp_credentials")
        slack_credentials_raw = data.get("slack_credentials")

        # ---------------------------------------
        # RESOLVE CHANNEL + VALIDATE REQUIRED FIELDS
        # ---------------------------------------
        resolved_channel = (
            (channel_value or (bot.channel.value if bot.channel else "") or "")
            .strip()
            .lower()
        )
        is_channel_credentials_only = resolved_channel in {"whatsapp", "slack"}
        colors_json = bot.colors or {}
        if not is_channel_credentials_only:
            colors_json = validate_customization_fields(data)
        # colors_raw = data.get("colors")

        # try:
        #     colors_json = json.loads(colors_raw) if colors_raw else {}
        # except Exception:
        #     raise ValueError("Invalid colors JSON format")

        # ---------------------------------------
        # FILE HANDLING
        # ---------------------------------------
        avatar_filename = handle_file_upload(
            files.get("avatar"),
            "avatars"
        )

        bg_filename = handle_file_upload(
            files.get("background_image"),
            "backgrounds"
        )

        # ---------------------------------------
        # UPDATE BOT FIELDS
        # ---------------------------------------
        if not is_channel_credentials_only:
            bot.disclaimer_text = data.get("disclaimer_text")
            bot.purpose = data.get("purpose")
            bot.colors = colors_json
            bot.theme = data.get("theme") or "Theme 1"
            bot.position = data.get("position") or "bottom_right"
            bot.page_config = data.get("page_config") or "all_pages"
            specific_pages_raw = data.get("specific_pages")

            if specific_pages_raw:
                try:
                    bot.specific_pages = json.loads(specific_pages_raw)
                except Exception:
                    raise ValueError("Invalid specific_pages JSON format")
            else:
                bot.specific_pages = []

            bot.greeting_type = data.get("greeting_type", "dynamic")
            bot.greeting_message = data.get("greeting_message") or \
                "Hello! I'm your friendly assistant. How can I help you today?"

        if channel_value:
            bot.channel = parse_enum(ChannelEnum, channel_value, "channel")

        def _safe_str(value):
            return str(value).strip() if value is not None else ""

        def _validate_whatsapp_credentials(payload):
            errors = []
            existing = bot.whatsapp_cred
            existing_json = bot.whatsapp_credentials or {}

            phone_number_id = _safe_str(
                payload.get("phone_number_id")
                or payload.get("business_phone_number_id")
                or (existing.phone_number_id if existing else None)
                or existing_json.get("phone_number_id")
                or existing_json.get("business_phone_number_id")
            )
            business_account_id = _safe_str(
                payload.get("business_account_id")
                or payload.get("whatsapp_business_account_id")
                or (existing.business_account_id if existing else None)
                or existing_json.get("business_account_id")
                or existing_json.get("whatsapp_business_account_id")
            )
            access_token = _safe_str(
                payload.get("access_token")
                or payload.get("token")
                or payload.get("permanent_token")
                or (existing.access_token if existing else None)
                or existing_json.get("access_token")
                or existing_json.get("token")
                or existing_json.get("permanent_token")
            )
            verify_token = _safe_str(
                payload.get("verify_token")
                or payload.get("verifyToken")
                or (existing.verify_token if existing else None)
                or existing_json.get("verify_token")
                or existing_json.get("verifyToken")
            )
            graph_api_version = _safe_str(
                payload.get("api_version")
                or payload.get("graph_api_version")
                or (existing.graph_api_version if existing else None)
                or existing_json.get("api_version")
                or existing_json.get("graph_api_version")
                or "v19.0"
            )
            default_recipient_number = _safe_str(
                payload.get("default_recipient_number")
                or (existing.default_recipient_number if existing else None)
                or existing_json.get("default_recipient_number")
            )

            if not phone_number_id:
                errors.append({"field": "whatsapp_credentials.phone_number_id", "message": "phone_number_id is required"})
            if not business_account_id:
                errors.append({"field": "whatsapp_credentials.business_account_id", "message": "business_account_id is required"})
            if not access_token:
                errors.append({"field": "whatsapp_credentials.access_token", "message": "access_token is required"})
            if not verify_token:
                errors.append({"field": "whatsapp_credentials.verify_token", "message": "verify_token is required"})

            if graph_api_version and not re.fullmatch(r"v\d+\.\d+", graph_api_version):
                errors.append({
                    "field": "whatsapp_credentials.graph_api_version",
                    "message": "graph_api_version must be like v19.0"
                })

            if default_recipient_number and not re.fullmatch(r"\+?\d{8,15}", default_recipient_number):
                errors.append({
                    "field": "whatsapp_credentials.default_recipient_number",
                    "message": "default_recipient_number must be a valid phone number (8-15 digits, optional leading +)"
                })

            # Prevent reusing any WhatsApp credential field across bots in this tenant.
            if phone_number_id:
                phone_exists = (
                    db.session.query(WhatsAppCred.id)
                    .join(CustomBotNew, WhatsAppCred.bot_id == CustomBotNew.bot_id)
                    .filter(
                        CustomBotNew.tenant_id == tenant.tenant_id,
                        CustomBotNew.del_flg == False,
                        WhatsAppCred.bot_id != bot.bot_id,
                        WhatsAppCred.phone_number_id == phone_number_id,
                    )
                    .first()
                )
                if phone_exists:
                    errors.append({
                        "field": "whatsapp_credentials.phone_number_id",
                        "message": "phone_number_id already exists"
                    })

            if business_account_id:
                ba_exists = (
                    db.session.query(WhatsAppCred.id)
                    .join(CustomBotNew, WhatsAppCred.bot_id == CustomBotNew.bot_id)
                    .filter(
                        CustomBotNew.tenant_id == tenant.tenant_id,
                        CustomBotNew.del_flg == False,
                        WhatsAppCred.bot_id != bot.bot_id,
                        WhatsAppCred.business_account_id == business_account_id,
                    )
                    .first()
                )
                if ba_exists:
                    errors.append({
                        "field": "whatsapp_credentials.business_account_id",
                        "message": "business_account_id already exists"
                    })

            if access_token:
                token_exists = (
                    db.session.query(WhatsAppCred.id)
                    .join(CustomBotNew, WhatsAppCred.bot_id == CustomBotNew.bot_id)
                    .filter(
                        CustomBotNew.tenant_id == tenant.tenant_id,
                        CustomBotNew.del_flg == False,
                        WhatsAppCred.bot_id != bot.bot_id,
                        WhatsAppCred.access_token == access_token,
                    )
                    .first()
                )
                if token_exists:
                    errors.append({
                        "field": "whatsapp_credentials.access_token",
                        "message": "access_token already exists"
                    })

            if verify_token:
                verify_exists = (
                    db.session.query(WhatsAppCred.id)
                    .join(CustomBotNew, WhatsAppCred.bot_id == CustomBotNew.bot_id)
                    .filter(
                        CustomBotNew.tenant_id == tenant.tenant_id,
                        CustomBotNew.del_flg == False,
                        WhatsAppCred.bot_id != bot.bot_id,
                        WhatsAppCred.verify_token == verify_token,
                    )
                    .first()
                )
                if verify_exists:
                    errors.append({
                        "field": "whatsapp_credentials.verify_token",
                        "message": "verify_token already exists"
                    })

            return errors

        def _validate_slack_credentials(payload):
            errors = []
            existing = bot.slack_cred

            bot_token = _safe_str(
                payload.get("bot_token")
                or payload.get("xoxb_token")
                or payload.get("access_token")
                or (existing.bot_token if existing else None)
            )
            signing_secret = _safe_str(
                payload.get("signing_secret")
                or payload.get("signingSecret")
                or (existing.signing_secret if existing else None)
            )
            app_token = _safe_str(
                payload.get("app_token")
                or payload.get("appToken")
                or (existing.app_token if existing else None)
            )
            default_channel_id = _safe_str(
                payload.get("channel_id")
                or payload.get("default_channel_id")
                or (existing.default_channel_id if existing else None)
            )

            if not bot_token:
                errors.append({"field": "slack_credentials.bot_token", "message": "bot_token is required"})
            elif not bot_token.startswith("xoxb-"):
                errors.append({"field": "slack_credentials.bot_token", "message": "bot_token must start with xoxb-"})

            if not signing_secret:
                errors.append({"field": "slack_credentials.signing_secret", "message": "signing_secret is required"})

            if app_token and not app_token.startswith("xapp-"):
                errors.append({"field": "slack_credentials.app_token", "message": "app_token must start with xapp-"})

            if default_channel_id and not re.fullmatch(r"[CGD][A-Z0-9]{8,}", default_channel_id):
                errors.append({
                    "field": "slack_credentials.channel_id",
                    "message": "channel_id must be a valid Slack channel/conversation ID"
                })

            # Prevent reusing any Slack credential field across bots in this tenant.
            if bot_token:
                token_exists = (
                    db.session.query(SlackCred.id)
                    .join(CustomBotNew, SlackCred.bot_id == CustomBotNew.bot_id)
                    .filter(
                        CustomBotNew.tenant_id == tenant.tenant_id,
                        CustomBotNew.del_flg == False,
                        SlackCred.bot_id != bot.bot_id,
                        SlackCred.bot_token == bot_token,
                    )
                    .first()
                )
                if token_exists:
                    errors.append({
                        "field": "slack_credentials.bot_token",
                        "message": "bot_token already exists"
                    })

            if signing_secret:
                secret_exists = (
                    db.session.query(SlackCred.id)
                    .join(CustomBotNew, SlackCred.bot_id == CustomBotNew.bot_id)
                    .filter(
                        CustomBotNew.tenant_id == tenant.tenant_id,
                        CustomBotNew.del_flg == False,
                        SlackCred.bot_id != bot.bot_id,
                        SlackCred.signing_secret == signing_secret,
                    )
                    .first()
                )
                if secret_exists:
                    errors.append({
                        "field": "slack_credentials.signing_secret",
                        "message": "signing_secret already exists"
                    })

            if app_token:
                app_exists = (
                    db.session.query(SlackCred.id)
                    .join(CustomBotNew, SlackCred.bot_id == CustomBotNew.bot_id)
                    .filter(
                        CustomBotNew.tenant_id == tenant.tenant_id,
                        CustomBotNew.del_flg == False,
                        SlackCred.bot_id != bot.bot_id,
                        SlackCred.app_token == app_token,
                    )
                    .first()
                )
                if app_exists:
                    errors.append({
                        "field": "slack_credentials.app_token",
                        "message": "app_token already exists"
                    })

            return errors

        if whatsapp_credentials_raw is not None:
            try:
                parsed_whatsapp_credentials = json.loads(whatsapp_credentials_raw)
            except Exception:
                return error_response(
                    message="Invalid whatsapp_credentials JSON format",
                    data=None,
                    code=400
                )

            if parsed_whatsapp_credentials is not None and not isinstance(parsed_whatsapp_credentials, dict):
                return error_response(
                    message="whatsapp_credentials must be a JSON object",
                    data=None,
                    code=400
                )

            whatsapp_errors = _validate_whatsapp_credentials(parsed_whatsapp_credentials or {})
            if whatsapp_errors:
                return error_response(
                    message="Validation failed for whatsapp_credentials",
                    data={"field_errors": whatsapp_errors},
                    code=400
                )

            bot.whatsapp_credentials = parsed_whatsapp_credentials or {}

            whatsapp_cred = WhatsAppCred.query.filter_by(bot_id=bot.bot_id).first()
            if not whatsapp_cred:
                whatsapp_cred = WhatsAppCred(bot_id=bot.bot_id)
                db.session.add(whatsapp_cred)

            payload = parsed_whatsapp_credentials or {}
            whatsapp_cred.phone_number_id = payload.get("phone_number_id") or payload.get("business_phone_number_id")
            whatsapp_cred.business_account_id = payload.get("business_account_id") or payload.get("whatsapp_business_account_id")
            whatsapp_cred.access_token = payload.get("access_token") or payload.get("token") or payload.get("permanent_token")
            whatsapp_cred.verify_token = payload.get("verify_token") or payload.get("verifyToken")
            whatsapp_cred.graph_api_version = payload.get("api_version") or payload.get("graph_api_version") or "v19.0"
            whatsapp_cred.default_recipient_number = payload.get("default_recipient_number")

        if slack_credentials_raw is not None:
            try:
                parsed_slack_credentials = json.loads(slack_credentials_raw)
            except Exception:
                return error_response(
                    message="Invalid slack_credentials JSON format",
                    data=None,
                    code=400
                )

            if parsed_slack_credentials is not None and not isinstance(parsed_slack_credentials, dict):
                return error_response(
                    message="slack_credentials must be a JSON object",
                    data=None,
                    code=400
                )

            slack_errors = _validate_slack_credentials(parsed_slack_credentials or {})
            if slack_errors:
                return error_response(
                    message="Validation failed for slack_credentials",
                    data={"field_errors": slack_errors},
                    code=400
                )

            slack_cred = SlackCred.query.filter_by(bot_id=bot.bot_id).first()
            if not slack_cred:
                slack_cred = SlackCred(bot_id=bot.bot_id)
                db.session.add(slack_cred)

            payload = parsed_slack_credentials or {}
            slack_cred.bot_token = payload.get("bot_token") or payload.get("xoxb_token") or payload.get("access_token")
            slack_cred.signing_secret = payload.get("signing_secret") or payload.get("signingSecret")
            slack_cred.app_token = payload.get("app_token") or payload.get("appToken")
            slack_cred.default_channel_id = payload.get("channel_id") or payload.get("default_channel_id")

        if not is_channel_credentials_only:
            bg_color = data.get("background_color")
            bot.background_color = bg_color if bg_color else None

            if avatar_filename:
                bot.avatar = avatar_filename

            if bg_filename:
                bot.background_image = bg_filename

        # ---------------------------------------
        # ACCESS RESTRICTIONS
        # ---------------------------------------
        if not is_channel_credentials_only:
            restrictions_raw = data.get("restrictions")

            if restrictions_raw:
                restrictions_payload = json.loads(restrictions_raw)

                process_access_restrictions(
                    bot=bot,
                    tenant_id=tenant.tenant_id,
                    restrictions_payload=restrictions_payload
                )

        # ---------------------------------------
        # PUBLISH LOGIC
        # ---------------------------------------
        publish_result = publish_bot_version(
            bot=bot,
            tenant_id=tenant.tenant_id
        )

        version = publish_result["version"]

        if publish_result["no_changes"]:
            if not bot.published_version_id:
                bot.published_version_id = version.version_id

            bot.bot_status = BotStatusEnum.LIVE
            db.session.commit()

            return success_response(
                message="No changes detected. Bot already up to date.",
                data={
                    "bot_id": bot.bot_id,
                    "channel": bot.channel.value if bot.channel else None,
                    "whatsapp_credentials": bot.whatsapp_credentials or {},
                    "slack_credentials": {
                        "bot_token": (bot.slack_cred.bot_token if bot.slack_cred else "") or "",
                        "signing_secret": (bot.slack_cred.signing_secret if bot.slack_cred else "") or "",
                        "app_token": (bot.slack_cred.app_token if bot.slack_cred else "") or "",
                        "channel_id": (bot.slack_cred.default_channel_id if bot.slack_cred else "") or "",
                    },
                    "version_number": version.version_number,
                    "version_id": version.version_id,
                    "status": bot.bot_status.value
                },
                code=200
            )

        # ✅ Changes exist
        bot.bot_status = BotStatusEnum.LIVE

        if not bot.published_version_id:
            bot.published_version_id = version.version_id

        db.session.commit()

        return success_response(
            message="Bot configured and published successfully",
            data={
                "bot_id": bot.bot_id,
                "channel": bot.channel.value if bot.channel else None,
                "whatsapp_credentials": bot.whatsapp_credentials or {},
                "slack_credentials": {
                    "bot_token": (bot.slack_cred.bot_token if bot.slack_cred else "") or "",
                    "signing_secret": (bot.slack_cred.signing_secret if bot.slack_cred else "") or "",
                    "app_token": (bot.slack_cred.app_token if bot.slack_cred else "") or "",
                    "channel_id": (bot.slack_cred.default_channel_id if bot.slack_cred else "") or "",
                },
                "version_number": version.version_number,
                "version_id": version.version_id,
                "status": bot.bot_status.value
            },
            code=200
        )
        # if publish_result["no_changes"]:

        #     version = publish_result["version"]

        #     db.session.commit()

        #     return success_response(
        #         message="No changes detected. Bot already up to date.",
        #         data={
        #             "bot_id": bot.bot_id,
        #             "version_number": version.version_number,
        #             "version_id": version.version_id,
        #             "status": bot.bot_status.value
        #         },
        #         code=200
        #     )

        # version = publish_result["version"]

        # db.session.commit()

        # logger.info(
        #     f"Bot configured and published | bot_id={bot.bot_id} | version={version.version_number}"
        # )

        # return success_response(
        #     message="Success",
        #     data={
        #         "message": "Bot configured and published successfully",
        #         "bot_id": bot.bot_id,
        #         "instance_id": bot.instance_id,
        #         "version_number": version.version_number,
        #         "version_id": version.version_id,
        #         "status": bot.bot_status.value
        #     },
        #     code=200
        # )

    except IntegrityError as ie:
        db.session.rollback()

        err_text = str(getattr(ie, "orig", ie))
        logger.exception(
            f"Database integrity error configuring bot | bot_id={bot.bot_id}"
        )

        if "tbl_custombot_access_restriction_bot_id_fkey" in err_text:
            if "is not present in table \"tbl_custombot_new\"" in err_text:
                return error_response(
                    message=(
                        f"Invalid bot_id={bot.bot_id} for custom_bot_new flow. "
                        "This bot ID does not exist in tbl_custombot_new. "
                        "Use a bot created from /custom_bot_new routes."
                    ),
                    data=None,
                    code=400
                )

            return error_response(
                message=(
                    "Access restriction save failed due to database schema mismatch. "
                    "Run migration c3d9f4b1a2e7 so "
                    "tbl_custombot_access_restriction.bot_id references "
                    "tbl_custombot_new(bot_id)."
                ),
                data=None,
                code=500
            )

        return error_response(
            message="Database integrity error while saving bot configuration",
            data=None,
            code=500
        )

    except ValueError as ve:
        db.session.rollback()

        logger.warning(
            f"Validation error | bot_id={bot.bot_id} | {str(ve)}"
        )

        return error_response(
            message=str(ve),
            data=None,
            code=400
        )

    except Exception:

        db.session.rollback()

        logger.exception(
            f"Unexpected error configuring bot | bot_id={bot.bot_id}"
        )

        return error_response(
            message="Server error",
            data=None,
            code=500
        )
        
def publish_bot_version(bot, tenant_id):
    """
    Handles snapshot creation, versioning, idempotency, and bot state update.
    Does NOT commit the session.
    Returns:
        dict -> publish result metadata
    """

    # ───────── Readiness check ─────────
    missing = [
        field for field, val in {
            "bot_name": bot.bot_name,
            "channel": bot.channel,
            "purpose": bot.purpose,
            "tone_of_voice": bot.tone_of_voice,
            "industry": bot.industry,
        }.items() if not val
    ]

    if missing:
        raise ValueError(
            "Bot is incomplete. Fill required fields before publishing."
        )

    # ───────── Build snapshot ─────────
    new_snapshot = build_snapshot(bot)
        # ✅ FIX: CLEAN SNAPSHOT HERE
    new_snapshot = make_json_safe(new_snapshot)
    new_hash = compute_snapshot_hash(new_snapshot)

    # ───────── Idempotency check ─────────
    if bot.published_version_id:
        # Prevent pending config writes (e.g. access restrictions) from being
        # autoflushed before the simple version lookup below.
        with db.session.no_autoflush:
            current_live = BotVersion.query.get(bot.published_version_id)

        if current_live and current_live.snapshot_hash == new_hash:

            return {
                "no_changes": True,
                "version": current_live
            }

    # ───────── Archive current version ─────────
    BotVersion.query.filter_by(
        bot_id=bot.bot_id,
        is_live=True
    ).update({"is_live": False})

    # ───────── Next version ─────────
    last = (
        BotVersion.query
        .filter_by(bot_id=bot.bot_id)
        .order_by(BotVersion.version_number.desc())
        .first()
    )

    next_number = (last.version_number + 1) if last else 1

    # ───────── Create new version ─────────
    new_version = BotVersion(
        bot_id=bot.bot_id,
        version_number=next_number,
        is_live=True,
        snapshot=new_snapshot,
        snapshot_hash=new_hash,
        published_by=tenant_id
    )

    db.session.add(new_version)
    db.session.flush()

    # ───────── Update bot pointers ─────────
    bot.bot_status = BotStatusEnum.LIVE
    bot.published_version_id = new_version.version_id
    bot.last_published_at = db.func.now()

    return {
        "no_changes": False,
        "version": new_version
    }

@custom_bot_blueprint_new.route("/<int:bot_id>/publish", methods=["POST"])
@jwt_required()
@validate_bot_access(
    allowed_status=[BotStatusEnum.CREATED, BotStatusEnum.LIVE, BotStatusEnum.PAUSED]
)
def publish_bot(bot_id):

    bot    = g.bot
    tenant = g.tenant

    logger.info(f"Publish requested | bot_id={bot.bot_id} | tenant_id={tenant.tenant_id}")

    try:
        # ───────── Readiness check ─────────
        missing = [
            field for field, val in {
                "bot_name":    bot.bot_name,
                "channel":     bot.channel,
                "purpose":     bot.purpose,
                "tone_of_voice": bot.tone_of_voice,
                "industry":    bot.industry,
            }.items() if not val
        ]

        if missing:
            return error_response(
                message="Bot is incomplete. Fill required fields before publishing.",
                data=None,
                code=400
            )

        # ───────── Build snapshot + hash (NEW ADDITION) ─────────
        new_snapshot = build_snapshot(bot)
        new_snapshot = make_json_safe(new_snapshot)
        new_hash = compute_snapshot_hash(new_snapshot)

        # ───────── Idempotency check (NEW ADDITION) ─────────
        if bot.published_version_id:
            current_live = BotVersion.query.get(bot.published_version_id)
            if current_live and current_live.snapshot_hash == new_hash:
                logger.info(f"No changes detected for bot_id={bot.bot_id}")
                return success_response(
                    message="No changes detected. Bot already up to date.",
                    data={
                        "bot_id": bot.bot_id,
                        "instance_id": bot.instance_id,
                        "version_number": current_live.version_number,
                        "version_id": current_live.version_id,
                        "status": bot.bot_status.value,
                    },
                    code=200
                )

        # ───────── Archive current live version ─────────
        BotVersion.query.filter_by(
            bot_id=bot.bot_id,
            is_live=True
        ).update({"is_live": False})

        # ───────── Next version number ─────────
        last = (
            BotVersion.query
            .filter_by(bot_id=bot.bot_id)
            .order_by(BotVersion.version_number.desc())
            .first()
        )
        next_number = (last.version_number + 1) if last else 1

        # ───────── Create new live snapshot (hash added) ─────────
        new_version = BotVersion(
            bot_id=bot.bot_id,
            version_number=next_number,
            is_live=True,
            snapshot=new_snapshot,
            snapshot_hash=new_hash,   # ✅ NEW FIELD
            published_by=tenant.tenant_id
        )

        db.session.add(new_version)
        db.session.flush()

        # ───────── Update draft pointer ─────────
        bot.bot_status           = BotStatusEnum.LIVE
        bot.published_version_id = new_version.version_id
        bot.last_published_at    = db.func.now()

        db.session.commit()

        logger.info(
            f"Bot published | bot_id={bot.bot_id} | version={next_number}"
        )

        return success_response(
            message="Success",
            data={
                "message":        "Bot published successfully",
                "bot_id":         bot.bot_id,
                "instance_id":    bot.instance_id,
                "version_number": next_number,
                "version_id":     new_version.version_id,
                "status":         bot.bot_status.value,
            },
            code=200
        )

    except Exception:
        db.session.rollback()
        logger.exception(f"Publish failed | bot_id={bot.bot_id}")
        return error_response(
            message="Unexpected error occurred",
            data=None,
            code=500
        )
        

@custom_bot_blueprint_new.route(
    "/<int:bot_id>/rollback/<int:version_id>",
    methods=["POST"]
)
@jwt_required()
@validate_bot_access(allowed_status=[BotStatusEnum.LIVE])
def rollback_bot(bot_id, version_id):

    bot = g.bot
    tenant = g.tenant

    try:
        target_version = BotVersion.query.filter_by(
            version_id=version_id,
            bot_id=bot.bot_id
        ).first()

        if not target_version:
            return jsonify({"error": "Version not found"}), 404

        if bot.published_version_id == version_id:
            return jsonify({"error": "Version is already live"}), 400

        # Deactivate current live safely
        if bot.published_version_id:
            current_live = BotVersion.query.get(bot.published_version_id)
            if current_live:
                current_live.is_live = False

        last = (
            BotVersion.query
            .filter_by(bot_id=bot.bot_id)
            .order_by(BotVersion.version_number.desc())
            .first()
        )
        next_number = last.version_number + 1 if last else 1

        rollback_snapshot = target_version.snapshot
        rollback_hash = compute_snapshot_hash(rollback_snapshot)

        new_version = BotVersion(
            bot_id=bot.bot_id,
            version_number=next_number,
            is_live=True,
            snapshot=rollback_snapshot,
            snapshot_hash=rollback_hash,
            published_by=tenant.tenant_id
        )

        db.session.add(new_version)
        db.session.flush()

        bot.published_version_id = new_version.version_id
        bot.bot_status = BotStatusEnum.LIVE
        bot.last_published_at = db.func.now()

        db.session.commit()

        return jsonify({
            "message": "Rollback successful",
            "new_version_number": next_number,
            "rolled_back_from": version_id
        }), 200

    except Exception:
        db.session.rollback()
        logger.exception("Rollback failed")
        return jsonify({"error": "Unexpected error occurred"}), 500
    

@custom_bot_blueprint_new.route(
    "/<int:bot_id>/channel",
    methods=["GET"]
)
@jwt_required()
@validate_bot_access()
def get_channel(bot_id):

    bot = g.bot

    return success_response(message = "Success", data = {
        "bot_id": bot.bot_id,
        "channel": bot.channel.value if bot.channel else None,
        "status": bot.bot_status.value
    }, code = 200)


@custom_bot_blueprint_new.route(
    "/<int:bot_id>/personalization",
    methods=["GET"]
)
@jwt_required()
@validate_bot_access()
def get_personalization(bot_id):

    bot = g.bot

    return success_response(message = "Success", data = {
        "bot_id": bot.bot_id,
        "bot_name": bot.bot_name,
        "tone_of_voice": bot.tone_of_voice.value if bot.tone_of_voice else None,
        "industry": bot.industry.value if bot.industry else None,
        "purpose": bot.purpose,
        "avatar": bot.avatar,
        "status": bot.bot_status.value
    }, code = 200)

@custom_bot_blueprint_new.route(
    "/<int:bot_id>/functionality",
    methods=["GET"]
)

@jwt_required()
@validate_bot_access()
def get_functionality(bot_id):

    bot = g.bot

    return success_response(message = "Success", data = {
        "bot_id": bot.bot_id,
        "core_features": bot.core_features or {},
        "instructions": bot.instructions or [],
        "kb_ids": bot.kb_ids or [],
        "kb_functionalities": bot.kb_functionalities or [],
        "status": bot.bot_status.value
    }, code = 200)

@custom_bot_blueprint_new.route(
    "/bots/<int:bot_id>/configure",
    methods=["GET"]
)

@jwt_required()
@validate_bot_access()
def get_configuration(bot_id):

    bot = g.bot

    restrictions = CustomBotAccessRestriction.query.filter_by(
        bot_id=bot.bot_id
    ).all()

    restriction_data = [
        {
            "allowed_ip": r.allowed_ip,
            "allowed_domain": r.allowed_domain
        }
        for r in restrictions
    ]

    return success_response(message = "Success", data = {
        "bot_id": bot.bot_id,
        "channel_type": bot.channel.value if bot.channel else None,
        "channel": bot.channel.value if bot.channel else None,
        "whatsapp_credentials": bot.whatsapp_credentials or {},
        "slack_credentials": {
            "bot_token": (bot.slack_cred.bot_token if bot.slack_cred else "") or "",
            "signing_secret": (bot.slack_cred.signing_secret if bot.slack_cred else "") or "",
            "app_token": (bot.slack_cred.app_token if bot.slack_cred else "") or "",
            "channel_id": (bot.slack_cred.default_channel_id if bot.slack_cred else "") or "",
        },
        "bot_name": bot.bot_name,
        "disclaimer_text": bot.disclaimer_text,
        "purpose": bot.purpose,
        "colors": bot.colors,
        "theme": bot.theme,
        "position": bot.position,
        "page_config": bot.page_config,
        "specific_pages": bot.specific_pages or [],
        "greeting_type": bot.greeting_type,
        "greeting_message": bot.greeting_message,
        "avatar": bot.avatar,
        "background_image": bot.background_image,
        "background_color": bot.background_color,
        "restrictions": restriction_data,
        "status": bot.bot_status.value
    }, code = 200)


@custom_bot_blueprint_new.route(
    "/<int:bot_id>/knowledge-base",
    methods=["GET"]
)
@jwt_required()
@validate_bot_access()
def get_knowledge_base_step(bot_id):

    bot = g.bot

    return success_response(message = "Success", data = {
        "bot_id": bot.bot_id,
        "kb_ids": bot.kb_ids or [],
        "kb_functionalities": bot.kb_functionalities or []
    }, code = 200)



    
    
#thsi is new get chat and this goes in the multi agentic system routes
# @multi_agents_blueprint.route('/get_chat', methods=['POST', 'OPTIONS'])
# def get_chat():

#     if request.method == 'OPTIONS':
#         return jsonify({"status": "ok"}), 200validate_client

#     try:
#         data = request.get_json()
#         if not data:
#             return jsonify({"error": "Invalid JSON payload."}), 400

#         query      = (data.get('query') or "").strip()
#         bot_id     = data.get('bot_id')
#         session_id = data.get('session_id')

#         if not query:
#             return jsonify({"error": "Query is required."}), 400
#         if not bot_id:
#             return jsonify({"error": "Bot ID is required."}), 400
#         if not session_id:
#             return jsonify({"error": "Session ID is required."}), 400
#         if len(query) > 2000:
#             return jsonify({"error": "Query is too long (max 2000 characters)."}), 400

#         # Ã¢â€ Â CHANGED: query CustomBotNew instead of CustomBot
#         bot = CustomBotNew.query.filter_by(bot_id=bot_id, del_flg=False).first()
#         logger.info("Processing query for bot_id=%s: %s", bot_id, query[:50])
#         if not bot:
#             return jsonify({"error": "Invalid bot_id or bot not found."}), 404

#         # Ã¢â€ Â CHANGED: resolve config (handles CREATED vs LIVE)
#         try:
#             config = resolve_bot_config(bot)
#         except PermissionError as e:
#             logger.warning(str(e))
#             return jsonify({"error": "Bot is not available for chat."}), 403
#         except ValueError as e:
#             logger.error(str(e))
#             return jsonify({"error": "Bot configuration unavailable."}), 503

#         is_test   = config["is_test_mode"]
#         tenant_id = bot.tenant_id

#         if not tenant_id:
#             return jsonify({"error": "Tenant ID not found for this bot."}), 500

#         # Ã¢â€ Â CHANGED: pass config fields into agent
#         multi_agent = get_or_create_multi_agent_system(
#             tenant_id=tenant_id,
#             bot_id=bot_id,
#             session_id=session_id,
#             kb_ids=config.get("kb_ids", []),
#             instructions=config.get("instructions", []),
#             core_features=config.get("core_features", []),
#             kb_functionalities=config.get("kb_functionalities", [])
#         )

#         agent_response = multi_agent.ask(query)

#         # Skip message decrement in test mode
#         if not is_test:
#             try:
#                 session = next(db_session())
#                 result = update_remaining_messages(session, tenant_id, 1)
#                 if isinstance(result, tuple):
#                     success, msg = result
#                     if not success:
#                         logger.warning(f"Message count update failed | tenant_id={tenant_id} | {msg}")
#                         session.rollback()
#                     else:
#                         session.commit()
#                 else:
#                     session.commit()
#             except Exception as e:
#                 logger.warning(f"Failed to update message count | {e}")
#                 session.rollback()
#             finally:
#                 session.close()

#         return jsonify({
#             "response":  agent_response,
#             "test_mode": is_test      # useful for frontend testing banner
#         }), 200

#     except Exception as e:
#         logger.exception(f"Unexpected error in get_chat | {e}")
#         return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500

# @custom_bot_blueprint_new.route('/chatbot/<instance_id>', methods=["GET"])
# def serve_chatbot_by_instance(instance_id):
#     try:
#         # Ã¢â€ Â CHANGED: single lookup by instance_id, no subdomain/session needed
#         draft = CustomBotNew.query.filter_by(
#             instance_id=instance_id,
#             del_flg=False
#         ).first()

#         if not draft:
#             return jsonify({"error": "Bot not found", "status": "error"}), 404

#         # Ã¢â€ Â CHANGED: resolve config handles LIVE vs CREATED
#         try:
#             config = resolve_bot_config(draft)
#         except PermissionError:
#             return jsonify({"error": "Bot is not published", "status": "error"}), 403
#         except ValueError:
#             return jsonify({"error": "Bot configuration unavailable", "status": "error"}), 503

#         logger.info(
#             f"Serving chatbot | instance_id={instance_id} | "
#             f"bot_id={draft.bot_id} | test={config['is_test_mode']}"
#         )

#         # Ã¢â€ Â CHANGED: all template vars come from config, not raw bot object
#         return render_template(
#             "chatbot.html",
#             bot_id=config["bot_id"],
#             bot_name=config["bot_name"],
#             theme=config["theme"],
#             colors=config["colors"],
#             position=config["position"],
#             greeting_message=config["greeting_message"],
#             disclaimer_text=config["disclaimer_text"],
#             background_image=config["background_image"],
#         )

#     except Exception:
#         logger.exception(f"Error serving chatbot | instance_id={instance_id}")
#         return jsonify({"error": "Server error", "status": "error"}), 500


# --------------------------------------------------------------



@custom_bot_blueprint_new.route('/validate_client', methods=["POST"])
def validate_client():
    data = request.get_json()
    bot_id = data.get('bot_id')
    client_ip = data.get('ip')
    domain = data.get('domain')

    def _normalize_domain(value):
        if not value:
            return None
        value = str(value).strip().lower()
        value = value.replace("https://", "").replace("http://", "")
        value = value.split("/")[0].split(":")[0]
        return value[4:] if value.startswith("www.") else value

    def _normalize_ip(value):
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    client_ip = _normalize_ip(client_ip)
    domain = _normalize_domain(domain)

    logger.info(f"Validating client for bot_id: {bot_id}, client_ip: {client_ip}, domain: {domain}")

    bot = CustomBotNew.query.filter_by(bot_id=bot_id, del_flg=False).first()
    if not bot:
        return error_response(message = "Bot not found", data = None, code = 404)

    # Fetch all restrictions for the bot
    restrictions = CustomBotNewAccessRestriction.query.filter_by(bot_id=bot.bot_id).all()

    # Pure IPs (not mapped to any domain)
    pure_ips = {
        _normalize_ip(r.allowed_ip)
        for r in restrictions
        if _normalize_ip(r.allowed_ip) and _normalize_domain(r.allowed_domain) is None
    }

    # Domain-mapped IPs
    mapped_ips = {
        _normalize_ip(r.allowed_ip)
        for r in restrictions
        if _normalize_ip(r.allowed_ip) and _normalize_domain(r.allowed_domain)
    }

    # Base domains
    base_domains = {
        _normalize_domain(r.allowed_domain)
        for r in restrictions
        if _normalize_domain(r.allowed_domain)
    }

    # Fallback to API key if no restrictions exist
    if not pure_ips and not mapped_ips and not base_domains:
        return jsonify({"status": "ok"})

    # 1Ã¯Â¸ÂÃ¢Æ’Â£ Check pure IPs first
    if client_ip in pure_ips:
        temp_token = generate_temp_token(bot_id, client_ip, domain, bot.tenant_id)
        return jsonify({"status": "ok", "token": temp_token})

    # 2Ã¯Â¸ÂÃ¢Æ’Â£ Check IPs mapped to domains
    if client_ip in mapped_ips:
        temp_token = generate_temp_token(bot_id, client_ip, domain, bot.tenant_id)
        return jsonify({"status": "ok", "token": temp_token})

    # 3Ã¯Â¸ÂÃ¢Æ’Â£ Check domain if IP not matched
    if domain and domain in base_domains:
        temp_token = generate_temp_token(bot_id, client_ip, domain, bot.tenant_id)
        return jsonify({"status": "ok", "token": temp_token})

    # 4Ã¯Â¸ÂÃ¢Æ’Â£ No match Ã¢â€ â€™ access denied
    return error_response(message = "Access not allowed", data = None, code = 403)

@custom_bot_blueprint_new.route('/JnanicChatbotJs.js')
def serve_chatbot_js():
    try:
        return send_from_directory(os.path.join(current_app.root_path, 'static', 'js'), 'JnanicChatbotJs.js')
    except Exception as e:
        logger.error(f"Error serving JnanicChatbotJs.js: {str(e)}")
        return error_response(message = "File not found", data = None, code = 404)

@custom_bot_blueprint_new.route('/LaunchBot.js')
def serve_launch_bot_js():
    try:
        response = send_from_directory(os.path.join(current_app.root_path, 'static', 'js'), 'LaunchBot.js')
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        logger.error(f"Error serving LaunchBot.js: {str(e)}")
        return error_response(message = "File not found", data = None, code = 404)

@custom_bot_blueprint_new.route('/JnanicChatbotCss.css')
def serve_chatbot_css():
    try:
        return send_from_directory(os.path.join(current_app.root_path, 'static', 'css'), 'JnanicChatbotCss.css')
    except Exception as e:
        logger.error(f"Error serving JnanicChatbotCss.css: {str(e)}")
        return error_response(message = "File not found", data = None, code = 404)

@custom_bot_blueprint_new.route('/chat-history/<instance_id>')
def get_chat_history(instance_id):
    try:
        host = request.host
        subdomain = host.split('.')[0] if '.' in host else None
        api_key = request.headers.get("X-API-Key")

        session = next(db_session())
        user = None

        if api_key:
            user = session.query(LoginUser).filter_by(api_key=api_key, del_flg=False).first()
            if not user:
                logger.error("Invalid API key provided")
                return error_response(message = "Invalid API key", data = None, code = 401)
        elif subdomain:
            user = session.query(Tenant).join(LoginUser).filter(LoginUser.account_name == subdomain, Tenant.tenant_status == "Active", LoginUser.del_flg == False).first()
            if not user:
                logger.error(f"No active tenant found for subdomain: {subdomain}")
                return error_response(message = "Subdomain not found or inactive", data = None, code = 404)
        else:
            logger.error("Subdomain or API key required")
            return error_response(message = "Subdomain or API key required", data = None, code = 400)

        bot = session.query(CustomBotNew).filter_by(
            instance_id=instance_id,
            tenant_id=user.tenant_id,
            del_flg=False
        ).first()
        if not bot:
            logger.error(f"Bot not found for instance_id: {instance_id}, tenant_id: {user.tenant_id}")
            abort(404, description=f"Invalid or inactive instance ID: {instance_id}")

        history = session.query(ChatHistory).filter_by(bot_id=bot.bot_id, tenant_id=user.tenant_id).all()
        logger.info(f"Fetched chat history for instance_id: {instance_id}")
        return jsonify({
            "data": {
                "history": [{"query": h.query, "response": h.response} for h in history]
            },
            "status": "success",
            "message": "Chat history fetched successfully"
        })

    except Exception as e:
        logger.error(f"Error fetching chat history for instance_id {instance_id}: {str(e)}")
        abort(500, description=f"Server error: {str(e)}")
    finally:
        session.close()

@custom_bot_blueprint_new.route("/dashboard/analytics", methods=["GET"])
@jwt_required()
def get_dashboard_analytics():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return error_response(message = "Tenant ID not found in token", data = None, code = 401)

        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        last_week = today - timedelta(days=7)

        def compute_delta(current, previous):
            if previous == 0:
                return {
                    "value": 100.0 if current > 0 else 0.0,
                    "direction": "up" if current > 0 else "neutral"
                }
            delta = ((current - previous) / previous) * 100
            return {
                "value": round(abs(delta), 1),
                "direction": "up" if delta > 0 else ("down" if delta < 0 else "neutral")
            }

        # Instead of 4 separate COUNT queries, use one query with CASE
        from sqlalchemy import case, cast, Date

        bot_counts = db.session.query(
            func.count().label("total_bots"),
            func.sum(
                case((func.date(CustomBotNew.created_at) <= yesterday, 1), else_=0)
            ).label("total_bots_yesterday"),
            func.sum(
                case((CustomBotNew.bot_status == BotStatusEnum.LIVE, 1), else_=0)
            ).label("live_bots"),
            func.sum(
                case((
                    (CustomBotNew.bot_status == BotStatusEnum.LIVE) &
                    (func.date(CustomBotNew.last_published_at) <= last_week),  # Ã¢Å“â€¦ fixed field
                    1
                ), else_=0)
            ).label("live_bots_last_week")
        ).filter(
            CustomBotNew.tenant_id == tenant_id,
            CustomBotNew.del_flg == False
        ).one()

        total_bots          = bot_counts.total_bots or 0
        total_bots_yesterday = bot_counts.total_bots_yesterday or 0
        live_bots           = bot_counts.live_bots or 0
        live_bots_last_week = bot_counts.live_bots_last_week or 0

        subscription = TenantSubscription.query.filter(
            TenantSubscription.tenant_id == tenant_id,
            TenantSubscription.subscription_status == "active",
            TenantSubscription.del_flg == False
        ).order_by(desc(TenantSubscription.created_at)).first()

        total_plan_msg = 0
        total_messages = 0
    

        if subscription:
            total_plan_msg  = subscription.total_plan_msg or 0
            remaining       = subscription.remaining_msg or 0
            total_messages  = total_plan_msg - remaining
            

       
        analytics = {
            "total_bots": {
                "count": total_bots,
                "delta": compute_delta(total_bots, total_bots_yesterday),
                "label": "Up from yesterday"
            },
            "live_bots": {
                "count": live_bots,
                "delta": compute_delta(live_bots, live_bots_last_week),
                "label": "Up from past week"
            },
            "total_messages": {
                "count": total_messages,
                "total_plan_msg": total_plan_msg,
                "label": "Messages used from plan"
            },
            "total_users": {
                "count": 0,
                "label": "Up from yesterday"
            }
        }

        logger.info(f"Dashboard analytics fetched | tenant_id={tenant_id}")
        return success_response(message = "Analytics fetched successfully", data = analytics, code = 200)

    except Exception as e:
        logger.exception(f"Error fetching dashboard analytics | tenant_id={tenant_id}")
        return error_response(message = str(e), data = {}, code = 500)



@custom_bot_blueprint_new.route("/", methods=["GET"])
@jwt_required()
def get_all_bots():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return error_response(message = "Tenant ID not found in token", data = [], code = 401)

        # -----------------------------
        # Pagination Params
        # -----------------------------
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)

        # Safety limits
        per_page = min(per_page, 100)

        # -----------------------------
        # Filter Params
        # -----------------------------
        channel = request.args.get("channel")
        bot_status = request.args.get("bot_status")
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")

        # -----------------------------
        # Base Query
        # -----------------------------
        query = CustomBotNew.query.filter(
            CustomBotNew.tenant_id == tenant_id,
            CustomBotNew.del_flg == False
        )

        # -----------------------------
        # Apply Filters
        # -----------------------------

        # Channel Filter
        if channel:
            try:
                channel_enum = parse_enum(ChannelEnum, channel, "channel")
                query = query.filter(CustomBotNew.channel == channel_enum)
            except ValueError as e:
                return error_response(message = str(e), data = [], code = 400)

        # Bot Status Filter
        if bot_status:
            try:
                status_enum = parse_enum(BotStatusEnum, bot_status, "bot_status")
                query = query.filter(CustomBotNew.bot_status == status_enum)
            except ValueError as e:
                return error_response(message = str(e), data = [], code = 400)

        # Date Range Filter (created_at)
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, "%Y-%m-%d")
                query = query.filter(CustomBotNew.created_at >= date_from_obj)
            except ValueError:
                return error_response(message = "Invalid date_from format. Use YYYY-MM-DD", data = [], code = 400)

        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, "%Y-%m-%d")
                query = query.filter(CustomBotNew.created_at <= date_to_obj)
            except ValueError:
                return error_response(message = "Invalid date_to format. Use YYYY-MM-DD", data = [], code = 400)

        # -----------------------------
        # Ordering
        # -----------------------------
        query = query.order_by(desc(CustomBotNew.bot_id))

        # -----------------------------
        # Pagination Execution
        # -----------------------------
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        bots = pagination.items

        base_url = current_app.config.get('BASE_URL', 'https://api.jnanic.com')
        avatar_base_path = "uploads/avatars"

        bot_list = [
            {
                "theme": bot.theme,
                "bot_id": bot.bot_id,
                "bot_name": bot.bot_name,
                "tenant_id": bot.tenant_id,
                "channel": bot.channel.value,
                "tone_of_voice": bot.tone_of_voice.value if bot.tone_of_voice else None,
                "industry": bot.industry.value if bot.industry else None,
                "avatar": (
                    f"{base_url}/{avatar_base_path}/{os.path.basename(bot.avatar)}"
                    if bot.avatar and not bot.avatar.startswith(('http://', 'https://'))
                    else bot.avatar or ""
                ),
                "purpose": bot.purpose or "",
                "core_features": bot.core_features or [],
                "instructions": bot.instructions or [],
                "created_at": bot.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": bot.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                "status": bot.bot_status.value
            }
            for bot in bots
        ]

        return success_response(message = "Bots fetched successfully", data = {"data": bot_list, "pagination": {"page": page, "per_page": per_page, "total_records": pagination.total, "total_pages": pagination.pages, "has_next": pagination.has_next, "has_prev": pagination.has_prev}}, code = 200)

    except Exception as e:
        logger.error(f"Error fetching bots: {str(e)}")
        return error_response(message = f"An error occurred: {str(e)}", data = [], code = 500)


# Route to fetch dropdown data for tones and industries (public, no JWT required)

@custom_bot_blueprint_new.route(
    "/get-kb-functionalities/<int:bot_id>",
    methods=["GET"]
)
@jwt_required()
def get_kb_functionalities(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        bot = CustomBotNew.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not bot:
            return error_response(message = "Bot not found or unauthorized", data = None, code = 404)

        return success_response(message = "Success", data = {"bot_id": bot.bot_id, "kb_functionalities": bot.kb_functionalities, "status":True}, code = 200)

    except Exception as e:
        return error_response(message = str(e), data = None, code = 500)



@custom_bot_blueprint_new.route('/update/<int:bot_id>', methods=['PUT'])
@jwt_required()
def update_custom_bot(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return error_response(message = "Tenant ID not found in token", data = None, code = 401)

        bot = CustomBotNew.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id
        ).first()

        if not bot:
            return error_response(message = "Bot not found or unauthorized!", data = None, code = 404)

        data = request.form
        avatar = request.files.get('avatar')
        avatar_url = data.get('avatar_url')

        bot_name = data.get('bot_name', bot.bot_name)
        tone_of_voice = data.get('tone_of_voice', bot.tone_of_voice.value)
        industry = data.get('industry', bot.industry.value)
        purpose = data.get('purpose', bot.purpose)
        instructions = data.get('instructions', '').split("\n")
        core_features = data.get('core_features', '').split("\n")

        try:
            tone_of_voice_enum = ToneOfVoiceEnum[tone_of_voice.upper()]
        except KeyError:
            return error_response(message = "Invalid tone of voice value!", data = None, code = 400)

        industry_enum = next(
            (m for m in IndustryEnum if m.value.lower() == industry.lower()),
            None
        )
        if not industry_enum:
            return error_response(message = "Invalid industry value!", data = None, code = 400)

        if avatar and allowed_file(avatar.filename):
            avatar_filename = secure_filename(avatar.filename)
            upload_folder = os.path.join('uploads', 'avatars')
            os.makedirs(upload_folder, exist_ok=True)
            avatar.save(os.path.join(upload_folder, avatar_filename))
            bot.avatar = avatar_filename
        elif avatar_url:
            bot.avatar = avatar_url

        bot.bot_name = bot_name
        bot.tone_of_voice = tone_of_voice_enum
        bot.industry = industry_enum
        bot.purpose = purpose
        bot.instructions = instructions
        bot.core_features = core_features

        # ---------------- KB IDS (ONLY SOURCE OF TRUTH) ----------------
        kb_ids_raw = data.get("kb_ids")

        if not isinstance(bot.kb_ids, list):
            bot.kb_ids = []

        if kb_ids_raw is not None:
            try:
                parsed_kb_ids = json.loads(kb_ids_raw)
                if isinstance(parsed_kb_ids, list):
                    bot.kb_ids = list(
                        dict.fromkeys(int(kb) for kb in parsed_kb_ids)
                    )
            except (ValueError, json.JSONDecodeError):
                return error_response(message = "Invalid kb_ids format", data = None, code = 400)

        logger.info(
            f"Bot updated | bot_id={bot_id} | kb_ids={bot.kb_ids}"
        )

        db.session.commit()
        return success_response(message = "Success", data = {"message": "Bot updated successfully!"}, code = 200)

    except Exception as e:
        db.session.rollback()
        logger.error(f"Update bot failed | bot_id={bot_id} | {str(e)}")
        return error_response(message = "Internal Server Error", data = None, code = 500)

@custom_bot_blueprint_new.route("/get_recent_bot_id", methods=["GET"])
@jwt_required()
def get_recent_bot_id():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return error_response(message = "Tenant ID not found in token", data = {}, code = 401)

        session = next(db_session())
        recent_bot = session.query(CustomBotNew).filter_by(tenant_id=tenant_id)\
            .order_by(CustomBotNew.created_at.desc()).first()
        bot_id = recent_bot.bot_id if recent_bot else None

        logger.info(f"Retrieved recent bot_id: {bot_id} for tenant_id: {tenant_id}")
        return success_response(message = "Recent bot ID retrieved", data = {
                "bot_id": bot_id
            }, code = 200)

    except Exception as e:
        logger.error(f"Error fetching recent bot ID: {str(e)}")
        return error_response(message = "Internal server error", data = {}, code = 500)
    finally:
        session.close()

@custom_bot_blueprint_new.route('/delete/<int:bot_id>', methods=['DELETE'])
@jwt_required()
def delete_custom_bot(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return error_response(message = "Tenant ID not found in token", data = None, code = 401)

        bot = CustomBotNew.query.filter_by(bot_id=bot_id, tenant_id=tenant_id).first()
        if not bot:
            logger.error(f"Bot not found or unauthorized for bot_id: {bot_id}, tenant_id: {tenant_id}")
            return error_response(message = "Bot not found or unauthorized!", data = None, code = 404)

        bot.del_flg = True
        db.session.commit()
        logger.info(f"Bot deleted (soft) for bot_id: {bot_id}")
        return success_response(message = "Success", data = {"message": "Bot deleted successfully!"}, code = 200)

    except Exception as e:
        logger.error(f"Error deleting bot {bot_id}: {str(e)}")
        db.session.rollback()
        return error_response(message = f"An error occurred: {str(e)}", data = None, code = 500)



@custom_bot_blueprint_new.route("/recent-running-bots", methods=["GET"])
@jwt_required()
def get_recent_running_bots():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return error_response(message = "Tenant ID not found in token", data = [], code = 401)

        session = next(db_session())
        recent_bots = session.query(CustomBotNew).filter_by(
            tenant_id=tenant_id,
            del_flg=False,
            bot_status=BotStatusEnum.CREATED.value
        ).order_by(
            CustomBotNew.updated_at.desc()
        ).limit(3).all()

        base_url = current_app.config.get('BASE_URL', 'https://api.jnanic.com')
        avatar_base_path = "uploads/avatars"

        bot_list = [
            {
                "bot_id": bot.bot_id,
                "bot_name": bot.bot_name,
                "tenant_id": bot.tenant_id,
                "tone_of_voice": bot.tone_of_voice.value,
                "industry": bot.industry.value,
                "avatar": (
                    f"{base_url}/{avatar_base_path}/{os.path.basename(bot.avatar)}"
                    if bot.avatar and not bot.avatar.startswith(('http://', 'https://'))
                    else bot.avatar or ""
                ),
                "purpose": bot.purpose,
                "core_features": bot.core_features,
                "instructions": bot.instructions,
                "created_at": bot.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": bot.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                "status": bot.bot_status.value if bot.bot_status else None
            }
            for bot in recent_bots
        ]

        logger.info(f"Fetched {len(bot_list)} recent running bots for tenant_id: {tenant_id}")
        return success_response(message = "Recent running bots fetched successfully", data = bot_list, code = 200)

    except Exception as e:
        logger.error(f"Error fetching recent running bots: {str(e)}")
        return error_response(message = f"An error occurred: {str(e)}", data = [], code = 500)
    finally:
        session.close()



# Lasted Old Version
@custom_bot_blueprint_new.route('/save-static-greeting/<int:bot_id>', methods=['POST'])
@jwt_required()
def save_static_greeting(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return error_response(message = "Tenant ID not found in token", data = None, code = 401)

        bot = CustomBotNew.query.filter_by(bot_id=bot_id, tenant_id=tenant_id, del_flg=False).first()
        if not bot:
            logger.error(f"Bot not found or unauthorized for bot_id: {bot_id}, tenant_id: {tenant_id}")
            return error_response(message = "Bot not found or unauthorized!", data = None, code = 404)

        if bot.greeting_type != "static" or not bot.greeting_message:
            logger.error("Bot is not set to static greeting or no greeting message provided")
            return error_response(message = "Bot is not set to static greeting or no greeting message provided!", data = None, code = 400)

        multi_agent_system = MultiAgentSystem(tenant_id=tenant_id, bot_id=bot_id)
        multi_agent_system._save_static_greeting_to_history()
        logger.info(f"Static greeting saved for bot_id: {bot_id}")
        return success_response(message = "Success", data = {
            "message": "Static greeting saved to chat history successfully!",
            "bot_id": bot.bot_id
        }, code = 200)

    except Exception as e:
        logger.error(f"Error saving static greeting for bot_id {bot_id}: {str(e)}")
        return error_response(message = f"An unexpected error occurred: {str(e)}", data = None, code = 500)

@custom_bot_blueprint_new.route('/uploads/backgrounds/<filename>')
def uploaded_background(filename):
    try:
        return send_from_directory(os.path.join(current_app.root_path, 'uploads', 'backgrounds'), filename)
    except Exception as e:
        logger.error(f"Error serving background image {filename}: {str(e)}")
        return error_response(message = "File not found", data = None, code = 404)

@custom_bot_blueprint_new.route('/uploads/avatars/<filename>')
def uploaded_avatars(filename):
    try:
        return send_from_directory(os.path.join(current_app.root_path, 'uploads', 'avatars'), filename)
    except Exception as e:
        logger.error(f"Error serving avatar image {filename}: {str(e)}")
        return error_response(message = "File not found", data = None, code = 404)


@custom_bot_blueprint_new.route('/resolve-instance/<instance_id>')
def resolve_instance(instance_id):
    try:
        host = request.host
        subdomain = host.split('.')[0] if '.' in host else None
        api_key = request.headers.get("X-API-Key")

        session = next(db_session())
        user = None

        if api_key:
            user = session.query(LoginUser).filter_by(api_key=api_key, del_flg=False).first()
            if not user:
                logger.error("Invalid API key provided")
                return error_response(message = "Invalid API key", data = None, code = 401)
        elif subdomain:
            user = session.query(Tenant).join(LoginUser).filter(LoginUser.account_name == subdomain, Tenant.tenant_status == "Active", LoginUser.del_flg == False).first()
            if not user:
                logger.error(f"No active tenant found for subdomain: {subdomain}")
                return error_response(message = "Subdomain not found or inactive", data = None, code = 404)
        else:
            logger.error("Subdomain or API key required")
            return error_response(message = "Subdomain or API key required", data = None, code = 400)

        bot = session.query(CustomBotNew).filter_by(
            instance_id=instance_id,
            tenant_id=user.tenant_id,
            del_flg=False
        ).first()
        if not bot:
            logger.error(f"Bot not found for instance_id: {instance_id}, tenant_id: {user.tenant_id}")
            abort(404, description=f"Invalid or inactive instance ID: {instance_id}")
        logger.info(f"Resolved instance_id {instance_id} to bot_id: {bot.bot_id}")
        return jsonify({
            "data": {"bot_id": bot.bot_id},
            "status": "success",
            "message": "Instance resolved successfully"
        })

    except Exception as e:
        logger.error(f"Error resolving instance_id {instance_id}: {str(e)}")
        abort(500, description=f"Server error: {str(e)}")
    finally:
        session.close()

@custom_bot_blueprint_new.route('/get-customize-by-bot/<bot_id>')
@jwt_required()
def get_customize_by_bot(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return error_response(message = "Tenant ID not found in token", data = None, code = 401)

        session = next(db_session())
        bot = session.query(CustomBotNew).filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()
        if not bot:
            logger.error(f"Bot not found for bot_id: {bot_id}, tenant_id: {tenant_id}")
            abort(404, description=f"Invalid or inactive bot ID: {bot_id}")
        if not bot.instance_id:
            logger.error(f"No instance_id configured for bot_id: {bot_id}")
            abort(400, description=f"No instance_id configured for bot_id: {bot_id}")

        base_url = current_app.config.get('BASE_URL', 'https://api.jnanic.com')
        avatar_base_path = "uploads/avatars"
        avatar_url = (
            f"{base_url}/{avatar_base_path}/{basename(bot.avatar)}"
            if bot.avatar and not bot.avatar.startswith(('http://', 'https://'))
            else bot.avatar or ""
        )
        logger.info(f"Fetched customization for bot_id: {bot_id}")
        return jsonify({
            "data": {
                "instance_id": bot.instance_id,
                "chatbot_name": bot.bot_name or "Chatbot",
                "disclaimer_text": bot.disclaimer_text or "Ã‚Â© 2025 Tata Realty. All rights reserved.",
                "greeting_type": bot.greeting_type or "static",
                "greeting_message": bot.greeting_message or "Hello! I'm your friendly assistant.",
                "avatar": avatar_url,
                "colors": bot.colors or {}
            },
            "status": "success",
            "message": "Customization details fetched successfully"
        })

    except Exception as e:
        logger.error(f"Error fetching customization for bot_id {bot_id}: {str(e)}")
        abort(500, description=f"Server error: {str(e)}")
    finally:
        session.close()


@custom_bot_blueprint_new.route('/chatbot/<instance_id>', methods=["GET"])
def serve_chatbot_by_instance(instance_id):
    try:
        # Ã¢â€ Â CHANGED: single lookup by instance_id, no subdomain/session needed
        draft = CustomBotNew.query.filter_by(
            instance_id=instance_id,
            del_flg=False
        ).first()

        if not draft:
            return jsonify({"error": "Bot not found", "status": "error"}), 404

        # Ã¢â€ Â CHANGED: resolve config handles LIVE vs CREATED
        try:
            config = resolve_bot_config(draft)
        except PermissionError:
            return jsonify({"error": "Bot is paused or unavailable", "status": "error"}), 403
        except ValueError:
            return jsonify({"error": "Bot configuration unavailable", "status": "error"}), 503

        logger.info(
            f"Serving chatbot | instance_id={instance_id} | "
            f"bot_id={draft.bot_id} | test={config['is_test_mode']}"
        )

        # Ã¢â€ Â CHANGED: all template vars come from config, not raw bot object
        return render_template(
            "chatbot.html",
            bot_id=config["bot_id"],
            bot_name=config["bot_name"],
            theme=config["theme"],
            colors=config["colors"],
            position=config["position"],
            greeting_message=config["greeting_message"],
            disclaimer_text=config["disclaimer_text"],
            background_image=config["background_image"],
        )

    except Exception:
        logger.exception(f"Error serving chatbot | instance_id={instance_id}")
        return jsonify({"error": "Server error", "status": "error"}), 500
    

@custom_bot_blueprint_new.route("/<int:bot_id>", methods=["GET"])
@jwt_required()
def get_bot_by_id(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return error_response(message = "Tenant ID not found in token", data = {}, code = 401)

        bot = CustomBotNew.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not bot:
            logger.error(f"Bot not found for bot_id: {bot_id}, tenant_id: {tenant_id}")
            return error_response(message = "Bot not found or unauthorized!", data = {}, code = 404)

        base_url = current_app.config.get("BASE_URL", "https://api.jnanic.com")
        avatar_base_path = "uploads/avatars"
        bg_base_path = "custom-bot/uploads/backgrounds"  # change if your folder differs

        avatar_url = (
            f"{base_url}/{avatar_base_path}/{os.path.basename(bot.avatar)}"
            if bot.avatar and not bot.avatar.startswith(("http://", "https://"))
            else bot.avatar or ""
        )

        background_url = (
            f"{base_url}/{bg_base_path}/{os.path.basename(bot.background_image)}"
            if bot.background_image and not bot.background_image.startswith(("http://", "https://"))
            else bot.background_image or ""
        )

        bot_details = {
            "avatar": avatar_url,
            "background_image": background_url,   # Ã¢Å“â€¦ added

            "bot_id": bot.bot_id,
            "theme": bot.theme,
            "color": bot.colors,
            "bot_name": bot.bot_name,
            "core_features": bot.core_features if isinstance(bot.core_features, list) else json.loads(bot.core_features) if bot.core_features else [""],
            "created_at": bot.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "industry": bot.industry.value,
            "instructions": bot.instructions if isinstance(bot.instructions, list) else json.loads(bot.instructions) if bot.instructions else [""],
            "purpose": bot.purpose or "",
            "status": bot.bot_status,
            "tenant_id": bot.tenant_id,
            "kb_ids": bot.kb_ids if isinstance(bot.kb_ids, list) else [],
            "tone_of_voice": bot.tone_of_voice.value,
            "updated_at": bot.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "greeting_type": bot.greeting_type or "dynamic",
            "greeting_message": bot.greeting_message or "Hello! I'm your friendly assistant. How can I help you today?"
        }

        logger.info(f"Fetched bot details for bot_id: {bot_id}")
        return success_response(message = "Bot details fetched successfully", data = bot_details, code = 200)

    except Exception as e:
        logger.error(f"Error fetching bot details for bot_id {bot_id}: {str(e)}")
        return error_response(message = f"An error occurred: {str(e)}", data = {}, code = 500)

def resolve_domain_to_ip(domain):
    try:
        return socket.gethostbyname(domain)
    except socket.gaierror:
        return None

import jwt
import os
from datetime import datetime, timedelta

def generate_temp_token(bot_id, client_ip, domain, tenant_id=None):
    return create_access_token(
        identity=str(bot_id),
        additional_claims={
            "bot_id": bot_id,
            "client_ip": client_ip,
            "domain": domain,
            "tenant_id": tenant_id
        }
    )

    token = jwt.encode(
        payload,
        os.getenv("JWT_SECRET_KEY"),
        algorithm="HS256"
    )

    return token
    
def require_valid_token(f):
    @wraps(f)
    def decorated_func(*args, **kwargs):
        data = request.get_json(silent=True) or {}
        bot_id = data.get("bot_id")

        if not bot_id:
            return error_response(message = "Bot ID is required.", data = None, code = 400)

        bot = CustomBotNew.query.filter(
            CustomBotNew.bot_id == bot_id,
            CustomBotNew.del_flg == False,
            CustomBotNew.bot_status.in_([
                BotStatusEnum.CREATED,
                BotStatusEnum.LIVE,
                BotStatusEnum.PAUSED
            ])
        ).first()
        if not bot:
            return error_response(message = "Invalid bot_id or bot not found.", data = None, code = 404)

        # Verify JWT (token already contains allowed IP/domain)
        verify_jwt_in_request()
        jwt_data = get_jwt()
        g.bot_id = get_jwt_identity()
        g.client_ip = jwt_data.get("client_ip")
        g.domain = jwt_data.get("domain")

        return f(*args, **kwargs)

    return decorated_func




@custom_bot_blueprint_new.route("/restriction/get/<int:bot_id>", methods=["GET"])
@jwt_required(optional=True)
def get_restriction_entries(bot_id):
    current_user = get_jwt_identity()
    login_user = LoginUser.query.filter_by(login_id=current_user).first()
    if not login_user or not login_user.tenant_id:
        return error_response(message = "Unauthorized", data = None, code = 403)

    bot = CustomBotNew.query.filter_by(bot_id=bot_id, tenant_id=login_user.tenant_id).first()
    if not bot:
        return error_response(message = "Bot not found or unauthorized", data = None, code = 404)

    entries = CustomBotNewAccessRestriction.query.filter_by(bot_id=bot_id).all()

    # Only pure IPs (not mapped to any domain)
    ip_list = [e.allowed_ip for e in entries if e.allowed_ip and e.allowed_domain is None]

    # Only base domains (do not return mapped IPs)
    domain_list = list({e.allowed_domain for e in entries if e.allowed_domain})

    return jsonify({
        "ip": ip_list,
        "domain": domain_list,
        "status": True
    })


@custom_bot_blueprint_new.route("/restriction/delete", methods=["POST"])
@jwt_required(optional=True)
def delete_restriction_entry():
    current_user = get_jwt_identity()
    login_user = LoginUser.query.filter_by(login_id=current_user).first()
    if not login_user or not login_user.tenant_id:
        return error_response(message = "Unauthorized", data = None, code = 403)

    data = request.get_json()
    bot_id = data.get("bot_id")
    value = data.get("value")
    restriction_type = data.get("type")

    if not bot_id or not value or restriction_type not in [0, 1]:
        return error_response(message = "Invalid data", data = None, code = 400)

    bot = CustomBotNew.query.filter_by(bot_id=bot_id, tenant_id=login_user.tenant_id).first()
    if not bot:
        return error_response(message = "Bot not found or unauthorized", data = None, code = 404)

    if restriction_type == 0:
        deleted_count = CustomBotNewAccessRestriction.query.filter_by(
            bot_id=bot_id,
            allowed_ip=value,
            allowed_domain=None
        ).delete(synchronize_session=False)
    else:
        deleted_count = CustomBotNewAccessRestriction.query.filter(
            CustomBotNewAccessRestriction.bot_id == bot_id,
            CustomBotNewAccessRestriction.allowed_domain == value
        ).delete(synchronize_session=False)

    if deleted_count == 0:
        return error_response(message = "No matching entry found", data = None, code = 404)

    db.session.commit()
    return success_response(message = "Entry deleted", data = None, code = 200)


@custom_bot_blueprint_new.route("/restriction", methods=["POST"])
@jwt_required(optional=True)
def add_access_restrictions():
    current_user = get_jwt_identity()
    login_user = LoginUser.query.filter_by(login_id=current_user).first()
    if not login_user or not login_user.tenant_id:
        return error_response(message = "Unauthorized", data = None, code = 403)

    payload = request.get_json()
    bot_id = payload.get("bot_id")
    entries = payload.get("data", [])
    type_ = payload.get("type")  # 0 = IP, 1 = Domain

    if not bot_id or type_ not in [0, 1] or not isinstance(entries, list):
        return error_response(message = "Invalid input", data = None, code = 400)

    bot = CustomBotNew.query.filter_by(bot_id=bot_id, tenant_id=login_user.tenant_id).first()
    if not bot:
        return error_response(message = "Bot not found or unauthorized", data = None, code = 404)

    # Fetch existing entries
    existing_entries = CustomBotNewAccessRestriction.query.filter_by(bot_id=bot_id).all()
    existing_ips = {r.allowed_ip for r in existing_entries if r.allowed_ip}
    existing_domains = {(r.allowed_domain, r.allowed_ip) for r in existing_entries if r.allowed_domain}

    for entry in entries:
        if type_ == 0:  # IP
            try:
                ipaddress.ip_address(entry)
            except ValueError:
                return error_response(message = f"Invalid IP address: {entry}", data = None, code = 400)
            if entry not in existing_ips:
                db.session.add(CustomBotNewAccessRestriction(bot_id=bot_id, allowed_ip=entry))
                existing_ips.add(entry)
        else:  # Domain
            if not any(d == entry for (d, ip) in existing_domains):
                db.session.add(CustomBotNewAccessRestriction(bot_id=bot_id, allowed_domain=entry, allowed_ip=None))
                existing_domains.add((entry, None))
            try:
                _, _, ip_list = socket.gethostbyname_ex(entry)
                for ip in ip_list:
                    if (entry, ip) not in existing_domains:
                        db.session.add(CustomBotNewAccessRestriction(bot_id=bot_id, allowed_domain=entry, allowed_ip=ip))
                        existing_domains.add((entry, ip))
            except socket.gaierror:
                pass

    db.session.commit()
    return success_response(message = "Entries added or updated", data = None, code = 200)




@custom_bot_blueprint_new.route("/remove-kb", methods=["DELETE"])
@jwt_required()
def remove_kb_from_bot():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        data = request.get_json(silent=True) or {}
        bot_id = data.get("bot_id")
        kb_id = data.get("kb_id")

        if not bot_id or not kb_id:
            return error_response(message = "bot_id and kb_id are required", data = None, code = 400)

        bot = CustomBotNew.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not bot:
            return error_response(message = "Bot not found or unauthorized", data = None, code = 404)

        if not isinstance(bot.kb_ids, list):
            bot.kb_ids = []

        bot.kb_ids = [x for x in bot.kb_ids if x != int(kb_id)]

        db.session.commit()

        return success_response(message = "Success", data = {
            "message": "Knowledge base removed successfully",
            "bot_id": bot_id,
            "removed_kb_id": kb_id,
            "remaining_kb_ids": bot.kb_ids
        }, code = 200)

    except Exception as e:
        db.session.rollback()
        logger.error(f"Remove KB failed | bot_id={bot_id} | {str(e)}")
        return error_response(message = "Internal server error", data = None, code = 500)



@custom_bot_blueprint_new.route("/<int:bot_id>/kbs", methods=["GET"])
@jwt_required()
def get_kbs_of_bot(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return error_response(message = "Tenant ID missing", data = None, code = 401)

        # Fetch bot
        bot = CustomBotNew.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not bot:
            return error_response(message = "Bot not found or unauthorized", data = None, code = 404)

        # Ensure kb_ids is a list
        kb_ids = bot.kb_ids if isinstance(bot.kb_ids, list) else []

        if not kb_ids:
            return success_response(message = "Success", data = {
                "bot_id": bot_id,
                "kb_ids": [],
                "knowledge_bases": []
            }, code = 200)

        # Fetch KB details
        kbs = KnowledgeBase.query.filter(
            KnowledgeBase.knowledge_base_id.in_(kb_ids),
            KnowledgeBase.tenant_id == tenant_id,
            KnowledgeBase.del_flg == False
        ).all()

        kb_data = []
        for kb in kbs:
            kb_data.append({
                "knowledge_base_id": kb.knowledge_base_id,
                "knowledge_base_name": kb.knowledge_base_name,
                "collection_name": kb.collection_name,
                "upload_pdf": kb.upload_pdf,
                "scrap_url": kb.scrap_url,
                "created_at": kb.created_at.isoformat() if kb.created_at else None,
                "updated_at": kb.updated_at.isoformat() if kb.updated_at else None
            })

        return success_response(message = "Success", data = {
            "bot_id": bot_id,
            "kb_ids": kb_ids,
            "knowledge_bases": kb_data
        }, code = 200)

    except Exception as e:
        logger.exception(f"Get KBs failed | bot_id={bot_id}")
        return error_response(message = "Internal server error", data = None, code = 500)



@custom_bot_blueprint_new.route('/get-customize/<instance_id>', methods=['GET'])
def get_customization(instance_id):
    session = next(db_session())
    try:
        host = request.host
        subdomain = host.split('.')[0] if '.' in host else None
        api_key = request.headers.get("X-API-Key")

        logger.info(
            f"Customization request | instance_id={instance_id} | subdomain={subdomain} | api_key={'YES' if api_key else 'NO'}"
        )

        user = None

        # -------------------------
        # AUTH: API KEY
        # -------------------------
        if api_key:
            user = session.query(LoginUser).filter_by(
                api_key=api_key,
                del_flg=False
            ).first()

            if not user:
                return error_response("Invalid API key", None, 401)

        # -------------------------
        # AUTH: SUBDOMAIN
        # -------------------------
        elif subdomain:
            tenant = session.query(Tenant).join(LoginUser).filter(
                LoginUser.account_name == subdomain,
                Tenant.tenant_status == "Active",
                LoginUser.del_flg == False
            ).first()

            if tenant:
                user = session.query(LoginUser).filter_by(
                    account_name=subdomain,
                    del_flg=False
                ).first()

            if not user:
                return error_response("Invalid subdomain", None, 401)

        else:
            return error_response("Subdomain or API key required", None, 400)

        # -------------------------
        # FETCH BOT
        # -------------------------
        bot = session.query(CustomBotNew).filter_by(
            instance_id=instance_id,
            tenant_id=user.tenant_id,
            del_flg=False
        ).first()

        if not bot:
            return error_response("Bot not found", None, 404)

        # -------------------------
        # 🔥 IMPORTANT: RESOLVE CONFIG (LIVE / CREATED)
        # -------------------------
        try:
            config = resolve_bot_config(bot)
        except PermissionError:
            return error_response("Bot is not active", None, 403)
        except ValueError:
            return error_response("Bot config unavailable", None, 503)

        # -------------------------
        # BUILD URL BASE
        # -------------------------
        base_url = current_app.config.get("BASE_URL", "https://api.jnanic.com")
        avatar_base_path = "uploads/avatars"
        bg_base_path = "custom-bot/uploads/backgrounds"

        avatar_url = (
            f"{base_url}/{avatar_base_path}/{basename(config.get('avatar'))}"
            if config.get("avatar") and not config.get("avatar").startswith(("http://", "https://"))
            else config.get("avatar") or ""
        )

        background_url = (
            f"{base_url}/{bg_base_path}/{basename(config.get('background_image'))}"
            if config.get("background_image") and not config.get("background_image").startswith(("http://", "https://"))
            else config.get("background_image") or ""
        )

        # -------------------------
        # RESPONSE
        # -------------------------
        customization = {
            "bot_id": config.get("bot_id") or bot.bot_id,
            "instance_id": bot.instance_id,
            "chatbot_name": config.get("bot_name") or "Chatbot",
            "disclaimer_text": config.get("disclaimer_text") or "",
            "avatar": avatar_url,
            "background_image": background_url,
            "background_color": config.get("background_color"),
            "colors": config.get("colors") or {},
            "theme": config.get("theme"),
            "position": config.get("position"),
            "greeting_type": config.get("greeting_type") or "dynamic",
            "greeting_message": config.get("greeting_message") or "Hello! How can I help you?",
        }

        logger.info(f"Customization fetched | bot_id={bot.bot_id}")

        return jsonify({
            "data": customization,
            "status": "success",
            "message": "Customization fetched successfully"
        }), 200

    except Exception as e:
        logger.exception(f"Customization error | instance_id={instance_id}")
        return error_response("Server error", None, 500)

    finally:
        session.close()


@custom_bot_blueprint_new.route(
    "/<int:bot_id>/access-restriction",
    methods=["DELETE"]
)
@jwt_required()
@validate_bot_access(
    allowed_status=[BotStatusEnum.DRAFT, BotStatusEnum.CREATED, BotStatusEnum.LIVE]
)
def delete_access_restriction(bot_id):

    bot = g.bot

    try:
        data = request.get_json() or {}

        allowed_ip = data.get("allowed_ip")
        allowed_domain = data.get("allowed_domain")

        if not allowed_ip and not allowed_domain:
            return error_response(
                message="Either allowed_ip or allowed_domain is required",
                data=None,
                code=400
            )

        query = CustomBotAccessRestriction.query.filter_by(bot_id=bot.bot_id)

        if allowed_ip:
            query = query.filter(
                CustomBotAccessRestriction.allowed_ip == allowed_ip
            )

        if allowed_domain:
            query = query.filter(
                CustomBotAccessRestriction.allowed_domain == allowed_domain
            )

        restrictions = query.all()

        if not restrictions:
            return error_response(
                message="No matching restriction found",
                data=None,
                code=404
            )

        for r in restrictions:
            db.session.delete(r)

        db.session.commit()

        return success_response(
            message="Success",
            data={
                "message": "Access restriction deleted successfully",
                "deleted_count": len(restrictions)
            },
            code=200
        )

    except Exception:
        db.session.rollback()
        logger.exception(f"Error deleting restriction | bot_id={bot.bot_id}")
        return error_response(
            message="Unexpected error occurred",
            data=None,
            code=500
        )
