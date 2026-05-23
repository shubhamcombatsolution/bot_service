# # app/utils/tool_utils.py
from logging_config import setup_logging
from sqlalchemy.exc import SQLAlchemyError
from app.database.DatabaseOperationPostgreSQL import db_session  # Adjust import as needed
from app.models.new_models.custom_bot import CustomBotNew  
import json
import os
from langchain_community.chat_models import ChatOpenAI
from langchain.schema import HumanMessage


logger = setup_logging("multi_agent_system_utils","DEBUG")



TOOL_FEATURE_MAPPING = {
    "Gmail": "gmail",          
    "Google Calendar": "calendar",   
    "Google Maps": "maps",           
    "Tavily": "tavily",         
    "HubSpot": "hubspot",
    "GSheets": "gsheets",
}


# Normalize feature labels from UI/integrations to internal tool keys.
_TOOL_FEATURE_ALIASES = {
    "gmail": "gmail",
    "google gmail": "gmail",
    "calendar": "calendar",
    "google calendar": "calendar",
    "gcalendar": "calendar",
    "googlecalendar": "calendar",
    "maps": "maps",
    "google maps": "maps",
    "gmaps": "maps",
    "hubspot": "hubspot",
    "hub spot": "hubspot",
    "tavily": "tavily",
    "gsheets": "gsheets",
    "google sheets": "gsheets",
    "sheets": "gsheets",
}

def _resolve_tool_key(feature_key):
    if feature_key is None:
        return None
    raw = str(feature_key).strip()
    if not raw:
        return None
    # Exact legacy mapping first
    mapped = TOOL_FEATURE_MAPPING.get(raw)
    if mapped:
        return mapped
    # Alias/case-insensitive fallback
    norm = " ".join(raw.lower().replace("_", " ").replace("-", " ").split())
    return _TOOL_FEATURE_ALIASES.get(norm)

def get_enabled_tools_from_features(
    tenant_id: str,
    bot_id: str,
    core_features: list = None  # ✅ NEW: injected from snapshot, skips DB entirely
) -> set:
    """
    If core_features is injected (from config snapshot), use it directly.
    Otherwise fall back to DB lookup (legacy path).
    """

    # ✅ FAST PATH: use injected core_features from resolve_bot_config snapshot
    if core_features is not None:
        return _parse_core_features_to_tools(core_features, bot_id)

    # ✅ LEGACY PATH: query DB (only used if called without injection)
    enabled_tools = set()
    try:
        session = next(db_session())
        try:
            # ✅ Query CustomBotNew instead of old CustomBot
            from app.models import CustomBotNew
            custom_bot = session.query(CustomBotNew).filter_by(
                bot_id=bot_id,
                tenant_id=tenant_id,
                del_flg=False
            ).first()

            if not custom_bot:
                logger.warning(
                    f"No bot found for tenant_id={tenant_id}, bot_id={bot_id}. "
                    f"Defaulting to all tools."
                )
                return set(TOOL_FEATURE_MAPPING.values())

            raw_core_features = custom_bot.core_features
            return _parse_core_features_to_tools(raw_core_features, bot_id)

        except SQLAlchemyError as db_err:
            logger.error(f"DB error querying core_features for bot_id={bot_id}: {db_err}")
            return set(TOOL_FEATURE_MAPPING.values())

        finally:
            session.close()

    except Exception as e:
        logger.exception(f"Unexpected error in get_enabled_tools_from_features for bot_id={bot_id}: {e}")
        return set(TOOL_FEATURE_MAPPING.values())


def _parse_core_features_to_tools(raw_core_features, bot_id: str) -> set:
    """
    Shared parsing logic for both injected and DB-loaded core_features.
    Handles dict (old format) and list (new format).
    """
    enabled_tools = set()

    # Handle JSON string
    if isinstance(raw_core_features, str):
        try:
            raw_core_features = json.loads(raw_core_features)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in core_features for bot_id={bot_id}: {e}")
            return set(TOOL_FEATURE_MAPPING.values())

    if not raw_core_features:
        logger.warning(f"Empty core_features for bot_id={bot_id}. Defaulting to all tools.")
        return set(TOOL_FEATURE_MAPPING.values())

    # ✅ Handle DICT format: {"Gmail": [...], "Google Calendar": [...]}
    if isinstance(raw_core_features, dict):
        for feature_key, feature_list in raw_core_features.items():
            if feature_list:
                internal_tool = _resolve_tool_key(feature_key)
                if internal_tool:
                    enabled_tools.add(internal_tool)
                else:
                    logger.warning(f"Unmapped feature key '{feature_key}' for bot_id={bot_id}.")

    # ✅ Handle LIST format: ["Gmail", "Google Calendar"]
    elif isinstance(raw_core_features, list):
        for feature_key in raw_core_features:
            internal_tool = _resolve_tool_key(feature_key)
            if internal_tool:
                enabled_tools.add(internal_tool)
            else:
                logger.warning(f"Unmapped feature key '{feature_key}' for bot_id={bot_id}.")

    else:
        logger.warning(f"Unexpected core_features type {type(raw_core_features)} for bot_id={bot_id}.")
        return set(TOOL_FEATURE_MAPPING.values())

    if not enabled_tools:
        logger.warning(f"No enabled tools parsed for bot_id={bot_id}. Defaulting to all.")
        return set(TOOL_FEATURE_MAPPING.values())

    # Product requirement: keep maps available by default for all bots/users.
    if "maps" not in enabled_tools:
        enabled_tools.add("maps")
        logger.info(f"Enabled maps by default for bot_id={bot_id}.")

    logger.info(f"Enabled tools for bot_id={bot_id}: {enabled_tools}")
    return enabled_tools


import random
from tiktoken import encoding_for_model
from langchain_community.chat_models import ChatOpenAI
from langchain.schema import HumanMessage
from openai import OpenAI

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo") 

def estimate_tokens(text: str, model: str = MODEL_NAME) -> int:
    encoder = encoding_for_model(model)
    return len(encoder.encode(text))


def generate_kb_summary_from_chunks(kb_name: str, qdrant_client, limit: int = 20) -> str:
    """
    Generate a KB summary using Qdrant content + OpenAI summarization.
    Tokens are controlled using sampling + hard token guard.
    No LangChain-Qdrant wrapper and no dependency on 'self'.
    """

    logger.info(f"[KB SUMMARY] Start → '{kb_name}'")

    # ---- Validate inputs ----
    if not qdrant_client:
        logger.error("[KB SUMMARY] Qdrant client is missing.")
        return ""

    # ---- Initialize OpenAI (local but reused) ----
    try:
        openai_client = OpenAI()  # uses existing OPENAI_API_KEY env var
    except Exception as e:
        logger.error(f"[KB SUMMARY] Failed to initialize OpenAI: {e}")
        return ""

    # ---- Step 1: Create base embedding for search ----
    try:
        emb = openai_client.embeddings.create(
            model="text-embedding-ada-002",
            input="overview of content"
        )
        query_vector = emb.data[0].embedding
    except Exception as e:
        logger.error(f"[KB SUMMARY] Embedding generation failed: {e}")
        return ""

    # ---- Step 2: Query Qdrant ----
    try:
        search_results = qdrant_client.search(
            collection_name=kb_name,
            query_vector=query_vector,
            limit=40,  # Fetch more → sample later
            with_payload=True
        )
    except Exception as e:
        logger.error(f"[KB SUMMARY] Qdrant search error: {e}")
        return ""

    if not search_results:
        logger.warning("[KB SUMMARY] No KB entries found.")
        return ""

    # ---- Step 3: Extract text ----
    chunks = []
    for r in search_results:
        text = (
            (r.payload.get("chunk_text") or r.payload.get("text") or "").strip()
        )
        if text:
            chunks.append(text)

    if not chunks:
        logger.warning("[KB SUMMARY] No readable text chunks found.")
        return ""

    # ---- Step 4: Random Sampling (avoid token explosion) ----
    random.shuffle(chunks)
    selected_chunks = chunks[:limit]

    combined_text = "\n\n---\n\n".join(selected_chunks)

    # ---- Step 5: Token Guard ----
    MAX_TOKENS = 3500
    if estimate_tokens(combined_text) > MAX_TOKENS:
        logger.warning("[KB SUMMARY] Exceeded token budget — trimming text.")
        combined_text = " ".join(combined_text.split()[:1500])  # extra safety

    # ---- Step 6: Summarize ----
    llm = ChatOpenAI(model=MODEL_NAME, temperature=0.2)

    prompt = f"""
Summarize the following content into **5–7 clear sentences**:

KB Name: {kb_name}

Content:
{combined_text}

Focus on:
- What type of information the KB contains
- What kind of questions it answers
- Common rules or repeated topics
- Tone or style of content

Do NOT mention summarization, embeddings, or internal processing.
"""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        summary = response.content.strip()
        logger.info(f"[KB SUMMARY] Summary generated ({len(summary)} chars).")
        return summary

    except Exception as e:
        logger.error(f"[KB SUMMARY] OpenAI summarization failed: {e}")
        return ""








# # Define mapping from DB feature keys to internal tool names

# TOOL_FEATURE_MAPPING = {
#     "Gmail": "gmail",          
#     "Google Calendar": "calendar",   
#     "Google Maps": "maps",           
#     "Tavily": "tavily",         
#     "HubSpot": "hubspot",
#     "GSheets": "gsheets",
# }

# def get_enabled_tools_from_features(tenant_id: str, bot_id: str) -> set:
#     """
#     Queries the DB for the bot's core_features, derives enabled tools based on non-empty feature lists.
#     Returns a set of internal tool names (e.g., {"gmail", "calendar"}).
    
#     Handles exceptions gracefully, logs everything, and defaults to all tools if features are missing/empty.
#     """
#     enabled_tools = set()
#     try:
#         session = next(db_session())
#         try:
#             custom_bot = session.query(CustomBot).filter_by(
#                 bot_id=bot_id, tenant_id=tenant_id, del_flg=False
#             ).first()
            
#             if not custom_bot:
#                 logger.warning(f"No bot found for tenant_id={tenant_id}, bot_id={bot_id}. Defaulting to all tools enabled.")
#                 return set(TOOL_FEATURE_MAPPING.values())  # Enable all for backward compat
            
#             # FIX: Parse core_features as JSON if it's a string
#             raw_core_features = custom_bot.core_features
#             if isinstance(raw_core_features, str):
#                 try:
#                     core_features = json.loads(raw_core_features)
#                     logger.info(f"Parsed raw core_features string for bot_id={bot_id}: {raw_core_features[:100]}...")
#                 except json.JSONDecodeError as json_err:
#                     logger.error(f"Invalid JSON in core_features for bot_id={bot_id}: {json_err}. Treating as empty.")
#                     core_features = {}
#             else:
#                 core_features = raw_core_features or {}
            
#             logger.info(f"Loaded core_features for bot_id={bot_id}: {core_features}")
            
#             for feature_key, feature_list in core_features.items():
#                 if feature_list:  # Non-empty list means enabled
#                     internal_tool = _resolve_tool_key(feature_key)
#                     if internal_tool:
#                         enabled_tools.add(internal_tool)
#                     else:
#                         logger.warning(f"Unmapped feature key '{feature_key}' for bot_id={bot_id}. Ignoring.")
            
#             if not enabled_tools:
#                 logger.warning(f"No enabled features for bot_id={bot_id}. Defaulting to all tools for backward compatibility.")
#                 return set(TOOL_FEATURE_MAPPING.values())
            
#             logger.info(f"Enabled tools for bot_id={bot_id}: {enabled_tools}")
#             return enabled_tools
        
#         except SQLAlchemyError as db_err:
#             logger.error(f"DB error querying core_features for bot_id={bot_id}: {db_err}")
#             return set(TOOL_FEATURE_MAPPING.values())  # Fallback to all
            
#         finally:
#             session.close()
    
#     except Exception as e:
#         logger.exception(f"Unexpected error in get_enabled_tools_from_features for bot_id={bot_id}: {e}")
#         return set(TOOL_FEATURE_MAPPING.values())  # Safe fallback

    
