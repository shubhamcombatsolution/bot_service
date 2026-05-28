import logging
from functools import wraps
from flask import jsonify, g
from flask_jwt_extended import get_jwt
from app.models.new_models.custom_bot import CustomBotNew
from app.models.tenant import Tenant
from app.models.knowledge_base import KnowledgeBase
from app.models.custombot_access_restriction import CustomBotAccessRestriction
import json
import ipaddress
import socket
import os
from werkzeug.utils import secure_filename
from app.models.new_models.custom_bot import CustomBotNew, BotStatusEnum
from app.models.new_models.bot_versions import BotVersion
import os
import hashlib
from flask import current_app
from werkzeug.utils import secure_filename
from app.models import db


logger = logging.getLogger(__name__)


UPLOAD_FOLDER = "uploads/avatars"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def allowed_file(filename):
    return (
        '.' in filename and
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )

def _normalize_enum_text(value):
    return " ".join(
        value.strip()
        .replace("&", " and ")
        .replace("-", " ")
        .replace("_", " ")
        .lower()
        .split()
    )

def parse_enum(enum_class, value, field_name):
    if not value:
        raise ValueError(f"{field_name} cannot be empty")

    normalized_input = _normalize_enum_text(value)

    for member in enum_class:
        normalized_member_value = _normalize_enum_text(member.value)
        normalized_member_name = _normalize_enum_text(member.name)

        if normalized_input in {
            normalized_member_value,
            normalized_member_name
        }:
            return member

    raise ValueError(
        f"Invalid {field_name}. Allowed values: {[e.value for e in enum_class]}"
    )


def validate_bot_access(allowed_status=None):
    """
    Decorator to validate bot access in a multi-tenant hierarchy.

    Validates:
    - JWT contains tenant_id
    - Tenant exists
    - Bot exists
    - Bot belongs to tenant OR parent tenant
    - Bot is not soft deleted
    - Optional status validation

    Injects:
        g.bot
        g.tenant
        g.allowed_tenant_ids
    """

    def decorator(func):

        @wraps(func)
        def wrapper(*args, **kwargs):

            bot_id = kwargs.get("bot_id")

            if not bot_id:
                logger.warning("Bot ID missing in route")
                return jsonify({"error": "Bot ID is required"}), 400

            claims = get_jwt()
            tenant_id = claims.get("tenant_id")

            if not tenant_id:
                logger.warning("Tenant ID missing in JWT")
                return jsonify({"error": "Unauthorized"}), 401

            tenant = Tenant.query.filter_by(
                tenant_id=tenant_id,
                del_flg=False
            ).first()

            if not tenant:
                logger.warning(f"Tenant not found | tenant_id={tenant_id}")
                return jsonify({"error": "Invalid tenant"}), 401

            # --------------------------------------------
            # Build Allowed Tenant List (Self + Parent)
            # --------------------------------------------
            allowed_tenant_ids = [tenant.tenant_id]

            parent_id = getattr(tenant, "parent_id", None)

            if parent_id:
                allowed_tenant_ids.append(parent_id)

            logger.debug(
                f"Allowed tenant scope: {allowed_tenant_ids}"
            )

            # --------------------------------------------
            # Validate Bot Ownership
            # --------------------------------------------
            bot = CustomBotNew.query.filter(
                CustomBotNew.bot_id == bot_id,
                CustomBotNew.tenant_id.in_(allowed_tenant_ids),
                CustomBotNew.del_flg == False
            ).first()

            if not bot:
                logger.warning(
                    f"Bot access denied | bot_id={bot_id} | "
                    f"tenant_scope={allowed_tenant_ids}"
                )
                return jsonify({
                    "error": "Bot not found or unauthorized"
                }), 404

            # --------------------------------------------
            # Optional Status Validation
            # --------------------------------------------
            if allowed_status:
                if bot.bot_status not in allowed_status:
                    logger.warning(
                        f"Invalid bot status | bot_id={bot_id} | "
                        f"current_status={bot.bot_status}"
                    )
                    return jsonify({
                        "error": "Bot is not in allowed state"
                    }), 400

            # Inject into request context
            g.bot = bot
            g.tenant = tenant
            g.allowed_tenant_ids = allowed_tenant_ids

            logger.debug(
                f"Bot access granted | bot_id={bot_id} | "
                f"tenant_scope={allowed_tenant_ids}"
            )

            return func(*args, **kwargs)

        return wrapper

    return decorator


def clean_enum_input(value):
    """Returns None if value is empty, quoted-empty, or literal 'null'"""
    if not value or value.strip().lower() in {'', '""', "null"}:
        return None
    return value.strip().strip('"').strip("'")


def process_kb_functionalities(functionalities):

    if not isinstance(functionalities, list):
        return None, "kb_functionalities must be a list"

    cleaned = []

    for item in functionalities:
        if not isinstance(item, dict):
            continue

        text = item.get("text")
        selected = item.get("selected", False)

        if not text or not isinstance(text, str):
            continue

        cleaned.append({
            "text": text.strip(),
            "selected": bool(selected)
        })

    return cleaned, None


def process_instructions(instructions):

    if not isinstance(instructions, list):
        return None, "Instructions must be a list"

    cleaned = []

    for inst in instructions:
        if not isinstance(inst, dict):
            continue

        inst_id = inst.get("id")
        question = inst.get("question")
        selected = inst.get("selected", False)

        if not inst_id or not question:
            continue

        cleaned.append({
            "id": int(inst_id),
            "question": question.strip(),
            "selected": bool(selected)
        })

    if not cleaned:
        return None, "No valid instructions provided"

    return cleaned, None


def process_kb_ids(bot, kb_ids_raw, allowed_tenant_ids):

    if kb_ids_raw is None:
        return None, "kb_ids is required"

    if isinstance(kb_ids_raw, list):
        raw_ids = kb_ids_raw
    else:
        raw_ids = [kb_ids_raw]

    # ----------------------------------------
    # Validate Integer
    # ----------------------------------------
    try:
        incoming_ids = [int(kb_id) for kb_id in raw_ids]
    except (TypeError, ValueError):
        return None, "kb_ids must be integer or list of integers"

    # ----------------------------------------
    # Validate KB Existence + Tenant Scope
    # ----------------------------------------
    valid_kbs = KnowledgeBase.query.filter(
        KnowledgeBase.knowledge_base_id.in_(incoming_ids),
        KnowledgeBase.tenant_id.in_(allowed_tenant_ids),
        KnowledgeBase.del_flg == False
    ).all()

    valid_ids = [kb.knowledge_base_id for kb in valid_kbs]

    # If any ID does not exist → reject
    if set(incoming_ids) != set(valid_ids):
        invalid_ids = list(set(incoming_ids) - set(valid_ids))
        return None, f"Invalid or unauthorized KB IDs: {invalid_ids}"

    # ----------------------------------------
    # Use only frontend-selected KB IDs
    # ----------------------------------------
    selected_ids = list(dict.fromkeys(valid_ids))
    return selected_ids, None


def process_core_features(core_features):
    """
    Normalize core_features payload.

    Accepts:
    1) dict tool -> list[{"label","selected"}]
    2) dict tool -> bool/str/dict
    3) list[str] or list[dict]
    """

    if core_features is None:
        return None, "core_features is required"

    if isinstance(core_features, str):
        try:
            core_features = json.loads(core_features)
        except Exception:
            return None, "core_features must be valid JSON when provided as string"

    normalized = {}

    if isinstance(core_features, list):
        for item in core_features:
            if isinstance(item, str):
                tool_name = clean_enum_input(item)
                if tool_name:
                    normalized[tool_name] = [{"label": tool_name, "selected": True}]
                continue

            if isinstance(item, dict):
                tool_name = clean_enum_input(
                    item.get("tool")
                    or item.get("name")
                    or item.get("key")
                    or item.get("label")
                )
                if tool_name:
                    normalized[tool_name] = [{
                        "label": tool_name,
                        "selected": bool(item.get("selected", True))
                    }]

        if not normalized:
            return None, "No valid core_features provided"
        return normalized, None

    if not isinstance(core_features, dict):
        return None, "core_features must be a dictionary or list"

    for tool, features in core_features.items():
        tool_name = clean_enum_input(tool)
        if not tool_name:
            continue

        # Legacy shape: {"tool": true/false}
        if isinstance(features, bool):
            normalized[tool_name] = [{"label": tool_name, "selected": features}]
            continue

        # Legacy shape: {"tool": "Feature Label"}
        if isinstance(features, str):
            label = clean_enum_input(features)
            if label:
                normalized[tool_name] = [{"label": label, "selected": True}]
            continue

        # Accept single object by wrapping into list
        if isinstance(features, dict):
            features = [features]

        if not isinstance(features, list):
            continue

        cleaned_features = []
        for feature in features:
            if isinstance(feature, str):
                label = clean_enum_input(feature)
                if label:
                    cleaned_features.append({
                        "label": label,
                        "selected": True
                    })
                continue

            if not isinstance(feature, dict):
                continue

            label = clean_enum_input(
                feature.get("label")
                or feature.get("name")
                or feature.get("tool")
            )
            selected = bool(feature.get("selected", False))

            if not label:
                continue

            cleaned_features.append({
                "label": label,
                "selected": selected
            })

        normalized[tool_name] = cleaned_features

    if not normalized:
        return None, "No valid core_features provided"

    return normalized, None

def process_access_restrictions(bot, tenant_id, restrictions_payload):
    """
    Handles IP / Domain restriction insertion.
    Supports payload:
    {
        "ips": [],
        "domains": []
    }
    """

    if restrictions_payload is None:
        return

    ips = restrictions_payload.get("ips", [])
    domains = restrictions_payload.get("domains", [])

    if not isinstance(ips, list) or not isinstance(domains, list):
        raise ValueError("Invalid restriction payload")

    # Treat payload as source-of-truth: replace existing restrictions.
    CustomBotAccessRestriction.query.filter_by(bot_id=bot.bot_id).delete(
        synchronize_session=False
    )
    existing_ips = set()
    existing_domains = set()

    # -------------------------
    # Process IP Restrictions
    # -------------------------
    for entry in ips:

        try:
            ipaddress.ip_address(entry)
        except ValueError:
            raise ValueError(f"Invalid IP address: {entry}")

        if entry not in existing_ips:
            db.session.add(
                CustomBotAccessRestriction(
                    bot_id=bot.bot_id,
                    allowed_ip=entry
                )
            )
            existing_ips.add(entry)

    # -------------------------
    # Process Domain Restrictions
    # -------------------------
    for entry in domains:
        if (entry, None) not in existing_domains:
            db.session.add(
                CustomBotAccessRestriction(
                    bot_id=bot.bot_id,
                    allowed_domain=entry,
                    allowed_ip=None
                )
            )

        # try:
        #     _, _, ip_list = socket.gethostbyname_ex(entry)

        #     for ip in ip_list:
        #         if (entry, ip) not in existing_domains:
        #             db.session.add(
        #                 CustomBotAccessRestriction(
        #                     bot_id=bot.bot_id,
        #                     allowed_domain=entry,
        #                     allowed_ip=ip
        #                 )
        #             )
        #             existing_domains.add((entry, ip))

        # except socket.gaierror:
        #     pass     
        
        
def generate_file_hash(file_obj):
    """
    Generate SHA256 hash of uploaded file content.
    """
    file_obj.seek(0)
    content = file_obj.read()
    file_obj.seek(0)
    return hashlib.sha256(content).hexdigest()


def handle_file_upload(file_obj, folder):
    """
    Save uploaded file using content-hash filename.
    Prevents duplicate uploads for identical files.
    """

    if not file_obj or file_obj.filename == "":
        return None

    if not allowed_file(file_obj.filename):
        raise ValueError("Invalid file type")

    original_filename = secure_filename(file_obj.filename)

    if "." not in original_filename:
        raise ValueError("File must have an extension")

    ext = original_filename.rsplit(".", 1)[1].lower()

    # Generate content hash
    file_hash = generate_file_hash(file_obj)

    # Final deterministic filename
    hashed_filename = f"{file_hash}.{ext}"

    upload_folder = os.path.join(
        current_app.root_path,
        "uploads",
        folder
    )

    os.makedirs(upload_folder, exist_ok=True)

    file_path = os.path.join(upload_folder, hashed_filename)

    # Only save if file does not already exist
    if not os.path.exists(file_path):
        file_obj.save(file_path)

    return hashed_filename

def validate_customization_fields(data):
    colors_raw = data.get("colors")

    print("RAW COLORS:", repr(colors_raw))  # DEBUG

    if not colors_raw:
        raise ValueError("colors is required")

    try:
        # ✅ Handle both string and dict safely
        if isinstance(colors_raw, str):
            colors_json = json.loads(colors_raw.strip())
        else:
            colors_json = colors_raw
    except Exception as e:
        print("JSON ERROR:", str(e))
        raise ValueError(f"Invalid colors JSON format: {colors_raw}")

    if not isinstance(colors_json, dict):
        raise ValueError("colors must be a JSON object")

    return colors_json

def build_snapshot(bot: CustomBotNew) -> dict:
    """Captures full bot config — called at publish time and in test mode."""
    logger.info(f"[build_snapshot] Building snapshot for bot_id={bot.bot_id} | status={bot.bot_status}")

    # --- kb_ids ---
    kb_ids = bot.kb_ids or []
    logger.debug(f"[build_snapshot] bot.kb_ids raw value={kb_ids} | type={type(kb_ids).__name__}")
    if isinstance(kb_ids, str):
        try:
            kb_ids = json.loads(kb_ids)
            logger.info(f"[build_snapshot] kb_ids parsed from string → {kb_ids}")
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[build_snapshot] Could not parse kb_ids for bot {bot.bot_id}: {kb_ids} — defaulting to []")
            kb_ids = []

    # --- core_features ---
    core_features = bot.core_features or {}
    logger.debug(f"[build_snapshot] bot.core_features raw type={type(core_features).__name__} | value_preview={str(core_features)[:100]}")
    if isinstance(core_features, str):
        try:
            core_features = json.loads(core_features)
            logger.info(f"[build_snapshot] core_features parsed from string successfully")
        except Exception as e:
            logger.warning(f"[build_snapshot] Could not parse core_features for bot {bot.bot_id}: {e} — defaulting to {{}}")
            core_features = {}

    # --- instructions ---
    instructions = bot.instructions or []
    logger.debug(f"[build_snapshot] bot.instructions raw type={type(instructions).__name__} | count={len(instructions) if isinstance(instructions, (list, dict)) else 'N/A'}")
    if isinstance(instructions, str):
        try:
            instructions = json.loads(instructions)
            logger.info(f"[build_snapshot] instructions parsed from string → {len(instructions)} items")
        except Exception as e:
            logger.warning(f"[build_snapshot] Could not parse instructions for bot {bot.bot_id}: {e} — defaulting to []")
            instructions = []

    snapshot = {
        "bot_id":             bot.bot_id,
        "instance_id":        bot.instance_id,
        "channel":            bot.channel.value if bot.channel else None,
        "whatsapp_credentials": bot.whatsapp_credentials or {},
        "slack_credentials": {
            "bot_token": (bot.slack_cred.bot_token if getattr(bot, "slack_cred", None) else "") or "",
            "signing_secret": (bot.slack_cred.signing_secret if getattr(bot, "slack_cred", None) else "") or "",
            "app_token": (bot.slack_cred.app_token if getattr(bot, "slack_cred", None) else "") or "",
            "channel_id": (bot.slack_cred.default_channel_id if getattr(bot, "slack_cred", None) else "") or "",
        },
        "bot_name":           bot.bot_name,
        "tone_of_voice":      bot.tone_of_voice.value if bot.tone_of_voice else None,
        "industry":           bot.industry.value if bot.industry else None,
        "purpose":            bot.purpose,
        "avatar":             bot.avatar,
        "core_features":      core_features,
        "instructions":       instructions,
        "kb_ids":             kb_ids,
        "kb_functionalities": bot.kb_functionalities or [],
        "position":           bot.position,
        "page_config":        bot.page_config,
        "specific_pages":     bot.specific_pages or [],
        "theme":              bot.theme,
        "colors":             bot.colors or {},
        "background_image":   bot.background_image,
        "background_color":   bot.background_color,
        "disclaimer_text":    bot.disclaimer_text,
        "greeting_type":      bot.greeting_type,
        "greeting_message":   bot.greeting_message,
        "memory_mode":        getattr(bot, "memory_mode", None),
    }

    logger.info(
        f"[build_snapshot] Snapshot built | bot={bot.bot_id} | "
        f"kb_ids={kb_ids} | "
        f"instructions_count={len(instructions) if isinstance(instructions, list) else 'non-list'} | "
        f"core_features_type={type(core_features).__name__} | "
        f"core_features_keys={list(core_features.keys()) if isinstance(core_features, dict) else 'non-dict'}"
    )

    return snapshot


def resolve_bot_config(bot: CustomBotNew) -> dict:
    logger.info(f"[resolve_bot_config] Resolving config | bot_id={bot.bot_id} | status={bot.bot_status}")

    if bot.bot_status == BotStatusEnum.LIVE:
        logger.info(f"[resolve_bot_config] LIVE bot — reading from published snapshot | published_version_id={bot.published_version_id}")

        if not bot.published_version_id:
            logger.error(f"[resolve_bot_config] LIVE bot {bot.bot_id} has no published_version_id")
            raise ValueError(
                f"Bot {bot.bot_id} is LIVE but has no published_version_id."
            )

        live_version = BotVersion.query.get(bot.published_version_id)
        if not live_version:
            logger.error(f"[resolve_bot_config] Published version {bot.published_version_id} not found for bot {bot.bot_id}")
            raise ValueError(
                f"Published version not found for bot {bot.bot_id}."
            )

        config = {"is_test_mode": False, **live_version.snapshot}
        logger.info(
            f"[resolve_bot_config] LIVE config loaded from snapshot | bot={bot.bot_id} | "
            f"kb_ids={config.get('kb_ids')} | "
            f"kb_ids_type={type(config.get('kb_ids')).__name__} | "
            f"instructions_count={len(config.get('instructions', [])) if isinstance(config.get('instructions'), list) else 'non-list'}"
        )
        return config

    elif bot.bot_status in (BotStatusEnum.CREATED, BotStatusEnum.DRAFT):
        logger.info(f"[resolve_bot_config] CREATED/DRAFT bot — building snapshot from live DB row | bot_id={bot.bot_id}")
        config = {"is_test_mode": True, **build_snapshot(bot)}
        logger.info(
            f"[resolve_bot_config] TEST config built | bot={bot.bot_id} | "
            f"kb_ids={config.get('kb_ids')} | "
            f"kb_ids_type={type(config.get('kb_ids')).__name__} | "
            f"instructions_count={len(config.get('instructions', [])) if isinstance(config.get('instructions'), list) else 'non-list'}"
        )
        return config

    else:
        logger.warning(f"[resolve_bot_config] Bot {bot.bot_id} has unserviceable status: {bot.bot_status}")
        raise PermissionError(
            f"Bot {bot.bot_id} status '{bot.bot_status.value}' cannot serve chats."
        )
