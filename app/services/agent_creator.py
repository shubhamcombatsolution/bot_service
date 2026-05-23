"""
agent_creator.py
Maps a validated agent config dict -> creates rows in:
  - tbl_agents              (Agent)
  - tbl_tool_authorization  (ToolAuthorization) -- one row per tool
  - tbl_mcp_agent_tools     (McpAgentTools)     -- so edit page shows tools
"""

import uuid
import logging
from datetime import datetime

from app.models import Agent, LLM, BaseLLM, KnowledgeBase, ToolAuthorization
from app.models.mcp_agent_tools import McpAgentTools
from app.models.tool import Tools
from app.database.DatabaseOperationPostgreSQL import db_session

logger = logging.getLogger(__name__)


class AgentCreator:

    def create(self, data: dict, tenant_id: int) -> dict:
        """
        Main entry point.
        Returns:
            {"status": "success", "agent_id": <int>, "agent": <dict>}
          or
            {"status": "error", "message": <str>}
        """
        session = next(db_session())
        try:
            # -- 1. Resolve LLM IDs -------------------------------------------
            llm_cfg      = data.get("llm", {})
            provider_str = (llm_cfg.get("provider") or "").strip().lower()
            model_str    = (llm_cfg.get("model")    or "").strip()

            llm_provider_id, llm_model_id = self._resolve_llm_ids(
                session, tenant_id, provider_str, model_str
            )

            if not llm_provider_id:
                return {
                    "status":  "error",
                    "message": (
                        f"LLM provider '{provider_str}' not found in your account. "
                        "Please configure this LLM under the LLM Settings page first."
                    ),
                }
            if not llm_model_id:
                return {
                    "status":  "error",
                    "message": (
                        f"LLM model '{model_str}' not found in your account. "
                        "Please configure this model under the LLM Settings page first."
                    ),
                }

            # -- 2. Resolve Knowledge Base IDs ---------------------------------
            kb_ids = self._resolve_kb_ids(session, tenant_id, data)

            # -- 3. Resolve memory settings ------------------------------------
            memory_cfg     = data.get("memory") or {}
            memory_enabled = memory_cfg.get("enabled", False)
            memory_type    = memory_cfg.get("type") if memory_enabled else None

            # -- 4. Build features & safe_ai_settings --------------------------
            core_features    = data.get("features") or {}
            safe_ai_settings = data.get("safe_ai_settings") or {}

            additional_instructions = self._generate_instructions(
                core_features, safe_ai_settings
            )

            # -- 5. Resolve tool_id (Agent.tool_id is NOT NULL) ----------------
            # The Agent DB column tool_id is NOT NULL, so we must resolve it
            # from tbl_tools using the first tool name in the import config.
            tools_list      = data.get("tools") or []
            first_tool_name = (tools_list[0].get("tool_name") or "").strip().lower() if tools_list else ""
            first_tool_type = (tools_list[0].get("tool_type") or "local").lower()    if tools_list else "local"

            resolved_tool = None
            if first_tool_name:
                resolved_tool = (
                    session.query(Tools)
                    .filter(Tools.tool_name.ilike(first_tool_name), Tools.del_flg == False)
                    .first()
                )

            # Fallback: any tool record so the NOT NULL constraint is satisfied
            if not resolved_tool:
                resolved_tool = session.query(Tools).filter(Tools.del_flg == False).first()

            resolved_tool_id   = resolved_tool.tool_id if resolved_tool else 1
            resolved_tool_type = first_tool_type if first_tool_name else "local"

            # -- 6. Create Agent row -------------------------------------------
            agent = Agent(
                tenant_id               = tenant_id,
                agent_name              = data["agent_name"].strip(),
                agent_description       = data["agent_description"].strip(),
                agent_role              = data["agent_role"].strip(),
                agent_instructions      = (data.get("agent_instructions") or "").strip(),
                llm_provider_id         = llm_provider_id,
                llm_model_id            = llm_model_id,
                tool_id                 = resolved_tool_id,
                tool_type               = resolved_tool_type,
                knowledge_base_ids      = kb_ids,
                memory_plugin           = memory_type,
                features                = core_features,
                safe_ai_settings        = safe_ai_settings,
                additional_instructions = additional_instructions,
                Examples                = (data.get("Examples") or "").strip(),
                deployment_method       = (data.get("deployment_method") or "local"),
                agent_key               = str(uuid.uuid4()),
                import_source           = data.get("_import_source"),
                imported_at             = datetime.utcnow() if data.get("_import_source") else None,
                del_flg                 = False,
            )

            session.add(agent)
            session.flush()  # get agent_id before tool rows

            logger.info(
                "agent_creator: created agent_id=%d for tenant_id=%d",
                agent.agent_id, tenant_id,
            )

            # -- 7. Save credentials + insert into tbl_mcp_agent_tools --------
            # _save_tool      -> tbl_tool_authorization (credential storage)
            # _save_mcp_agent_tool -> tbl_mcp_agent_tools (edit page reads this)
            for tool in tools_list:
                self._save_tool(session, tenant_id, agent.agent_id, tool)
                self._save_mcp_agent_tool(session, tenant_id, agent.agent_id, tool)

            session.commit()
            session.refresh(agent)

            return {
                "status":   "success",
                "agent_id": agent.agent_id,
                "agent":    agent.to_dict(),
            }

        except Exception as exc:
            session.rollback()
            logger.exception("agent_creator: unexpected error")
            return {"status": "error", "message": str(exc)}

        finally:
            session.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_llm_ids(self, session, tenant_id: int, provider_str: str, model_str: str):
        """
        Look up tbl_llm rows for the tenant, join with tbl_basellm to match
        human-readable provider + model strings.
        Returns (llm_provider_id, llm_model_id) as integers or None.
        """
        all_llms = (
            session.query(LLM)
            .filter_by(tenant_id=tenant_id, del_flg=False)
            .all()
        )

        provider_id = None
        model_id    = None

        for llm in all_llms:
            if provider_id is None and llm.provider:
                if llm.provider.base_provider.lower() == provider_str:
                    provider_id = llm.llm_id
            if model_id is None and llm.model_name:
                if llm.model_name.base_model_name.lower() == model_str.lower():
                    model_id = llm.llm_id

        logger.debug(
            "agent_creator: resolved llm provider_id=%s model_id=%s "
            "for provider='%s' model='%s'",
            provider_id, model_id, provider_str, model_str,
        )
        return provider_id, model_id

    def _resolve_kb_ids(self, session, tenant_id: int, data: dict) -> list:
        """
        Returns a deduplicated list of valid knowledge_base_id integers.
        Accepts ids (integers) and/or names (strings) from the config.
        """
        kb_cfg    = data.get("knowledge_base") or {}
        id_list   = kb_cfg.get("ids")   or []
        name_list = kb_cfg.get("names") or []
        result    = []

        if id_list:
            valid = (
                session.query(KnowledgeBase)
                .filter(
                    KnowledgeBase.tenant_id == tenant_id,
                    KnowledgeBase.del_flg   == False,
                    KnowledgeBase.knowledge_base_id.in_(id_list),
                )
                .all()
            )
            result.extend(kb.knowledge_base_id for kb in valid)

        if name_list:
            valid = (
                session.query(KnowledgeBase)
                .filter(
                    KnowledgeBase.tenant_id             == tenant_id,
                    KnowledgeBase.del_flg               == False,
                    KnowledgeBase.knowledge_base_name.in_(name_list),
                )
                .all()
            )
            result.extend(kb.knowledge_base_id for kb in valid)

        seen    = set()
        deduped = []
        for kid in result:
            if kid not in seen:
                seen.add(kid)
                deduped.append(kid)

        logger.debug("agent_creator: resolved kb_ids=%s", deduped)
        return deduped

    def _save_tool(self, session, tenant_id: int, agent_id: int, tool: dict):
        """
        Upsert a ToolAuthorization row (tbl_tool_authorization).

        Token storage rules (mirrors multi_agentic_system_routes.py OAuth callbacks):

          NO_AUTH_TOOLS (system, file, text, llm, invoke)
            → skip entirely, no row created.

          HubSpot (local)
            → token_json: {access_token, refresh_token, hub_id,
                           expires_in, token_type, expiry, scopes}

          Google OAuth tools (gmail, gcalendar, gsheets)
            → token_json: {access_token, refresh_token, token_uri,
                           client_id, client_secret, scopes, expiry}

          Gmaps (local)
            → token_json: {api_key}

          MCP tools
            → mcp_url + mcp_json stored; token_json empty.
        """
        from app.services.agent_validator import NO_AUTH_TOOLS

        tool_name = (tool.get("tool_name") or "").strip().lower()
        tool_type = (tool.get("tool_type") or "local").lower()

        if not tool_name:
            logger.warning("agent_creator: skipping tool with no tool_name")
            return

        # System-level tools need no credentials row
        if tool_name in NO_AUTH_TOOLS:
            logger.debug(
                "agent_creator: skipping ToolAuthorization for no-auth tool '%s'",
                tool_name,
            )
            return

        creds    = tool.get("credentials") or {}
        mcp_url  = tool.get("mcp_url")
        mcp_json = tool.get("mcp_json") or {}

        # Build the token_json that matches what OAuth callbacks store
        if tool_type == "mcp":
            token_json = {}   # MCP auth lives in mcp_url / mcp_json
        elif tool_name == "hubspot":
            token_json = {
                "access_token":  creds.get("access_token"),
                "refresh_token": creds.get("refresh_token"),
                "hub_id":        creds.get("hub_id"),
                "expires_in":    creds.get("expires_in"),
                "token_type":    creds.get("token_type", "bearer"),
                "expiry":        creds.get("expiry"),
                "scopes":        creds.get("scopes", ""),
            }
        elif tool_name in ("gmail", "gcalendar", "gsheets"):
            # Match exact structure stored by google_callback / gmail_callback
            token_json = {
                "access_token":    creds.get("access_token"),
                "refresh_token":   creds.get("refresh_token"),
                "token_uri":       creds.get("token_uri", "https://oauth2.googleapis.com/token"),
                "client_id":       creds.get("client_id"),
                "client_secret":   creds.get("client_secret"),
                "scopes":          creds.get("scopes", []),
                "universe_domain": "googleapis.com",
                "account":         creds.get("account", ""),
                "expiry":          creds.get("expiry"),
            }
        elif tool_name == "gmaps":
            token_json = {"api_key": creds.get("api_key")}
        else:
            # Any other local tool — store credentials as-is
            token_json = creds

        existing = (
            session.query(ToolAuthorization)
            .filter_by(tenant_id=tenant_id, tool_name=tool_name, del_flag=False)
            .first()
        )

        if existing:
            existing.token_json = token_json
            existing.tool_type  = tool_type
            existing.mcp_url    = mcp_url if tool_type == "mcp" else existing.mcp_url
            existing.mcp_json   = mcp_json if tool_type == "mcp" else existing.mcp_json
            logger.debug(
                "agent_creator: updated ToolAuthorization for tool='%s'", tool_name
            )
        else:
            ta = ToolAuthorization(
                tenant_id  = tenant_id,
                tool_name  = tool_name,
                token_json = token_json,
                tool_type  = tool_type,
                mcp_url    = mcp_url if tool_type == "mcp" else None,
                mcp_json   = mcp_json if tool_type == "mcp" else None,
            )
            session.add(ta)
            logger.debug(
                "agent_creator: inserted ToolAuthorization for tool='%s'", tool_name
            )

    def _save_mcp_agent_tool(self, session, tenant_id: int, agent_id: int, tool: dict):
        """
        Insert or update a McpAgentTools row (tbl_mcp_agent_tools).
        This is what the AgentBuilderContent edit page reads via
        GET /mcp_agent_tools/{agent_id}.

        action_tools is validated by AgentValidator._check_action_tools()
        so it's always properly populated here.
        """
        tool_name    = (tool.get("tool_name") or "").strip().lower()
        tool_type    = (tool.get("tool_type") or "local").lower()
        action_tools = tool.get("action_tools") or []   # validated by validator

        if not tool_name:
            return

        mcp_url = tool.get("mcp_url") if tool_type == "mcp" else None

        existing = (
            session.query(McpAgentTools)
            .filter_by(tenant_id=tenant_id, agent_id=agent_id, tool_name=tool_name)
            .first()
        )

        if existing:
            existing.mcp_url     = mcp_url
            existing.action_tools = action_tools   # refresh with user-specified actions
            logger.debug(
                "agent_creator: updated McpAgentTools for agent_id=%d tool='%s' actions=%d",
                agent_id, tool_name, len(action_tools),
            )
        else:
            mcp_row = McpAgentTools(
                tenant_id                = tenant_id,
                agent_id                 = agent_id,
                tool_name                = tool_name,
                mcp_url                  = mcp_url,
                mcp_id                   = None,          # no tbl_mcp_tools entry for imported tools
                action_tools             = action_tools,   # user-specified action list
                action_tools_description = [],
            )
            session.add(mcp_row)
            logger.debug(
                "agent_creator: inserted McpAgentTools for agent_id=%d tool='%s' actions=%s",
                agent_id, tool_name, action_tools,
            )

    def _generate_instructions(self, features: dict, safe_ai: dict) -> str:
        """
        Mirror of generate_generalized_instructions() in agent_routes.py.
        Keeps parity so imported agents behave identically.
        """
        parts = []

        feature_parts = []
        if features.get("soundNatural"):
            feature_parts.append("use a natural, engaging tone")
        if features.get("thinkBack"):
            feature_parts.append("reflect on past interactions for context")
        if features.get("stayOnTopic"):
            feature_parts.append("stay focused on relevant topics")
        if features.get("explainClearly"):
            feature_parts.append("provide clear, concise explanations")
        if feature_parts:
            parts.append(f"Respond professionally, {', '.join(feature_parts)}.")

        safe_parts = []
        if safe_ai.get("harmfulContent"):
            safe_parts.append(
                f"filter harmful content (threshold: {safe_ai.get('harmfulThreshold', 0.5)})"
            )
        if safe_ai.get("maliciousInstructions"):
            safe_parts.append(
                f"block malicious commands (threshold: {safe_ai.get('maliciousThreshold', 0.5)})"
            )
        if safe_ai.get("allowedTopics") and safe_ai.get("allowedKeywords"):
            safe_parts.append(
                f"focus on professional topics: {', '.join(safe_ai['allowedKeywords'])}"
            )
        if safe_ai.get("blockedTopics") and safe_ai.get("blockedKeywords"):
            safe_parts.append(
                f"avoid topics: {', '.join(safe_ai['blockedKeywords'])}"
            )
        if safe_ai.get("secrets"):
            items = safe_ai.get("secretKeywords") or ["API keys", "tokens", "passwords"]
            safe_parts.append(f"mask sensitive information ({', '.join(items)})")
        if safe_ai.get("keywordsEnabled") and safe_ai.get("keywordList"):
            kw_parts = []
            for kw in safe_ai["keywordList"]:
                if kw.get("type") == "block":
                    kw_parts.append(f"block '{kw.get('key')}'")
                elif kw.get("type") == "mask":
                    kw_parts.append(f"mask '{kw.get('key')}' as '{kw.get('mask')}'")
            if kw_parts:
                safe_parts.append(f"manage keywords: {', '.join(kw_parts)}")

        if safe_parts:
            parts.append(f"Ensure safety by {', '.join(safe_parts)}.")

        return " ".join(parts)
