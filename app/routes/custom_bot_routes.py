from flask import Blueprint, request, jsonify, current_app, render_template, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt,get_jwt_identity
from werkzeug.utils import secure_filename
from app.models import db, CustomBot, Tenant, ToneOfVoiceEnum, IndustryEnum, BotDiagram, BaseAgent, Agent, LLM, Tools, ChatHistory, LoginUser
from app.models.mcp_agent_tools import McpAgentTools
from app.database.DatabaseOperationPostgreSQL import db_session
from MultiAgentSystem import MultiAgentSystem
import logging
import os
import json
import traceback
from sqlalchemy.exc import IntegrityError
import uuid
from datetime import datetime
from os.path import basename
from flask import abort
from sqlalchemy import desc
import ipaddress
import re
from app.models.custombot_access_restriction import CustomBotAccessRestriction
from app.models.agent import AgentStatusEnum
# from urllib.parse import urlparse
# from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError,IntegrityError
from functools import wraps
import os
from functools import wraps
from flask import request, jsonify
from flask_jwt_extended import create_access_token,verify_jwt_in_request
from datetime import timedelta
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is required in environment")
from flask import g
import socket
from app.models.knowledge_base import KnowledgeBase
from logging_config import setup_logging

# Define blueprint
custom_bot_blueprint = Blueprint('custom-bot', __name__)

logger = setup_logging("custom-bot", level="DEBUG")

# Define file path for default diagram
DEFAULT_DIAGRAM_PATH = os.path.join(os.path.dirname(__file__), "../data/default_diagram.json")

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

# Helper function to load default diagram
def load_default_diagram():
    try:
        with open(DEFAULT_DIAGRAM_PATH, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        raise Exception(f"Default diagram file not found at {DEFAULT_DIAGRAM_PATH}")
    except json.JSONDecodeError:
        raise Exception("Invalid JSON format in default_diagram.json")

def assign_all_tools_to_agent(agent_id, tenant_id):
    """
    ✅ NEW FUNCTION: Assign all available tools to an agent
    
    Loads all tools from tools_config.json and creates McpAgentTools records
    for each tool with all its available actions enabled by default.
    
    Args:
        agent_id: The ID of the agent
        tenant_id: The tenant ID
    """
    try:
        # Load tools config from langgraph service
        tools_config_path = os.path.join(
            os.path.dirname(__file__),
            '../../bb_langgraph_service/tools_config.json'
        )
        
        if not os.path.exists(tools_config_path):
            logger.warning(f"tools_config.json not found at {tools_config_path}, skipping tool assignment")
            return
        
        with open(tools_config_path, 'r') as f:
            tools_config = json.load(f)
        
        # Extract all tools and their actions
        tools_to_assign = {}
        for tool_category, tool_list in tools_config.items():
            if isinstance(tool_list, list):
                for tool_def in tool_list:
                    action = tool_def.get('action')
                    if action:
                        if tool_category not in tools_to_assign:
                            tools_to_assign[tool_category] = []
                        tools_to_assign[tool_category].append(action)
        
        logger.info(f"[TOOL ACCESS - BOT] Assigning {len(tools_to_assign)} tools to agent {agent_id}")
        
        # Create McpAgentTools records for each tool with all actions
        for tool_name, actions in tools_to_assign.items():
            try:
                # Check if tool already exists for this agent
                existing_tool = db.session.query(McpAgentTools).filter_by(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    tool_name=tool_name,
                    del_flag=False
                ).first()
                
                if existing_tool:
                    # Merge actions if tool already exists
                    existing_tool.action_tools = list(set((existing_tool.action_tools or []) + actions))
                    logger.info(f"[TOOL ACCESS - BOT] Updated {tool_name} with {len(existing_tool.action_tools)} actions for agent {agent_id}")
                else:
                    # Create new tool assignment
                    new_tool_assignment = McpAgentTools(
                        tenant_id=tenant_id,
                        agent_id=agent_id,
                        tool_name=tool_name,
                        action_tools=actions,
                        action_tools_description=[],
                        del_flag=False
                    )
                    db.session.add(new_tool_assignment)
                    logger.info(f"[TOOL ACCESS - BOT] Assigned {tool_name} with {len(actions)} actions to agent {agent_id}")
            except Exception as e:
                logger.error(f"[TOOL ACCESS - BOT] Failed to assign {tool_name} to agent {agent_id}: {str(e)}")
        
        db.session.commit()
        logger.info(f"[TOOL ACCESS - BOT] ✅ All tools successfully assigned to agent {agent_id}")
        
    except Exception as e:
        logger.error(f"[TOOL ACCESS - BOT] Error assigning tools to agent: {str(e)}")
        db.session.rollback()
        # Don't raise, allow bot creation to succeed even if tool assignment fails

# Route to fetch dropdown data for tones and industries (public, no JWT required)
@custom_bot_blueprint.route("/dropdown-data", methods=["GET"])
def get_dropdown_data():
    try:
        tones = [{"value": tone.value, "label": tone.value} for tone in ToneOfVoiceEnum]
        industries = [{"value": industry.value, "label": industry.value} for industry in IndustryEnum]
        return jsonify({"tones": tones, "industries": industries}), 200
    except Exception as e:
        logger.error(f"Error fetching dropdown data: {str(e)}")
        return jsonify({"error": str(e)}), 500
        
def clean_enum_input(value):
    """Returns None if value is empty, quoted-empty, or literal 'null'"""
    if not value or value.strip().lower() in {'', '""', "null"}:
        return None
    return value.strip().strip('"').strip("'")

# @custom_bot_blueprint.route("/create", methods=["POST"])
# @jwt_required()
# def create_custombot():
#     try:
#         claims = get_jwt()
#         tenant_id = claims.get("tenant_id")
#         if not tenant_id:
#             logger.error("Tenant ID not found in token")
#             return jsonify({"error": "Tenant ID not found in token"}), 401

#         data = request.form
#         avatar = request.files.get('avatar')
#         avatar_url = data.get('avatar_url')
#         # bot_type = data.get('bot_type')
#         # bot_name = data.get('bot_name')
#         # tone_of_voice = data.get('tone_of_voice')
#         # industry = data.get('industry', bot_type)
#         # purpose = data.get('purpose')
        
#         bot_type = clean_enum_input(data.get('bot_type'))
#         bot_name = data.get('bot_name')
#         tone_of_voice = data.get('tone_of_voice')
#         industry = clean_enum_input(data.get('industry', bot_type))
#         purpose = clean_enum_input(data.get('purpose'))
#         print(f"{bot_name}{tone_of_voice}{industry}{purpose}")
#         if not bot_name or not tone_of_voice or not industry or not purpose:
#             logger.error("Missing required fields")
#             return jsonify({"error": "All fields are required!"}), 400

#         existing_bot = CustomBot.query.filter_by(
#             tenant_id=tenant_id,
#             bot_name=bot_name,
#             bot_status="Created",
#             del_flg=False
#         ).first()
#         if existing_bot:
#             logger.error(f"Bot with name '{bot_name}' already exists for tenant_id: {tenant_id}")
#             return jsonify({"error": f"A bot with the name '{bot_name}' already exists!"}), 400

#         try:
#             tone_of_voice_enum = ToneOfVoiceEnum[tone_of_voice.upper()]
#         except KeyError:
#             logger.error("Invalid tone of voice value")
#             return jsonify({"error": "Invalid tone of voice value!"}), 400

#         if bot_type is not None and bot_type.lower() != 'null':
#             final_industry = bot_type.upper().replace(" ", "_")
#         else:
#             industry_enum = next((member for member in IndustryEnum if member.value.lower() == industry.lower()), None)
#             if not industry_enum:
#                 logger.error("Invalid industry value")
#                 return jsonify({"error": "Invalid industry value!"}), 400
#             final_industry = industry_enum

#         avatar_filename = None
#         if avatar and allowed_file(avatar.filename):
#             avatar_filename = secure_filename(avatar.filename)
#             upload_folder = os.path.join('uploads', 'avatars')
#             os.makedirs(upload_folder, exist_ok=True)
#             avatar.save(os.path.join(upload_folder, avatar_filename))
#         elif avatar_url:
#             avatar_filename = avatar_url

#         if not avatar_filename:
#             logger.error("Avatar is required")
#             return jsonify({"error": "Avatar is required!"}), 400

#         new_bot = CustomBot(
#             tenant_id=tenant_id,
#             bot_name=bot_name,
#             tone_of_voice=tone_of_voice_enum,
#             industry=final_industry,
#             avatar=avatar_filename,
#             purpose=purpose,
#             bot_type=bot_type,
#             instance_id=str(uuid.uuid4())  # Generate unique instance_id
#         )

#         db.session.add(new_bot)
#         db.session.flush()

#         default_diagram_json = load_default_diagram()
#         default_diagram = BotDiagram(
#             bot_id=new_bot.bot_id,
#             tenant_id=tenant_id,
#             diagram_json=json.dumps(default_diagram_json)
#         )
#         db.session.add(default_diagram)

#         db.session.commit()
#         logger.info(f"Created bot: bot_id={new_bot.bot_id}, instance_id={new_bot.instance_id}, tenant_id={tenant_id}")
#         return jsonify({
#             "message": "Custom bot and default diagram created successfully!",
#             "bot_id": new_bot.bot_id,
#             "instance_id": new_bot.instance_id,
#             "diagram_id": default_diagram.diagram_id,
#             "status" : new_bot.bot_status
#         }), 201

#     except IntegrityError as e:
#         logger.error(f"Database integrity error: {str(e)}")
#         db.session.rollback()
#         return jsonify({"error": "A database integrity error occurred."}), 400
#     except Exception as e:
#         logger.error(f"Unexpected error: {str(e)}")
#         db.session.rollback()
#         return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500



@custom_bot_blueprint.route("/create", methods=["POST"])
@jwt_required()
def create_custombot():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({"error": "Tenant ID not found in token"}), 401

        data = request.form
        avatar = request.files.get('avatar')
        avatar_url = data.get('avatar_url')
        bot_type = clean_enum_input(data.get('bot_type'))
        bot_name = data.get('bot_name')
        tone_of_voice = data.get('tone_of_voice')
        industry = clean_enum_input(data.get('industry', bot_type))
        purpose = clean_enum_input(data.get('purpose'))
        Bot_id = "" if clean_enum_input(data.get('Bot_id')) == "undefined" else data.get('Bot_id')

        if not bot_name or not tone_of_voice or not industry or not purpose:
            logger.error("Missing required fields")
            return jsonify({"error": "All fields are required!"}), 400

        try:
            tone_of_voice_enum = ToneOfVoiceEnum[tone_of_voice.upper()]
        except KeyError:
            logger.error("Invalid tone of voice value")
            return jsonify({"error": "Invalid tone of voice value!"}), 400

        if bot_type is not None and bot_type.lower() != 'null':
            final_industry = bot_type.upper().replace(" ", "_")
        else:
            industry_enum = next((member for member in IndustryEnum if member.value.lower() == industry.lower()), None)
            if not industry_enum:
                logger.error("Invalid industry value")
                return jsonify({"error": "Invalid industry value!"}), 400
            final_industry = industry_enum

        avatar_filename = None
        if avatar and allowed_file(avatar.filename):
            avatar_filename = secure_filename(avatar.filename)
            upload_folder = os.path.join('uploads', 'avatars')
            os.makedirs(upload_folder, exist_ok=True)
            avatar.save(os.path.join(upload_folder, avatar_filename))
        elif avatar_url:
            avatar_filename = avatar_url

        if not avatar_filename:
            logger.error("Avatar is required")
            return jsonify({"error": "Avatar is required!"}), 400

        # Update bot if lms_id is given
        # Update bot if Bot_id is given
        if Bot_id:
            try:
                existing_bot = CustomBot.query.filter(
                    CustomBot.bot_id == Bot_id,
                    CustomBot.tenant_id == tenant_id,
                    CustomBot.bot_status.in_(["Created", "InProgerss"])
                ).first()

                if not existing_bot:
                    logger.error(
                        f"No bot found with bot_id '{Bot_id}' "
                        f"for tenant_id {tenant_id} in valid state"
                    )
                    return jsonify({
                        "error": f"No editable bot found with ID '{Bot_id}'"
                    }), 404

                # Update fields
                existing_bot.bot_name = bot_name
                existing_bot.tone_of_voice = tone_of_voice_enum
                existing_bot.industry = final_industry
                existing_bot.avatar = avatar_filename
                existing_bot.purpose = purpose
                existing_bot.bot_type = bot_type

                db.session.commit()

                logger.info(
                    f"Updated bot {Bot_id} with status {existing_bot.bot_status}"
                )

                return jsonify({
                    "message": "Custom bot updated successfully!",
                    "bot_id": existing_bot.bot_id,
                    "instance_id": existing_bot.instance_id,
                    "status": existing_bot.bot_status,
                    "isExisted": True
                }), 200

            except Exception as e:
                logger.exception("Error while updating bot")
                db.session.rollback()
                return jsonify({"error": "Internal server error"}), 500

        existing_bot = CustomBot.query.filter_by(
            tenant_id=tenant_id,
            bot_name=bot_name,
            bot_status="Created",
            del_flg=False
        ).first()
        if existing_bot:
            logger.error(f"Bot with name '{bot_name}' already exists for tenant_id: {tenant_id}")
            return jsonify({"error": f"A bot with the name '{bot_name}' already exists!"}), 400

        new_bot = CustomBot(
            tenant_id=tenant_id,
            bot_name=bot_name,
            tone_of_voice=tone_of_voice_enum,
            industry=final_industry,
            avatar=avatar_filename,
            purpose=purpose,
            bot_type=bot_type,
            bot_status="InProgerss",
            instance_id=str(uuid.uuid4())
        )

        db.session.add(new_bot)
        db.session.flush()

        # ✅ CREATE DEFAULT AGENT WITH FULL TOOL ACCESS FOR BOT
        default_agent = Agent(
            tenant_id=tenant_id,
            agent_name=f"{bot_name} Default Agent",
            agent_description=f"Default agent for bot {bot_name}",
            llm_model_id=None,
            agent_status=AgentStatusEnum.DRAFT,
            knowledge_base_ids=[],
            Examples="",
            additional_instructions="",
            memory_mode="",
            deployment_method="local",
            agent_key=str(uuid.uuid4()),
            del_flg=False
        )
        db.session.add(default_agent)
        db.session.flush()
        
        # Assign all tools to the default agent
        assign_all_tools_to_agent(default_agent.agent_id, tenant_id)
        logger.info(f"[BOT CREATION] Bot {new_bot.bot_id} created with default agent {default_agent.agent_id} and full tool access")

        db.session.commit()

        logger.info(f"Created bot: bot_id={new_bot.bot_id}, instance_id={new_bot.instance_id}, tenant_id={tenant_id}")
        return jsonify({
            "message": "Custom bot created with full tool access!",
            "bot_id": new_bot.bot_id,
            "instance_id": new_bot.instance_id,
            "agent_id": default_agent.agent_id,
            # "diagram_id": default_diagram.diagram_id,
            "status": new_bot.bot_status
        }), 201

    except IntegrityError as e:
        logger.error(f"Database integrity error: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "A database integrity error occurred."}), 400
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        db.session.rollback()
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500



# @custom_bot_blueprint.route("/create", methods=["POST"])
# @jwt_required()
# def create_custombot():
#     try:
#         claims = get_jwt()
#         tenant_id = claims.get("tenant_id")
#         if not tenant_id:
#             logger.error("Tenant ID not found in token")
#             return jsonify({"error": "Tenant ID not found in token"}), 401

#         data = request.form
#         avatar = request.files.get('avatar')
#         avatar_url = data.get('avatar_url')
#         bot_type = clean_enum_input(data.get('bot_type'))
#         bot_name = data.get('bot_name')
#         tone_of_voice = data.get('tone_of_voice')
#         industry = clean_enum_input(data.get('industry', bot_type))
#         purpose = clean_enum_input(data.get('purpose'))
#         Bot_id = "" if clean_enum_input(data.get('Bot_id')) == "undefined" else data.get('Bot_id')

#         if not bot_name or not tone_of_voice or not industry or not purpose:
#             logger.error("Missing required fields")
#             return jsonify({"error": "All fields are required!"}), 400

#         # Validate tone of voice
#         try:
#             tone_of_voice_enum = ToneOfVoiceEnum[tone_of_voice.upper()]
#         except KeyError:
#             logger.error("Invalid tone of voice value")
#             return jsonify({"error": "Invalid tone of voice value!"}), 400

#         # Determine industry or bot type
#         if bot_type and bot_type.lower() != 'null':
#             final_industry = bot_type.upper().replace(" ", "_")
#         else:
#             industry_enum = next((member for member in IndustryEnum if member.value.lower() == industry.lower()), None)
#             if not industry_enum:
#                 logger.error("Invalid industry value")
#                 return jsonify({"error": "Invalid industry value!"}), 400
#             final_industry = industry_enum

#         # Handle avatar upload or URL
#         avatar_filename = None
#         if avatar and allowed_file(avatar.filename):
#             avatar_filename = secure_filename(avatar.filename)
#             upload_folder = os.path.join('uploads', 'avatars')
#             os.makedirs(upload_folder, exist_ok=True)
#             avatar.save(os.path.join(upload_folder, avatar_filename))
#         elif avatar_url:
#             avatar_filename = avatar_url

#         if not avatar_filename:
#             logger.error("Avatar is required")
#             return jsonify({"error": "Avatar is required!"}), 400

#         # --- UPDATE EXISTING BOT ---
#         if Bot_id:
#             try:
#                 existing_bot = CustomBot.query.filter_by(
#                     bot_id=Bot_id,
#                     tenant_id=tenant_id,
#                     bot_status="Created",
#                 ).first()

#                 if not existing_bot:
#                     logger.error(f"No bot found with LMS ID '{Bot_id}' for tenant_id: {tenant_id}")
#                     return jsonify({"error": f"No bot found with LMS ID '{Bot_id}'"}), 404

#                 existing_bot.bot_name = bot_name
#                 existing_bot.tone_of_voice = tone_of_voice_enum
#                 existing_bot.industry = final_industry
#                 existing_bot.avatar = avatar_filename
#                 existing_bot.purpose = purpose
#                 existing_bot.bot_type = bot_type

#                 db.session.commit()

#                 logger.info(f"Updated bot with LMS ID: {Bot_id}")
#                 return jsonify({
#                     "message": "Custom bot updated successfully!",
#                     "bot_id": existing_bot.bot_id,
#                     "instance_id": existing_bot.instance_id,
#                     "status": existing_bot.bot_status,
#                     "isExisted": True
#                 }), 200

#             except Exception as e:
#                 logger.exception("Error while updating bot")
#                 db.session.rollback()
#                 return jsonify({"error": "Internal server error"}), 500

#         # --- CREATE NEW BOT ---
#         existing_bot = CustomBot.query.filter_by(
#             tenant_id=tenant_id,
#             bot_name=bot_name,
#             bot_status="Created",
#             del_flg=False
#         ).first()
#         if existing_bot:
#             logger.error(f"Bot with name '{bot_name}' already exists for tenant_id: {tenant_id}")
#             return jsonify({"error": f"A bot with the name '{bot_name}' already exists!"}), 400

#         new_bot = CustomBot(
#             tenant_id=tenant_id,
#             bot_name=bot_name,
#             tone_of_voice=tone_of_voice_enum,
#             industry=final_industry,
#             avatar=avatar_filename,
#             purpose=purpose,
#             bot_status="Created",
#             bot_type=bot_type,
#             instance_id=str(uuid.uuid4())
#         )

#         db.session.add(new_bot)
#         db.session.flush()  # <---- ⭐ critical fix: ensures bot_id exists

#         # If there is logic that inserts related agent entries or tools, ID is now safe to use

#         db.session.commit()

#         logger.info(f"Created bot: bot_id={new_bot.bot_id}, instance_id={new_bot.instance_id}, tenant_id={tenant_id}")
#         return jsonify({
#             "message": "Custom bot created successfully!",
#             "bot_id": new_bot.bot_id,
#             "instance_id": new_bot.instance_id,
#             "status": new_bot.bot_status
#         }), 201

#     except IntegrityError as e:
#         logger.error(f"Database integrity error: {str(e)}")
#         db.session.rollback()
#         return jsonify({"error": "A database integrity error occurred."}), 400
#     except Exception as e:
#         logger.error(f"Unexpected error: {str(e)}")
#         db.session.rollback()
#         return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

# @custom_bot_blueprint.route("/update_instructions/<int:bot_id>", methods=["POST"])
# @jwt_required()
# def update_instructions(bot_id):
#     try:
#         claims = get_jwt()
#         tenant_id = claims.get("tenant_id")
#         if not tenant_id:
#             logger.error("Tenant ID not found in token")
#             return jsonify({"error": "Tenant ID not found in token"}), 401

#         bot = CustomBot.query.filter_by(bot_id=bot_id, tenant_id=tenant_id).first()
#         if not bot:
#             logger.error(f"Bot not found or unauthorized for bot_id: {bot_id}, tenant_id: {tenant_id}")
#             return jsonify({"error": "Bot not found or unauthorized!"}), 404

#         data = request.get_json()
#         selected_instructions = data.get("selectedInstructions", [])

#         if selected_instructions:
#             bot.instructions = json.dumps(selected_instructions)
#             db.session.commit()
#             logger.info(f"Instructions updated for bot_id: {bot_id}")
#             return jsonify({"message": "Instructions updated successfully!"}), 200
#         else:
#             logger.error("No instructions selected")
#             return jsonify({"error": "No instructions selected."}), 400

#     except Exception as e:
#         logger.error(f"Error updating instructions for bot_id {bot_id}: {str(e)}")
#         db.session.rollback()
#         return jsonify({"error": f"Failed to save selected instructions: {str(e)}"}), 500

@custom_bot_blueprint.route("/update_instructions/<int:bot_id>", methods=["POST"])
@jwt_required()
def update_instructions(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        bot = CustomBot.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id
        ).first()

        if not bot:
            return jsonify({"error": "Bot not found or unauthorized"}), 404

        data = request.get_json() or {}
        instructions = data.get("instructions")

        # ✅ Validate payload
        if not isinstance(instructions, list):
            return jsonify({"error": "Instructions must be a list"}), 400

        cleaned_instructions = []

        for inst in instructions:
            if not isinstance(inst, dict):
                continue

            inst_id = inst.get("id")
            question = inst.get("question")
            selected = inst.get("selected", False)

            if not inst_id or not question:
                continue

            cleaned_instructions.append({
                "id": int(inst_id),
                "question": question.strip(),
                "selected": bool(selected)
            })

        if not cleaned_instructions:
            return jsonify({"error": "No valid instructions provided"}), 400

        # ✅ Store full instruction state (JSON column)
        bot.instructions = cleaned_instructions

        db.session.commit()

        return jsonify({
            "message": "Instructions updated successfully",
            "count": len(cleaned_instructions)
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@custom_bot_blueprint.route(
    "/get-instructions/<int:bot_id>",
    methods=["GET"]
)
@jwt_required()
def get_instructions(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        bot = CustomBot.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id
        ).first()

        if not bot:
            return jsonify({
                "error": "Bot not found or unauthorized"
            }), 404

        return jsonify({
            "bot_id": bot.bot_id,
            "instructions": bot.instructions or []
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@custom_bot_blueprint.route(
    "/update-kb-functionalities/<int:bot_id>",
    methods=["POST"]
)
@jwt_required()
def update_kb_functionalities(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        bot = CustomBot.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not bot:
            return jsonify({
                "error": "Bot not found or unauthorized",
                "status":False
            }), 404

        data = request.get_json()
        functionalities = data.get("kb_functionalities")

        if not isinstance(functionalities, list):
            return jsonify({
                "error": "kb_functionalities must be a list",
                "status":False
            }), 400

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

        # 🔥 Save (nullable supported)
        bot.kb_functionalities = cleaned
        db.session.commit()

        return jsonify({
            "message": "KB functionalities updated successfully",
            "kb_functionalities": cleaned,
            "status":True
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e),"status":False}), 500


@custom_bot_blueprint.route(
    "/get-kb-functionalities/<int:bot_id>",
    methods=["GET"]
)
@jwt_required()
def get_kb_functionalities(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        bot = CustomBot.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not bot:
            return jsonify({
                "error": "Bot not found or unauthorized",
                "status":False
            }), 404

        return jsonify({
            "bot_id": bot.bot_id,
            "kb_functionalities": bot.kb_functionalities,  # can be null
            "status":True
        }), 200

    except Exception as e:
        return jsonify({"error": str(e),"status":False}), 500


@custom_bot_blueprint.route("/", methods=["GET"])
@jwt_required()
def get_all_bots():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({
                "data": [],
                "message": "Tenant ID not found in token",
                "status": "error"
            }), 401

        # bots = CustomBot.query.filter_by(tenant_id=tenant_id, del_flg=False).all()
        try:

            bots = (CustomBot.query
                .filter(
                    CustomBot.tenant_id == tenant_id,
                    CustomBot.del_flg == False,
                    CustomBot.bot_status.in_(["Created", "InProgerss"])
                )
                .order_by(desc(CustomBot.bot_id))
                .all()
            )

        except Exception as e:
            logger.error(f"An error occurred while fetching bots: {e}")
            return jsonify({"error": "Failed to retrieve bots"}), 500

        base_url = current_app.config.get('BASE_URL', 'https://api.jnanic.com')
        avatar_base_path = "custom-bot/uploads/avatars"

        bot_list = [
            {
                "theme": bot.theme,
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
                "purpose": bot.purpose or "",
                "core_features": bot.core_features if bot.core_features is not None else [""],
                "instructions": bot.instructions if bot.instructions is not None else [""],
                "created_at": bot.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": bot.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                "status": bot.bot_status
            }
            for bot in bots
        ]

        logger.info(f"Fetched {len(bot_list)} bots for tenant_id: {tenant_id}")
        return jsonify({
            "data": bot_list,
            "bot_id": [bot.bot_id for bot in bots],
            "message": "Bots fetched successfully",
            "status": "success"
        }), 200

    except Exception as e:
        logger.error(f"Error fetching bots: {str(e)}")
        return jsonify({
            "data": [],
            "message": f"An error occurred: {str(e)}",
            "status": "error"
        }), 500

@custom_bot_blueprint.route('/update-status/<int:bot_id>', methods=['PATCH', 'OPTIONS'])
@jwt_required()
def toggle_bot_status(bot_id):
    if request.method == "OPTIONS":
        return jsonify({"message": "CORS preflight successful"}), 200

    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({"error": "Tenant ID not found in token"}), 401

        bot = CustomBot.query.filter_by(bot_id=bot_id, tenant_id=tenant_id).first()
        if not bot:
            logger.error(f"Bot not found or unauthorized for bot_id: {bot_id}, tenant_id: {tenant_id}")
            return jsonify({"error": "Bot not found or unauthorized!"}), 404

        bot.status = not bot.status
        db.session.commit()
        logger.info(f"Bot status updated to {bot.status} for bot_id: {bot_id}")
        return jsonify({
            "message": "Bot status updated successfully",
            "bot_id": bot.bot_id,
            "new_status": bot.status
        }), 200

    except Exception as e:
        logger.error(f"Error updating bot status for bot_id {bot_id}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

import json

# @custom_bot_blueprint.route('/update/<int:bot_id>', methods=['PUT'])
# @jwt_required()
# def update_custom_bot(bot_id):
#     try:
#         claims = get_jwt()
#         tenant_id = claims.get("tenant_id")
#         if not tenant_id:
#             logger.error("Tenant ID not found in token")
#             return jsonify({"error": "Tenant ID not found in token"}), 401

#         bot = CustomBot.query.filter_by(bot_id=bot_id, tenant_id=tenant_id).first()
#         if not bot:
#             logger.error(f"Bot not found or unauthorized for bot_id: {bot_id}, tenant_id: {tenant_id}")
#             return jsonify({"error": "Bot not found or unauthorized!"}), 404

#         data = request.form
#         avatar = request.files.get('avatar')
#         avatar_url = data.get('avatar_url')
#         bot_name = data.get('bot_name', bot.bot_name)
#         tone_of_voice = data.get('tone_of_voice', bot.tone_of_voice.value)
#         industry = data.get('industry', bot.industry.value)
#         purpose = data.get('purpose', bot.purpose)
#         instructions = data.get('instructions', '').split("\n")
#         core_features = data.get('core_features', '').split("\n")
#         knowledge_base_id = data.get('knowledge_base_id')

#         try:
#             tone_of_voice_enum = ToneOfVoiceEnum[tone_of_voice.upper()]
#         except KeyError:
#             logger.error("Invalid tone of voice value")
#             return jsonify({"error": "Invalid tone of voice value!"}), 400

#         industry_enum = next((member for member in IndustryEnum if member.value.lower() == industry.lower()), None)
#         if not industry_enum:
#             logger.error("Invalid industry value")
#             return jsonify({"error": "Invalid industry value!"}), 400

#         if avatar and allowed_file(avatar.filename):
#             avatar_filename = secure_filename(avatar.filename)
#             upload_folder = os.path.join('uploads', 'avatars')
#             os.makedirs(upload_folder, exist_ok=True)
#             avatar.save(os.path.join(upload_folder, avatar_filename))
#             bot.avatar = avatar_filename
#         elif avatar_url:
#             bot.avatar = avatar_url

#         bot.bot_name = bot_name
#         bot.tone_of_voice = tone_of_voice_enum
#         bot.industry = industry_enum
#         bot.purpose = purpose
#         bot.instructions = instructions
#         bot.core_features = core_features

        
#         # ---------------- MULTI KB SUPPORT ----------------

#         kb_ids_raw = data.get("kb_ids")
#         single_kb_raw = data.get("knowledge_base_id")

#         # Normalize existing kb_ids
#         if not isinstance(bot.kb_ids, list):
#             try:
#                 bot.kb_ids = json.loads(bot.kb_ids)
#             except Exception:
#                 bot.kb_ids = []

#         parsed_kb_ids = None

#         # Case 1: kb_ids sent
#         if kb_ids_raw is not None:
#             try:
#                 parsed_kb_ids = json.loads(kb_ids_raw)

#                 # Ignore empty list (no wipe)
#                 if isinstance(parsed_kb_ids, list) and len(parsed_kb_ids) > 0:
#                     bot.kb_ids = list(
#                         dict.fromkeys(int(kb) for kb in parsed_kb_ids)
#                     )

#             except (ValueError, json.JSONDecodeError):
#                 logger.warning("Invalid kb_ids format received")

#         # Case 2: single KB sent
#         if single_kb_raw is not None:
#             kb_id = int(single_kb_raw)

#             # append ONLY if missing
#             if kb_id not in bot.kb_ids:
#                 bot.kb_ids.append(kb_id)

#             # active always updated
#             bot.knowledge_base_id = kb_id

#         # Case 3: only kb_ids sent
#         elif isinstance(parsed_kb_ids, list) and len(parsed_kb_ids) > 0:
#             bot.knowledge_base_id = bot.kb_ids[-1]

            
#         logger.info(
#             f"KB update | bot_id={bot_id} | active_kb={bot.knowledge_base_id} | kb_ids={bot.kb_ids}"
#         )


#         db.session.commit()
#         logger.info(f"Bot updated successfully for bot_id: {bot_id}")
#         return jsonify({"message": "Bot updated successfully!"}), 200

#     except Exception as e:
#         logger.error(f"Error updating bot {bot_id}: {str(e)}")
#         db.session.rollback()
#         return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

@custom_bot_blueprint.route('/update/<int:bot_id>', methods=['PUT'])
@jwt_required()
def update_custom_bot(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return jsonify({"error": "Tenant ID not found in token"}), 401

        bot = CustomBot.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id
        ).first()

        if not bot:
            return jsonify({"error": "Bot not found or unauthorized!"}), 404

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
            return jsonify({"error": "Invalid tone of voice value!"}), 400

        industry_enum = next(
            (m for m in IndustryEnum if m.value.lower() == industry.lower()),
            None
        )
        if not industry_enum:
            return jsonify({"error": "Invalid industry value!"}), 400

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
                return jsonify({"error": "Invalid kb_ids format"}), 400

        logger.info(
            f"Bot updated | bot_id={bot_id} | kb_ids={bot.kb_ids}"
        )

        db.session.commit()
        return jsonify({"message": "Bot updated successfully!"}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Update bot failed | bot_id={bot_id} | {str(e)}")
        return jsonify({"error": "Internal Server Error"}), 500

@custom_bot_blueprint.route("/get_recent_bot_id", methods=["GET"])
@jwt_required()
def get_recent_bot_id():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Tenant ID not found in token"
            }), 401

        session = next(db_session())
        recent_bot = session.query(CustomBot).filter_by(tenant_id=tenant_id)\
            .order_by(CustomBot.created_at.desc()).first()
        bot_id = recent_bot.bot_id if recent_bot else None

        logger.info(f"Retrieved recent bot_id: {bot_id} for tenant_id: {tenant_id}")
        return jsonify({
            "data": {
                "bot_id": bot_id
            },
            "status": "success",
            "message": "Recent bot ID retrieved"
        }), 200

    except Exception as e:
        logger.error(f"Error fetching recent bot ID: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
    finally:
        session.close()

@custom_bot_blueprint.route('/delete/<int:bot_id>', methods=['DELETE'])
@jwt_required()
def delete_custom_bot(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({"error": "Tenant ID not found in token"}), 401

        bot = CustomBot.query.filter_by(bot_id=bot_id, tenant_id=tenant_id).first()
        if not bot:
            logger.error(f"Bot not found or unauthorized for bot_id: {bot_id}, tenant_id: {tenant_id}")
            return jsonify({"error": "Bot not found or unauthorized!"}), 404

        bot.del_flg = True
        db.session.commit()
        logger.info(f"Bot deleted (soft) for bot_id: {bot_id}")
        return jsonify({"message": "Bot deleted successfully!"}), 200

    except Exception as e:
        logger.error(f"Error deleting bot {bot_id}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@custom_bot_blueprint.route("/bot-names", methods=["GET"])
@jwt_required()
def get_all_bot_names():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({"error": "Tenant ID not found in token"}), 401

        bot_names = [bot.bot_name for bot in CustomBot.query.filter_by(tenant_id=tenant_id, del_flg=False).all()]
        logger.info(f"Fetched {len(bot_names)} bot names for tenant_id: {tenant_id}")
        return jsonify({"bot_names": bot_names}), 200

    except Exception as e:
        logger.error(f"Error fetching bot names: {str(e)}")
        return jsonify({"message": f"An error occurred: {str(e)}", "status": "error"}), 500

# @custom_bot_blueprint.route('/update-knowledge-base/<int:bot_id>', methods=['PATCH', 'OPTIONS'])
# @jwt_required()
# def update_knowledge_base(bot_id):
#     if request.method == 'OPTIONS':
#         return jsonify({'status': 'ok'}), 200

#     try:
#         claims = get_jwt()
#         tenant_id = claims.get("tenant_id")
#         if not tenant_id:
#             logger.error("Tenant ID not found in token")
#             return jsonify({"error": "Tenant ID not found in token"}), 401

#         bot = CustomBot.query.filter_by(bot_id=bot_id, tenant_id=tenant_id).first()
#         if not bot:
#             logger.error(f"Bot not found or unauthorized for bot_id: {bot_id}, tenant_id: {tenant_id}")
#             return jsonify({"error": "Bot not found or unauthorized!"}), 404

#         data = request.get_json()
#         if not data or "knowledge_base_ids" not in data:
#             logger.error("Knowledge Base ID is required")
#             return jsonify({"error": "Knowledge Base ID is required."}), 400

#         bot.knowledge_base_id = data.get("knowledge_base_ids")
#         bot.bot_status = "Created"
#         db.session.commit()
#         logger.info(f"Knowledge Base ID updated for bot_id: {bot_id}")
#         return jsonify({
#             "message": "Knowledge Base ID updated successfully!",
#             "bot_id": bot.bot_id,
#             "knowledge_base_id": bot.knowledge_base_id
#         }), 200

#     except Exception as e:
#         logger.error(f"Error updating knowledge base for bot_id {bot_id}: {str(e)}")
#         db.session.rollback()
#         return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


@custom_bot_blueprint.route('/update-knowledge-base/<int:bot_id>', methods=['PATCH', 'OPTIONS'])
@jwt_required()
def update_knowledge_base(bot_id):
    # --------------------------------------------------
    # CORS preflight
    # --------------------------------------------------
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200

    try:
        # --------------------------------------------------
        # Auth / Tenant validation (UNCHANGED)
        # --------------------------------------------------
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return jsonify({"error": "Tenant ID not found in token"}), 401

        bot = CustomBot.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id
        ).first()

        if not bot:
            return jsonify({"error": "Bot not found or unauthorized!"}), 404

        # --------------------------------------------------
        # Parse request body
        # --------------------------------------------------
        data = request.get_json(silent=True) or {}
        kb_ids_raw = data.get("kb_ids")

        if kb_ids_raw is None:
            return jsonify({
                "error": "kb_ids is required"
            }), 400

        # --------------------------------------------------
        # ✅ Allow SINGLE value or LIST
        # --------------------------------------------------
        if isinstance(kb_ids_raw, list):
            raw_ids = kb_ids_raw
        else:
            # single value → normalize to list
            raw_ids = [kb_ids_raw]

        # --------------------------------------------------
        # Ensure existing kb_ids is a valid list
        # --------------------------------------------------
        existing_kb_ids = bot.kb_ids or []
        if not isinstance(existing_kb_ids, list):
            existing_kb_ids = []

        # --------------------------------------------------
        # Validate & normalize incoming KB IDs
        # --------------------------------------------------
        try:
            incoming_kb_ids = [int(kb_id) for kb_id in raw_ids]
        except (TypeError, ValueError):
            return jsonify({
                "error": "kb_ids must be an integer or a list of integers"
            }), 400

        # --------------------------------------------------
        # ✅ APPEND-ONLY MERGE (PRESERVE OLD + ADD NEW)
        # --------------------------------------------------
        merged_kb_ids = list(
            dict.fromkeys(existing_kb_ids + incoming_kb_ids)
        )

        bot.kb_ids = merged_kb_ids

        # --------------------------------------------------
        # Preserve existing behavior
        # --------------------------------------------------
        # bot.bot_status = "Created"

        db.session.commit()

        logger.info(
            f"KB updated (append) | bot_id={bot_id} | kb_ids={bot.kb_ids}"
        )

        return jsonify({
            "message": "Knowledge bases updated successfully!",
            "bot_id": bot.bot_id,
            "kb_ids": bot.kb_ids
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(
            f"Error updating knowledge base | bot_id={bot_id} | {str(e)}"
        )
        return jsonify({
            "error": "An unexpected error occurred"
        }), 500


@custom_bot_blueprint.route("/recent-running-bots", methods=["GET"])
@jwt_required()
def get_recent_running_bots():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({
                "data": [],
                "status": "error",
                "message": "Tenant ID not found in token"
            }), 401

        session = next(db_session())
        recent_bots = session.query(CustomBot).filter_by(
            tenant_id=tenant_id,
            status=True,
            del_flg=False,bot_status = 'Created'
        ).order_by(
            CustomBot.updated_at.desc()
        ).limit(3).all()

        base_url = current_app.config.get('BASE_URL', 'https://api.jnanic.com')
        avatar_base_path = "custom-bot/uploads/avatars"

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
                "status": bot.status
            }
            for bot in recent_bots
        ]

        logger.info(f"Fetched {len(bot_list)} recent running bots for tenant_id: {tenant_id}")
        return jsonify({
            "data": bot_list,
            "status": "success",
            "message": "Recent running bots fetched successfully"
        }), 200

    except Exception as e:
        logger.error(f"Error fetching recent running bots: {str(e)}")
        return jsonify({
            "data": [],
            "status": "error",
            "message": f"An error occurred: {str(e)}"
        }), 500
    finally:
        session.close()

FEATURE_AGENT_MAPPING = {
    "Property Details with Carousel Images with Price": {
        "agent_role": "You are an expert Image-Text Carousel Agent.",
        "tool_id": 1
    },
    "Video Tours (360° & Live Walkthroughs)": {
        "agent_role": "You are an expert Virtual Tour Agent",
        "tool_id": 2
    },
    "Market Trends - Proposed Rental Income": {
        "agent_role": "You are an expert Rental Income Estimation Agent.",
        "tool_id": 3
    },
    "Loan Assistance - Check Availability with Lender": {
        "agent_role": "You are an expert Legal & Documentation Agent.",
        "tool_id": 4
    },
    "Check Nearby Amenities": {
        "agent_role": "You are an expert Nearby Facility Agent.",
        "tool_id": 5
    },
    "Show Commute Travel Time with Different Time Spans": {
        "agent_role": "You are an expert Commute Time Agent.",
        "tool_id": 1
    },
    "Schedule Property Visits in Google Calendar": {
        "agent_role": "You are an expert Appointment Scheduling Agent.",
        "tool_id": 2
    },
    "Use Memory/Keep Chat History for Latest Communication": {
        "agent_role": "You are an expert Property Matching Agent.",
        "tool_id": 3
    },
    "Use Multi-Language Support": {
        "agent_role": "You are an expert Customer Support Agent",
        "tool_id": 4
    }
}

@custom_bot_blueprint.route('/update_features/<int:bot_id>', methods=['POST'])
@jwt_required()
def update_features(bot_id):
    try:
        # --------------------------------------------------
        # 1. AUTH & BOT VALIDATION
        # --------------------------------------------------
        tenant_id = get_jwt().get("tenant_id")
        if not tenant_id:
            return jsonify({"error": "Tenant ID missing"}), 401

        bot = CustomBot.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not bot:
            return jsonify({"error": "Bot not found or unauthorized"}), 404

        # --------------------------------------------------
        # 2. READ PAYLOAD
        # --------------------------------------------------
        payload = request.get_json(silent=True) or {}

        selected_features = payload.get("selectedFeatures", {})
        full_features = payload.get("fullFunctionalities", {})

        if not isinstance(full_features, dict) or not full_features:
            return jsonify({"error": "No features provided"}), 400

        # --------------------------------------------------
        # 3. NORMALIZE FEATURES (🔥 FIXED LOGIC)
        # --------------------------------------------------
        normalized = {}

        for tool, all_feats in full_features.items():
            if not isinstance(all_feats, list):
                continue

            # collect selected labels only where selected=true
            selected_labels = {
                f.get("label")
                for f in selected_features.get(tool, [])
                if isinstance(f, dict) and f.get("selected") is True
            }

            normalized[tool] = [
                {
                    "label": feat.get("label"),
                    "selected": feat.get("label") in selected_labels
                }
                for feat in all_feats
                if isinstance(feat, dict) and feat.get("label")
            ]

        # --------------------------------------------------
        # 4. SAVE TO BOT
        # --------------------------------------------------
        bot.core_features = json.dumps(normalized)
        db.session.commit()

        # --------------------------------------------------
        # 5. FETCH ACTIVE LLM
        # --------------------------------------------------
        llm = LLM.query.filter_by(
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not llm:
            return jsonify({"error": "No LLM configured"}), 400

        # --------------------------------------------------
        # 6. CREATE AGENTS FOR SELECTED FEATURES
        # --------------------------------------------------
        for tool, feats in normalized.items():
            if not any(f["selected"] for f in feats):
                continue

            if tool not in FEATURE_AGENT_MAPPING:
                continue

            agent_role = FEATURE_AGENT_MAPPING[tool]["agent_role"]
            tool_id = FEATURE_AGENT_MAPPING[tool]["tool_id"]

            # skip if agent already exists
            exists = Agent.query.filter_by(
                tenant_id=tenant_id,
                agent_role=agent_role,
                del_flg=False
            ).first()

            if exists:
                continue

            base = BaseAgent.query.filter_by(
                agent_role=agent_role,
                del_flg=False
            ).first()

            if not base:
                return jsonify({
                    "error": f"Base agent missing for role: {agent_role}"
                }), 400

            db.session.add(
                Agent(
                    tenant_id=tenant_id,
                    agent_name=base.agent_name,
                    agent_description=base.agent_description,
                    llm_model_id=llm.llm_id,
                    agent_role=agent_role,
                    agent_instructions=base.agent_instructions,
                    tool_id=tool_id,
                    Examples=base.Examples,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    del_flg=False
                )
            )

        db.session.commit()

        # --------------------------------------------------
        # 7. RESPONSE
        # --------------------------------------------------
        return jsonify({
            "message": "Features updated successfully",
            "bot_id": bot_id,
            "core_features": normalized
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "error": "Failed to update features",
            "details": str(e)
        }), 500
        
@custom_bot_blueprint.route('/get_features/<int:bot_id>', methods=['GET'])
@jwt_required()
def get_features(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return jsonify({"error": "Tenant ID not found in token"}), 401

        bot = CustomBot.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not bot:
            return jsonify({"error": "Bot not found or unauthorized"}), 404

        core_features = {}

        if bot.core_features:
            try:
                core_features = json.loads(bot.core_features)
            except Exception as e:
                logger.error(f"Failed to parse core_features: {str(e)}")
                return jsonify({"error": "Invalid core features format"}), 500

        return jsonify({
            "bot_id": bot.bot_id,
            "core_features": core_features
        }), 200

    except Exception as e:
        logger.error(f"Error fetching core features for bot_id {bot_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@custom_bot_blueprint.route('/save-customize/<int:bot_id>', methods=['POST'])
@jwt_required()
def save_customization(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({"error": "Tenant ID not found in token"}), 401

        bot = CustomBot.query.filter_by(bot_id=bot_id, tenant_id=tenant_id, del_flg=False).first()
        if not bot:
            logger.error(f"Bot not found or unauthorized for bot_id: {bot_id}, tenant_id: {tenant_id}")
            return jsonify({"error": "Bot not found or unauthorized!"}), 404

        data = request.form
        avatar = request.files.get('avatar')
        background_image = request.files.get('background_image')

        chatbot_name = data.get('chatbot_name')
        disclaimer_text = data.get('disclaimer_text')
        purpose = data.get('purpose')
        colors = data.get('colors')
        greeting_type = data.get('greeting_type')
        greeting_message = data.get('greeting_message')
        theme = data.get('theme')  # ✅ new field

        if not chatbot_name or not disclaimer_text or not colors or not purpose:
            logger.error("Required fields missing")
            return jsonify({"error": "Chatbot name, disclaimer text, colors, and purpose are required!"}), 400

        try:
            colors_json = json.loads(colors)
        except json.JSONDecodeError:
            logger.error("Invalid colors JSON format")
            return jsonify({"error": "Invalid colors JSON format!"}), 400

        if avatar and allowed_file(avatar.filename):
            avatar_filename = secure_filename(avatar.filename)
            upload_folder = os.path.join('uploads', 'avatars')
            os.makedirs(upload_folder, exist_ok=True)
            avatar.save(os.path.join(upload_folder, avatar_filename))
            bot.avatar = avatar_filename

        if background_image and allowed_file(background_image.filename):
            background_filename = secure_filename(background_image.filename)
            upload_folder = os.path.join('uploads', 'backgrounds')
            os.makedirs(upload_folder, exist_ok=True)
            background_image.save(os.path.join(upload_folder, background_filename))
            bot.background_image = background_filename

        # 🧠 Update fields
        bot.bot_name = chatbot_name
        bot.disclaimer_text = disclaimer_text
        bot.purpose = purpose
        bot.colors = colors_json
        bot.theme = theme or "Theme 1"  # ✅ store theme
        bot.greeting_type = greeting_type or "dynamic"
        bot.greeting_message = greeting_message or "Hello! I'm your friendly assistant. How can I help you today?"

        db.session.commit()

        if greeting_type == "static" and greeting_message:
            try:
                multi_agent_system = MultiAgentSystem(tenant_id=tenant_id, bot_id=bot_id)
                multi_agent_system._save_static_greeting_to_history()
            except Exception as e:
                logger.error(f"Error saving static greeting to chat history: {str(e)}")

        logger.info(f"Customization saved for bot_id: {bot_id}")
        return jsonify({
            "message": "Chatbot customization saved successfully!",
            "bot_id": bot.bot_id
        }), 200

    except Exception as e:
        logger.error(f"Error saving customization for bot_id {bot_id}: {str(e)}")
        
# Latest old version
@custom_bot_blueprint.route('/get-customize/<instance_id>', methods=['GET'])
def get_customization(instance_id):
    try:
        host = request.host
        subdomain = host.split('.')[0] if '.' in host else None
        api_key = request.headers.get("X-API-Key")
        logger.info(f"Request for instance_id: {instance_id}, subdomain: {subdomain}, api_key: {api_key}")

        session = next(db_session())
        user = None
        if api_key:
            user = session.query(LoginUser).filter_by(api_key=api_key, del_flg=False).first()
            logger.info(f"API key user: {user.account_name if user else 'None'}")
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
            logger.info(f"Subdomain user: {user.account_name if user else 'None'}")
        else:
            logger.error("Subdomain or API key required")
            return jsonify({"error": "Subdomain or API key required", "status": "error"}), 400

        if not user:
            logger.error(f"No active tenant found for subdomain: {subdomain} or api_key: {api_key}")
            return jsonify({"error": "Subdomain or API key invalid", "status": "error"}), 401

        bot = session.query(CustomBot).filter_by(
            instance_id=instance_id,
            tenant_id=user.tenant_id,
            del_flg=False,
            status=True
        ).first()
        if not bot:
            logger.error(f"Bot not found for instance_id: {instance_id}, tenant_id: {user.tenant_id}")
            abort(404, description=f"Invalid or inactive instance ID: {instance_id}")

        base_url = f"https://{subdomain}.jnanic.com"
        avatar_base_path = "custom-bot/uploads/avatars"
        background_base_path = "custom-bot/uploads/backgrounds/"

        customization_details = {
            "bot_id": bot.bot_id,
            "chatbot_name": bot.bot_name,
            "disclaimer_text": bot.disclaimer_text or "",
            "avatar": (
                f"{base_url}/{avatar_base_path}/{os.path.basename(bot.avatar)}"
                if bot.avatar and not bot.avatar.startswith(('http://', 'https://'))
                else bot.avatar or ""
            ),
            "background_image": (
                f"{base_url}/{background_base_path}/{os.path.basename(bot.background_image)}"
                if bot.background_image and not bot.background_image.startswith(('http://', 'https://'))
                else bot.background_image or ""
            ),
            "colors": bot.colors or {},
            "greeting_type": bot.greeting_type or "dynamic",
            "greeting_message": bot.greeting_message or "Hello! I'm your friendly assistant. How can I help you today?",
            "created_at": bot.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": bot.updated_at.strftime("%Y-%m-%d %H:%M:%S")
        }
        logger.info(f"Fetched customization details for instance_id: {instance_id}, bot_id: {bot.bot_id}")
        return jsonify({
            "data": customization_details,
            "message": "Customization details fetched successfully",
            "status": "success"
        }), 200
    except Exception as e:
        logger.error(f"Error fetching customization for instance_id {instance_id}: {str(e)}")
        abort(500, description=f"Server error: {str(e)}")
    finally:
        session.close()
        

# Lasted Old Version
@custom_bot_blueprint.route('/save-static-greeting/<int:bot_id>', methods=['POST'])
@jwt_required()
def save_static_greeting(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({"error": "Tenant ID not found in token"}), 401

        bot = CustomBot.query.filter_by(bot_id=bot_id, tenant_id=tenant_id, del_flg=False).first()
        if not bot:
            logger.error(f"Bot not found or unauthorized for bot_id: {bot_id}, tenant_id: {tenant_id}")
            return jsonify({"error": "Bot not found or unauthorized!"}), 404

        if bot.greeting_type != "static" or not bot.greeting_message:
            logger.error("Bot is not set to static greeting or no greeting message provided")
            return jsonify({"error": "Bot is not set to static greeting or no greeting message provided!"}), 400

        multi_agent_system = MultiAgentSystem(tenant_id=tenant_id, bot_id=bot_id)
        multi_agent_system._save_static_greeting_to_history()
        logger.info(f"Static greeting saved for bot_id: {bot_id}")
        return jsonify({
            "message": "Static greeting saved to chat history successfully!",
            "bot_id": bot.bot_id
        }), 200

    except Exception as e:
        logger.error(f"Error saving static greeting for bot_id {bot_id}: {str(e)}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@custom_bot_blueprint.route('/uploads/backgrounds/<filename>')
def uploaded_background(filename):
    try:
        return send_from_directory(os.path.join(current_app.root_path, 'uploads', 'backgrounds'), filename)
    except Exception as e:
        logger.error(f"Error serving background image {filename}: {str(e)}")
        return jsonify({"error": "File not found", "status": "error"}), 404

@custom_bot_blueprint.route('/uploads/avatars/<filename>')
def uploaded_avatars(filename):
    try:
        return send_from_directory(os.path.join(current_app.root_path, 'uploads', 'avatars'), filename)
    except Exception as e:
        logger.error(f"Error serving avatar image {filename}: {str(e)}")
        return jsonify({"error": "File not found", "status": "error"}), 404

@custom_bot_blueprint.route('/JnanicChatbotJs.js')
def serve_chatbot_js():
    try:
        return send_from_directory(os.path.join(current_app.root_path, 'static', 'js'), 'JnanicChatbotJs.js')
    except Exception as e:
        logger.error(f"Error serving JnanicChatbotJs.js: {str(e)}")
        return jsonify({"error": "File not found", "status": "error"}), 404

@custom_bot_blueprint.route('/JnanicChatbotCss.css')
def serve_chatbot_css():
    try:
        return send_from_directory(os.path.join(current_app.root_path, 'static', 'css'), 'JnanicChatbotCss.css')
    except Exception as e:
        logger.error(f"Error serving JnanicChatbotCss.css: {str(e)}")
        return jsonify({"error": "File not found", "status": "error"}), 404

@custom_bot_blueprint.route('/resolve-instance/<instance_id>')
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
                return jsonify({"error": "Invalid API key", "status": "error"}), 401
        elif subdomain:
            user = session.query(Tenant).join(LoginUser).filter(LoginUser.account_name == subdomain, Tenant.tenant_status == "Active", LoginUser.del_flg == False).first()
            if not user:
                logger.error(f"No active tenant found for subdomain: {subdomain}")
                return jsonify({"error": "Subdomain not found or inactive", "status": "error"}), 404
        else:
            logger.error("Subdomain or API key required")
            return jsonify({"error": "Subdomain or API key required", "status": "error"}), 400

        bot = session.query(CustomBot).filter_by(instance_id=instance_id, tenant_id=user.tenant_id, del_flg=False, status=True).first()
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

@custom_bot_blueprint.route('/get-customize-by-bot/<bot_id>')
@jwt_required()
def get_customize_by_bot(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({"error": "Tenant ID not found in token", "status": "error"}), 401

        session = next(db_session())
        bot = session.query(CustomBot).filter_by(bot_id=bot_id, tenant_id=tenant_id, del_flg=False, status=True).first()
        if not bot:
            logger.error(f"Bot not found for bot_id: {bot_id}, tenant_id: {tenant_id}")
            abort(404, description=f"Invalid or inactive bot ID: {bot_id}")
        if not bot.instance_id:
            logger.error(f"No instance_id configured for bot_id: {bot_id}")
            abort(400, description=f"No instance_id configured for bot_id: {bot_id}")

        base_url = current_app.config.get('BASE_URL', 'https://api.jnanic.com')
        avatar_base_path = "custom-bot/uploads/avatars"
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
                "disclaimer_text": bot.disclaimer_text or "© 2025 Tata Realty. All rights reserved.",
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

@custom_bot_blueprint.route('/chat-history/<instance_id>')
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
                return jsonify({"error": "Invalid API key", "status": "error"}), 401
        elif subdomain:
            user = session.query(Tenant).join(LoginUser).filter(LoginUser.account_name == subdomain, Tenant.tenant_status == "Active", LoginUser.del_flg == False).first()
            if not user:
                logger.error(f"No active tenant found for subdomain: {subdomain}")
                return jsonify({"error": "Subdomain not found or inactive", "status": "error"}), 404
        else:
            logger.error("Subdomain or API key required")
            return jsonify({"error": "Subdomain or API key required", "status": "error"}), 400

        bot = session.query(CustomBot).filter_by(instance_id=instance_id, tenant_id=user.tenant_id, del_flg=False, status=True).first()
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

@custom_bot_blueprint.route('/chatbot/<instance_id>', methods=["GET"])
def serve_chatbot_by_instance(instance_id):
    try:
        host = request.host
        subdomain = host.split('.')[0] if '.' in host else None
        if not subdomain:
            logger.error("Subdomain not found in request host")
            return jsonify({"error": "Subdomain is required", "status": "error"}), 400

        session = next(db_session())

        # Get active tenant
        user, login_user = (
            session.query(Tenant, LoginUser)
            .join(LoginUser)
            .filter(
                LoginUser.account_name == subdomain,
                Tenant.tenant_status == "Active",
                LoginUser.del_flg == False
            )
            .first()
        )


        if not user:
            logger.error(f"No active tenant found for subdomain: {subdomain}")
            return jsonify({"error": "Subdomain not found or inactive", "status": "error"}), 404

        # Get bot for tenant
        bot = (
            session.query(CustomBot)
            .filter_by(
                instance_id=instance_id,
                tenant_id=login_user.tenant_id,
                del_flg=False,
                status=True
            )
            .first()
        )
        if not bot:
            logger.error(f"Bot not found for instance_id: {instance_id}, tenant_id: {user.tenant_id}")
            return jsonify({"error": "Bot not found, inactive, or unauthorized!", "status": "error"}), 404

        logger.info(f"Serving chatbot for instance_id: {instance_id}, bot_id: {bot.bot_id}")
       
        # Pass tenant_key (API key) to template
        return render_template(
            "chatbot.html",
            bot_id=bot.bot_id,
            api_key=login_user.api_key  # <--- API key here
        )

    except Exception as e:
        logger.error(f"Error serving chatbot for instance_id {instance_id}: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}", "status": "error"}), 500

    finally:
        session.close()

@custom_bot_blueprint.route("/<int:bot_id>", methods=["GET"])
@jwt_required()
def get_bot_by_id(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({
                "data": {},
                "message": "Tenant ID not found in token",
                "status": "error"
            }), 401

        bot = CustomBot.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not bot:
            logger.error(f"Bot not found for bot_id: {bot_id}, tenant_id: {tenant_id}")
            return jsonify({
                "data": {},
                "message": "Bot not found or unauthorized!",
                "status": "error"
            }), 404

        base_url = current_app.config.get("BASE_URL", "https://api.jnanic.com")
        avatar_base_path = "custom-bot/uploads/avatars"
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
            "background_image": background_url,   # ✅ added

            "bot_id": bot.bot_id,
            "theme": bot.theme,
            "color": bot.colors,
            "bot_name": bot.bot_name,
            "core_features": bot.core_features if isinstance(bot.core_features, list) else json.loads(bot.core_features) if bot.core_features else [""],
            "created_at": bot.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "industry": bot.industry.value,
            "instructions": bot.instructions if isinstance(bot.instructions, list) else json.loads(bot.instructions) if bot.instructions else [""],
            "purpose": bot.purpose or "",
            "status": bot.status,
            "tenant_id": bot.tenant_id,
            "kb_ids": bot.kb_ids if isinstance(bot.kb_ids, list) else [],
            "tone_of_voice": bot.tone_of_voice.value,
            "updated_at": bot.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "greeting_type": bot.greeting_type or "dynamic",
            "greeting_message": bot.greeting_message or "Hello! I'm your friendly assistant. How can I help you today?"
        }

        logger.info(f"Fetched bot details for bot_id: {bot_id}")
        return jsonify({
            "data": bot_details,
            "message": "Bot details fetched successfully",
            "status": "success"
        }), 200

    except Exception as e:
        logger.error(f"Error fetching bot details for bot_id {bot_id}: {str(e)}")
        return jsonify({
            "data": {},
            "message": f"An error occurred: {str(e)}",
            "status": "error"
        }), 500

@custom_bot_blueprint.route("/launch/<int:bot_id>", methods=["POST"])
@jwt_required()
def launch_bot(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({
                "message": "Tenant ID not found in token",
                "status": "error"
            }), 401

        bot = CustomBot.query.filter(
            CustomBot.bot_id == bot_id,
            CustomBot.tenant_id == tenant_id,
            CustomBot.del_flg == False
        ).first()

        if not bot:
            logger.error(f"Bot not found: bot_id={bot_id}, tenant_id={tenant_id}")
            return jsonify({
                "message": "Bot not found or unauthorized",
                "status": "error"
            }), 404

        # ✅ Allow launch only from valid states
        if bot.bot_status not in ["Created", "InProgerss"]:
            logger.warning(
                f"Invalid launch attempt for bot_id={bot_id}, status={bot.bot_status}"
            )
            return jsonify({
                "message": f"Bot cannot be launched from status '{bot.bot_status}'",
                "status": "error"
            }), 400

        # 🚀 Launch bot
        bot.bot_status = "Launched"   # or "Published"
        bot.updated_at = datetime.utcnow()

        db.session.commit()

        logger.info(
            f"Bot launched successfully: bot_id={bot_id}, tenant_id={tenant_id}"
        )

        return jsonify({
            "message": "Bot launched successfully",
            "bot_id": bot.bot_id,
            "status": bot.bot_status
        }), 200

    except Exception as e:
        logger.exception("Error while launching bot")
        db.session.rollback()
        return jsonify({
            "message": "Internal server error",
            "status": "error"
        }), 500

@custom_bot_blueprint.route("/bot_status/<int:bot_id>", methods=["POST"])
@jwt_required()
def update_bot_status(bot_id):
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    status = request.json.get("status")

    if status not in ["Created", "InProgerss"]:
        return jsonify({"message": "Invalid status"}), 400

    bot = CustomBot.query.filter_by(
        bot_id=bot_id,
        tenant_id=tenant_id,
        del_flg=False
    ).first()

    if not bot:
        return jsonify({"message": "Bot not found"}), 404

    bot.bot_status = status
    bot.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "message": "Bot status updated",
        "status": bot.bot_status
    }), 200


def resolve_domain_to_ip(domain):
    try:
        return socket.gethostbyname(domain)
    except socket.gaierror:
        return None

# def require_valid_token(f):
#     @wraps(f)
#     def decorated_func(*args, **kwargs):
#         data = request.get_json(silent=True) or {}
#         bot_id = data.get("bot_id")

#         if not bot_id:
#             return jsonify({"error": "Bot ID is required."}), 400

#         bot = CustomBot.query.filter_by(
#             bot_id=bot_id, del_flg=False, status=True
#         ).first()

#         if not bot:
#             return jsonify({"error": "Invalid bot_id or bot not found."}), 404

#         # If restriction is disabled, skip token verification
#         if bot.access_restriction_type is None:
#             g.bot_id = bot.bot_id
#             return f(*args, **kwargs)

#         # If restriction is enabled, require and verify JWT
#         verify_jwt_in_request()
#         g.bot_id = get_jwt_identity()
#         return f(*args, **kwargs)

#     return decorated_func



def generate_temp_token(bot_id, client_ip, domain):
    access_token = create_access_token(
        identity=bot_id,  
        additional_claims={"client_ip": client_ip, "domain": domain},
        expires_delta=timedelta(minutes=15)
    )
    return access_token
    
# @custom_bot_blueprint.route('/validate_client', methods=["POST"])
# def validate_client():
#     data = request.get_json()
#     bot_id = data.get('bot_id')
#     client_ip = data.get('ip')
#     domain = data.get('domain')

#     bot = CustomBot.query.filter_by(
#         bot_id=bot_id, del_flg=False, status=True
#     ).first()

#     if not bot:
#         return jsonify({"error": "Bot not found"}), 404

#     # No restriction type → treated as key-based (middleware handles it)
#     if bot.access_restriction_type is None:
#         return jsonify({"status": "ok"})

#     # -------------------------
#     # IP-based restriction
#     # -------------------------
#     if bot.access_restriction_type == 0:
#         allowed_ips = [
#             ip for (ip,) in db.session.query(CustomBotAccessRestriction.allowed_ip)
#             .filter_by(bot_id=bot.bot_id)
#             .filter(CustomBotAccessRestriction.allowed_ip != None)
#             .all()
#         ]
#         if client_ip in allowed_ips:
#             temp_token = generate_temp_token(bot_id, client_ip, domain)
#             return jsonify({"status": "ok", "token": temp_token})
#         return jsonify({"error": "Access not allowed"}), 403

#     # -------------------------
#     # Domain-based restriction
#     # -------------------------
#     if bot.access_restriction_type == 1:
#         if domain:
#             # only match base domain entries (ignore IP mappings)
#             base_domains = [
#                 e.allowed_domain
#                 for e in CustomBotAccessRestriction.query.filter_by(
#                     bot_id=bot.bot_id, allowed_ip=None
#                 ).all()
#                 if e.allowed_domain
#             ]
#             if domain in base_domains:
#                 temp_token = generate_temp_token(bot_id, client_ip, domain)
#                 return jsonify({"status": "ok", "token": temp_token})
#         return jsonify({"error": "Access not allowed"}), 403

def require_valid_token(f):
    @wraps(f)
    def decorated_func(*args, **kwargs):
        data = request.get_json(silent=True) or {}
        bot_id = data.get("bot_id")

        if not bot_id:
            return jsonify({"error": "Bot ID is required."}), 400

        bot = CustomBot.query.filter_by(bot_id=bot_id, del_flg=False, status=True).first()
        if not bot:
            return jsonify({"error": "Invalid bot_id or bot not found."}), 404

        # Verify JWT (token already contains allowed IP/domain)
        verify_jwt_in_request()
        jwt_data = get_jwt()
        g.bot_id = get_jwt_identity()
        g.client_ip = jwt_data.get("client_ip")
        g.domain = jwt_data.get("domain")

        return f(*args, **kwargs)

    return decorated_func



@custom_bot_blueprint.route('/validate_client', methods=["POST"])
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

    bot = CustomBot.query.filter_by(bot_id=bot_id, del_flg=False, status=True).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    # Fetch all restrictions for the bot
    restrictions = CustomBotAccessRestriction.query.filter_by(bot_id=bot.bot_id).all()

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

    # 1️⃣ Check pure IPs first
    if client_ip in pure_ips:
        temp_token = generate_temp_token(bot_id, client_ip, domain)
        return jsonify({"status": "ok", "token": temp_token})

    # 2️⃣ Check IPs mapped to domains
    if client_ip in mapped_ips:
        temp_token = generate_temp_token(bot_id, client_ip, domain)
        return jsonify({"status": "ok", "token": temp_token})

    # 3️⃣ Check domain if IP not matched
    if domain and domain in base_domains:
        temp_token = generate_temp_token(bot_id, client_ip, domain)
        return jsonify({"status": "ok", "token": temp_token})

    # 4️⃣ No match → access denied
    return jsonify({"error": "Access not allowed"}), 403




@custom_bot_blueprint.route("/restriction/get/<int:bot_id>", methods=["GET"])
@jwt_required(optional=True)
def get_restriction_entries(bot_id):
    current_user = get_jwt_identity()
    login_user = LoginUser.query.filter_by(login_id=current_user).first()
    if not login_user or not login_user.tenant_id:
        return jsonify({"message": "Unauthorized", "status": False}), 403

    bot = CustomBot.query.filter_by(bot_id=bot_id, tenant_id=login_user.tenant_id).first()
    if not bot:
        return jsonify({"message": "Bot not found or unauthorized", "status": False}), 404

    entries = CustomBotAccessRestriction.query.filter_by(bot_id=bot_id).all()

    # Only pure IPs (not mapped to any domain)
    ip_list = [e.allowed_ip for e in entries if e.allowed_ip and e.allowed_domain is None]

    # Only base domains (do not return mapped IPs)
    domain_list = list({e.allowed_domain for e in entries if e.allowed_domain})

    return jsonify({
        "ip": ip_list,
        "domain": domain_list,
        "status": True
    })


@custom_bot_blueprint.route("/restriction/delete", methods=["POST"])
@jwt_required(optional=True)
def delete_restriction_entry():
    current_user = get_jwt_identity()
    login_user = LoginUser.query.filter_by(login_id=current_user).first()
    if not login_user or not login_user.tenant_id:
        return jsonify({"message": "Unauthorized", "status": False}), 403

    data = request.get_json()
    bot_id = data.get("bot_id")
    value = data.get("value")
    restriction_type = data.get("type")

    if not bot_id or not value or restriction_type not in [0, 1]:
        return jsonify({"message": "Invalid data", "status": False}), 400

    bot = CustomBot.query.filter_by(bot_id=bot_id, tenant_id=login_user.tenant_id).first()
    if not bot:
        return jsonify({"message": "Bot not found or unauthorized", "status": False}), 404

    if restriction_type == 0:
        deleted_count = CustomBotAccessRestriction.query.filter_by(
            bot_id=bot_id,
            allowed_ip=value,
            allowed_domain=None
        ).delete(synchronize_session=False)
    else:
        deleted_count = CustomBotAccessRestriction.query.filter(
            CustomBotAccessRestriction.bot_id == bot_id,
            CustomBotAccessRestriction.allowed_domain == value
        ).delete(synchronize_session=False)

    if deleted_count == 0:
        return jsonify({"message": "No matching entry found", "status": False}), 404

    db.session.commit()
    return jsonify({"message": "Entry deleted", "status": True}), 200


@custom_bot_blueprint.route("/restriction", methods=["POST"])
@jwt_required(optional=True)
def add_access_restrictions():
    current_user = get_jwt_identity()
    login_user = LoginUser.query.filter_by(login_id=current_user).first()
    if not login_user or not login_user.tenant_id:
        return jsonify({"message": "Unauthorized", "status": False}), 403

    payload = request.get_json()
    bot_id = payload.get("bot_id")
    entries = payload.get("data", [])
    type_ = payload.get("type")  # 0 = IP, 1 = Domain

    if not bot_id or type_ not in [0, 1] or not isinstance(entries, list):
        return jsonify({"message": "Invalid input", "status": False}), 400

    bot = CustomBot.query.filter_by(bot_id=bot_id, tenant_id=login_user.tenant_id).first()
    if not bot:
        return jsonify({"message": "Bot not found or unauthorized", "status": False}), 404

    # Fetch existing entries
    existing_entries = CustomBotAccessRestriction.query.filter_by(bot_id=bot_id).all()
    existing_ips = {r.allowed_ip for r in existing_entries if r.allowed_ip}
    existing_domains = {(r.allowed_domain, r.allowed_ip) for r in existing_entries if r.allowed_domain}

    for entry in entries:
        if type_ == 0:  # IP
            try:
                ipaddress.ip_address(entry)
            except ValueError:
                return jsonify({"message": f"Invalid IP address: {entry}", "status": False}), 400
            if entry not in existing_ips:
                db.session.add(CustomBotAccessRestriction(bot_id=bot_id, allowed_ip=entry))
                existing_ips.add(entry)
        else:  # Domain
            if not any(d == entry for (d, ip) in existing_domains):
                db.session.add(CustomBotAccessRestriction(bot_id=bot_id, allowed_domain=entry, allowed_ip=None))
                existing_domains.add((entry, None))
            try:
                _, _, ip_list = socket.gethostbyname_ex(entry)
                for ip in ip_list:
                    if (entry, ip) not in existing_domains:
                        db.session.add(CustomBotAccessRestriction(bot_id=bot_id, allowed_domain=entry, allowed_ip=ip))
                        existing_domains.add((entry, ip))
            except socket.gaierror:
                pass

    db.session.commit()
    return jsonify({"message": "Entries added or updated", "status": True}), 200



@custom_bot_blueprint.route("/nodes/<int:bot_id>", methods=["GET"])
@jwt_required()
def get_custombot_nodes(bot_id):
    """
    Fetch a specific bot's data (name, core_features),
    its connected tools, and associated knowledge base.
    """
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({
                "error": "Tenant ID not found in token"
            }), 401

        # --- Fetch Custom Bot ---
        bot = CustomBot.query.filter_by(
            tenant_id=tenant_id,
            bot_id=bot_id,
            bot_status="Created",
            del_flg=False
        ).first()

        if not bot:
            return jsonify({
                "message": "Bot not found",
                "status": "error"
            }), 404

        # --- Build Tools List ---
        tools_list = [{"core_features": bot.core_features}] if bot.core_features else []

        # --- Fetch Knowledge Base ---
        knowledge_base_list = []
        knowledge_base = KnowledgeBase.query.filter_by(
            tenant_id=tenant_id,
            knowledge_base_id=bot.knowledge_base_id,
            del_flg=False
        ).first()

        if knowledge_base:
            knowledge_base_list.append({
                "knowledge_base_id": knowledge_base.knowledge_base_id,
                "tenant_id": knowledge_base.tenant_id,
                "knowledge_base_name": knowledge_base.knowledge_base_name,
                "upload_pdf": knowledge_base.upload_pdf,
                "scrap_url": knowledge_base.scrap_url,
                "max_crawl_pages": knowledge_base.max_crawl_pages,
                "max_crawl_depth": knowledge_base.max_crawl_depth,
                "dynamic_wait": knowledge_base.dynamic_wait,
                "raw_text": knowledge_base.raw_text,
                "chunk_size": knowledge_base.chunk_size,
                "chunk_overlap": knowledge_base.chunk_overlap,
                "collection_name": knowledge_base.collection_name,
            })

        return jsonify({
            "message": "Nodes fetched successfully",
            "status": "success",
            "tools": tools_list,
            "knowledge_bases": knowledge_base_list
        }), 200

    except Exception as e:
        logger.exception(f"Unexpected error fetching bot nodes for bot_id={bot_id}")
        return jsonify({
            "error": f"An unexpected error occurred: {str(e)}"
        }), 500

# @custom_bot_blueprint.route("/<int:bot_id>", methods=["GET"])
# @jwt_required()
# def get_bot(bot_id):
#     try:
#         claims = get_jwt()
#         tenant_id = claims.get("tenant_id")
#         if not tenant_id:
#             logger.error("Tenant ID not found in token")
#             return jsonify({
#                 "data": [],
#                 "message": "Tenant ID not found in token",
#                 "status": "error"
#             }), 401

#         bot = CustomBot.query.filter_by(
#             tenant_id=tenant_id,
#             bot_id=bot_id,
#             del_flg=False
#         ).order_by(CustomBot.created_at.desc()).first()

#         if not bot:
#             return jsonify({
#                 "data": [],
#                 "message": f"No bot found with ID {bot_id}",
#                 "status": "error"
#             }), 404

#         base_url = request.host_url.rstrip("/")
#         avatar_base_path = "uploads/avatars"  # adjust as per your folder

#         bot_data = {
#             "bot_id": bot.bot_id,
#             "bot_name": bot.bot_name,
#             "tenant_id": bot.tenant_id,
#             "tone_of_voice": bot.tone_of_voice.value if bot.tone_of_voice else "",
#             "industry": bot.industry.value if bot.industry else "",
#             "avatar": (
#                 f"{base_url}/{avatar_base_path}/{os.path.basename(bot.avatar)}"
#                 if bot.avatar and not bot.avatar.startswith(('http://', 'https://'))
#                 else bot.avatar or ""
#             ),
#             "purpose": bot.purpose or "",
#             "core_features": bot.core_features if bot.core_features is not None else [""],
#             "instructions": bot.instructions if bot.instructions is not None else [""],
#             "created_at": bot.created_at.strftime("%Y-%m-%d %H:%M:%S"),
#             "updated_at": bot.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
#             "status": bot.status
#         }

#         logger.info(f"Fetched bot_id={bot_id} for tenant_id={tenant_id}")
#         return jsonify({
#             "data": [bot_data],
#             "message": "Bot fetched successfully",
#             "status": "success"
#         }), 200

#     except Exception as e:
#         logger.error(f"Error fetching bot: {str(e)}")
#         return jsonify({
#             "data": [],
#             "message": f"An error occurred: {str(e)}",
#             "status": "error"
#         }), 500


@custom_bot_blueprint.route("/<int:bot_id>", methods=["GET"])
@jwt_required()
def get_bot(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        bot = CustomBot.query.filter_by(
            tenant_id=tenant_id,
            bot_id=bot_id,
            del_flg=False
        ).first()

        if not bot:
            return jsonify({
                "data": [],
                "message": f"No bot found with ID {bot_id}",
                "status": "error"
            }), 404

        base_url = current_app.config.get('BASE_URL', 'https://api.jnanic.com')
        avatar_base_path = "custom-bot/uploads/avatars"
        avatar_url = (
            f"{base_url}/{avatar_base_path}/{os.path.basename(bot.avatar)}"
            if bot.avatar and not bot.avatar.startswith(('http://', 'https://'))
            else bot.avatar or ""
        )

        bot_details = {
            "avatar": avatar_url,
            "bot_id": bot.bot_id,
            "theme": bot.theme,
            "color": bot.colors,
            "bot_name": bot.bot_name,
            "core_features": bot.core_features if isinstance(bot.core_features, list)
                else json.loads(bot.core_features) if bot.core_features else [],
            "created_at": bot.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "industry": bot.industry.value if bot.industry else "",
            "instructions": bot.instructions if isinstance(bot.instructions, list)
                else json.loads(bot.instructions) if bot.instructions else [],
            "purpose": bot.purpose or "",
            "status": bot.status,
            "tenant_id": bot.tenant_id,
            "kb_ids": bot.kb_ids if isinstance(bot.kb_ids, list) else [],
            "tone_of_voice": bot.tone_of_voice.value if bot.tone_of_voice else "",
            "updated_at": bot.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "greeting_type": bot.greeting_type or "dynamic",
            "greeting_message": bot.greeting_message or
                "Hello! I'm your friendly assistant. How can I help you today?"
        }

        return jsonify({
            "data": [bot_details],  # ✅ backward compatible
            "message": "Bot details fetched successfully",
            "status": "success"
        }), 200


    except Exception as e:
        return jsonify({
            "data": [],
            "message": f"An error occurred: {str(e)}",
            "status": "error"
        }), 500



@custom_bot_blueprint.route("/remove-kb", methods=["DELETE"])
@jwt_required()
def remove_kb_from_bot():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        data = request.get_json(silent=True) or {}
        bot_id = data.get("bot_id")
        kb_id = data.get("kb_id")

        if not bot_id or not kb_id:
            return jsonify({"error": "bot_id and kb_id are required"}), 400

        bot = CustomBot.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not bot:
            return jsonify({"error": "Bot not found or unauthorized"}), 404

        if not isinstance(bot.kb_ids, list):
            bot.kb_ids = []

        bot.kb_ids = [x for x in bot.kb_ids if x != int(kb_id)]

        db.session.commit()

        return jsonify({
            "message": "Knowledge base removed successfully",
            "bot_id": bot_id,
            "removed_kb_id": kb_id,
            "remaining_kb_ids": bot.kb_ids
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Remove KB failed | bot_id={bot_id} | {str(e)}")
        return jsonify({"error": "Internal server error"}), 500



@custom_bot_blueprint.route("/<int:bot_id>/kbs", methods=["GET"])
@jwt_required()
def get_kbs_of_bot(bot_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return jsonify({"error": "Tenant ID missing"}), 401

        # Fetch bot
        bot = CustomBot.query.filter_by(
            bot_id=bot_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not bot:
            return jsonify({"error": "Bot not found or unauthorized"}), 404

        # Ensure kb_ids is a list
        kb_ids = bot.kb_ids if isinstance(bot.kb_ids, list) else []

        if not kb_ids:
            return jsonify({
                "bot_id": bot_id,
                "kb_ids": [],
                "knowledge_bases": []
            }), 200

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

        return jsonify({
            "bot_id": bot_id,
            "kb_ids": kb_ids,
            "knowledge_bases": kb_data
        }), 200

    except Exception as e:
        logger.exception(f"Get KBs failed | bot_id={bot_id}")
        return jsonify({"error": "Internal server error"}), 500



