"""
prebuilt_agent_service.py

Business logic for tenant-facing prebuilt agent operations.

Handles:
  - Granting prebuilt agents to tenants (on registration)
  - Checking tool authorization status
  - Activating prebuilt agents (cloning to tbl_agents)
  - Refreshing tool status
"""

import logging
from datetime import datetime

from app.models.prebuilt_agent import PrebuiltAgent
from app.models.prebuilt_agent_tools import PrebuiltAgentTools
from app.models.tenant_prebuilt_agents import TenantPrebuiltAgents
from app.models.tool_authorization import ToolAuthorization
from app.database.DatabaseOperationPostgreSQL import db_session

logger = logging.getLogger(__name__)


class PrebuiltAgentService:
    """
    Tenant-facing service for prebuilt agents.
    Manages the full lifecycle: grant → check tools → activate.
    """

    # ══════════════════════════════════════════════════════════════════════
    # GRANTING (called on user registration / plan purchase)
    # ══════════════════════════════════════════════════════════════════════

    def grant_prebuilt_agents_to_tenant(self, tenant_id: int, plan: str = None) -> dict:
        """
        Grant all active prebuilt agents to a tenant.
        Called after user registration or plan upgrade.

        Args:
            tenant_id: The tenant to grant agents to
            plan: Subscription plan name (for future plan-based filtering)

        Returns:
            {"granted_count": int, "already_had": int, "agents": [...]}
        """
        session = next(db_session())
        try:
            # Get all active prebuilt agents
            prebuilt_agents = (
                session.query(PrebuiltAgent)
                .filter_by(is_active=True, del_flg=False)
                .all()
            )

            granted_count = 0
            already_had = 0
            granted_agents = []

            for agent in prebuilt_agents:
                # Check if already granted
                existing = (
                    session.query(TenantPrebuiltAgents)
                    .filter_by(
                        tenant_id=tenant_id,
                        prebuilt_agent_id=agent.prebuilt_agent_id
                    )
                    .first()
                )

                if existing:
                    already_had += 1
                    continue

                # Get required tools (from tbl_prebuilt_agent_tools or JSONB fallback)
                required_tool_names = self._get_required_tool_names(
                    session, agent.prebuilt_agent_id, prebuilt_agent=agent
                )

                # Check which tools tenant has
                missing_tools = self._get_missing_tools(session, tenant_id, required_tool_names)

                # Grant with appropriate status
                status = "ready" if not missing_tools else "pending_tools"

                grant = TenantPrebuiltAgents(
                    tenant_id=tenant_id,
                    prebuilt_agent_id=agent.prebuilt_agent_id,
                    agent_id=None,
                    status=status,
                    missing_tools=missing_tools,
                    granted_at=datetime.utcnow(),
                    last_checked_at=datetime.utcnow(),
                )
                session.add(grant)
                granted_count += 1
                granted_agents.append({
                    "prebuilt_agent_id": agent.prebuilt_agent_id,
                    "agent_name": agent.agent_name,
                    "status": status,
                    "missing_tools": missing_tools,
                })

            session.commit()

            logger.info(
                "grant_prebuilt_agents_to_tenant: tenant=%d granted=%d already_had=%d",
                tenant_id, granted_count, already_had
            )

            return {
                "granted_count": granted_count,
                "already_had": already_had,
                "agents": granted_agents,
            }

        except Exception as exc:
            session.rollback()
            logger.exception("grant_prebuilt_agents_to_tenant: error")
            return {"granted_count": 0, "already_had": 0, "agents": [], "error": str(exc)}

        finally:
            session.close()

    # ══════════════════════════════════════════════════════════════════════
    # GET AVAILABLE AGENTS FOR TENANT
    # ══════════════════════════════════════════════════════════════════════

    def get_available_prebuilt_agents(self, tenant_id: int) -> dict:
        """
        Get all prebuilt agents available to tenant with current status.

        Returns:
            {"agents": [...]} with status, missing_tools, agent_id
        """
        session = next(db_session())
        try:
            # Get tenant's granted agents with prebuilt agent details
            grants = (
                session.query(TenantPrebuiltAgents, PrebuiltAgent)
                .join(
                    PrebuiltAgent,
                    TenantPrebuiltAgents.prebuilt_agent_id == PrebuiltAgent.prebuilt_agent_id
                )
                .filter(
                    TenantPrebuiltAgents.tenant_id == tenant_id,
                    PrebuiltAgent.is_active == True,
                    PrebuiltAgent.del_flg == False,
                )
                .all()
            )

            result = []
            for grant, agent in grants:
                # Get required tools (tbl_prebuilt_agent_tools or JSONB fallback)
                required_tools = self._get_required_tool_names(
                    session, agent.prebuilt_agent_id, prebuilt_agent=agent
                )

                result.append({
                    "prebuilt_agent_id": agent.prebuilt_agent_id,
                    "agent_name": agent.agent_name,
                    "agent_description": agent.agent_description,
                    "category": agent.category,
                    "tags": agent.tags or [],
                    "is_featured": agent.is_featured,
                    "llm_provider": agent.llm_provider,
                    "llm_model": agent.llm_model,
                    "status": grant.status,
                    "required_tools": required_tools,
                    "missing_tools": grant.missing_tools or [],
                    "agent_id": grant.agent_id,
                    "granted_at": grant.granted_at.isoformat() if grant.granted_at else None,
                    "activated_at": grant.activated_at.isoformat() if grant.activated_at else None,
                })

            logger.info(
                "get_available_prebuilt_agents: tenant=%d found %d agents",
                tenant_id, len(result)
            )

            return {"agents": result}

        except Exception as exc:
            logger.exception("get_available_prebuilt_agents: error")
            return {"agents": [], "error": str(exc)}

        finally:
            session.close()

    # ══════════════════════════════════════════════════════════════════════
    # CHECK TOOLS
    # ══════════════════════════════════════════════════════════════════════

    def check_and_update_tool_status(self, tenant_id: int, prebuilt_agent_id: int) -> dict:
        """
        Refresh tool authorization status for a tenant's prebuilt agent.
        Called after OAuth connection or on demand.

        Returns:
            {"status": str, "missing_tools": [...], "can_activate": bool}
        """
        session = next(db_session())
        try:
            grant = (
                session.query(TenantPrebuiltAgents)
                .filter_by(
                    tenant_id=tenant_id,
                    prebuilt_agent_id=prebuilt_agent_id,
                )
                .first()
            )

            if not grant:
                return {
                    "status": "not_found",
                    "missing_tools": [],
                    "can_activate": False,
                    "error": "Prebuilt agent not granted to this tenant"
                }

            # Get required tools (from tbl_prebuilt_agent_tools or JSONB fallback)
            required_tool_names = self._get_required_tool_names(session, prebuilt_agent_id)

            # Check missing tools
            missing = self._get_missing_tools(session, tenant_id, required_tool_names)

            # Update grant record
            grant.missing_tools = missing
            grant.last_checked_at = datetime.utcnow()

            if grant.status != "active":
                grant.status = "ready" if not missing else "pending_tools"

            session.commit()

            return {
                "status": grant.status,
                "missing_tools": missing,
                "can_activate": grant.status == "ready",
                "required_tools": required_tool_names,
            }

        except Exception as exc:
            session.rollback()
            logger.exception("check_and_update_tool_status: error")
            return {"status": "error", "missing_tools": [], "can_activate": False, "error": str(exc)}

        finally:
            session.close()

    # ══════════════════════════════════════════════════════════════════════
    # ACTIVATION (clone to tbl_agents with user credentials)
    # ══════════════════════════════════════════════════════════════════════

    def activate_prebuilt_agent(self, tenant_id: int, prebuilt_agent_id: int) -> dict:
        """
        Activate a prebuilt agent for a tenant:
        - Clones agent structure to tbl_agents
        - Links tenant's existing tool credentials
        - Updates tbl_tenant_prebuilt_agents to status='active'

        Returns:
            {"status": "success", "agent_id": int, "agent": {...}}
        """
        session = next(db_session())
        try:
            # Get grant record
            grant = (
                session.query(TenantPrebuiltAgents)
                .filter_by(
                    tenant_id=tenant_id,
                    prebuilt_agent_id=prebuilt_agent_id,
                )
                .first()
            )

            if not grant:
                return {
                    "status": "error",
                    "error": "Prebuilt agent not granted to your account"
                }

            if grant.status == "active" and grant.agent_id:
                return {
                    "status": "error",
                    "error": "Agent is already activated",
                    "agent_id": grant.agent_id
                }

            # Get prebuilt agent
            prebuilt = (
                session.query(PrebuiltAgent)
                .filter_by(
                    prebuilt_agent_id=prebuilt_agent_id,
                    is_active=True,
                    del_flg=False
                )
                .first()
            )

            if not prebuilt:
                return {"status": "error", "error": "Prebuilt agent not found or inactive"}

            # Get required tools
            required_tools = (
                session.query(PrebuiltAgentTools)
                .filter_by(prebuilt_agent_id=prebuilt_agent_id)
                .all()
            )

            # Re-check tool authorization using the smart helper
            required_tool_names = self._get_required_tool_names(
                session, prebuilt_agent_id, prebuilt_agent=prebuilt
            )
            missing = self._get_missing_tools(session, tenant_id, required_tool_names)
            if missing:
                # Update grant record with fresh missing tools
                grant.missing_tools = missing
                grant.status = "pending_tools"
                grant.last_checked_at = datetime.utcnow()
                session.commit()
                return {
                    "status": "error",
                    "error": f"Cannot activate. Connect these tools first: {', '.join(missing)}",
                    "missing_tools": missing,
                }

            # Import here to avoid circular imports
            from app.models import Agent, LLM
            from app.models.mcp_agent_tools import McpAgentTools
            from app.models.tool import Tools
            import uuid

            # Resolve LLM IDs for this tenant
            llm_provider_id, llm_model_id = self._resolve_llm_ids(
                session, tenant_id,
                prebuilt.llm_provider, prebuilt.llm_model
            )

            if not llm_provider_id or not llm_model_id:
                return {
                    "status": "error",
                    "error": (
                        f"Agent requires {prebuilt.llm_provider} ({prebuilt.llm_model}). "
                        "Please configure this LLM in your LLM Settings first."
                    )
                }

            # Resolve primary tool_id
            first_tool = required_tools[0] if required_tools else None
            resolved_tool = None
            if first_tool:
                resolved_tool = (
                    session.query(Tools)
                    .filter(
                        Tools.tool_name.ilike(first_tool.tool_name),
                        Tools.del_flg == False
                    )
                    .first()
                )
            if not resolved_tool:
                resolved_tool = session.query(Tools).filter(Tools.del_flg == False).first()

            resolved_tool_id = resolved_tool.tool_id if resolved_tool else 1

            # Clone agent to tbl_agents
            cloned_agent = Agent(
                tenant_id=tenant_id,
                agent_name=prebuilt.agent_name,
                agent_description=prebuilt.agent_description,
                agent_role=prebuilt.agent_role,
                agent_instructions=prebuilt.agent_instructions,
                llm_provider_id=llm_provider_id,
                llm_model_id=llm_model_id,
                tool_id=resolved_tool_id,
                tool_type="local",
                knowledge_base_ids=[],
                features=prebuilt.features or {},
                safe_ai_settings=prebuilt.safe_ai_settings or {},
                additional_instructions=prebuilt.additional_instructions,
                Examples=prebuilt.examples,
                memory_plugin=prebuilt.memory_type,
                deployment_method="local",
                agent_key=str(uuid.uuid4()),
                import_source="prebuilt",
                imported_at=datetime.utcnow(),
                del_flg=False,
            )

            session.add(cloned_agent)
            session.flush()

            # Link tools (tbl_mcp_agent_tools)
            for tool in required_tools:
                mcp_tool = McpAgentTools(
                    tenant_id=tenant_id,
                    agent_id=cloned_agent.agent_id,
                    tool_name=tool.tool_name,
                    action_tools=tool.action_tools or [],
                    action_tools_description=[],
                )
                session.add(mcp_tool)

            # Update grant: status = active, agent_id = cloned
            grant.agent_id = cloned_agent.agent_id
            grant.status = "active"
            grant.activated_at = datetime.utcnow()
            grant.last_checked_at = datetime.utcnow()
            grant.missing_tools = []

            session.commit()
            session.refresh(cloned_agent)

            logger.info(
                "activate_prebuilt_agent: SUCCESS tenant=%d prebuilt=%d -> agent=%d",
                tenant_id, prebuilt_agent_id, cloned_agent.agent_id
            )

            return {
                "status": "success",
                "agent_id": cloned_agent.agent_id,
                "agent": cloned_agent.to_dict(),
                "message": f"'{prebuilt.agent_name}' has been activated and is ready to use!"
            }

        except Exception as exc:
            session.rollback()
            logger.exception("activate_prebuilt_agent: error")
            return {"status": "error", "error": f"Activation failed: {str(exc)}"}

        finally:
            session.close()

    # ══════════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════════

    def _get_required_tool_names(self, session, prebuilt_agent_id: int, prebuilt_agent=None) -> list:
        """
        Get required tool names for a prebuilt agent.
        Reads from tbl_prebuilt_agent_tools first.
        Falls back to required_tools JSONB on the agent record (for older imports).
        """
        # Primary: read from tbl_prebuilt_agent_tools
        rows = (
            session.query(PrebuiltAgentTools)
            .filter_by(prebuilt_agent_id=prebuilt_agent_id, is_required=True)
            .all()
        )
        if rows:
            return [r.tool_name.lower() for r in rows]

        # Fallback: read from required_tools JSONB column (older imports)
        if prebuilt_agent is None:
            prebuilt_agent = (
                session.query(PrebuiltAgent)
                .filter_by(prebuilt_agent_id=prebuilt_agent_id)
                .first()
            )
        if prebuilt_agent and prebuilt_agent.required_tools:
            utility = {"system", "llm", "text", "file", "invoke"}
            return [
                t["tool_name"].lower()
                for t in prebuilt_agent.required_tools
                if t.get("tool_name") and t["tool_name"].lower() not in utility
            ]
        return []

    @staticmethod
    def _normalize_tool_name(name: str) -> str:
        """
        Normalize tool name to base name for comparison.
        Matches the same logic used in auth_tools.py catalog endpoint.
        Examples:
          Jnanic_MCP_Gmail  -> gmail
          Gmail             -> gmail
          HubSpot           -> hubspot
          hubspot           -> hubspot
        """
        return name.lower().replace("jnanic_mcp_", "").strip()

    def _get_missing_tools(self, session, tenant_id: int, required_tool_names: list) -> list:
        """Check which required tools tenant has NOT authorized."""
        if not required_tool_names:
            return []

        authorized = (
            session.query(ToolAuthorization.tool_name)
            .filter_by(tenant_id=tenant_id, del_flag=False)
            .all()
        )
        # Normalize all authorized tool names to base names
        authorized_set = {self._normalize_tool_name(t.tool_name) for t in authorized}

        # These utility tools are always available — no OAuth needed
        utility = {"system", "llm", "text", "file", "invoke", "tavily"}

        missing = [
            t for t in required_tool_names
            if self._normalize_tool_name(t) not in authorized_set
            and self._normalize_tool_name(t) not in utility
        ]
        return missing

    def _resolve_llm_ids(self, session, tenant_id: int, provider_str: str, model_str: str):
        """Resolve LLM provider ID and model ID for tenant."""
        from app.models import LLM

        all_llms = (
            session.query(LLM)
            .filter_by(tenant_id=tenant_id, del_flg=False)
            .all()
        )

        provider_id = None
        model_id = None

        for llm in all_llms:
            try:
                if provider_id is None and llm.provider:
                    prov = (
                        llm.provider.base_provider
                        if hasattr(llm.provider, "base_provider")
                        else str(llm.provider)
                    )
                    if prov.lower() == provider_str.lower():
                        provider_id = llm.llm_id

                if model_id is None and llm.model_name:
                    model = (
                        llm.model_name.base_model_name
                        if hasattr(llm.model_name, "base_model_name")
                        else str(llm.model_name)
                    )
                    if model.lower() == model_str.lower():
                        model_id = llm.llm_id
            except Exception:
                continue

        # Fallback: use any available LLM
        if not provider_id and all_llms:
            provider_id = all_llms[0].llm_id
        if not model_id and all_llms:
            model_id = all_llms[0].llm_id

        return provider_id, model_id
