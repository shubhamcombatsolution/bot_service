#engine/utils.py
import os
import json
import re
import requests
from sqlalchemy.orm import joinedload
from dotenv import load_dotenv

from app.database.DatabaseOperationPostgreSQL import db_session
from app.models.mcp_agent_tools import McpAgentTools
from app.models.mcp_tools import McpTools
from app.models.agent import Agent
from app.models.llm import LLM
from app.models.basellm import BaseLLM
from app.models.embedding_model import EmbeddingModel
from app.models.system_embedding_model import SystemEmbeddingModel
from app.models.knowledge_base import KnowledgeBase
from app.models.tool_authorization import ToolAuthorization
from app.services.encryption_utils import decrypt_value
from logging_config import setup_logging


load_dotenv()

logger = setup_logging("engine_utils", level="DEBUG")

MCP_SERVICE_URL    = os.getenv("MCP_SERVICE_URL", "http://mcp-service:5006")
BB_SERVICE_URL     = os.getenv("BB_SERVICE_URL", "http://bot-builder-service:5000")
CONSTANT_ENDPOINT  = "https://mcp.jnanic.com/call_tool"
LOCAL_ENDPOINT     = f"{BB_SERVICE_URL}/local_tool/call"
CONSTANT_METHOD    = "POST"

# Tools that are always available — no OAuth / MCP record needed
UTILITY_TOOLS = {"system", "llm", "text", "file", "invoke"}

# Canonical local tool names — quick pre-filter before DB lookup
_LOCAL_TOOL_NAMES = {
    "gmail", "calendar", "gcalendar", "gsheets", "sheets", "hubspot",
}

# Tools routed through the local MCP server (not /local_tool/call, not tbl_mcp_tools)
_LOCAL_MCP_TOOLS = {"zoom"}

# Inline action definitions for local MCP tools (loaded from tools_config.json equivalent)
_LOCAL_MCP_TOOL_ACTIONS = {
    "zoom": [
        {"action": "create_meeting", "category": "Zoom", "description": "Create a new Zoom meeting and get the join URL and password.", "parameters": [{"name": "topic", "required": True}, {"name": "start_time", "required": True}, {"name": "timezone", "required": False}, {"name": "duration", "required": False}, {"name": "agenda", "required": False}]},
        {"action": "get_meetings",   "category": "Zoom", "description": "Retrieve all active Zoom meetings.", "parameters": []},
        {"action": "update_meeting", "category": "Zoom", "description": "Update an existing Zoom meeting by ID.", "parameters": [{"name": "id", "required": True}, {"name": "topic", "required": False}, {"name": "start_time", "required": False}, {"name": "duration", "required": False}, {"name": "timezone", "required": False}]},
        {"action": "delete_meeting", "category": "Zoom", "description": "Delete an existing Zoom meeting by ID.", "parameters": [{"name": "id", "required": True}]},
    ],
}


def _get_tool_type_from_agent(tool_name: str, agent_id: int, session) -> str:
    """
    Read tool_type directly from tbl_mcp_agent_tools.tool_type column.
    Returns: 'local' | 'jnanic_mcp' | 'mcp' | 'external'
    """
    try:
        row = session.query(McpAgentTools).filter(
            McpAgentTools.agent_id == agent_id,
            McpAgentTools.tool_name.ilike(tool_name),
            McpAgentTools.del_flag == False,
        ).first()
        if row and row.tool_type:
            return str(row.tool_type).strip().lower()
    except Exception as e:
        logger.warning("[TOOL_TYPE_LOOKUP] DB check failed for tool='%s': %s", tool_name, e)
    return "mcp"  # default


def _is_local_tool(tool_name: str, tenant_id: int, session, agent_id: int = None) -> bool:
    """
    Returns True if the tool should use the local Python class path (/local_tool/call).

    Priority:
    1. Read tool_type from tbl_mcp_agent_tools.tool_type (Option A — dedicated column)
    2. Fallback: check tbl_tool_authorization for tool_type='local'
    """
    norm = str(tool_name).strip().lower().replace("jnanic_mcp_", "")

    # Quick reject: only known local-capable tool names
    if norm not in _LOCAL_TOOL_NAMES:
        return False

    # ── Priority 1: Read directly from tbl_mcp_agent_tools.tool_type ──
    if agent_id:
        ttype = _get_tool_type_from_agent(tool_name, agent_id, session)
        if ttype == "local":
            logger.info(
                "[LOCAL_TOOL_CHECK] tool='%s' agent=%s → local=True (tbl_mcp_agent_tools.tool_type)",
                tool_name, agent_id,
            )
            return True
        if ttype in ("jnanic_mcp", "mcp", "external"):
            logger.info(
                "[LOCAL_TOOL_CHECK] tool='%s' agent=%s → local=False (tool_type=%s)",
                tool_name, agent_id, ttype,
            )
            return False

    # ── Priority 2: Fallback — check tbl_tool_authorization ──
    # Handles cases where agent_id not provided or tool_type not yet set
    try:
        from sqlalchemy import or_
        # Build name variants to handle mismatches like "Gcalendar" vs "Calendar"
        name_variants = list({tool_name, norm, norm.replace("g", "", 1).capitalize()})
        filters = [ToolAuthorization.tool_name.ilike(v) for v in name_variants]
        row = session.query(ToolAuthorization).filter(
            ToolAuthorization.tenant_id == tenant_id,
            ToolAuthorization.tool_type == "local",
            ToolAuthorization.del_flag == False,
            or_(*filters),
        ).first()
        if row:
            logger.info(
                "[LOCAL_TOOL_CHECK] tool='%s' tenant=%s → local=True (fallback tbl_tool_authorization id=%s)",
                tool_name, tenant_id, row.id,
            )
            return True
    except Exception as e:
        logger.warning("[LOCAL_TOOL_CHECK] Fallback DB check failed for tool='%s': %s", tool_name, e)

    return False


def _normalize_mcp_server_params(mcp_url: str, mcp_json: dict | None) -> dict:
    """Build runtime MCP server params from DB config."""
    config = mcp_json if isinstance(mcp_json, dict) else {}
    transport = str(config.get("transport") or "").strip().lower()

    # Jnanic/default MCP should run through local stdio server.
    if not transport or transport == "stdio" or "mcp.jnanic.com" in str(mcp_url or ""):
        logger.info(
            "[MCP TRANSPORT] Selected stdio | mcp_url=%s | db_transport=%s",
            mcp_url,
            transport or "missing",
        )
        return {"transport": "stdio"}

    if transport in {"http", "sse", "streamable-http"}:
        out = {
            "transport": transport,
            "url": config.get("url"),
        }
        if isinstance(config.get("headers"), dict):
            out["headers"] = config.get("headers")
        if config.get("timeout") is not None:
            out["timeout"] = config.get("timeout")
        logger.info(
            "[MCP TRANSPORT] Selected remote | transport=%s | url=%s | headers=%s | timeout=%s",
            out.get("transport"),
            out.get("url"),
            bool(out.get("headers")),
            out.get("timeout"),
        )
        return out

    # Fallback safety
    logger.warning(
        "[MCP TRANSPORT] Unsupported DB transport '%s' for mcp_url=%s. Falling back to stdio.",
        transport,
        mcp_url,
    )
    return {"transport": "stdio"}


_mcp_definitions_cache: dict | None = None


def _normalize_tool_name(name: str) -> str:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _normalize_model_id(provider: str, model_name: str) -> str:
    """
    Convert UI/display model labels to provider API model IDs.
    Keeps unknown values unchanged to avoid breaking custom/private deployments.
    """
    raw_model = (model_name or "").strip()
    if not raw_model:
        return raw_model

    provider_norm = (provider or "").strip().lower()
    label_norm = re.sub(r"\s+", " ", raw_model).strip().lower()

    if provider_norm == "openai":
        openai_aliases = {
            "gpt-4o (omni)": "gpt-4o",
            "gpt 4o (omni)": "gpt-4o",
            "gpt4o (omni)": "gpt-4o",
            "gpt-4o": "gpt-4o",
            "gpt 4o": "gpt-4o",
            "gpt-4o-mini (omni)": "gpt-4o-mini",
            "gpt 4o mini (omni)": "gpt-4o-mini",
            "gpt-4o-mini": "gpt-4o-mini",
            "gpt 4o mini": "gpt-4o-mini",
            # Realtime models are not valid for the chat-completions path used
            # by create_agent in this service. Fallback to a compatible model.
            "gpt-realtime-1.5": "gpt-4o",
            "gpt realtime 1.5": "gpt-4o",
            "gpt-realtime": "gpt-4o",
        }
        if label_norm in openai_aliases:
            return openai_aliases[label_norm]

        # Guardrail for any OpenAI realtime model variants that are not
        # supported by this chat-completions integration path.
        if "realtime" in label_norm:
            return "gpt-4o"

        # Fallback: remove parenthetical UI suffixes and normalize spaces.
        candidate = re.sub(r"\s*\([^)]*\)\s*", "", label_norm).strip()
        candidate = candidate.replace("_", "-")
        candidate = re.sub(r"\s+", "-", candidate)
        candidate = re.sub(r"-+", "-", candidate)
        if candidate.startswith("gpt-"):
            return candidate

    elif provider_norm == "anthropic":
        anthropic_aliases = {
            "claude 3.5 sonnet": "claude-3-5-sonnet-latest",
            "claude-3.5-sonnet": "claude-3-5-sonnet-latest",
            "claude 3 sonnet": "claude-3-sonnet-20240229",
            "claude-3-sonnet": "claude-3-sonnet-20240229",
            "claude 3 haiku": "claude-3-haiku-20240307",
            "claude-3-haiku": "claude-3-haiku-20240307",
            "claude 3 opus": "claude-3-opus-20240229",
            "claude-3-opus": "claude-3-opus-20240229",
        }
        if label_norm in anthropic_aliases:
            return anthropic_aliases[label_norm]

    return raw_model


def _infer_provider_from_model(model_name: str) -> str:
    """
    Best-effort provider inference from model id/label.
    Returns: "openai", "anthropic", or "" when unknown.
    """
    raw = (model_name or "").strip().lower()
    if not raw:
        return ""

    # Anthropic family
    if "claude" in raw:
        return "anthropic"

    # OpenAI families commonly used in this project
    if (
        raw.startswith(("gpt", "o1", "o3", "o4", "text-embedding"))
        or "realtime" in raw
    ):
        return "openai"

    return ""


def _infer_embedding_provider_from_model(model_name: str) -> str:
    raw = (model_name or "").strip().lower()
    if not raw:
        return ""
    if raw.startswith("text-embedding"):
        return "openai"
    return ""


def _maybe_decrypt_secret(value: str) -> str:
    if not value:
        return ""
    if not isinstance(value, str):
        return str(value)
    try:
        return decrypt_value(value)
    except Exception:
        # Value may already be plaintext.
        return value


def _get_mcp_definitions() -> dict:
    """
    Fetch all action definitions from the MCP service.
    Cached per process lifetime (restarted with container).
    Returns: {"gmail": [{"action": ..., "category": ..., "parameters": [...]}], ...}
    Supplements with tools_config.json so newly added tools (e.g. Tavily) are always
    known even when the MCP service cache is stale.
    """
    global _mcp_definitions_cache
    if _mcp_definitions_cache is not None:
        return _mcp_definitions_cache

    lookup = {}

    try:
        resp = requests.post(
            f"{MCP_SERVICE_URL}/connect_mcp",
            json={
                "mcpServers": {
                    "main-server": {
                        "command": "/usr/local/bin/python",
                        "args": ["/app/mcp_server.py"],
                        "env": {},
                        "transport": "stdio"
                    }
                }
            },
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            tools_data = data.get("tools", {})
            if isinstance(tools_data, dict):
                for category, actions in tools_data.items():
                    lookup[category.lower()] = actions
            logger.info(f"✅ MCP definitions loaded from service: {list(lookup.keys())}")
    except Exception as e:
        logger.warning(f"⚠️ Could not fetch MCP definitions from service: {e}")

    # Supplement with tools_config.json so tools added there are always resolvable
    # even before the MCP service is restarted (prevents stale cache issues).
    try:
        tools_config_path = os.path.join(
            os.path.dirname(__file__),
            "../../bb_langgraph_service/tools_config.json",
        )
        if os.path.exists(tools_config_path):
            with open(tools_config_path, "r") as f:
                tc = json.load(f)
            for category, tool_list in tc.items():
                cat_lower = category.lower()
                if cat_lower not in lookup and isinstance(tool_list, list):
                    lookup[cat_lower] = tool_list
                    logger.info("📋 MCP definitions supplemented from tools_config.json: %s", category)
    except Exception as e:
        logger.warning("⚠️ Could not load tools_config.json supplement: %s", e)

    _mcp_definitions_cache = lookup
    logger.info(f"✅ Final MCP definitions: {list(lookup.keys())}")
    return lookup


def _resolve_fallback_actions(tool_base: str, mcp_defs: dict) -> list:
    """
    Resolve MCP fallback actions even when category keys vary across deployments.
    """
    if not isinstance(mcp_defs, dict) or not tool_base:
        return []

    base_norm = _normalize_tool_name(tool_base)
    if not base_norm:
        return []

    direct = mcp_defs.get(tool_base, [])
    if isinstance(direct, list) and direct:
        return direct

    alias_map = {
        "gmail": {"gmail", "googlemail"},
        "gcalendar": {"gcalendar", "calendar", "googlecalendar"},
        "gsheets": {"gsheets", "sheets", "googlesheets"},
        "gmaps": {"gmaps", "maps", "googlemaps"},
        "hubspot": {"hubspot"},
        "charges": {"charges", "freight"},
    }
    aliases = alias_map.get(base_norm, {base_norm})

    # 1) Category-key match via normalized aliases
    for category_key, actions in mcp_defs.items():
        if not isinstance(actions, list) or not actions:
            continue
        category_norm = _normalize_tool_name(category_key)
        if category_norm in aliases:
            return actions

    # 2) Action-name heuristic match
    for _category_key, actions in mcp_defs.items():
        if not isinstance(actions, list) or not actions:
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_name_norm = _normalize_tool_name(action.get("action", ""))
            if any(alias in action_name_norm for alias in aliases):
                return actions

    return []


def _find_action_in_mcp_definitions(action_name: str) -> dict | None:
    """
    Resolve an action from live MCP definitions (category + parameters).
    Useful when DB stores generic invoker-style actions without category.
    """
    defs = _get_mcp_definitions()
    if not defs:
        return None

    for category_key, actions in defs.items():
        if not isinstance(actions, list):
            continue

        for action in actions:
            if not isinstance(action, dict):
                continue
            if action.get("action") != action_name:
                continue

            resolved = dict(action)
            resolved["category"] = resolved.get("category") or str(category_key).capitalize()
            if not isinstance(resolved.get("parameters"), list):
                resolved["parameters"] = []
            return resolved

    return None



def get_agent_kb_collections(agent_id: int, override_kb_ids: list[int] | None = None) -> dict:
    """
    Fetch KB metadata for all knowledge bases linked to this agent.

    Supports:
    - NEW: knowledge_base_ids (list)
    - LEGACY: knowledge_base_id (single FK)

    Returns:
    {
        "knowledge_bases": [
            {
                "kb_id": int,
                "collection_name": str,
                "summary": str
            }
        ],
        "default_kb_id": Optional[int]
    }
    """

    session = next(db_session())

    try:
        agent = session.query(Agent).filter(
            Agent.agent_id == agent_id,
            Agent.del_flg == False
        ).first()
        # Verify agent exists and capture its tenant for KB isolation below


        if not agent:
            raise ValueError(f"Agent ID {agent_id} not found")

        kb_ids: list[int] = []

        # ---- KB IDS ----
        # Priority 1: workflow/node override (if provided)
        if isinstance(override_kb_ids, list) and len(override_kb_ids) > 0:
            kb_ids.extend(override_kb_ids)
            logger.info(f"✅ Using override knowledge_base_ids from workflow node: {override_kb_ids}")
        else:
            # Priority 2: persisted agent mapping
            knowledge_base_ids = getattr(agent, "knowledge_base_ids", None) or []
            if isinstance(knowledge_base_ids, list):
                kb_ids.extend(knowledge_base_ids)
                logger.info(f"✅ Found knowledge_base_ids: {knowledge_base_ids}")

        # Normalize + dedupe (preserve original order)
        normalized_ids = []
        seen_ids = set()
        for raw_id in kb_ids:
            if raw_id is None:
                continue
            kb_id = int(raw_id)
            if kb_id in seen_ids:
                continue
            seen_ids.add(kb_id)
            normalized_ids.append(kb_id)
        kb_ids = normalized_ids

        logger.info(f"🔍 Final KB IDs to resolve: {kb_ids}")

        if not kb_ids:
            logger.warning(f"⚠️ No KB IDs linked to agent {agent_id}")
            return {
                "knowledge_bases": [],
                "default_kb_id": None
            }

        kb_items = session.query(KnowledgeBase).filter(
            KnowledgeBase.knowledge_base_id.in_(kb_ids),
            KnowledgeBase.tenant_id == agent.tenant_id,  # enforce tenant ownership
            KnowledgeBase.del_flg == False,
            KnowledgeBase.collection_name.isnot(None),
            KnowledgeBase.collection_name != ""
        ).all()

        knowledge_bases = []

        requested_order = [int(k) for k in kb_ids]
        kb_items_by_id = {int(kb.knowledge_base_id): kb for kb in kb_items}

        eligible_kbs = []
        skipped_kbs = []
        for kb_id in requested_order:
            kb = kb_items_by_id.get(kb_id)
            if not kb:
                skipped_kbs.append((kb_id, "missing record/collection"))
                continue

            # Runtime guard: only use KBs that are actually built and chunked.
            kb_status = (getattr(kb, "status", "") or "").strip().lower()
            kb_chunks = int(getattr(kb, "total_chunks", 0) or 0)
            is_ready = kb_chunks > 0 and kb_status == "completed"
            if is_ready:
                eligible_kbs.append(kb)
            else:
                skipped_kbs.append(
                    (kb_id, f"status={kb_status or '-'} total_chunks={kb_chunks}")
                )

        if skipped_kbs:
            for kb_id, reason in skipped_kbs:
                logger.warning(f"⚠️ Skipping KB id={kb_id} because it is not ready ({reason})")

        for kb in eligible_kbs:
            knowledge_bases.append({
                "kb_id": kb.knowledge_base_id,
                "collection_name": kb.collection_name,
                "summary": kb.kb_summary or "",
                # Optional hint; when unknown we leave it null and let query-time
                # logic auto-detect from Qdrant vector size.
                "embedding_model": None,
            })

            logger.info(
                f"📘 KB Loaded | id={kb.knowledge_base_id} "
                f"| collection={kb.collection_name} "
                f"| summary_present={bool(kb.kb_summary)}"
            )

        if not knowledge_bases:
            logger.warning(
                "⚠️ No eligible KBs after readiness filtering for agent %s (requested_ids=%s)",
                agent_id,
                requested_order,
            )

        default_kb_id = knowledge_bases[0]["kb_id"] if knowledge_bases else None
        return {
            "knowledge_bases": knowledge_bases,
            "default_kb_id": default_kb_id
        }

    finally:
        session.close()


def safe_json_load(value):
    """Safely parse JSON that may be dict, list, or string."""
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed
        except Exception:
            return {}
    return {}


def _normalize_action_def(
    action_name: str,
    action_def: dict | None,
    default_category: str,
    default_description: str,
) -> dict:
    """
    Ensure each tool action matches the langgraph ToolDefinition schema.
    """
    normalized = dict(action_def) if isinstance(action_def, dict) else {}
    normalized["action"] = normalized.get("action") or action_name
    normalized["category"] = normalized.get("category") or default_category
    normalized["description"] = normalized.get("description") or default_description

    # Pydantic expects a list for parameters; coerce bad/absent values.
    if not isinstance(normalized.get("parameters"), list):
        normalized["parameters"] = []

    return normalized


def _resolve_embedding_config(session, agent: Agent, tenant_id: int, agent_id: int) -> dict:
    """
    Resolve embedding config for KB ingestion/query.

    The embedding MODEL is always fixed to text-embedding-3-large — no DB or
    payload override is applied.  Only the API key is resolved from the tenant's
    stored OpenAI credentials (or env fallback).
    """
    _FIXED_MODEL = "text-embedding-3-large"
    _FIXED_PROVIDER = "openai"

    # Resolve API key from the tenant's OpenAI LLM record (key only, model ignored)
    api_key = ""
    tenant_openai_llm = (
        session.query(LLM)
        .options(joinedload(LLM.base_llm))
        .filter(LLM.tenant_id == tenant_id, LLM.del_flg != True)
        .order_by(LLM.llm_id.desc())
        .all()
    )
    for tenant_llm in tenant_openai_llm:
        base = getattr(tenant_llm, "base_llm", None)
        if not base:
            continue
        provider_name = str(getattr(base, "base_provider", "") or "").strip().lower()
        if provider_name != "openai":
            continue
        api_key = _maybe_decrypt_secret(getattr(tenant_llm, "llm_secret_key", ""))
        if api_key:
            break

    # Env fallback for API key
    if not api_key:
        api_key = os.getenv("KB_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""

    logger.info(
        "Embedding config resolved | agent_id=%s model=%s (fixed) key_present=%s",
        agent_id,
        _FIXED_MODEL,
        bool(api_key),
    )

    return {
        "provider": _FIXED_PROVIDER,
        "model": _FIXED_MODEL,
        "api_key": api_key,
        "source": "fixed",
    }

    
def prepare_agent_input(
    agent_id: int,
    task: str = "",
    use_temp_llm: bool = False,
    use_temp_mcp_endpoint: bool = False,
    override_tenant_id: int = None,
    override_kb_ids: list[int] | None = None,
    agent_type: str = None,  # 🆕 ADD THIS
    llm_model_override: str = None,  # 🆕 ADD THIS FOR DYNAMIC MODEL
    agent_role_override: str = None,         # 🆕 per-node persona override (bot workflow)
    agent_instructions_override: str = None, # 🆕 per-node instructions override (bot workflow)
    tool_names_override: list | None = None, # 🆕 per-node tool subset (bot workflow)
    memory_mode_override: str = None,        # 🆕 per-node memory mode (bot workflow)
) -> dict:
    """
    Prepare the full agent input payload by fetching metadata, MCP tool configs,
    and LLM info.

    ✅ Keeps same structure and logic
    ✅ Endpoint constant: https://mcp.jnanic.com/call_tool
    ✅ Adds 'method': 'POST'
    ✅ Uses the category name from DB as the key (e.g., "Gmail", not "gmail")
    ✅ override_tenant_id: use this tenant's MCP tools instead of agent owner's
       (required for prebuilt/cloned agents so correct OAuth tools are found)
    """

    session = next(db_session())
    try:
        # 1️⃣ Fetch Agent Metadata
        agent_query = session.query(Agent)
        if not use_temp_llm:
            agent_query = agent_query.options(
                joinedload(Agent.llm_model).joinedload(LLM.base_llm),
                joinedload(Agent.llm_model).joinedload(LLM.provider),
                joinedload(Agent.llm_model).joinedload(LLM.model_name),
            )
            

        agent = agent_query.filter(
            Agent.agent_id == agent_id,
            Agent.del_flg == False
        ).first()

        if not agent:
            raise ValueError(f"Agent with id={agent_id} not found")

        # Use override_tenant_id if provided (for prebuilt/cloned agents)
        # This ensures we look up the RUNNING tenant's tools, not the agent owner's
        tenant_id = override_tenant_id if override_tenant_id else agent.tenant_id
        logger.info(
            f"✅ Agent found: {agent.agent_name} "
            f"(agent.tenant_id={agent.tenant_id}, resolved_tenant_id={tenant_id})"
        )
        logger.info(
            "Agent DB links | agent_id=%s llm_provider_id=%s llm_model_id=%s llm_rel_id=%s",
            agent_id,
            getattr(agent, "llm_provider_id", None),
            getattr(agent, "llm_model_id", None),
            getattr(agent, "llm_id", None),
        )

        # 2️⃣ Fetch Agent Tool Mappings
        agent_tools = session.query(McpAgentTools).filter(
            McpAgentTools.agent_id == agent_id,
            McpAgentTools.del_flag == False
        ).all()

        # 3️⃣ Fetch Tenant Tools (from tbl_mcp_tools)
        tenant_tools = session.query(McpTools).filter(
            McpTools.tenant_id == tenant_id,
            McpTools.del_flag == False
        ).all()

        tools_config = {}

        # 4️⃣ Build Tool Config
        for at in agent_tools:
            tool_name = at.tool_name.strip()
            
            # 🔧 Normalize generic tool names (e.g., 'invoker' → 'gmail') based on actions
            action_tools_list = []
            if isinstance(at.action_tools, list):
                action_tools_list = at.action_tools
            elif isinstance(at.action_tools, dict):
                action_tools_list = list(at.action_tools.values())
            elif isinstance(at.action_tools, str):
                try:
                    parsed = json.loads(at.action_tools)
                    action_tools_list = parsed if isinstance(parsed, list) else []
                except Exception:
                    action_tools_list = []
            
            # Map generic tool names to specific ones based on actions
            if tool_name.lower() in ("invoker", "generic", "unknown", ""):
                if action_tools_list:
                    all_actions = " ".join(str(a) for a in action_tools_list).lower()
                    if any(x in all_actions for x in ("gmail", "email", "message_full")):
                        tool_name = "gmail"
                    elif any(x in all_actions for x in ("hubspot", "contact", "company", "deal")):
                        tool_name = "hubspot"
                    elif any(x in all_actions for x in ("calendar", "event")):
                        tool_name = "calendar"
                    elif any(x in all_actions for x in ("sheet", "spreadsheet")):
                        tool_name = "sheets"
                    elif any(x in all_actions for x in ("map", "gmaps", "location", "commute")):
                        tool_name = "gmaps"
            
            normalized_tool_name = _normalize_tool_name(tool_name)
            logger.info(f"⚙️ Processing agent tool: {tool_name}")

            # ── LOCAL TOOL CHECK ──────────────────────────────────────────
            # If this tool is registered as type='local' in tbl_tool_authorization,
            # route it through /local_tool/call (Python class) NOT via MCP server.
            if _is_local_tool(tool_name, tenant_id, session, agent_id=agent_id):
                # Fetch action definitions from tbl_mcp_tools (same tenant)
                # tbl_mcp_tools stores action schemas keyed by tool name
                tool_base    = tool_name.lower().replace("jnanic_mcp_", "")
                category_key = tool_name.capitalize()  # e.g. "Gmail", "Gcalendar"
                local_actions = []

                for mcp_t in tenant_tools:
                    try:
                        # Use mcp_action_tools (has full action defs with parameters)
                        action_field = mcp_t.mcp_action_tools
                        if isinstance(action_field, str):
                            action_field = json.loads(action_field)
                        if isinstance(action_field, dict):
                            actions_list = (
                                action_field.get(tool_name)
                                or action_field.get(tool_name.capitalize())
                                or action_field.get(category_key)
                            )
                            if not actions_list:
                                for k, v in action_field.items():
                                    if _normalize_tool_name(k) == _normalize_tool_name(tool_name):
                                        actions_list = v
                                        break
                            if isinstance(actions_list, list) and actions_list:
                                local_actions = actions_list
                                break
                    except Exception:
                        continue

                # Fallback to MCP service if tbl_mcp_tools had nothing
                if not local_actions:
                    mcp_defs      = _get_mcp_definitions()
                    local_actions = _resolve_fallback_actions(tool_base, mcp_defs) or []

                # Get assigned actions from tbl_mcp_agent_tools
                assigned_actions = []
                if isinstance(at.action_tools, list):
                    assigned_actions = [a for a in at.action_tools if a]
                elif isinstance(at.action_tools, dict):
                    assigned_actions = [v for v in at.action_tools.values() if v]
                else:
                    try:
                        parsed = json.loads(at.action_tools or "[]")
                        assigned_actions = [a for a in parsed if a] if isinstance(parsed, list) else []
                    except Exception:
                        assigned_actions = []

                # If no specific actions assigned, use all available
                if not assigned_actions and local_actions:
                    assigned_actions = [
                        a.get("action") for a in local_actions
                        if isinstance(a, dict) and a.get("action")
                    ]

                if category_key not in tools_config:
                    tools_config[category_key] = []

                for action_name in assigned_actions:
                    raw_def = next(
                        (a for a in local_actions if isinstance(a, dict) and a.get("action") == action_name),
                        {"action": action_name, "category": category_key, "parameters": []},
                    )
                    action_def = _normalize_action_def(
                        action_name=action_name,
                        action_def=raw_def,
                        default_category=category_key,
                        default_description=f"{tool_name}:{action_name}",
                    )
                    tools_config[category_key].append({
                        "endpoint": LOCAL_ENDPOINT,   # ← /local_tool/call, NOT mcp
                        "method":   CONSTANT_METHOD,
                        **action_def,
                    })

                logger.info(
                    "✅ Local tool '%s' → LOCAL_ENDPOINT | %d action(s) | category=%s",
                    tool_name, len(assigned_actions), category_key,
                )
                continue  # skip MCP matching below
            # ── END LOCAL TOOL CHECK ──────────────────────────────────────

            # Match tool in tenant MCP tools
            mcp_tool = None
            for t in tenant_tools:
                try:
                    mcp_tools_field = t.mcp_tools
                    if isinstance(mcp_tools_field, str):
                        mcp_tools_field = json.loads(mcp_tools_field)
                    if isinstance(mcp_tools_field, dict):
                        normalized_keys = {_normalize_tool_name(key) for key in mcp_tools_field.keys()}
                        if normalized_tool_name in normalized_keys:
                            mcp_tool = t
                            break
                    if isinstance(mcp_tools_field, list):
                        normalized_items = {_normalize_tool_name(item) for item in mcp_tools_field}
                        if normalized_tool_name in normalized_items:
                            mcp_tool = t
                            break
                except Exception as e:
                    logger.warning(f"⚠️ Error parsing mcp_tools for {t.mcp_name}: {e}")
                    continue

            # Fallback match by MCP URL when agent tool_name differs from DB tool key
            # (common for external MCP where agent tool label is generic like "invoker").
            if not mcp_tool and getattr(at, "mcp_url", None):
                agent_mcp_url = str(getattr(at, "mcp_url", "")).strip()
                mcp_tool = next(
                    (
                        t for t in tenant_tools
                        if str(getattr(t, "mcp_url", "")).strip() == agent_mcp_url
                    ),
                    None,
                )
                if mcp_tool:
                    logger.info(
                        "✅ Matched external MCP by URL for tool '%s' -> mcp_name='%s' url=%s",
                        tool_name,
                        getattr(mcp_tool, "mcp_name", "unknown"),
                        agent_mcp_url,
                    )

            if not mcp_tool:
                # ── Fallback: load action defs directly from MCP service ──────
                # This handles prebuilt/cloned agents whose tools were connected
                # via OAuth (tbl_tool_authorization) rather than MCP config UI
                # (tbl_mcp_tools). Utility tools (system, llm etc.) are skipped.
                tool_base = tool_name.lower().replace("jnanic_mcp_", "")

                if tool_base in UTILITY_TOOLS:
                    logger.info(f"⚠️ Skipping utility tool '{tool_name}' (no MCP record needed)")
                    continue

                # ── Local MCP tools (e.g. Zoom) — served by local stdio npx process ──
                if tool_base in _LOCAL_MCP_TOOLS:
                    local_mcp_actions = _LOCAL_MCP_TOOL_ACTIONS.get(tool_base, [])
                    assigned_actions = at.action_tools if isinstance(at.action_tools, list) else []
                    if not assigned_actions:
                        assigned_actions = [a["action"] for a in local_mcp_actions if isinstance(a, dict)]
                    category_key = tool_name.capitalize()
                    if category_key not in tools_config:
                        tools_config[category_key] = []
                    for action_name in assigned_actions:
                        raw_def = next(
                            (a for a in local_mcp_actions if isinstance(a, dict) and a.get("action") == action_name),
                            {"action": action_name, "category": category_key, "parameters": []},
                        )
                        action_def = _normalize_action_def(
                            action_name=action_name,
                            action_def=raw_def,
                            default_category=category_key,
                            default_description=f"{tool_name}:{action_name}",
                        )
                        tools_config[category_key].append({
                            "endpoint": f"{MCP_SERVICE_URL}/call_tool",
                            "method":   CONSTANT_METHOD,
                            **action_def,
                        })
                    logger.info("✅ Local MCP tool '%s' → mcp-service | %d action(s)", tool_name, len(assigned_actions))
                    continue

                logger.warning(
                    f"⚠️ No tbl_mcp_tools match for '{tool_name}' — "
                    f"falling back to MCP service definitions"
                )

                mcp_defs = _get_mcp_definitions()
                fallback_actions = _resolve_fallback_actions(tool_base, mcp_defs)

                if not fallback_actions:
                    logger.warning(f"⚠️ MCP service also has no definitions for '{tool_name}' — skipping")
                    continue

                # Get assigned actions from tbl_mcp_agent_tools
                assigned_actions = []
                if isinstance(at.action_tools, list):
                    assigned_actions = at.action_tools
                elif isinstance(at.action_tools, dict):
                    assigned_actions = list(at.action_tools.values())
                else:
                    try:
                        assigned_actions = json.loads(at.action_tools)
                        if not isinstance(assigned_actions, list):
                            assigned_actions = []
                    except Exception:
                        assigned_actions = []

                # If no specific actions assigned, use all available from MCP
                if not assigned_actions:
                    assigned_actions = [
                        a.get("action") for a in fallback_actions
                        if isinstance(a, dict) and a.get("action")
                    ]

                fallback_category = None
                for action_name in assigned_actions:
                    raw_action_def = next(
                        (a for a in fallback_actions
                         if isinstance(a, dict) and a.get("action") == action_name),
                        {"action": action_name, "category": tool_base.capitalize(), "parameters": []}
                    )
                    action_def = _normalize_action_def(
                        action_name=action_name,
                        action_def=raw_action_def,
                        default_category=tool_base.capitalize(),
                        default_description=f"{tool_name}:{action_name}",
                    )

                    # 🔧 FIX: Use tool_name/tool_base as category key, not MCP-returned category
                    # This ensures "gmail" tools use "Gmail" key, not "Invoker" key
                    category_key = tool_base.capitalize()
                    fallback_category = category_key

                    if category_key not in tools_config:
                        tools_config[category_key] = []

                    tools_config[category_key].append({
                        "endpoint": CONSTANT_ENDPOINT,
                        "method":   CONSTANT_METHOD,
                        **action_def
                    })

                logger.info(
                    f"✅ Tool '{tool_name}' configured via MCP fallback under '{fallback_category}'"
                )
                continue  # skip the rest of the loop below (which needs mcp_tool)

            # Load action definitions
            try:
                mcp_actions_json = (
                    safe_json_load(mcp_tool.mcp_action_tools)
                    if isinstance(mcp_tool.mcp_action_tools, str)
                    else mcp_tool.mcp_action_tools
                ) or {}
            except Exception as e:
                logger.warning(f"⚠️ Failed to parse mcp_action_tools for {mcp_tool.mcp_name}: {e}")
                mcp_actions_json = {}

            runtime_mcp_server_params = _normalize_mcp_server_params(
                getattr(mcp_tool, "mcp_url", None),
                getattr(mcp_tool, "mcp_json", None),
            )
            logger.info(
                "[MCP TOOL CFG] tool=%s mcp_name=%s transport=%s url=%s",
                tool_name,
                getattr(mcp_tool, "mcp_name", "unknown"),
                runtime_mcp_server_params.get("transport"),
                runtime_mcp_server_params.get("url"),
            )

            available_actions = []
            if isinstance(mcp_actions_json, dict):
                available_actions = mcp_actions_json.get(tool_name, [])
                if not available_actions:
                    normalized_tool_key = _normalize_tool_name(tool_name)
                    for key, actions in mcp_actions_json.items():
                        if _normalize_tool_name(key) == normalized_tool_key and isinstance(actions, list):
                            available_actions = actions
                            break
                if not available_actions:
                    # Last fallback for external MCP schemas keyed differently than agent tool_name.
                    merged_actions = []
                    for actions in mcp_actions_json.values():
                        if isinstance(actions, list):
                            merged_actions.extend(actions)
                    available_actions = merged_actions
            elif isinstance(mcp_actions_json, list):
                available_actions = mcp_actions_json

            # Get assigned actions
            assigned_actions = []
            if isinstance(at.action_tools, list):
                # Accept both ["send_email"] and [{"action":"send_email"}] forms.
                for item in at.action_tools:
                    if isinstance(item, str):
                        assigned_actions.append(item)
                    elif isinstance(item, dict) and item.get("action"):
                        assigned_actions.append(str(item.get("action")))
            elif isinstance(at.action_tools, dict):
                assigned_actions = list(at.action_tools.values())
            else:
                try:
                    assigned_actions = json.loads(at.action_tools)
                    if isinstance(assigned_actions, list):
                        normalized = []
                        for item in assigned_actions:
                            if isinstance(item, str):
                                normalized.append(item)
                            elif isinstance(item, dict) and item.get("action"):
                                normalized.append(str(item.get("action")))
                        assigned_actions = normalized
                    else:
                        assigned_actions = []
                except Exception:
                    assigned_actions = []

            # If no explicit action assignment is stored, include all available
            # actions for this connected MCP tool so runtime can still call tools.
            if not assigned_actions:
                assigned_actions = [
                    str(a.get("action"))
                    for a in available_actions
                    if isinstance(a, dict) and a.get("action")
                ]
                logger.info(
                    "ℹ️ Tool '%s' had no assigned actions; defaulting to all available actions: %s",
                    tool_name,
                    assigned_actions,
                )

            # 5️⃣ Prepare Config for This Tool (Category key)
            for action_name in assigned_actions:
                # Find matching action
                action_def = None
                action_category = None

                for a in available_actions:
                    if isinstance(a, dict) and a.get("action") == action_name:
                        action_def = a
                        raw_category = str(a.get("category") or "").strip().lower()
                        needs_inference = (not raw_category) or (raw_category == "invoker")
                        if needs_inference:
                            # Some DB entries (e.g. invoker) miss provider category.
                            inferred = _find_action_in_mcp_definitions(action_name)
                            if inferred:
                                # Prefer inferred MCP registry category over generic DB aliases.
                                action_def = {**a, **inferred}
                            else:
                                # Fallback for external MCPs: use connected MCP name instead of "invoker".
                                action_def = {**a, "category": getattr(mcp_tool, "mcp_name", tool_name)}
                        action_category = action_def.get("category") or tool_name
                        break

                if not action_def:
                    inferred = _find_action_in_mcp_definitions(action_name)
                    if inferred:
                        action_def = inferred
                        action_category = inferred.get("category") or tool_name.capitalize()
                    else:
                        action_def = {"action": action_name, "description": f"{tool_name}:{action_name}"}
                        action_category = tool_name.capitalize()
                else:
                    action_category = action_category or tool_name.capitalize()

                action_def = _normalize_action_def(
                    action_name=action_name,
                    action_def=action_def,
                    default_category=action_category,
                    default_description=f"{tool_name}:{action_name}",
                )

                # 🔧 FIX: Use tool_name as category key for tools_config dict
                # Preserves agent tool assignment (e.g., "Gmail" not "Invoker")
                # Keep action_def["category"] for documentation/description
                category_key = tool_name.capitalize()

                if category_key not in tools_config:
                    tools_config[category_key] = []

                # ── Choose endpoint based on mcp_tool.tool_type ──────────────
                mcp_tool_type = str(getattr(mcp_tool, "tool_type", "jnanic_mcp") or "jnanic_mcp").strip().lower()

                if mcp_tool_type == "external":
                    # External MCP: call the tool's own remote URL directly
                    tool_endpoint = str(mcp_tool.mcp_url or CONSTANT_ENDPOINT).strip()
                    if not tool_endpoint.endswith("/call_tool"):
                        tool_endpoint = tool_endpoint.rstrip("/") + "/call_tool"
                    logger.info(
                        "[TOOL_ENDPOINT] tool=%s → EXTERNAL endpoint=%s",
                        tool_name, tool_endpoint,
                    )
                else:
                    # Jnanic MCP (default): route via mcp.jnanic.com
                    tool_endpoint = CONSTANT_ENDPOINT
                    logger.info(
                        "[TOOL_ENDPOINT] tool=%s → JNANIC_MCP endpoint=%s",
                        tool_name, tool_endpoint,
                    )

                enriched_action = {
                    "endpoint": tool_endpoint,
                    "method": CONSTANT_METHOD,
                    "mcp_server_params": runtime_mcp_server_params,
                    **action_def
                }

                tools_config[category_key].append(enriched_action)

            configured_categories = [
                category
                for category, actions in tools_config.items()
                if any(
                    isinstance(action, dict)
                    and action.get("action") in assigned_actions
                    for action in actions
                )
            ]
            logger.info(
                "✅ Tool '%s' configured with %s assigned action(s) across categories: %s",
                tool_name,
                len(assigned_actions),
                configured_categories or ["none"],
            )

        # 6️⃣ LLM Config
        if use_temp_llm:
            llm_provider = "openai"
            llm_model = os.getenv("AGENT_PRIMARY_OPENAI_MODEL", "gpt-4o")
            llm_api_key = os.getenv("OPENAI_API_KEY", "")
        else:
            llm_provider = None
            llm_model = None
            llm_api_key = ""

            if agent.llm_model:
                provider_rel = getattr(agent.llm_model, "provider", None)
                model_name_rel = getattr(agent.llm_model, "model_name", None)
                base_llm_rel = getattr(agent.llm_model, "base_llm", None)

                # Prefer explicit provider/model relationships; fallback to base_llm.
                llm_provider = (
                    getattr(provider_rel, "base_provider", None)
                    or getattr(base_llm_rel, "base_provider", None)
                )
                llm_model = (
                    getattr(model_name_rel, "base_model_name", None)
                    or getattr(base_llm_rel, "base_model_name", None)
                )

                encrypted_key = getattr(agent.llm_model, "llm_secret_key", None)
                if encrypted_key:
                    try:
                        llm_api_key = decrypt_value(encrypted_key)
                    except Exception as decrypt_err:
                        logger.warning(
                            "⚠ Failed to decrypt tenant LLM key for agent_id=%s: %s",
                            agent_id,
                            decrypt_err,
                        )

            if not llm_api_key:
                provider = (llm_provider or "").strip().lower()
                if provider == "anthropic":
                    llm_api_key = os.getenv("ANTHROPIC_API_KEY", "")
                elif provider == "openai":
                    llm_api_key = os.getenv("OPENAI_API_KEY", "")
                else:
                    # Let downstream service raise a clear provider-specific key error.
                    llm_api_key = ""

        llm_provider = (llm_provider or "").strip().lower()
        llm_model = (llm_model or "").strip()

        # Guard against incomplete DB LLM linkage.
        # Dynamic-from-DB is the default policy; optional fallback can be enabled
        # explicitly using ALLOW_LLM_DB_FALLBACK=true.
        allow_llm_db_fallback = str(
            os.getenv("ALLOW_LLM_DB_FALLBACK", "false")
        ).strip().lower() in {"1", "true", "yes", "on"}

        if not llm_provider or not llm_model:
            if not allow_llm_db_fallback:
                raise ValueError(
                    "Missing LLM provider/model linkage in DB "
                    f"for agent_id={agent_id} (llm_provider='{llm_provider}', llm_model='{llm_model}'). "
                    "Fix tbl_llm provider/model relations or set ALLOW_LLM_DB_FALLBACK=true temporarily."
                )

            if not llm_provider:
                llm_provider = (os.getenv("AGENT_DEFAULT_PROVIDER", "openai") or "openai").strip().lower()
                logger.warning(
                    "Agent %s missing DB llm_provider; fallback enabled -> using '%s'",
                    agent_id,
                    llm_provider,
                )
            if not llm_model:
                if llm_provider == "anthropic":
                    llm_model = os.getenv("AGENT_FALLBACK_ANTHROPIC_MODEL", "claude-haiku-4-5")
                else:
                    llm_model = os.getenv("AGENT_PRIMARY_OPENAI_MODEL", "gpt-4o")
                logger.warning(
                    "Agent %s missing DB llm_model; fallback enabled -> using '%s'",
                    agent_id,
                    llm_model,
                )

        if not llm_api_key:
            if llm_provider == "anthropic":
                llm_api_key = os.getenv("ANTHROPIC_API_KEY", "")
            elif llm_provider == "openai":
                llm_api_key = os.getenv("OPENAI_API_KEY", "")

        normalized_model = _normalize_model_id(llm_provider, llm_model)
        if normalized_model != llm_model:
            logger.info(
                "Normalized model label '%s' -> '%s' for provider '%s'",
                llm_model,
                normalized_model,
                llm_provider,
            )
            llm_model = normalized_model

        # 7️⃣ Examples
        try:
            examples = json.loads(agent.Examples) if agent.Examples else []
        except json.JSONDecodeError:
            examples = []

        # kb_collections = get_agent_kb_collections(agent_id)
        kb_payload = get_agent_kb_collections(agent_id, override_kb_ids=override_kb_ids)
        knowledge_bases = kb_payload.get("knowledge_bases", [])
        default_kb_id = kb_payload.get("default_kb_id")

        
        logger.info(f"📦 KB paylod: {kb_payload}")
        logger.info(f"📦 KB knowledge_bases: {knowledge_bases}")
        logger.info(f"📦 KB default_kb_id: {default_kb_id}")
        

        # 8️⃣ Resolve agent type:
        # Prefer explicit runtime override from node formData; otherwise
        # preserve DB value so planner/reflex/decision flows are honored.
        resolved_agent_type = (
            agent_type.strip().lower()
            if isinstance(agent_type, str) and agent_type.strip()
            else (str(getattr(agent, "agent_type", "") or "").strip().lower() or "none")
        )

        # 9️⃣ Final Payload
        effective_model = llm_model_override or llm_model
        inferred_provider = _infer_provider_from_model(effective_model)
        if (
            llm_model_override
            and inferred_provider
            and llm_provider
            and inferred_provider != llm_provider
        ):
            # Keep DB/provider truth as source of truth to avoid cross-provider
            # mismatches (for example provider=openai + model=claude-...),
            # which can produce create_agent 422 failures.
            logger.warning(
                "Ignoring incompatible llm_model_override='%s' for agent_id=%s "
                "(db_provider=%s, inferred_provider=%s). Using DB model '%s'.",
                llm_model_override,
                agent_id,
                llm_provider,
                inferred_provider,
                llm_model,
            )
            effective_model = llm_model

        effective_model = _normalize_model_id(llm_provider, effective_model)

        # 🆕 Per-node persona override (bot workflow): compose description from
        # form_data agent_role / agent_instructions when supplied. Custom-agent
        # workflows leave these None, so DB description is preserved.
        role_txt = (agent_role_override or "").strip() if isinstance(agent_role_override, str) else ""
        inst_txt = (agent_instructions_override or "").strip() if isinstance(agent_instructions_override, str) else ""
        if role_txt and inst_txt:
            effective_description = f"{role_txt}\n\n{inst_txt}"
        elif role_txt:
            effective_description = role_txt
        elif inst_txt:
            effective_description = inst_txt
        else:
            effective_description = agent.agent_description

        # 🆕 Per-node tool subset (bot workflow): filter tools_config by
        # requested tool_names. Empty/None list = no filter (custom-agent path).
        effective_tools_config = tools_config
        if isinstance(tool_names_override, list) and tool_names_override:
            allowed = {_normalize_tool_name(n) for n in tool_names_override if n}
            if allowed:
                effective_tools_config = {
                    k: v for k, v in tools_config.items()
                    if _normalize_tool_name(k) in allowed
                }
                logger.info(
                    "🔧 Applied per-node tool filter: requested=%s, kept=%s, dropped=%s",
                    sorted(allowed),
                    list(effective_tools_config.keys()),
                    [k for k in tools_config.keys() if k not in effective_tools_config],
                )

        # Map agent.memory_mode to remember_now / remember_long for LangGraph
        _memory_mode = (memory_mode_override or agent.memory_mode or "").strip().lower()
        _remember_now  = _memory_mode in ("session", "short_term", "conversation", "persistent", "long_term")
        _remember_long = _memory_mode in ("persistent", "long_term")

        config = {
            "name": agent.agent_name,
            "description": effective_description,
            "llm_provider": llm_provider,
            "llm_model": effective_model,
            "llm_api_key": llm_api_key,
            "tools_config": effective_tools_config,
            "knowledge_bases": knowledge_bases,
            "default_kb_id": default_kb_id,
            "examples": examples,
            "agent_type": resolved_agent_type,
            "remember_now": _remember_now,
            "remember_long": _remember_long,
        }

        embedding_cfg = _resolve_embedding_config(
            session=session,
            agent=agent,
            tenant_id=tenant_id,
            agent_id=agent_id,
        )
        if embedding_cfg.get("provider"):
            config["embedding_provider"] = embedding_cfg.get("provider")
        if embedding_cfg.get("model"):
            config["embedding_model"] = embedding_cfg.get("model")
        if embedding_cfg.get("api_key"):
            config["embedding_api_key"] = embedding_cfg.get("api_key")

        logger.info(f"📦 Config knowledge_bases before return: {config.get('knowledge_bases')}")

        

        final_payload = {
            "task": task,
            "config": config,
            "tenant_id": tenant_id
        }

        logger.info(f"📦 Final payload knowledge_bases: {final_payload['config'].get('knowledge_bases')}")
        logger.info(f"📦 Final payload JSON: {json.dumps(final_payload, default=str)}")

        return final_payload


    except Exception as e:
        logger.error(f"Error in prrpare agent input: {e}")
        raise 
    finally:
        session.close() 
        
        
