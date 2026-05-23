"""
agent_cloning_service.py

Clones prebuilt agents to tenant accounts.

CRITICAL FLOW:
  1. Check if tenant has access to ALL required tools
  2. If yes → clone agent to tenant's account
  3. Link cloned agent to tenant's existing tool authorizations
  4. Track cloning in tbl_tenant_cloned_agents
"""

import logging
from typing import List, Tuple
from datetime import datetime

from app.models import Agent, LLM
from app.models.prebuilt_agent import PrebuiltAgent, TenantClonedAgent
from app.models.tool_authorization import ToolAuthorization
from app.models.mcp_agent_tools import McpAgentTools
from app.models.tool import Tools
from app.database.DatabaseOperationPostgreSQL import db_session

logger = logging.getLogger(__name__)


def _normalize_tool_name_for_actions(tool_name: str, action_tools: List[str]) -> str:
    """
    Normalize generic tool names like 'invoker' to specific tool names based on actions.
    
    This fixes the issue where prebuilt agents store tool_name='invoker' but their
    actions are for specific tools (Gmail, HubSpot, etc.).
    
    Args:
        tool_name: Current tool name (may be 'invoker' or generic)
        action_tools: List of action names
        
    Returns:
        Normalized tool name (Gmail, HubSpot, Calendar, etc.)
    """
    tool_name_lower = str(tool_name or "").strip().lower()
    
    # Only normalize if generic/unknown
    if tool_name_lower not in ("invoker", "generic", "unknown", ""):
        return tool_name
    
    # Infer from action names
    if not action_tools:
        return tool_name
    
    # Combine all actions to check
    all_actions = " ".join(action_tools).lower()
    
    # Gmail actions
    if any(x in all_actions for x in ("gmail", "send_email", "read_email", "list_email", 
                                       "search_email", "modify_email", "delete_email", 
                                       "draft_email", "message_full")):
        return "gmail"
    
    # HubSpot actions
    elif any(x in all_actions for x in ("hubspot", "contact", "company", "deal", "pipeline")):
        return "hubspot"
    
    # Calendar actions
    elif any(x in all_actions for x in ("calendar", "event", "gcalendar")):
        return "calendar"
    
    # Sheets actions
    elif any(x in all_actions for x in ("sheet", "spreadsheet", "gsheets")):
        return "sheets"
    
    # Maps actions
    elif any(x in all_actions for x in ("map", "gmaps", "location", "commute", "facility")):
        return "gmaps"
    
    # Webhook/invoker actions - keep as-is
    elif "webhook" in all_actions or "invoke" in all_actions:
        return "invoker"
    
    # Default: keep original
    return tool_name


class AgentCloningService:
    """
    Clones prebuilt agents to tenant accounts.
    Validates tenant has required tool access before cloning.
    """

    def check_tool_access(
        self, tenant_id: int, prebuilt_agent_id: int
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Check if tenant has access to all tools required by prebuilt agent.
        
        Args:
            tenant_id: The tenant ID
            prebuilt_agent_id: The prebuilt agent ID
            
        Returns:
            (has_access, available_tools, missing_tools)
            - has_access: True if tenant has ALL required tools
            - available_tools: List of tool names tenant has
            - missing_tools: List of tool names tenant is missing
        """
        session = next(db_session())
        try:
            # Get prebuilt agent
            prebuilt = (
                session.query(PrebuiltAgent)
                .filter_by(
                    prebuilt_agent_id=prebuilt_agent_id,
                    del_flg=False,
                    is_active=True
                )
                .first()
            )

            if not prebuilt:
                logger.error(
                    "check_tool_access: prebuilt agent %d not found",
                    prebuilt_agent_id
                )
                return False, [], []

            # Get required tools
            required_tools = prebuilt.get_required_tool_names()
            if not required_tools:
                # No tools required - always pass
                logger.info(
                    "check_tool_access: prebuilt agent %d requires no tools",
                    prebuilt_agent_id
                )
                return True, [], []

            logger.debug(
                "check_tool_access: prebuilt agent %d requires tools: %s",
                prebuilt_agent_id, required_tools
            )

            # Get tenant's authorized tools
            tenant_tools = (
                session.query(ToolAuthorization)
                .filter_by(
                    tenant_id=tenant_id,
                    del_flag=False
                )
                .all()
            )

            tenant_tool_names = set(
                tool.tool_name.lower() 
                for tool in tenant_tools 
                if tool.tool_name
            )

            logger.debug(
                "check_tool_access: tenant %d has tools: %s",
                tenant_id, tenant_tool_names
            )

            # Compare
            required_set = set(t.lower() for t in required_tools)
            available = list(required_set & tenant_tool_names)
            missing = list(required_set - tenant_tool_names)

            has_access = len(missing) == 0

            logger.info(
                "check_tool_access: tenant=%d prebuilt=%d has_access=%s "
                "available=%s missing=%s",
                tenant_id, prebuilt_agent_id, has_access, available, missing
            )

            return has_access, available, missing

        finally:
            session.close()

    def clone_to_tenant(
        self, tenant_id: int, prebuilt_agent_id: int
    ) -> dict:
        """
        Clone a prebuilt agent to tenant's account.
        
        Validates:
          1. Tenant has not already cloned this agent
          2. Tenant has access to ALL required tools
          3. Tenant's plan level is sufficient
          
        Args:
            tenant_id: The tenant ID
            prebuilt_agent_id: The prebuilt agent ID
            
        Returns:
            {
                "status": "success",
                "agent_id": int,
                "agent": {...},
                "message": str
            }
            OR
            {
                "status": "error",
                "error_code": str,  # 'already_cloned', 'missing_tools', 'plan_restricted'
                "message": str,
                "missing_tools": [...]  # Only if error_code='missing_tools'
            }
        """
        session = next(db_session())
        try:
            # ──────────────────────────────────────────────────────────────
            # STEP 1: Get prebuilt agent
            # ──────────────────────────────────────────────────────────────
            prebuilt = (
                session.query(PrebuiltAgent)
                .filter_by(
                    prebuilt_agent_id=prebuilt_agent_id,
                    del_flg=False,
                    is_active=True
                )
                .first()
            )

            if not prebuilt:
                return {
                    "status": "error",
                    "error_code": "not_found",
                    "message": f"Prebuilt agent {prebuilt_agent_id} not found or inactive"
                }

            # ──────────────────────────────────────────────────────────────
            # STEP 2: Check if already cloned
            # ──────────────────────────────────────────────────────────────
            existing = (
                session.query(TenantClonedAgent)
                .filter_by(
                    tenant_id=tenant_id,
                    prebuilt_agent_id=prebuilt_agent_id
                )
                .first()
            )

            if existing:
                logger.warning(
                    "clone_to_tenant: tenant %d already cloned prebuilt %d",
                    tenant_id, prebuilt_agent_id
                )
                return {
                    "status": "error",
                    "error_code": "already_cloned",
                    "message": (
                        f"You have already added '{prebuilt.agent_name}' to your account. "
                        f"Check your agents list (agent_id: {existing.cloned_agent_id})"
                    ),
                    "existing_agent_id": existing.cloned_agent_id
                }

            # ──────────────────────────────────────────────────────────────
            # STEP 3: Check tool access
            # ──────────────────────────────────────────────────────────────
            has_access, available, missing = self.check_tool_access(
                tenant_id, prebuilt_agent_id
            )

            if not has_access:
                logger.warning(
                    "clone_to_tenant: tenant %d missing tools: %s",
                    tenant_id, missing
                )
                return {
                    "status": "error",
                    "error_code": "missing_tools",
                    "message": (
                        f"To use '{prebuilt.agent_name}', you need to connect these tools first: "
                        f"{', '.join(missing)}. "
                        "Please connect them via the Tools page and try again."
                    ),
                    "missing_tools": missing,
                    "required_tools": prebuilt.get_required_tool_names(),
                }

            # ──────────────────────────────────────────────────────────────
            # STEP 4: Resolve LLM IDs
            # ──────────────────────────────────────────────────────────────
            llm_provider_id, llm_model_id = self._resolve_llm_ids(
                session, tenant_id, prebuilt.llm_provider, prebuilt.llm_model
            )

            if not llm_provider_id or not llm_model_id:
                return {
                    "status": "error",
                    "error_code": "llm_not_configured",
                    "message": (
                        f"This agent requires {prebuilt.llm_provider} {prebuilt.llm_model}. "
                        "Please configure this LLM in your account first (LLM Settings page)."
                    )
                }

            # ──────────────────────────────────────────────────────────────
            # STEP 5: Resolve tool_id (Agent.tool_id NOT NULL constraint)
            # ──────────────────────────────────────────────────────────────
            required_tool_names = prebuilt.get_required_tool_names()
            first_tool_name = required_tool_names[0] if required_tool_names else ""
            
            resolved_tool = None
            if first_tool_name:
                resolved_tool = (
                    session.query(Tools)
                    .filter(Tools.tool_name.ilike(first_tool_name), Tools.del_flg == False)
                    .first()
                )

            # Fallback
            if not resolved_tool:
                resolved_tool = session.query(Tools).filter(Tools.del_flg == False).first()

            resolved_tool_id = resolved_tool.tool_id if resolved_tool else 1

            # ──────────────────────────────────────────────────────────────
            # STEP 6: Create Agent (clone)
            # ──────────────────────────────────────────────────────────────
            import uuid
            cloned_agent = Agent(
                tenant_id=tenant_id,
                agent_name=f"{prebuilt.agent_name}",  # Could add "(Prebuilt)" suffix if desired
                agent_description=prebuilt.agent_description,
                agent_role=prebuilt.agent_role,
                agent_instructions=prebuilt.agent_instructions,
                llm_provider_id=llm_provider_id,
                llm_model_id=llm_model_id,
                tool_id=resolved_tool_id,
                tool_type="local",  # Most common
                knowledge_base_ids=[],  # TODO: Clone KB if needed
                features=prebuilt.features,
                safe_ai_settings=prebuilt.safe_ai_settings,
                additional_instructions=prebuilt.additional_instructions,
                Examples=prebuilt.examples,
                memory_plugin=prebuilt.memory_type,
                deployment_method="local",
                agent_key=str(uuid.uuid4()),
                import_source="prebuilt_clone",
                imported_at=datetime.utcnow(),
                del_flg=False,
            )

            session.add(cloned_agent)
            session.flush()

            logger.info(
                "clone_to_tenant: created agent_id=%d for tenant=%d from prebuilt=%d",
                cloned_agent.agent_id, tenant_id, prebuilt_agent_id
            )

            # ──────────────────────────────────────────────────────────────
            # STEP 7: Link tools to cloned agent (tbl_mcp_agent_tools)
            # ──────────────────────────────────────────────────────────────
            for tool_req in (prebuilt.required_tools or []):
                tool_name = tool_req.get("tool_name")
                action_tools = tool_req.get("action_tools", [])

                if not tool_name:
                    continue

                # 🔧 Normalize generic tool names (e.g., 'invoker' → 'gmail')
                normalized_tool_name = _normalize_tool_name_for_actions(tool_name, action_tools)

                mcp_tool = McpAgentTools(
                    tenant_id=tenant_id,
                    agent_id=cloned_agent.agent_id,
                    tool_name=normalized_tool_name,
                    action_tools=action_tools,
                    action_tools_description=[],
                )
                session.add(mcp_tool)

                logger.debug(
                    "clone_to_tenant: linked tool '%s' (normalized from '%s') with %d actions to agent %d",
                    normalized_tool_name, tool_name, len(action_tools), cloned_agent.agent_id
                )

            # ──────────────────────────────────────────────────────────────
            # STEP 8: Track cloning in tbl_tenant_cloned_agents
            # ──────────────────────────────────────────────────────────────
            clone_record = TenantClonedAgent(
                tenant_id=tenant_id,
                prebuilt_agent_id=prebuilt_agent_id,
                cloned_agent_id=cloned_agent.agent_id,
                cloned_at=datetime.utcnow(),
                is_active=True,
            )
            session.add(clone_record)

            # ──────────────────────────────────────────────────────────────
            # STEP 9: Update prebuilt agent clone count
            # ──────────────────────────────────────────────────────────────
            prebuilt.clone_count = (prebuilt.clone_count or 0) + 1

            session.commit()
            session.refresh(cloned_agent)

            logger.info(
                "clone_to_tenant: SUCCESS - tenant=%d cloned prebuilt=%d -> agent=%d",
                tenant_id, prebuilt_agent_id, cloned_agent.agent_id
            )

            return {
                "status": "success",
                "agent_id": cloned_agent.agent_id,
                "agent": cloned_agent.to_dict(),
                "message": f"'{prebuilt.agent_name}' has been added to your account!"
            }

        except Exception as exc:
            session.rollback()
            logger.exception("clone_to_tenant: unexpected error")
            return {
                "status": "error",
                "error_code": "unexpected_error",
                "message": f"Failed to clone agent: {str(exc)}"
            }

        finally:
            session.close()

    def _resolve_llm_ids(
        self, session, tenant_id: int, provider_str: str, model_str: str
    ) -> Tuple[int, int]:
        """Resolve LLM provider and model IDs for tenant"""
        all_llms = (
            session.query(LLM)
            .filter_by(tenant_id=tenant_id, del_flg=False)
            .all()
        )

        provider_id = None
        model_id = None

        for llm in all_llms:
            if provider_id is None and llm.provider:
                if llm.provider.base_provider.lower() == provider_str.lower():
                    provider_id = llm.llm_id
            if model_id is None and llm.model_name:
                if llm.model_name.base_model_name.lower() == model_str.lower():
                    model_id = llm.llm_id

        logger.debug(
            "resolve_llm_ids: provider_id=%s model_id=%s for %s/%s",
            provider_id, model_id, provider_str, model_str
        )

        return provider_id, model_id
