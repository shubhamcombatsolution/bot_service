


"""
Unified Multi-Agent System with a LangGraph Workflow.

This file refactors the ReAct agent into a structured LangGraph workflow.
It uses a decision agent to route tasks to specialized nodes: a greeting agent,
a knowledge base agent, or a powerful tool-using agent (the original ReAct agent).
A final summarization agent polishes the response for the user.
"""
import os
import re
import json
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, TypedDict, Optional
from app.models import Agent,BotDiagram
from app.models.new_models.custom_bot import CustomBotNew
# --- Environment and Database Imports ---
from dotenv import load_dotenv
from app.database.DatabaseOperationPostgreSQL import db_session
from app.models import BaseAgent, ChatHistory, CustomBot, KnowledgeBase, Lead

# --- AI and Vector DB Imports ---
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, BaseMessage
from langchain.agents import initialize_agent, AgentType
from langchain_core.tools import Tool as LangchainTool
import openai
from qdrant_client import QdrantClient

# --- LangGraph Imports ---
import langgraph.graph as lg
from langgraph.graph import StateGraph, END

# --- Flask Imports ---
from flask import Blueprint, request, jsonify, redirect

# --- Custom Tool Imports ---
# Ensure these imports are correct and the files exist in the specified paths
from Tools.CalendarTool import CalendarTool
from Tools.CommuteTimeTool import CommuteTimeTool
from Tools.NearbyFacilitiesTool import NearbyFacilitiesTool
from Tools.TavilyRentalIncomeTool import TavilyRentalIncomeTool
from Tools.GmailTool import GmailTool
from Tools.HubspotTool import HubSpotTool
from zoneinfo import ZoneInfo
from utils import get_enabled_tools_from_features
import os
from logging_config import setup_logging
from typing import List
from pydantic import BaseModel, Field


# --- Initial Setup ---
load_dotenv()




logger = setup_logging("multi_agent_system", level="DEBUG")

# --- Setup separate logs folder ---
# LOG_DIR = "logs"
# os.makedirs(LOG_DIR, exist_ok=True)

# # --- Create module-specific logger ---
# logger = logging.getLogger("multi_agent_system")
# logger.setLevel(logging.INFO)

# # --- Create file handler ONLY for this module ---
# module_log_file = os.path.join(LOG_DIR, "multi_agent_system.log")
# file_handler = logging.FileHandler(module_log_file)
# file_handler.setLevel(logging.INFO)

# # --- Create formatter ---
# formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
# file_handler.setFormatter(formatter)

# # --- Attach handler to this logger ---
# logger.addHandler(file_handler)

# # --- Optional: prevent double logging from root handlers ---
# logger.propagate = False

# --- API Keys & Configuration ---
# Use a default if not found, but log a warning. It's better to fail early if keys are missing.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
HUBSPOT_ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o")
CLIENT_SECRET_PATH = os.getenv("GOOGLE_CLIENT_SECRET_PATH", "client_secret.json")
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_PATH", "token.json")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5000/callback")
SESSION_SECRET = os.getenv("FLASK_SESSION_SECRET", "dev-secret-change-me")
TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "token.json") # Duplicate, but harmless
TOKEN_GMAIL_FILE = "gmailToken.json"
# --- Initialize Clients (Singleton Pattern) ---
openai_client: Optional[openai.Client] = None
llm: Optional[ChatOpenAI] = None

try:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not set.")
    openai_client = openai.Client(api_key=OPENAI_API_KEY)
    # llm = ChatOpenAI(model=MODEL_NAME, temperature=0.1)
    llm = ChatOpenAI(model=MODEL_NAME, temperature=0.1, max_tokens=1000)

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_client = QdrantClient(url=qdrant_url, timeout=120)
    logger.info(f"Successfully initialized OpenAI and Qdrant clients.")
except Exception as e:
    logger.error(f"Failed to initialize AI/DB clients: {e}")
    # Depending on your application's needs, you might want to exit or handle this more gracefully.
    # For now, we'll let it proceed but the system will likely fail later.

# --- LangGraph State Definition ---
class AgentState(TypedDict):
    """
    Defines the state that is passed between nodes in the LangGraph.
    """
    query: str
    chat_memory: List[Dict[str, str]]
    next_agent: str  # The name of the next node to execute
    agent_output: str # The raw output from an agent node
    final_response: str # The polished response for the user

class MultiAgentSystem:
    """
    Manages state and orchestrates a LangGraph workflow for a bot instance.
    """


    def __init__(
        self,
        tenant_id: str,
        bot_id: str,
        session_id: str,
        kb_ids: list = None,
        instructions: list = None,
        core_features: list = None,
        kb_functionalities: list = None,
        memory_mode: str = None
    ):
        self.tenant_id = tenant_id
        self.bot_id = bot_id
        self.session_id = session_id
        # None -> default "session" behavior (load/save scoped to this session)
        self.memory_mode = self._normalize_memory_mode(memory_mode)
        self.qdrant_client = qdrant_client
        self.openai_client = openai_client
        self.llm = llm
        self.rewrite_llm = ChatOpenAI(model=MODEL_NAME, temperature=0.0, max_tokens=50)
        self.strict_llm = ChatOpenAI(model=MODEL_NAME, temperature=0.0, max_tokens=1000)
        self.collection_name = None
        self.bot_details = {}
        self.chat_memory = []
        self.enabled_tools = set()
        self.kb_summary: Optional[str] = None
        self.kb_catalog = []
        self.default_kb_id = None
        self.bot_instructions = []

        # ✅ Store injected config from resolve_bot_config snapshot
        self._injected_kb_ids = kb_ids or []
        self._injected_instructions = instructions or []
        self._injected_core_features = core_features or []
        self._injected_kb_functionalities = kb_functionalities or []

        if not all([self.qdrant_client, self.openai_client, self.llm]):
            raise ConnectionError("One or more required clients failed to initialize.")

        self._load_config_from_db()
        
        # STEP 1: MODE CONTROL
        self.mode = "kb_strict" if self.kb_catalog else "general"
        logger.info(f"[MODE] {self.mode}")
        
        self._load_chat_history()
        self._initialize_tools()
        logger.info(
            "[TOOLS READY] bot_id=%s tenant_id=%s enabled_tools=%s maps_enabled=%s nearby_ready=%s commute_ready=%s maps_api_key_present=%s",
            self.bot_id,
            self.tenant_id,
            sorted(list(self.enabled_tools)) if isinstance(self.enabled_tools, set) else self.enabled_tools,
            "maps" in self.enabled_tools,
            bool(getattr(self, "nearby_facilities_tool", None)),
            bool(getattr(self, "commute_time_tool", None)),
            bool(GOOGLE_MAPS_API_KEY),
        )

        self.graph_executor = self._initialize_graph()
        logger.info(
            f"Initialized MultiAgentSystem with LangGraph for tenant '{tenant_id}', bot '{bot_id}'"
        )
    def _initialize_tools(self):
        """Instantiate only the tools that are allowed for this bot."""
        # Calendar
        if "calendar" in self.enabled_tools:
            self.calendar_tool = CalendarTool(
                credentials_file=CLIENT_SECRET_PATH,
                redirect_uri=REDIRECT_URI,
                auth_mode="manual",
                tenant_id=self.tenant_id
            )
        else:
            self.calendar_tool = None

        # Gmail
        if "gmail" in self.enabled_tools:
            self.gmail_tool = GmailTool(
                credentials_file=CLIENT_SECRET_PATH,
                redirect_uri=REDIRECT_URI,
                tenant_id=self.tenant_id
            )
        else:
            self.gmail_tool = None

        # HubSpot — load per-tenant credentials from tbl_tool_authorization via
        # HubSpotTool._load_token(); do NOT inject the global HUBSPOT_ACCESS_TOKEN
        # env var as preloaded_creds because that token belongs to the server account,
        # not to the individual tenant who connected their HubSpot workspace.
        if "hubspot" in self.enabled_tools:
            self.hubspot_tool = HubSpotTool(
                tenant_id=self.tenant_id,
                client_id=os.getenv("HUBSPOT_CLIENT_ID"),
                client_secret=os.getenv("HUBSPOT_CLIENT_SECRET"),
                redirect_uri="https://jnanic.com/Admin/Tools",
                # preloaded_creds intentionally omitted — tool fetches from DB per tenant
            )
        else:
            self.hubspot_tool = None

        # Maps-related tools
        if "maps" in self.enabled_tools and GOOGLE_MAPS_API_KEY:
            self.nearby_facilities_tool = NearbyFacilitiesTool(api_key=GOOGLE_MAPS_API_KEY)
        else:
            self.nearby_facilities_tool = None

        if "maps" in self.enabled_tools:
            self.commute_time_tool = CommuteTimeTool()
        else:
            self.commute_time_tool = None

        # Tavily (Rental Income)
        if "tavily" in self.enabled_tools and TAVILY_API_KEY:
            self.rental_income_tool = TavilyRentalIncomeTool(api_key=TAVILY_API_KEY)
        else:
            self.rental_income_tool = None
    
    #  Instrctution extrcator
    def _safely_extract_instructions(self, custom_bot) -> list:
        """
        Generic instruction extractor - handles any format
        No assumptions about content or structure
        """
        try:
            raw = custom_bot.instructions
            
            if not raw:
                return []
            
            # Handle list of strings (preferred format)
            if isinstance(raw, list):
                result = []
                for item in raw:
                    if isinstance(item, str):
                        text = item.strip()
                    elif isinstance(item, dict):
                        # Extract from common dict keys
                        text = (
                            item.get("question") or 
                            item.get("text") or 
                            item.get("instruction") or 
                            str(item)
                        ).strip()
                    else:
                        text = str(item).strip()
                    
                    if text and len(text) > 5:  # Basic validation
                        result.append(text)
                
                return result
            
            # Handle single string (edge case)
            if isinstance(raw, str):
                return [raw.strip()] if raw.strip() else []
            
            logger.warning(f"Unexpected instruction format: {type(raw)}")
            return []
            
        except Exception as e:
            logger.error(f"Error extracting instructions: {e}")
            return []
 

    
    def _load_config_from_db(self):
        """Loads bot meta from CustomBotNew; uses injected config for KBs/instructions."""
        logger.info(f"[_load_config_from_db] START | bot_id={self.bot_id} | tenant_id={self.tenant_id} | tenant_id_type={type(self.tenant_id).__name__}")
        logger.info(f"[_load_config_from_db] Injected config | kb_ids={self._injected_kb_ids} | kb_ids_type={type(self._injected_kb_ids).__name__} | instructions_count={len(self._injected_instructions) if isinstance(self._injected_instructions, list) else 'non-list'} | core_features_type={type(self._injected_core_features).__name__}")

        session = next(db_session())
        try:
            custom_bot = session.query(CustomBotNew).filter_by(
                bot_id=self.bot_id,
                tenant_id=self.tenant_id
            ).first()

            if not custom_bot:
                logger.warning(f"[_load_config_from_db] No bot found for bot_id={self.bot_id} | tenant_id={self.tenant_id}. Using defaults.")
                self.bot_details = {
                    "name": "Assistant",
                    "tone": "professional",
                    "industry": "general",
                    "purpose": "assist users"
                }
                return

            logger.info(f"[_load_config_from_db] Bot found | bot_id={self.bot_id} | name={custom_bot.bot_name} | status={custom_bot.bot_status}")

            # Bot meta
            self.bot_details = {
                "name": custom_bot.bot_name or "Assistant",
                "tone": custom_bot.tone_of_voice.value if custom_bot.tone_of_voice else "professional",
                "industry": custom_bot.industry.value if custom_bot.industry else "general",
                "purpose": custom_bot.purpose or "assist users",
            }
            logger.debug(f"[_load_config_from_db] Bot details set | {self.bot_details}")

            # Tools
            logger.info(f"[_load_config_from_db] Resolving tools | core_features={self._injected_core_features}")
            self.enabled_tools = get_enabled_tools_from_features(
                self.tenant_id,
                self.bot_id,
                core_features=self._injected_core_features
            )
            logger.info(f"[_load_config_from_db] Enabled tools resolved | tools={self.enabled_tools}")

            # KBs
            self.collection_names = []
            self.kb_summaries = []
            self.kb_catalog = []

            kb_ids = self._injected_kb_ids
            logger.info(f"[_load_config_from_db] Raw injected kb_ids={kb_ids} | type={type(kb_ids).__name__}")
            if not kb_ids:
                kb_ids = getattr(custom_bot, "kb_ids", []) or []
                logger.info(
                    f"[_load_config_from_db] Injected kb_ids empty; fallback to custom_bot.kb_ids={kb_ids} "
                    f"| type={type(kb_ids).__name__}"
                )

            # Defensive parse
            if isinstance(kb_ids, str):
                logger.warning(f"[_load_config_from_db] kb_ids is a string — attempting json.loads")
                try:
                    kb_ids = json.loads(kb_ids)
                    logger.info(f"[_load_config_from_db] kb_ids parsed from string → {kb_ids}")
                except Exception as e:
                    logger.warning(f"[_load_config_from_db] Failed to parse kb_ids string: {e} — defaulting to []")
                    kb_ids = []

            if not isinstance(kb_ids, list):
                logger.warning(f"[_load_config_from_db] kb_ids is not a list after parse (type={type(kb_ids).__name__}) — defaulting to []")
                kb_ids = []

            # Normalize ids to integers and drop invalid values.
            normalized_kb_ids = []
            for raw_id in kb_ids:
                try:
                    normalized_kb_ids.append(int(raw_id))
                except (TypeError, ValueError):
                    logger.warning(f"[_load_config_from_db] Skipping invalid kb_id value: {raw_id}")
            kb_ids = list(dict.fromkeys(normalized_kb_ids))

            logger.info(f"[_load_config_from_db] Final kb_ids to query={kb_ids} | element_types={[type(x).__name__ for x in kb_ids]}")

            if not kb_ids:
                logger.warning(f"[_load_config_from_db] kb_ids is empty — no KB query will be made for bot {self.bot_id}")
            else:
                logger.info(
                    f"[_load_config_from_db] Querying KnowledgeBase | "
                    f"kb_ids={kb_ids} | "
                    f"tenant_id={self.tenant_id} (type={type(self.tenant_id).__name__}) | "
                    f"del_flg=False"
                )

                kbs = (
                    session.query(KnowledgeBase)
                    .filter(
                        KnowledgeBase.knowledge_base_id.in_(kb_ids),
                        KnowledgeBase.tenant_id == self.tenant_id,
                        KnowledgeBase.del_flg == False
                    )
                    .all()
                )

                logger.info(f"[_load_config_from_db] KB query returned {len(kbs)} record(s)")

                # ✅ If nothing found — run unfiltered query to diagnose WHY
                if not kbs:
                    logger.warning(f"[_load_config_from_db] No KBs matched all filters. Running diagnostic unfiltered query...")
                    unfiltered = session.query(KnowledgeBase).filter(
                        KnowledgeBase.knowledge_base_id.in_(kb_ids)
                    ).all()

                    if not unfiltered:
                        logger.error(f"[_load_config_from_db] KB id(s) {kb_ids} do NOT exist in KnowledgeBase table at all")
                    else:
                        for kb in unfiltered:
                            logger.warning(
                                f"[_load_config_from_db] KB exists but filtered out | "
                                f"kb_id={kb.knowledge_base_id} (type={type(kb.knowledge_base_id).__name__}) | "
                                f"kb_tenant_id={kb.tenant_id} (type={type(kb.tenant_id).__name__}) | "
                                f"bot_tenant_id={self.tenant_id} (type={type(self.tenant_id).__name__}) | "
                                f"tenant_match={kb.tenant_id == self.tenant_id} | "
                                f"del_flg={kb.del_flg} | "
                                f"collection_name={kb.collection_name}"
                            )
                else:
                    for kb in kbs:
                        logger.info(
                            f"[_load_config_from_db] KB matched | "
                            f"kb_id={kb.knowledge_base_id} | "
                            f"tenant_id={kb.tenant_id} | "
                            f"del_flg={kb.del_flg} | "
                            f"collection_name={kb.collection_name} | "
                            f"has_collection={'YES' if kb.collection_name else 'NO — will be skipped'}"
                        )
                        if not kb.collection_name:
                            logger.warning(f"[_load_config_from_db] KB {kb.knowledge_base_id} skipped — collection_name is None/empty")
                            continue

                        # Skip stale KB records whose Qdrant collection does not exist.
                        try:
                            self.qdrant_client.get_collection(kb.collection_name)
                        except Exception as e:
                            logger.warning(
                                f"[_load_config_from_db] KB {kb.knowledge_base_id} skipped — "
                                f"Qdrant collection not found or inaccessible: {kb.collection_name} | error={e}"
                            )
                            continue

                        self.kb_catalog.append({
                            "kb_id": kb.knowledge_base_id,
                            "collection_name": kb.collection_name,
                            "summary": getattr(kb, "kb_summary", None)
                        })
                        self.collection_names.append(kb.collection_name)
                        self.kb_summaries.append(getattr(kb, "kb_summary", None))

                logger.info(f"[_load_config_from_db] KB catalog built | count={len(self.kb_catalog)} | catalog={self.kb_catalog}")

            self.collection_name = self.collection_names[0] if self.collection_names else None
            self.kb_summary = self.kb_summaries[0] if self.kb_summaries else None
            self.default_kb_id = self.kb_catalog[0]["kb_id"] if self.kb_catalog else None

            logger.info(
                f"[_load_config_from_db] KB state set | "
                f"collection_name={self.collection_name} | "
                f"kb_summary={'present' if self.kb_summary else 'None'} | "
                f"default_kb_id={self.default_kb_id}"
            )

            # Instructions
            logger.info(f"[_load_config_from_db] Extracting instructions | raw_count={len(self._injected_instructions) if isinstance(self._injected_instructions, list) else 'non-list'}")
            self.bot_instructions = self._safely_extract_instructions_from_list(
                self._injected_instructions
            )
            logger.info(f"[_load_config_from_db] Instructions extracted | count={len(self.bot_instructions)}")

            # ─── 🆕 Diagram overlay ────────────────────────────────────────
            # Read the bot's latest saved workflow (tbl_bot_diagrams) and
            # apply any per-bot edits the user made in the workflow designer
            # on top of the values just loaded from tbl_custombot_new.
            #
            # Backward compatibility: when no diagram exists, or the Bot Agent
            # node has no override fields, nothing changes — MAS keeps the
            # core_features / kb_ids / instructions it just resolved.
            try:
                # Primary: diagrams already linked to this bot.
                diagram = (
                    session.query(BotDiagram)
                    .filter(
                        BotDiagram.bot_id == self.bot_id,
                        BotDiagram.tenant_id == self.tenant_id,
                        BotDiagram.del_flg == False,
                    )
                    .order_by(
                        BotDiagram.updated_at.desc().nullslast(),
                        BotDiagram.diagram_id.desc(),
                    )
                    .first()
                )

                # 🆕 Fallback for legacy detached rows (bot_id IS NULL).
                # If we can identify a detached diagram in this tenant that
                # matches the bot by workflow_name (== bot_name) or by the
                # legacy `custom_bot_new_{bot_id}` pattern, opportunistically
                # re-link it so subsequent loads find it directly.
                if not diagram:
                    bot_name_norm = (
                        (custom_bot.bot_name or "").strip().lower()
                        if custom_bot is not None else ""
                    )
                    legacy_name = f"custom_bot_new_{self.bot_id}"
                    detached = (
                        session.query(BotDiagram)
                        .filter(
                            BotDiagram.tenant_id == self.tenant_id,
                            BotDiagram.bot_id.is_(None),
                            BotDiagram.del_flg == False,
                        )
                        .order_by(
                            BotDiagram.updated_at.desc().nullslast(),
                            BotDiagram.diagram_id.desc(),
                        )
                        .all()
                    )
                    for cand in detached:
                        wn_norm = (cand.workflow_name or "").strip().lower()
                        if wn_norm and (wn_norm == bot_name_norm or wn_norm == legacy_name.lower()):
                            try:
                                cand.bot_id = self.bot_id
                                session.commit()
                                logger.info(
                                    f"[_load_config_from_db] Healed detached diagram | "
                                    f"diagram_id={cand.diagram_id} → bot_id={self.bot_id} "
                                    f"(matched workflow_name='{cand.workflow_name}')"
                                )
                                diagram = cand
                                break
                            except Exception as heal_err:
                                # Persistent link failed (commonly because the
                                # legacy FK `tbl_bot_diagrams_bot_id_fkey` still
                                # references `tbl_custombot` while this bot lives
                                # in `tbl_custombot_new`). Don't give up — use
                                # the matched diagram for this run's overlay so
                                # the user's workflow edits still take effect.
                                session.rollback()
                                logger.warning(
                                    f"[_load_config_from_db] Failed to heal diagram link "
                                    f"(legacy FK?) | diagram_id={cand.diagram_id} | "
                                    f"using diagram for this run only | err={heal_err}"
                                )
                                # Re-fetch a clean instance after rollback so
                                # the row is usable on the active session.
                                try:
                                    diagram = session.query(BotDiagram).filter(
                                        BotDiagram.diagram_id == cand.diagram_id,
                                        BotDiagram.del_flg == False,
                                    ).first()
                                except Exception:
                                    diagram = cand
                                if diagram:
                                    break
                if diagram and diagram.diagram_json:
                    try:
                        diagram_data = (
                            json.loads(diagram.diagram_json)
                            if isinstance(diagram.diagram_json, str)
                            else diagram.diagram_json
                        )
                    except Exception as parse_err:
                        logger.warning(
                            f"[_load_config_from_db] Diagram JSON parse failed | "
                            f"diagram_id={diagram.diagram_id} | err={parse_err}"
                        )
                        diagram_data = None

                    agent_node = None
                    if isinstance(diagram_data, dict):
                        for _node in diagram_data.get("nodes", []) or []:
                            if isinstance(_node, dict) and _node.get("type") == "GenericAgentNode":
                                agent_node = _node
                                break

                    if agent_node:
                        node_data = agent_node.get("data") or {}
                        form_data = node_data.get("formData") or {}
                        logger.info(
                            f"[_load_config_from_db] Diagram overlay | "
                            f"diagram_id={diagram.diagram_id} | "
                            f"node_id={agent_node.get('id')} | "
                            f"formData_keys={list(form_data.keys())}"
                        )

                        # 1) tool_names → replace enabled_tools when provided.
                        raw_tool_names = form_data.get("tool_names")
                        if isinstance(raw_tool_names, list) and raw_tool_names:
                            overlay_tools = {
                                str(t).strip().lower()
                                for t in raw_tool_names
                                if isinstance(t, str) and t.strip()
                            }
                            if overlay_tools:
                                logger.info(
                                    f"[_load_config_from_db] Diagram overlay | "
                                    f"tool_names from formData={sorted(overlay_tools)} | "
                                    f"replacing feature-derived tools="
                                    f"{sorted(self.enabled_tools) if isinstance(self.enabled_tools, set) else self.enabled_tools}"
                                )
                                self.enabled_tools = overlay_tools

                        # 2) agent_role / agent_instructions → append to bot_instructions.
                        overlay_lines = []
                        role_txt = form_data.get("agent_role")
                        if isinstance(role_txt, str) and role_txt.strip():
                            overlay_lines.append(role_txt.strip())
                        instr_txt = form_data.get("agent_instructions")
                        if isinstance(instr_txt, str) and instr_txt.strip():
                            overlay_lines.append(instr_txt.strip())
                        task_txt = form_data.get("task")
                        if isinstance(task_txt, str) and task_txt.strip():
                            overlay_lines.append(task_txt.strip())
                        if overlay_lines:
                            self.bot_instructions = list(self.bot_instructions or []) + overlay_lines
                            logger.info(
                                f"[_load_config_from_db] Diagram overlay | "
                                f"appended {len(overlay_lines)} persona/instruction line(s) from formData"
                            )

                        # 3) knowledge_base_ids → replace KB catalog when provided.
                        overlay_kb_raw = form_data.get("knowledge_base_ids")
                        if isinstance(overlay_kb_raw, list) and overlay_kb_raw:
                            overlay_kb_ids = []
                            for raw_id in overlay_kb_raw:
                                try:
                                    overlay_kb_ids.append(int(raw_id))
                                except (TypeError, ValueError):
                                    continue
                            overlay_kb_ids = list(dict.fromkeys(overlay_kb_ids))
                            current_ids = {kb["kb_id"] for kb in self.kb_catalog}
                            if overlay_kb_ids and set(overlay_kb_ids) != current_ids:
                                logger.info(
                                    f"[_load_config_from_db] Diagram overlay | "
                                    f"reloading KBs from formData kb_ids={overlay_kb_ids}"
                                )
                                new_catalog, new_names, new_summaries = [], [], []
                                kbs = (
                                    session.query(KnowledgeBase)
                                    .filter(
                                        KnowledgeBase.knowledge_base_id.in_(overlay_kb_ids),
                                        KnowledgeBase.tenant_id == self.tenant_id,
                                        KnowledgeBase.del_flg == False,
                                    )
                                    .all()
                                )
                                for kb in kbs:
                                    if not kb.collection_name:
                                        continue
                                    try:
                                        self.qdrant_client.get_collection(kb.collection_name)
                                    except Exception:
                                        continue
                                    new_catalog.append({
                                        "kb_id": kb.knowledge_base_id,
                                        "collection_name": kb.collection_name,
                                        "summary": getattr(kb, "kb_summary", None),
                                    })
                                    new_names.append(kb.collection_name)
                                    new_summaries.append(getattr(kb, "kb_summary", None))
                                if new_catalog:
                                    self.kb_catalog = new_catalog
                                    self.collection_names = new_names
                                    self.kb_summaries = new_summaries
                                    self.collection_name = new_names[0]
                                    self.kb_summary = new_summaries[0]
                                    self.default_kb_id = new_catalog[0]["kb_id"]
                    else:
                        logger.info(
                            f"[_load_config_from_db] Diagram overlay skipped | "
                            f"no GenericAgentNode found in diagram_id={diagram.diagram_id}"
                        )
                else:
                    logger.info(
                        f"[_load_config_from_db] Diagram overlay skipped | "
                        f"no diagram for bot_id={self.bot_id}"
                    )
            except Exception as overlay_err:
                logger.warning(
                    f"[_load_config_from_db] Diagram overlay skipped due to error: {overlay_err}",
                    exc_info=True,
                )
            # ─── end overlay ──────────────────────────────────────────────

            logger.info(
                f"[_load_config_from_db] COMPLETE | bot={self.bot_id} | "
                f"kbs={len(self.kb_catalog)} | "
                f"instructions={len(self.bot_instructions)} | "
                f"tools={self.enabled_tools}"
            )

        except Exception as e:
            logger.error(f"[_load_config_from_db] ERROR | bot={self.bot_id} | {e}", exc_info=True)
        finally:
            session.close()
            logger.debug(f"[_load_config_from_db] DB session closed | bot={self.bot_id}")
    
    
    def _safely_extract_instructions_from_list(self, instructions: list) -> list:
        """Extracts instructions from an already-resolved list (from snapshot)."""
        if not instructions:
            return []
        result = []
        for item in instructions:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
            # Skip instructions that are explicitly deselected
                if item.get("selected") is False:
                  continue
                text = (
                   item.get("question") or
                   item.get("text") or
                   item.get("instruction") or
                    str(item)
                ).strip()
            else:
                text = str(item).strip()
            if text and len(text) > 5:
                result.append(text)
        return result
        
    @staticmethod
    def _normalize_memory_mode(memory_mode):
        """Collapse stored memory_mode strings into: 'structured' | 'session' | 'persistent'.

        Handles both vocabularies seen in the DB:
          jnanic  : 'structured' | 'session' | 'persistent' | 'conversation'
          legacy  : null | 'short_term' | 'long_term'
        None / unknown defaults to 'session' (preserves prior behavior).
        """
        value = (memory_mode or "").strip().lower()
        if value == "structured":
            return "structured"
        if value in ("persistent", "long_term"):
            return "persistent"
        # 'session', 'short_term', 'conversation', '', None, unknown
        return "session"

    def _load_chat_history(self):
        """Loads chat history from the database, scoped by memory_mode.

        structured -> no history (no memory between messages)
        session    -> only this session's turns
        persistent -> all turns for (tenant_id, bot_id), across sessions
        """
        if self.memory_mode == "structured":
            self.chat_memory = []
            return

        session = next(db_session())
        try:
            query = session.query(ChatHistory).filter_by(
                tenant_id=self.tenant_id, bot_id=self.bot_id
            )
            if self.memory_mode == "session":
                query = query.filter_by(session_id=self.session_id)
            history = (
                query.order_by(ChatHistory.created_at.asc())
                .limit(20)
                .all()
            )
            self.chat_memory = [{"query": entry.query, "response": entry.response} for entry in history]
        except Exception as e:
            logger.error(f"Error loading chat history: {e}")
        finally:
            session.close()

    def save_chat_history(self, query: str, response: str):
        """Saves a conversation turn to the database. No-op for structured mode."""
        if self.memory_mode == "structured":
            return

        session = next(db_session())
        try:
            chat_entry = ChatHistory(
                tenant_id=self.tenant_id,
                bot_id=self.bot_id,
                session_id=self.session_id,
                query=query,
                response=str(response),
                created_at=datetime.now()
            )
            session.add(chat_entry)
            session.commit()
            response_summary = response[:300] + "..." if len(response) > 300 else response
            self.chat_memory.append({"query": query, "response": response_summary})
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving chat history: {e}")
            # Fallback: still store in memory even if DB save fails
            response_summary = response[:300] + "..." if len(response) > 300 else response
            self.chat_memory.append({"query": query, "response": response_summary})
        finally:
            session.close()

    def _initialize_graph(self):
        """Sets up and compiles the LangGraph workflow."""
        workflow = StateGraph(AgentState)

        # Define the nodes
        workflow.add_node("rephrase", self.rephrase_agent)  # <-- new rephrase agent
        workflow.add_node("decision", self.decision_agent)
        workflow.add_node("greeting", self.greeting_agent)
        workflow.add_node("kb", self.kb_agent)
        workflow.add_node("tools", self.tools_agent)
        workflow.add_node("summarization", self.summarization_agent)

        # Entry point → rephrase agent first
        workflow.set_entry_point("rephrase")

        # Flow: rephrase → decision
        workflow.add_edge("rephrase", "decision")

        # Decision node routes to agents
        workflow.add_conditional_edges(
            "decision",
            lambda state: state["next_agent"],
            {
                "greeting": "greeting",
                "kb": "kb",
                "tools": "tools"
            }
        )

        # All agent nodes → summarization
        workflow.add_edge("greeting", "summarization")
        workflow.add_edge("kb", "summarization")
        workflow.add_edge("tools", "summarization")

        # Summarization is the end
        workflow.add_edge("summarization", END)

        return workflow.compile()

    # --- Router and Agent Nodes ---

    def _classify_intent(self, query: str) -> str:
        """Classifies the user's intent to route to the correct agent node."""
        q_lower = query.lower().strip()

        # Simple greetings
        if re.match(r"^(hi|hello|hey|good morning|good afternoon)\b", q_lower):
            return "greeting"

        # Keywords for knowledge base
        kb_keywords = ["property", "2bhk", "3bhk", "policy", "company info", "details about"]
        if any(keyword in q_lower for keyword in kb_keywords):
            return "kb"

        # Default to the powerful tools agent for everything else
        return "tools"

    
    def rephrase_agent(self, state: AgentState) -> Dict[str, Any]:
        """
        Rephrases the user's raw query considering chat history.
        Outputs a clean, concise query for the decision agent.
        """
        raw_query = state["query"]
        if self.mode == "kb_strict":
            logger.info("[Rephrase] Skipped in strict mode")
            return {
                "query": raw_query,
                "chat_memory": state.get("chat_memory", [])
            }
        chat_memory = state.get("chat_memory", [])

        formatted_history = ""
        if chat_memory:
            formatted_history = "Conversation history:\n"
            for turn in chat_memory[-5:]:
               user_q = turn.get('query', '')
               # Truncate bot response to 150 chars — rephrase only needs topic context
               bot_r = turn.get('response', '')
               bot_r_short = (bot_r[:150] + "...") if len(bot_r) > 150 else bot_r
               formatted_history += f"User: {user_q}\nAI: {bot_r_short}\n"
            formatted_history += "\n"

        rephrase_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

        rephrase_prompt = f"""Task:
Rephrase the following user query into a clear and concise standalone version,
while considering the conversation history for context.

Rules (strict):
1. If the message is only a greeting (hi, hello, hey, good morning, etc.) and contains no task or question,
return it exactly as written.
2. If the message contains a task or question, remove greetings and politeness.
3. If the message contains pronouns like "it", "its", "this", or "that",
replace them with the explicit subject mentioned most recently by the USER.
4. Do not invent new topics or subjects.
5. If the subject cannot be confidently resolved from conversation history,
return the original message unchanged.
6. Output only the rewritten query. No explanations.

Conversation history:
{formatted_history}

User's raw query: "{raw_query}"


Provide only the rephrased query.
        """

        try:
            rephrase_response = rephrase_llm.invoke(rephrase_prompt)
            rephrased_query = rephrase_response.content.strip()
            state["query"] = rephrased_query
            logger.info(f"Rephrase Agent: Rephrased query: '{rephrased_query}'")
            return {
                "query": rephrased_query,   # overwrite query for decision agent
                "chat_memory": chat_memory, # keep history for later agents if needed
            }
        except Exception as e:
            logger.error(f"Rephrase Agent error: {e}. Falling back to raw query.")
            return {"query": raw_query, "chat_memory": chat_memory}

    def decision_agent(self, state: AgentState) -> Dict[str, Any]:
        query = (state.get("query") or "").strip()
        query_lower = query.lower()

        # Always greet on empty/bootstrapping messages from widget.
        if not query or query_lower in {"start", "start chat", "init", "initialize", "null", "undefined"}:
            logger.info("[Decision Agent] Empty/bootstrap query detected → routing to greeting")
            return {"next_agent": "greeting"}
        pure_greeting = re.match(
            r"^(hi|hello|hey|hii|helo|hy|good\s+morning|good\s+afternoon|good\s+evening|good\s+night|yo|sup|what('?s|\s+is)\s+up)\s*[!.,]?\s*$",
            query.strip(),
            re.IGNORECASE
        )
        if self.mode == "kb_strict":
            if pure_greeting:
                logger.info("[Decision Agent] kb_strict + greeting detected → routing to greeting")
                return {"next_agent": "greeting"}
            # Force map/location queries to tools in strict mode.
            strict_map_intent = re.compile(
                r"\b("
                r"distance|near|nearby|nearest|directions?|route|travel time|commute|eta|travel|maps|google maps|"
                r"how far|minutes away|location|map|hospital|school|restaurant|airport|station|college|university|park|museum|hotel|gas station|pharmacy| petrol pump|cafe|coffee shop|bank|atm|library|mall|supermarket|bus stand|train station|subway|parking|zomato|swiggy|ubereats"
                r")\b",
                re.IGNORECASE
            )
            if strict_map_intent.search(query):
                logger.info("[Decision Agent] kb_strict + map/location intent → routing to tools")
                return {"next_agent": "tools"}
            explicit_tool_actions = re.compile(
                r"\b("
                r"send(\s+an?)?\s+e?mail|"
                r"book|schedule|create\s+lead|create\s+contact|"
                r"calendar|hubspot|commute|near|nearby|distance|directions?|route|travel|"
                r"call|message|sms|whatsapp"
                r")\b",
                re.IGNORECASE
            )
            if explicit_tool_actions.search(query):
                logger.info("[Decision Agent] kb_strict + explicit tool intent → routing to tools")
                return {"next_agent": "tools"}
            logger.info("[Decision Agent] kb_strict active → routing to KB by default")
            return {"next_agent": "kb"}
        greetings = [
            "hi", "hello", "hey", "hii", "helo", "hy",
            "good morning", "good afternoon", "good evening", "good night",
            "yo", "sup", "what's up", "whats up",
            "start", "start chat"
        ]
        
        # Match only clean greetings (avoid false positives like "this", "high", etc.)
        if any(query_lower == greet or query_lower.startswith(greet + " ") for greet in greetings):
            logger.info("[Decision Agent] Greeting detected → routing to greeting")
            return {"next_agent": "greeting"}
        
        logger.info(f"[Decision Agent] Incoming query: '{query}'")

        # Deterministic task routing: if user asks to perform an action and tools exist, use tools.
        action_intent_pattern = re.compile(
            r"\b("
            r"send|schedule|book|find|calculate|lookup|fetch|create|update|generate|translate|"
            r"search|email|call|open|close|delete|remove|add|set|check|track|show|navigate"
            r")\b",
            re.IGNORECASE
        )
        has_tools = bool(_build_tool_map(self, exclude_kb=True))
        if has_tools and action_intent_pattern.search(query):
            logger.info("[Decision Agent] Explicit action intent detected with tools available → routing to tools")
            return {"next_agent": "tools"}

        # Hard-route map/location intent to tools so Google Maps tools are used reliably.
        map_intent_pattern = re.compile(
            r"\b("
            r"near|nearby|nearest|distance|directions?|route|travel time|commute|eta|"
            r"how far|minutes away|location|hospital|school|restaurant|airport|station"
            r")\b",
            re.IGNORECASE
        )
        if map_intent_pattern.search(query):
            logger.info("[Decision Agent] Map/location intent detected → routing to tools")
            return {"next_agent": "tools"}

        card_keywords_pattern = re.compile(
            r"\b(status|blocked|block|active|freeze|frozen|hotlist|lost|stolen|activate|deactivate)\b",
            re.IGNORECASE,
        )
        if re.search(r"\b(card|debit card|credit card)\b", query, re.IGNORECASE) and card_keywords_pattern.search(query):
            logger.info("[Decision Agent] Card management intent detected → routing to tools")
            return {"next_agent": "tools"}

        banking_state_pattern = re.compile(
            r"\b("
            r"balance|statement|mini statement|transactions?|transaction history|"
            r"account details|account status|card details|card status|"
            r"unblock|unfreeze|reactivate|block|freeze|hotlist|"
            r"account number|last \d+ transactions"
            r")\b",
            re.IGNORECASE,
        )
        if banking_state_pattern.search(query):
            logger.info("[Decision Agent] Banking state query detected → routing to tools")
            return {"next_agent": "tools"}

        # Deterministic informational routing: pure question/info queries should go to KB.
        informational_pattern = re.compile(
            r"^\s*(what|which|when|where|who|why|how|tell me|explain|details about)\b",
            re.IGNORECASE
        )
        if informational_pattern.search(query) and not action_intent_pattern.search(query):
            logger.info("[Decision Agent] Informational intent detected → routing to KB")
            return {"next_agent": "kb"}
        
        if pure_greeting:
            return {"next_agent": "greeting"}
        def prefers_tools(text: str) -> bool:
            return bool(action_intent_pattern.search(text))

        # --- Step 1: Build runtime tool metadata ---
        try:
            tools = _build_tool_map(self, exclude_kb=False)  # include all
            tool_metadata_section = "\n".join([
                f"Tool Name: {t.name}\n"
                f"Purpose: {t.description.split('.')[0]}\n"
                f"Required Input: {getattr(t, 'args_schema', 'Unknown')}\n"
                for t in tools
            ])
            logger.debug(f"[Decision Agent] Tools Available:\n{tool_metadata_section}")
        except Exception as e:
            logger.error(f"[Decision Agent] Failed to load tools: {str(e)}")
            tools = []
            tool_metadata_section = "No tools available."

        # --- Step 2: Prepare KB Summary Context ---
        kb_summary_text = self.kb_summary or ""
        if len(kb_summary_text) > 0:
            logger.info("[Decision Agent] KB summary detected.")
        else:
            logger.warning("[Decision Agent] No KB summary available.")

        # --- Step 3: LLM Routing Prompt (Generalized Intent Classifier) ---
        routing_prompt = f"""
            You are an intelligent routing controller inside a multi-agent system.

            Your job is to analyze the user's intent and route their query to the correct agent.

            -------------------------
            User Query:
            \"\"\"{query}\"\"\"

            -------------------------
            Available Agents:
            - greeting → casual hello, conversation, chit-chat
            - kb → informational queries, FAQs, policies, help articles, knowledge-based answers
            - tools → actionable tasks that require external execution via available tools

            -------------------------
            Knowledge Base Context (Optional):
            \"\"\"{kb_summary_text}\"\"\"

            -------------------------
            Tool Catalog:
            {tool_metadata_section}

            -------------------------
            Routing Rules:
            1. If the query is a greeting (hello / hi / hey / good morning / good afternoon / good evening) → respond: greeting
            2. If the user asks for an action requiring a tool (send, schedule, book, find, calculate, lookup, fetch, create, update, generate, translate, search, or any external execution), respond: tools
            3. If the user asks for information that can be answered from the knowledge base, respond: kb
            4. If the query is not clearly an action and KB context exists, prefer kb.
            5. Only route to tools when a real external action or tool execution is required.

            -------------------------
            Respond with ONLY ONE WORD exactly as written:
            - greeting
            - kb
            - tools
            """

        # --- Step 4: Call LLM for Routing Decision ---
        try:
            decision_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
            response = decision_llm.invoke(routing_prompt)
            next_agent = response.content.strip().lower()

            if next_agent not in ["greeting", "kb", "tools"]:
                logger.warning(f"[Decision Agent] Invalid LLM routing '{next_agent}'. Fallback applied.")
                if tools and prefers_tools(query):
                    next_agent = "tools"
                else:
                    next_agent = "kb" if kb_summary_text else ("tools" if tools else "kb")

            logger.info(f"[Decision Agent] Final routing decision → {next_agent.upper()}")
            return {"next_agent": next_agent}

        except Exception as e:
            logger.error(f"[Decision Agent] LLM routing failed: {e}")
            if tools and prefers_tools(query):
                fallback_agent = "tools"
            else:
                fallback_agent = "kb" if kb_summary_text else ("tools" if tools else "kb")
            logger.warning(f"[Decision Agent] Using heuristic fallback agent → {fallback_agent}")
            return {"next_agent": fallback_agent}


    def greeting_agent(self, state: AgentState) -> Dict[str, str]:
        """Node to handle simple greetings."""
        logger.info("Executing Greeting Agent.")
        name = self.bot_details.get('name', 'Assistant')
        output = f"Hi! I'm {name}. How can I help you today?"
        return {"agent_output": output}


    def kb_agent(self, state: AgentState) -> Dict[str, str]:
        logger.info("Executing KB Agent (multi-KB enabled).")
        query = state["query"]
        search_query = self.rewrite_query_for_search(query)
        query_l = (query or "").lower()
        # Lightweight entity extraction for exact-match prioritization (year/make/model style queries).
        key_tokens = set(re.findall(r"\b(?:19|20)\d{2}\b|[a-z]{2,}\d*[a-z]*", query_l))
        stop_tokens = {
            "what", "was", "the", "of", "for", "and", "with", "from", "that", "this",
            "listing", "price", "sedan", "car", "cars", "vehicle", "model"
        }
        key_tokens = {t for t in key_tokens if t not in stop_tokens}
        
        #------------------ Fallback if no kbs --------------------
        recent_context = []
        for turn in state.get("chat_memory", [])[-3:]:
            if turn.get("query"):
                recent_context.append(f"- {turn['query']}")

        context_block = "\n".join(recent_context)

        prompt = f"""
        The user is continuing a conversation.

        Recent context:
        {context_block}

        Current question:
        "{query}"

        Answer the question in the same topic and context.
        """

        if not self.kb_catalog:
            logger.info("No KB configured. Returning KB-only fallback message.")
            return {"agent_output": "I couldn't find any configured knowledge base to answer that question."}
        
        #------------------------------------------------------

        # ---------- KB ROUTING ----------
        # Skip router if only one KB — no routing decision needed
        if len(self.kb_catalog) == 1:
            kb_ids_to_search = [self.kb_catalog[0]["kb_id"]]
            logger.info(f"Single KB — skipping router, using KB {kb_ids_to_search[0]}")
        else:
            decision = route_knowledge_bases(
                llm=self.llm,
                query=query,
                kb_metadata=self.kb_catalog,
                default_kb_id=self.default_kb_id
            )

            logger.info(
                f"[KB ROUTER] selected_kb_ids={decision.selected_kb_ids} | "
                f"fallback={decision.fallback_to_default} | "
                f"reason={decision.reason}"
            )

            valid_kb_ids = {kb["kb_id"] for kb in self.kb_catalog}
            kb_ids_to_search = [
                kb_id for kb_id in decision.selected_kb_ids if kb_id in valid_kb_ids
            ]

            # ---- FINAL KB SELECTION LOGIC ----
            if decision.fallback_to_default or not kb_ids_to_search:
                # ✅ Always fall back to ALL kbs rather than none
                kb_ids_to_search = [kb["kb_id"] for kb in self.kb_catalog]
                logger.info(f"Router fallback — searching all {len(kb_ids_to_search)} KBs")

        STRICT_THRESHOLD = 0.25
        top_score = 0
        all_context_chunks = []

        logger.info(f"[KB SEARCH] Starting KB search | kb_ids_to_search={kb_ids_to_search} | rewritten_query='{search_query}'")

        # ---------- SEARCH SELECTED KBS ----------
        for kb in self.kb_catalog:
            if kb["kb_id"] not in kb_ids_to_search:
                continue

            kb_id = kb["kb_id"]
            collection_name = kb["collection_name"]
            logger.info(f"[KB SEARCH] Processing KB {kb_id} | collection={collection_name}")

            self.collection_name = collection_name
            self.kb_summary = kb.get("summary")
            search_results = None

            try:
                logger.debug(f"[KB SEARCH] Creating embeddings for KB {kb_id} | query='{search_query}'")
                embedding_response = self.openai_client.embeddings.create(
                    model="text-embedding-3-large",  # Must match the model used when indexing KBs
                    input=search_query,
                )
                query_vector = embedding_response.data[0].embedding
                logger.debug(f"[KB SEARCH] Query vector created for KB {kb_id} | vector_dim={len(query_vector)}")
           
                logger.debug(f"[KB SEARCH] Querying Qdrant for KB {kb_id} | collection={collection_name} | limit=12")
                search_results = self.qdrant_client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    limit=12,
                    with_payload=True,
                )
                
                logger.info(f"[KB SEARCH] Qdrant raw results for KB {kb_id} | total_hits={len(search_results.points) if search_results and search_results.points else 0}")
                
                # Log all raw results with scores
                if search_results and search_results.points:
                    for idx, hit in enumerate(search_results.points):
                        logger.debug(f"[KB SEARCH] Hit[{idx}] KB {kb_id} | score={hit.score:.4f} | payload_keys={list(hit.payload.keys()) if hit.payload else 'None'}")
                        if hit.payload:
                            chunk_preview = (hit.payload.get("chunk_text") or hit.payload.get("text") or "[empty]")[:100]
                            logger.debug(f"[KB SEARCH] Hit[{idx}] Preview: {chunk_preview}...")
                
                collected_from_kb = 0
                for hit in search_results.points:
                    top_score = max(top_score, hit.score)
                    if hit.score < 0.3:
                        logger.debug(f"[KB SEARCH] Filtering out KB {kb_id} hit | score={hit.score:.4f} below threshold 0.3")
                        continue
                    payload = hit.payload or {}
                    text = (
                        payload.get("chunk_text")
                        or payload.get("text")
                        or ""
                    )
                    if text.strip():
                        text_l = text.lower()
                        source_url = str(payload.get("source_url", "")).lower()
                        token_hits_text = sum(1 for t in key_tokens if t in text_l) if key_tokens else 0
                        token_hits_url = sum(1 for t in key_tokens if t in source_url) if key_tokens else 0
                        token_hits = token_hits_text + token_hits_url
                        # For entity-heavy queries, require at least one entity token hit.
                        if key_tokens and token_hits == 0:
                            logger.debug(f"[KB SEARCH] Skipping chunk without key token match | score={hit.score:.4f}")
                            continue
                        all_context_chunks.append(text.strip())
                        collected_from_kb += 1
                        logger.debug(
                            f"[KB SEARCH] Collected chunk from KB {kb_id} | score={hit.score:.4f} | token_hits_text={token_hits_text} | token_hits_url={token_hits_url} | chunk_len={len(text.strip())}"
                        )
                
                logger.info(f"[KB SEARCH] KB {kb_id} collection complete | chunks_collected={collected_from_kb} | top_score={top_score:.4f}")
                

            except Exception as e:
                logger.error(f"[KB SEARCH] KB search failed for KB {kb_id} | error={e}", exc_info=True)
        
        # ---- DEDUPLICATE CONTEXT CHUNKS (ORDER PRESERVED) ----
        logger.info(f"[KB SEARCH] Before dedup | total_chunks={len(all_context_chunks)}")
        all_context_chunks = list(dict.fromkeys(all_context_chunks))
        logger.info(f"[KB SEARCH] After dedup | final_chunks={len(all_context_chunks)} | top_score={top_score:.4f}")

        if len(all_context_chunks) == 0:
            logger.warning(f"[KB SEARCH] No chunks collected after filtering | top_score={top_score:.4f}")
            return {
                "agent_output": "I don't have enough chunks in the configured knowledge base to answer that question."
            }
        
        # STEP: STRICT KB GATE
        if top_score < STRICT_THRESHOLD:
            logger.info(f"[KB STRICT] Top score {top_score:.4f} below threshold {STRICT_THRESHOLD}")
            return {
                "agent_output": "I don't have enough info in the configured knowledge base to answer that question."
            }



        # ---------- ANSWER GENERATION ----------
        context = "\n\n---\n\n".join(all_context_chunks)
        logger.info(f"[KB ANSWER] Generating answer | context_chunks={len(all_context_chunks)} | total_context_len={len(context)} | mode={self.mode}")

        # ✅ ADD THIS
        instructions_block = build_instructions_context(self.bot_instructions)

        prompt = f"""
        You are an AI assistant answering strictly based on the provided knowledge base context.

        IMPORTANT RULES:
        - Use ONLY the information available in the context.
        - Do NOT hallucinate or invent information.
        - Do NOT use any external knowledge.
        - If context only partially answers the query, provide the available answer and clearly say what is missing.
        - Combine information from multiple context chunks when needed.

        RESPONSE BEHAVIOR:
        - If the query asks for a list → return a clear, structured list.
        - If the query asks for details → provide a clear explanation.
        - If the query asks for comparison → organize response accordingly.
        - If exact answer is not present → clearly state what is known and what is missing, without boilerplate phrases.

        {instructions_block}

        Context:
        {context}

        User Query: {query}

        Answer:
        """
        # STEP 9: Select LLM based on mode
        llm_to_use = self.strict_llm if self.mode == "kb_strict" else self.llm

        response = llm_to_use.invoke([HumanMessage(content=prompt)]).content.strip()
        response = self._remove_boilerplate_prefix(response)
        logger.info(f"[KB ANSWER] Complete | response_len={len(response)} | mode={self.mode}")
        logger.debug(f"[KB ANSWER] Response preview: {response[:200]}...")

        return {"agent_output": response}
    
    def rewrite_query_for_search(self, query: str) -> str:
        prompt = f"""
    Convert this user query into a short keyword search query.

    Rules:
    - Keep only important keywords
    - Remove filler words
    - Do NOT change meaning
    - Output ONLY the keywords

    Query: {query}
    """
        response = self.rewrite_llm.invoke([HumanMessage(content=prompt)]).content.strip()
        return response

    def tools_agent(self, state: AgentState, verbose: bool = False) -> Dict[str, str]:
        """
        ReAct-based tools agent with SAFE history usage.
        """
        logger.info("Executing Tools Agent (ReAct).")
        query = state["query"]
        if self.mode == "kb_strict" and not _build_tool_map(self, exclude_kb=True):
            # No external tools available but KB is configured — answer from KB instead
            # of returning a dead-end error message to the user.
            logger.info("[Tools Agent] kb_strict mode with no external tools — delegating to KB agent")
            return self.kb_agent(state)

        try:
            agent_tools = _build_tool_map(self, exclude_kb=True)

            agent_executor = initialize_agent(
                tools=agent_tools,
                llm=self.llm,
                agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
                verbose=verbose,
                handle_parsing_errors=True,
                max_iterations=5,
            )

            # --- SAFE HISTORY COMPRESSION ---
            recent_context = []
            for turn in self.chat_memory[-5:]:
                if turn.get("query") and turn.get("response"):
                    recent_context.append(f"- User asked about: {turn['query']}")

            context_block = "\n".join(recent_context)

            prompt = f"""
                You are an execution agent.

                Context from earlier conversation (for reference only):
                {context_block}

                Current user query:
                "{query}"

                Instructions:
                - Decide if a tool is required.
                - For maps/location/travel/near/nearby/distance/route questions, you MUST use map tools (find_nearby_facilities or calculate_commute_time) when available.
                - For distance/commute queries, prefer calculate_commute_time.
                - If the user says "my location" and origin is missing, ask a short follow-up for origin location; do NOT answer from KB fallback text.
                - If a tool is required, select the correct tool and provide valid input.
                - If information is missing, ask the user.
                - If no tool is needed, answer directly.
                - Be concise and factual.
                """

            result = agent_executor.invoke({"input": prompt})

            final_response = result.get("output")

            # --- HARD SAFETY FALLBACK ---
            if not final_response or "Action:" in final_response:
                logger.warning("ReAct incomplete. Falling back to direct LLM answer.")
                final_response = self.llm.invoke(
                    [HumanMessage(content=query)]
                ).content.strip()

            return {"agent_output": final_response}

        except Exception as e:
            logger.exception(f"Tools Agent error: {e}")
            return {"agent_output": "Sorry, I couldn't complete that action."}

    
    def summarization_agent(self, state: AgentState) -> Dict[str, str]:
            logger.info("Executing Summarization Agent.")
            agent_output = state["agent_output"]
            
            # STEP 7: DO NOT MODIFY KB ANSWER
            if self.mode == "kb_strict":
                logger.info("[Summarization] Skipped in strict mode")
                return {"final_response": agent_output}
            if state.get("next_agent") == "greeting":
                logger.info("[Summarization] Skipped for greeting response")
                return {"final_response": agent_output}
            query = state["query"]

            if not self.llm:
                return {"final_response": "Sorry, the summarization service is unavailable."}

            # ✅ ADD THIS
            instructions_block = build_instructions_context(self.bot_instructions)

            prompt = f"""
            You are a {self.bot_details.get('industry')} assistant named {self.bot_details.get('name')},
            with a {self.bot_details.get('tone', 'professional')} tone.

            {instructions_block}

            User Query: "{query}"
            Agent Response: "{agent_output}"

            Your task:
            - Preserve ALL information — never cut or shorten a detailed answer
            - If the answer is simple, keep it short (1-2 sentences)
            - If the answer is detailed or has multiple points, respond with full detail
            - Use bullet points if the answer has multiple items
            - Improve clarity and readability
            - Do NOT prefix with "Based on info", "Based on available information", or similar unless the agent response explicitly says data is incomplete.
            - DO NOT always end with "Is there anything else..." — only ask a follow-up if it genuinely makes sense
            - DO NOT add a word limit — respond based on what the answer requires
            - Sound natural and conversational, not robotic or templated
            """

            try:
                final_response = self.llm.invoke([HumanMessage(content=prompt)]).content.strip()
                final_response = self._remove_boilerplate_prefix(final_response)
                return {"final_response": final_response}
            except Exception as e:
                logger.error(f"Summarization agent error: {e}")
                return {"final_response": agent_output}

    @staticmethod
    def _remove_boilerplate_prefix(text: str) -> str:
            """Removes repetitive boilerplate openings from model outputs."""
            if not text:
                return text
            cleaned = text.strip()
            patterns = [
                r"^\s*based on (the )?(available )?information[:,]?\s*",
                r"^\s*from (the )?(available )?information[:,]?\s*",
                r"^\s*according to (the )?(available )?information[:,]?\s*",
            ]
            for pattern in patterns:
                cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
            return cleaned.strip()
    
    
    def ask(self, query: str, save_history: bool = True) -> str:
        """Main entry point to process a user query using the LangGraph workflow."""
        logger.info(
            "[ASK START] bot_id=%s tenant_id=%s session_id=%s query=%s maps_enabled=%s nearby_ready=%s commute_ready=%s",
            self.bot_id,
            self.tenant_id,
            self.session_id,
            query,
            "maps" in self.enabled_tools,
            bool(getattr(self, "nearby_facilities_tool", None)),
            bool(getattr(self, "commute_time_tool", None)),
        )
        initial_state = {
            "query": query,
            "chat_memory": self.chat_memory # Pass current chat memory to the state
        }

        # The graph executor runs the entire workflow from decision to summarization
        try:
            final_state = self.graph_executor.invoke(initial_state)
            
            final_response = (
                final_state.get("final_response")
                or final_state.get("agent_output")
                or "Sorry, I couldn't generate a response."
            )

            logger.info(f"[Final State Dump] {json.dumps(final_state, indent=2, default=str)}")
            logger.info(f"[Returned to UI] {final_response}")
            logger.info(
                "[ASK END] bot_id=%s session_id=%s next_agent=%s response_len=%s",
                self.bot_id,
                self.session_id,
                final_state.get("next_agent"),
                len(final_response) if final_response else 0,
            )

            if save_history:
                self.save_chat_history(query, final_response)

            return final_response
        except Exception as e:
            logger.exception(f"Error during LangGraph execution for query '{query}': {e}")
            return "An unexpected error occurred while processing your request."

  
def _build_tool_map(mas: MultiAgentSystem, exclude_kb: bool = False) -> List[LangchainTool]:
    """
    Builds a list of LangChain-compatible tools.
    Now respects the enabled_tools set from core_features (zero regression.
    """
    
    # --- All your original wrappers remain 100% unchanged ---
    def tool_query_knowledge_base(query: str) -> str:
        logger.info(f"Tool: query_knowledge_base called with query: {query}")
        if not mas.collection_name:
            return "Error: Knowledge base not configured."
        try:
            return mas.kb_agent({"query": query}).get("agent_output", "Error: KB agent returned no output.")
        except Exception as e:
            logger.error(f"Error in tool_query_knowledge_base: {e}")
            return f"Error querying knowledge base: {e}"

    def tool_create_lead(details_json: str) -> str:
        logger.info(f"Tool: create_lead called with input: {details_json}")
        try:
            details = json.loads(details_json)
            required = ['full_name', 'email', 'phone']
            if not all(k in details for k in required):
                missing = [k for k in required if k not in details]
                return f"Error: Missing required information. You must provide {', '.join(missing)}."

            tenant_id = mas.tenant_id
            bot_id = mas.bot_id
            if not tenant_id or not bot_id:
                return "Error: Tenant ID or Bot ID not available for lead creation."

            session = next(db_session())
            try:
                lead = Lead(
                    tenant_id=tenant_id,
                    bot_id=bot_id,
                    full_name=details['full_name'],
                    email=details['email'],
                    phone=details['phone'],
                    created_at=datetime.now()
                )
                session.add(lead)
                session.commit()
                return f"Successfully created a lead for {details['full_name']} with email {details['email']} and phone {details['phone']}."
            except Exception as db_err:
                session.rollback()
                logger.error(f"Database error in tool_create_lead: {db_err}")
                return f"Database error: {db_err}"
            finally:
                session.close()
        except json.JSONDecodeError:
            return "Error: Invalid JSON format for lead details. Please provide a valid JSON string."
        except Exception as e:
            logger.error(f"Unexpected error in tool_create_lead: {e}")
            return f"An unexpected error occurred: {e}"

    def safe_book_appointment_tool(json_string: str) -> str:
        logger.info(f"Tool: book_appointment called with input: {json_string}")
        try:
            details = json.loads(json_string)
            required = ["title", "start_time_str"]
            missing = [k for k in required if k not in details or not details[k]]
            if missing:
                return f"Missing required information: {', '.join(missing)}. Please provide these details."

            appointment_result = mas.calendar_tool.book_appointment(
                title=details["title"],
                start_time_str=details["start_time_str"],
                duration=details.get("duration", 1.0),
                attendees=details.get("attendees", []),
                location=details.get("location", "Google Meet"),
                description=details.get("description", ""),
                time_zone=details.get("time_zone", "Asia/Kolkata")
            )

            if "error" in appointment_result:
                return f"Failed to book appointment: {appointment_result['error']}"

            attendees = details.get("attendees", [])
            if attendees and mas.gmail_tool:
                try:
                    start_dt = datetime.fromisoformat(details["start_time_str"].replace("Z", "+00:00"))
                    ist_tz = ZoneInfo("Asia/Kolkata")
                    start_dt_ist = start_dt.astimezone(ist_tz)
                    formatted_time = start_dt_ist.strftime("%A, %B %d, %Y at %I:%M %p IST")

                    email_body = (
                        f"Dear Attendee(s),\n\n"
                        f"This is to confirm your meeting: '{details['title']}'.\n\n"
                        f"Details:\n"
                        f"- Date and Time: {formatted_time}\n"
                        f"- Location: {details.get('location', 'Google Meet')}\n"
                        f"- Description: {details.get('description', '')}\n"
                        f"- Duration: {details.get('duration', 1.0)} hour(s)\n\n"
                        f"Please find the calendar invite in your Google Calendar or email.\n\n"
                        f"Best regards,\n[Your Name]"
                    )

                    email_result = mas.gmail_tool.send_email(
                        to=attendees,
                        subject=f"Meeting Confirmation: {details['title']}",
                        body=email_body,
                        html=False
                    )

                    if "error" in email_result:
                        logger.warning(f"Failed to send confirmation email: {email_result['error']}")
                        return (
                            f"Appointment booked successfully: {appointment_result}\n"
                            f"Warning: Failed to send confirmation email: {email_result['error']}"
                        )
                    else:
                        return (
                            f"Appointment booked successfully: {appointment_result}\n"
                            f"Confirmation email sent successfully: {email_result}"
                        )
                except Exception as e:
                    logger.error(f"Error sending confirmation email: {e}")
                    return (
                        f"Appointment booked successfully: {appointment_result}\n"
                        f"Warning: Failed to send confirmation email: {e}"
                    )
            else:
                if not attendees:
                    logger.info("No attendees provided, skipping email.")
                elif not mas.gmail_tool:
                    logger.warning("GmailTool not initialized, skipping email.")
                return f"Appointment booked successfully: {appointment_result}"

        except json.JSONDecodeError:
            return "Invalid JSON format. Please provide appointment details as valid JSON."
        except Exception as e:
            logger.error(f"Error in safe_book_appointment_tool: {e}")
            return f"Error while booking appointment: {e}"

    def tool_send_email(json_string: str) -> str:
        logger.info(f"Tool: send_email called with input: {json_string}")
        try:
            email_data = json.loads(json_string)
            required_fields = ['to', 'subject', 'body']
            if not all(field in email_data for field in required_fields):
                missing = [field for field in required_fields if field not in email_data]
                return f"Error: Missing required email fields: {', '.join(missing)}."

            return mas.gmail_tool.send_email(
                to=email_data['to'],
                subject=email_data['subject'],
                body=email_data['body']
            )
        except json.JSONDecodeError:
            return "Error: Invalid JSON format for email details. Please provide a valid JSON string."
        except Exception as e:
            logger.error(f"Error in tool_send_email: {e}")
            return f"An error occurred while sending the email: {e}"

    def tool_create_hubspot_contact(json_string: str) -> str:
        logger.info(f"Tool: create_hubspot_contact called with input: {json_string}")
        if not mas.hubspot_tool:
            return "Error: HubSpot tool is not initialized. Access token might be missing."
        try:
            contact_properties = json.loads(json_string)
            if 'email' not in contact_properties:
                return "Error: Missing required HubSpot contact field: email. Please provide it."
            return mas.hubspot_tool.create_contact(**contact_properties)
        except json.JSONDecodeError:
            return "Error: Invalid JSON format for HubSpot contact details."
        except Exception as e:
            logger.error(f"Error in tool_create_hubspot_contact: {e}")
            return f"An error occurred while creating the HubSpot contact: {e}"

    def tool_get_rental_income(json_string: str) -> str:
        logger.info(f"Tool: get_rental_income called with input: {json_string}")
        if not mas.rental_income_tool:
            return "Error: Rental income tool is not initialized. TAVILY_API_KEY might be missing."
        try:
            params = json.loads(json_string)
            location = params.get('location')
            property_type = params.get('property_type')
            if not location or not property_type:
                return "Error: Missing 'location' or 'property_type' in JSON input for rental income."
            return mas.rental_income_tool.process(location=location, property_type=property_type)
        except json.JSONDecodeError:
            return "Error: Invalid JSON format for rental income details."
        except Exception as e:
            logger.error(f"Error in tool_get_rental_income: {e}")
            return f"An error occurred while estimating rental income: {e}"

    def tool_find_nearby_facilities(json_string: str) -> str:
        logger.info(f"Tool: find_nearby_facilities called with input: {json_string}")
        if not mas.nearby_facilities_tool:
            return "Error: Nearby facilities tool is not initialized. GOOGLE_MAPS_API_KEY might be missing."
        try:
            params = json.loads(json_string)
            location = params.get('location')
            facility_type = params.get('facility_type')
            if not location or not facility_type:
                return "Error: Missing 'location' or 'facility_type' in JSON input for nearby facilities."
            results = mas.nearby_facilities_tool.process(location=location, facility_type=facility_type)
            if isinstance(results, dict) and results.get("error"):
                return f"Error finding nearby {facility_type}: {results.get('error')}"
            if not isinstance(results, list) or not results:
                return f"No nearby {facility_type} found near {location}."

            top = results[:5]
            lines = []
            for idx, place in enumerate(top, start=1):
                name = place.get("name") or "Unknown"
                address = place.get("address") or place.get("vicinity") or "Address unavailable"
                rating = place.get("rating")
                ratings_total = place.get("user_ratings_total")
                if rating is not None and ratings_total is not None:
                    lines.append(f"{idx}. {name} - {address} (Rating: {rating}/5 from {ratings_total} reviews)")
                elif rating is not None:
                    lines.append(f"{idx}. {name} - {address} (Rating: {rating}/5)")
                else:
                    lines.append(f"{idx}. {name} - {address}")

            return f"Top nearby {facility_type} near {location}:\n" + "\n".join(lines)
        except json.JSONDecodeError:
            return "Error: Invalid JSON format for nearby facilities details."
        except Exception as e:
            logger.error(f"Error in tool_find_nearby_facilities: {e}")
            return f"An error occurred while finding nearby facilities: {e}"

    def tool_calculate_commute_time(json_string: str) -> str:
        logger.info(f"Tool: calculate_commute_time called with input: {json_string}")
        if not mas.commute_time_tool:
            return "Error: Commute time tool is not initialized. Google Maps tools are not available."
        try:
            params = json.loads(json_string)
            origin = params.get('origin')
            destination = params.get('destination')
            future_date = params.get('future_date', (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))

            # Natural-language fallback parsing when agent sends raw query-style input.
            if not origin or not destination:
                raw_query = str(
                    params.get("query")
                    or params.get("text")
                    or params.get("message")
                    or json_string
                )
                q = " ".join(raw_query.strip().split())

                # Example: "distance from my location nashik to mumbai office of tata realty"
                m = re.search(
                    r"(?:from\s+)?(?:my\s+location\s+)?(?P<origin>.+?)\s+to\s+(?P<destination>.+)$",
                    q,
                    re.IGNORECASE
                )
                if m:
                    guessed_origin = m.group("origin").strip(" ,.")
                    guessed_destination = m.group("destination").strip(" ,.")
                    if not origin and guessed_origin:
                        origin = guessed_origin
                    if not destination and guessed_destination:
                        destination = guessed_destination

            if not origin or not destination:
                return "Please share both origin and destination (for example: origin='Nashik', destination='Mumbai office of Tata Realty')."
            result = mas.commute_time_tool.process(
                origin=origin,
                destination=destination,
                future_date_str=future_date
            )
            if isinstance(result, dict):
                return result.get("message") or result.get("error") or json.dumps(result)
            return str(result)
        except json.JSONDecodeError:
            return "Error: Invalid JSON. Expected: {\"origin\": \"A\", \"destination\": \"B\", \"future_date\": \"YYYY-MM-DD\"}"
        except Exception as e:
            logger.error(f"Commute tool error: {e}")
            return f"Error calculating commute time: {e}"

    # --- Tool Registration: Now Respects enabled_tools ---
    tool_definitions = []

    def log_wrapper(func, name):
        def wrapped(*args, **kwargs):
            logger.info(f"Tool '{name}' called with args={args}, kwargs={kwargs}")
            return func(*args, **kwargs)
        return wrapped

    # KB Tool (always available unless excluded)
    if not exclude_kb:
        tool_definitions.append(LangchainTool.from_function(
            func=log_wrapper(tool_query_knowledge_base, "query_knowledge_base"),
            name="query_knowledge_base",
            description="Use this tool to answer questions about specific properties, company information, internal policies, or any data stored in the knowledge base. Input should be the user's question string."
        ))

    # Rental Income — Tavily
    if "tavily" in mas.enabled_tools and mas.rental_income_tool:
        tool_definitions.append(LangchainTool.from_function(
            func=log_wrapper(tool_get_rental_income, "get_rental_income"),
            name="get_rental_income",
            description="Estimates potential rental income for a property. Input must be a JSON string with 'location' and 'property_type'."
        ))

    # Nearby Facilities — Google Maps
    if "maps" in mas.enabled_tools and mas.nearby_facilities_tool:
        tool_definitions.append(LangchainTool.from_function(
            func=log_wrapper(tool_find_nearby_facilities, "find_nearby_facilities"),
            name="find_nearby_facilities",
            description="Finds nearby facilities like schools, hospitals, or restaurants. Input must be JSON with 'location' and 'facility_type'."
        ))

    # Commute Time — Google Maps
    if "maps" in mas.enabled_tools and mas.commute_time_tool:
        tool_definitions.append(LangchainTool.from_function(
            func=log_wrapper(tool_calculate_commute_time, "calculate_commute_time"),
            name="calculate_commute_time",
            description="Calculates estimated commute time between two locations. Input must be JSON with 'origin' and 'destination'."
        ))

    # Create Lead — always allowed (internal)
    tool_definitions.append(LangchainTool.from_function(
        func=log_wrapper(tool_create_lead, "create_lead"),
        name="create_lead",
        description="ONLY use this when the user explicitly asks to add a new sales lead. Required: full_name, email, phone."
    ))

    # Book Calendar Appointment — Google Calendar
    if "calendar" in mas.enabled_tools and mas.calendar_tool:
        tool_definitions.append(LangchainTool.from_function(
            func=log_wrapper(safe_book_appointment_tool, "book_calendar_appointment"),
            name="book_calendar_appointment",
            description="Use this to book an appointment. Input MUST be valid JSON with 'title' and 'start_time_str'."
        ))

    # Send Email — Gmail
    if "gmail" in mas.enabled_tools and mas.gmail_tool:
        tool_definitions.append(LangchainTool.from_function(
            func=log_wrapper(tool_send_email, "send_email"),
            name="send_email",
            description="Sends an email. Input must be JSON with 'to', 'subject', and 'body'."
        ))

    # HubSpot Contact
    if "hubspot" in mas.enabled_tools and mas.hubspot_tool:
        tool_definitions.append(LangchainTool.from_function(
            func=log_wrapper(tool_create_hubspot_contact, "create_hubspot_contact"),
            name="create_hubspot_contact",
            description="ONLY use this when explicitly asked to add or update a contact in HubSpot CRM."
        ))

    logger.info(f"Registered {len(tool_definitions)} tools for bot {mas.bot_id}: {[t.name for t in tool_definitions]}")

    return tool_definitions

def get_gmail_service():
    """
    Get Gmail API service. Automatically refresh or recreate token if expired.
    Returns:
        service: Gmail API service instance
    """
    try:
        creds = None

        # Step 1: Load existing token
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            logger.info("✅ Loaded existing Gmail token.")

        if creds and creds.expired:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning("Refresh failed, creating new token...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRET_FILE, SCOPES
                )
                creds = flow.run_local_server(port=5000)

            # Step 3: Save new or refreshed token
            with open(TOKEN_FILE, "w") as token_file:
                token_file.write(creds.to_json())
                logger.info("✅ Gmail token saved/updated successfully.")

        # Step 4: Build service
        service = build("gmail", "v1", credentials=creds)
        return service

    except Exception as e:
        logger.error(f"Failed to initialize Gmail service: {e}")
        raise



# ------------------------- KB Router ------------------------------

class KBRouteDecision(BaseModel):
    selected_kb_ids: List[int] = Field(default_factory=list)
    fallback_to_default: bool
    reason: str


ROUTER_SYSTEM_PROMPT = """
You are a routing component inside a multi-agent system.

Your task is to decide which knowledge base(s) should be searched
to answer the user query.

You must NOT answer the user.
You must NOT invent information.
You must ONLY select from the provided knowledge bases.

If none of the knowledge bases clearly match the query,
indicate fallback to the default knowledge base.
"""


def route_knowledge_bases(
    llm,
    query: str,
    kb_metadata: List[dict],
    default_kb_id: int
) -> KBRouteDecision:
    """
    LLM-based KB router.
    This function ONLY decides which KBs to search.
    """
    logger.info(f"[KB ROUTER] START | query='{query}' | kb_metadata_count={len(kb_metadata) if kb_metadata else 0} | default_kb_id={default_kb_id}")

    if not kb_metadata:
        logger.warning("[KB ROUTER] No KB metadata provided")
        return KBRouteDecision(
            selected_kb_ids=[],
            fallback_to_default=True,
            reason="No knowledge bases available."
        )

    # Log KB metadata details
    for idx, kb in enumerate(kb_metadata):
        logger.debug(f"[KB ROUTER] KB[{idx}] | id={kb.get('kb_id')} | collection={kb.get('collection_name')} | summary_len={len(kb.get('summary', '')) if kb.get('summary') else 0}")

    kb_list_text = "\n".join([
        f"KB ID: {kb['kb_id']}\nSummary: {kb.get('summary') or 'No summary provided.'}"
        for kb in kb_metadata
    ])

    user_prompt = f"""
User Query:
"{query}"

Available Knowledge Bases:
{kb_list_text}

Rules:
- Use only the summaries to decide.
- Select the most relevant knowledge base(s).
- If multiple are relevant, include all.
- If none are relevant, return an empty list and fallback_to_default=true.
- Do NOT guess or invent.
- Respond ONLY in structured JSON format.
"""

    structured_llm = llm.with_structured_output(KBRouteDecision)

    logger.debug(f"[KB ROUTER] Invoking LLM to route query")
    decision = structured_llm.invoke([
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])

    logger.info(f"[KB ROUTER] LLM Decision | selected_ids={decision.selected_kb_ids} | fallback={decision.fallback_to_default} | reason={decision.reason}")

    # Safety fallback
    if not decision.selected_kb_ids and not decision.fallback_to_default:
        logger.warning("[KB ROUTER] No KB selected and no fallback; enforcing fallback")
        decision.fallback_to_default = True
        decision.reason = "No KB selected; enforced fallback."

    logger.info(f"[KB ROUTER] FINAL | selected_ids={decision.selected_kb_ids} | fallback={decision.fallback_to_default}")
    return decision


# -----------------------------------------------------------------------------

def build_instructions_context(instructions: list) -> str:
    """
    Formats bot instructions for LLM prompts.
    Safe, optional, no side effects.
    """
    if not instructions:
        return ""

    formatted = "\n".join(f"- {instr}" for instr in instructions)

    return f"""
IMPORTANT GUIDELINES (apply when relevant):
{formatted}
"""
  
