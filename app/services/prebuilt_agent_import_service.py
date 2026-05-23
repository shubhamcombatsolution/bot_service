# """
# prebuilt_agent_import_service.py

# Orchestrates prebuilt agent import: parse → validate → create
# Used by Super Admin to add new prebuilt agent templates.

# KEY DIFFERENCE from agent_import_service.py:
#   - NO credential validation
#   - Stores to tbl_prebuilt_agents (not tbl_agents)
#   - NO tenant_id (global templates)
# """

# import logging
# from .prebuilt_agent_parser import PrebuiltAgentParser
# from .prebuilt_agent_validator import PrebuiltAgentValidator
# from .prebuilt_agent_creator import PrebuiltAgentCreator

# logger = logging.getLogger(__name__)

# _SOURCE_MAP = {
#     ".json": "json",
#     ".zip": "zip",
# }


# class PrebuiltAgentImportService:
#     """
#     Import service for Super Admin prebuilt agents.
#     NO credential handling - templates only.
#     """

#     def __init__(self, created_by_user_id: int = None):
#         """
#         Initialize the prebuilt agent import service.
        
#         Args:
#             created_by_user_id: Super Admin user ID (for audit tracking)
#         """
#         self.created_by_user_id = created_by_user_id
#         self.parser = PrebuiltAgentParser()
#         self.validator = PrebuiltAgentValidator()
#         self.creator = PrebuiltAgentCreator()

#     # ══════════════════════════════════════════════════════════════════════
#     # PUBLIC API
#     # ══════════════════════════════════════════════════════════════════════

#     def validate(self, file) -> dict:
#         """
#         Dry-run validation: parse + validate only. No DB writes.
        
#         Returns:
#             {
#                 "valid": True/False,
#                 "errors": [...],
#                 "warnings": [...],
#                 "preview": {...}
#             }
#         """
#         # Parse
#         try:
#             data = self.parser.parse(file)
#             logger.info(
#                 "prebuilt_agent_import_service.validate: parsed file "
#                 "(type: %s)",
#                 "multi" if isinstance(data, list) else "single"
#             )
#         except ValueError as exc:
#             logger.error("prebuilt_agent_import_service.validate: parse failed - %s", exc)
#             return {
#                 "valid": False,
#                 "errors": [str(exc)],
#                 "warnings": [],
#                 "preview": None,
#             }
#         except Exception as exc:
#             logger.exception("prebuilt_agent_import_service.validate: parse error")
#             return {
#                 "valid": False,
#                 "errors": [f"Unexpected parse error: {exc}"],
#                 "warnings": [],
#                 "preview": None,
#             }

#         # Validate
#         # ── Multi-agent ──
#         if isinstance(data, list):
#             logger.info(
#                 "prebuilt_agent_import_service.validate: multi-agent with %d agents",
#                 len(data)
#             )
            
#             results = []
#             overall_valid = True

#             for idx, agent_data in enumerate(data):
#                 res = self.validator.validate(agent_data)

#                 if res["valid"]:
#                     res["preview"] = self._build_preview(agent_data)
#                 else:
#                     overall_valid = False

#                 results.append({"index": idx, **res})

#             return {
#                 "valid": overall_valid,
#                 "multi_agent": True,
#                 "count": len(results),
#                 "results": results,
#                 "preview": None,
#             }

#         # ── Single agent ──
#         result = self.validator.validate(data)

#         if result["valid"]:
#             result["preview"] = self._build_preview(data)

#         return result

#     def import_prebuilt_agent(self, file) -> dict:
#         """
#         Full import: parse → validate → create.
        
#         Returns:
#             {
#                 "status": "success",
#                 "prebuilt_agent_id": int,
#                 "prebuilt_agent": {...}
#             }
#             OR (multi-agent)
#             {
#                 "status": "success",
#                 "multi_agent": True,
#                 "created_count": int,
#                 "created": [...]
#             }
#         """
#         # Parse
#         try:
#             filename = getattr(file, "filename", "")
#             ext = _get_ext(filename)
#             data = self.parser.parse(file)
#             source = _SOURCE_MAP.get(ext, "json")
            
#             logger.info(
#                 "prebuilt_agent_import_service.import: parsed '%s' - type: %s",
#                 filename,
#                 "multi" if isinstance(data, list) else "single"
#             )
#         except ValueError as exc:
#             logger.error("prebuilt_agent_import_service.import: parse failed - %s", exc)
#             return {"status": "error", "errors": [str(exc)], "warnings": []}
#         except Exception as exc:
#             logger.exception("prebuilt_agent_import_service.import: parse error")
#             return {
#                 "status": "error",
#                 "errors": [f"File parse error: {exc}"],
#                 "warnings": [],
#             }

#         # ── Multi-agent ──
#         if isinstance(data, list):
#             logger.info(
#                 "prebuilt_agent_import_service.import: importing %d prebuilt agents",
#                 len(data)
#             )
            
#             created = []
#             failed = []

#             for idx, agent_data in enumerate(data):
#                 agent_data["_import_source"] = source
#                 agent_name = agent_data.get("agent_name", f"agent_{idx}")

#                 # Validate
#                 validation = self.validator.validate(agent_data)
#                 if not validation["valid"]:
#                     logger.warning(
#                         "prebuilt_agent_import_service.import: agent %d (%s) validation FAILED",
#                         idx, agent_name
#                     )
#                     failed.append({
#                         "index": idx,
#                         "agent_name": agent_name,
#                         "errors": validation["errors"],
#                         "warnings": validation["warnings"],
#                     })
#                     continue

#                 # Create
#                 result = self.creator.create(agent_data, self.created_by_user_id)

#                 if result["status"] == "success":
#                     logger.info(
#                         "prebuilt_agent_import_service.import: agent %d (%s) created - id=%d",
#                         idx, agent_name, result["prebuilt_agent_id"]
#                     )
#                     created.append(result)
#                 else:
#                     logger.error(
#                         "prebuilt_agent_import_service.import: agent %d (%s) creation FAILED",
#                         idx, agent_name
#                     )
#                     failed.append({
#                         "index": idx,
#                         "agent_name": agent_name,
#                         "errors": [result.get("message")],
#                         "warnings": validation["warnings"],
#                     })

#             return {
#                 "status": "success" if created else "error",
#                 "multi_agent": True,
#                 "created_count": len(created),
#                 "failed_count": len(failed),
#                 "created": created,
#                 "failed": failed,
#             }

#         # ── Single agent ──
#         data["_import_source"] = source
#         agent_name = data.get("agent_name", "unnamed")

#         logger.info(
#             "prebuilt_agent_import_service.import: importing prebuilt agent '%s'",
#             agent_name
#         )

#         # Validate
#         validation = self.validator.validate(data)
#         if not validation["valid"]:
#             logger.warning(
#                 "prebuilt_agent_import_service.import: validation FAILED - %d errors",
#                 len(validation["errors"])
#             )
#             return {
#                 "status": "error",
#                 "errors": validation["errors"],
#                 "warnings": validation["warnings"],
#             }

#         # Create
#         result = self.creator.create(data, self.created_by_user_id)

#         if result["status"] == "error":
#             logger.error(
#                 "prebuilt_agent_import_service.import: creation FAILED - %s",
#                 result.get("message")
#             )
#             return {
#                 "status": "error",
#                 "errors": [result.get("message")],
#                 "warnings": validation["warnings"],
#             }

#         logger.info(
#             "prebuilt_agent_import_service.import: SUCCESS - prebuilt_agent_id=%d",
#             result["prebuilt_agent_id"]
#         )

#         return {
#             "status": "success",
#             "prebuilt_agent_id": result["prebuilt_agent_id"],
#             "prebuilt_agent": result["prebuilt_agent"],
#             "warnings": validation["warnings"],
#         }

#     # ══════════════════════════════════════════════════════════════════════
#     # HELPERS
#     # ══════════════════════════════════════════════════════════════════════

#     def _build_preview(self, data: dict) -> dict:
#         """Build safe preview summary"""
#         tools = data.get("tools") or []
#         llm = data.get("llm") or {}
        
#         return {
#             "agent_name": data.get("agent_name", ""),
#             "agent_description": data.get("agent_description", ""),
#             "category": data.get("category", "General"),
#             "tags": data.get("tags", []),
#             "llm_provider": llm.get("provider", ""),
#             "llm_model": llm.get("model", ""),
#             "tools_count": len(tools),
#             "tool_names": [t.get("tool_name") for t in tools if t.get("tool_name")],
#             "minimum_plan_level": data.get("minimum_plan_level", 1),
#             "is_featured": data.get("is_featured", False),
#         }


# def _get_ext(filename: str) -> str:
#     """Extract file extension"""
#     import os
#     return os.path.splitext((filename or "").lower())[1]






"""
prebuilt_agent_service.py

Business logic for prebuilt agents:
1. Grant prebuilt agents to new tenants
2. Check tool authorization status
3. Activate prebuilt agents (clone to tbl_agents with user's credentials)
"""

import logging
from datetime import datetime
from app.models.prebuilt_agent import PrebuiltAgent
from app.models.prebuilt_agent_tools import PrebuiltAgentTools
from app.models.tenant_prebuilt_agents import TenantPrebuiltAgents
from app.models.agent import Agent
from app.models.tool_authorization import ToolAuthorization
from app.models.mcp_agent_tools import McpAgentTools
from app.models.llm import LLM
from app.database.DatabaseOperationPostgreSQL import db_session

logger = logging.getLogger(__name__)


class PrebuiltAgentService:
    """
    Handles prebuilt agent lifecycle for tenants.
    """
    
    def grant_prebuilt_agents_to_tenant(self, tenant_id: int, plan: str = "basic") -> dict:
        """
        Grant prebuilt agents to a new tenant based on their plan.
        
        Called after user registration and plan purchase.
        
        Args:
            tenant_id: The new tenant's ID
            plan: Their subscription plan (basic/pro/enterprise)
            
        Returns:
            {"status": "success", "granted_count": 5, "agents": [...]}
        """
        session = next(db_session())
        try:
            # Fetch active prebuilt agents
            # TODO: Filter by plan if needed (basic gets fewer agents)
            prebuilt_agents = (
                session.query(PrebuiltAgent)
                .filter_by(is_active=True, del_flg=False)
                .all()
            )
            
            granted = []
            
            for prebuilt in prebuilt_agents:
                # Check if already granted
                existing = (
                    session.query(TenantPrebuiltAgents)
                    .filter_by(
                        tenant_id=tenant_id,
                        prebuilt_agent_id=prebuilt.prebuilt_agent_id
                    )
                    .first()
                )
                
                if existing:
                    logger.debug(
                        "prebuilt_agent_service: agent %d already granted to tenant %d",
                        prebuilt.prebuilt_agent_id, tenant_id
                    )
                    continue
                
                # Check missing tools
                missing_tools = self._check_missing_tools(session, tenant_id, prebuilt.prebuilt_agent_id)
                
                # Grant access
                grant = TenantPrebuiltAgents(
                    tenant_id=tenant_id,
                    prebuilt_agent_id=prebuilt.prebuilt_agent_id,
                    status='ready' if len(missing_tools) == 0 else 'pending_tools',
                    missing_tools=missing_tools,
                    granted_at=datetime.utcnow(),
                    last_checked_at=datetime.utcnow(),
                )
                session.add(grant)
                granted.append(prebuilt.agent_name)
                
                logger.info(
                    "prebuilt_agent_service: granted agent '%s' to tenant %d (status=%s)",
                    prebuilt.agent_name, tenant_id, grant.status
                )
            
            session.commit()
            
            return {
                "status": "success",
                "granted_count": len(granted),
                "agents": granted,
            }
        
        except Exception as exc:
            session.rollback()
            logger.exception("prebuilt_agent_service: error granting agents to tenant")
            return {"status": "error", "message": str(exc)}
        
        finally:
            session.close()
    
    def get_available_prebuilt_agents(self, tenant_id: int) -> dict:
        """
        Get all prebuilt agents available to a tenant with authorization status.
        
        Returns:
            {
                "agents": [
                    {
                        "prebuilt_agent_id": 1,
                        "agent_name": "Email Assistant",
                        "status": "ready" | "pending_tools" | "active",
                        "required_tools": ["gmail", "system"],
                        "missing_tools": ["gmail"],
                        "agent_id": 123 (if activated)
                    }
                ]
            }
        """
        session = next(db_session())
        try:
            # Get tenant's granted agents
            grants = (
                session.query(TenantPrebuiltAgents)
                .filter_by(tenant_id=tenant_id)
                .all()
            )
            
            result = []
            
            for grant in grants:
                # Get prebuilt agent details
                prebuilt = (
                    session.query(PrebuiltAgent)
                    .filter_by(
                        prebuilt_agent_id=grant.prebuilt_agent_id,
                        del_flg=False
                    )
                    .first()
                )
                
                if not prebuilt:
                    continue
                
                # Get required tools
                required_tools = (
                    session.query(PrebuiltAgentTools)
                    .filter_by(prebuilt_agent_id=prebuilt.prebuilt_agent_id)
                    .all()
                )
                
                # Update missing tools status
                missing_tools = self._check_missing_tools(session, tenant_id, prebuilt.prebuilt_agent_id)
                
                if grant.status != 'active':
                    new_status = 'ready' if len(missing_tools) == 0 else 'pending_tools'
                    if grant.status != new_status:
                        grant.status = new_status
                        grant.missing_tools = missing_tools
                        grant.last_checked_at = datetime.utcnow()
                        session.commit()
                
                result.append({
                    **prebuilt.to_dict(),
                    "grant_id": grant.id,
                    "status": grant.status,
                    "required_tools": [t.tool_name for t in required_tools],
                    "missing_tools": missing_tools,
                    "agent_id": grant.agent_id,
                    "activated_at": grant.activated_at.isoformat() if grant.activated_at else None,
                })
            
            return {"agents": result}
        
        finally:
            session.close()
    
    def activate_prebuilt_agent(self, tenant_id: int, prebuilt_agent_id: int) -> dict:
        """
        Activate a prebuilt agent for a tenant by cloning it to tbl_agents.
        
        Uses tenant's own tool credentials from tbl_tool_authorization.
        
        Args:
            tenant_id: The tenant activating the agent
            prebuilt_agent_id: The prebuilt agent to activate
            
        Returns:
            {"status": "success", "agent_id": 123}
            or
            {"status": "error", "message": "...", "missing_tools": ["gmail"]}
        """
        session = next(db_session())
        try:
            # Check grant exists
            grant = (
                session.query(TenantPrebuiltAgents)
                .filter_by(
                    tenant_id=tenant_id,
                    prebuilt_agent_id=prebuilt_agent_id
                )
                .first()
            )
            
            if not grant:
                return {
                    "status": "error",
                    "message": "You don't have access to this prebuilt agent."
                }
            
            # Check if already activated
            if grant.status == 'active' and grant.agent_id:
                return {
                    "status": "error",
                    "message": "This prebuilt agent is already activated.",
                    "agent_id": grant.agent_id
                }
            
            # Check tool authorization
            missing_tools = self._check_missing_tools(session, tenant_id, prebuilt_agent_id)
            
            if missing_tools:
                return {
                    "status": "error",
                    "message": "Please connect the required tools before activating this agent.",
                    "missing_tools": missing_tools
                }
            
            # Get prebuilt agent
            prebuilt = (
                session.query(PrebuiltAgent)
                .filter_by(
                    prebuilt_agent_id=prebuilt_agent_id,
                    del_flg=False
                )
                .first()
            )
            
            if not prebuilt:
                return {
                    "status": "error",
                    "message": "Prebuilt agent not found."
                }
            
            # Resolve LLM IDs for tenant
            llm_provider_id, llm_model_id = self._resolve_llm_ids(
                session, tenant_id, prebuilt.llm_provider, prebuilt.llm_model
            )
            
            if not llm_provider_id or not llm_model_id:
                return {
                    "status": "error",
                    "message": f"LLM {prebuilt.llm_provider}/{prebuilt.llm_model} not configured for your account. Please add it in LLM Settings first."
                }
            
            # Resolve tool_id (required by Agent table)
            required_tools = (
                session.query(PrebuiltAgentTools)
                .filter_by(prebuilt_agent_id=prebuilt_agent_id)
                .all()
            )
            
            first_tool_name = required_tools[0].tool_name if required_tools else None
            tool_id = self._resolve_tool_id(session, first_tool_name)
            
            # Clone to tbl_agents
            agent = Agent(
                tenant_id=tenant_id,
                agent_name=prebuilt.agent_name,
                agent_description=prebuilt.agent_description,
                agent_role=prebuilt.agent_role,
                agent_instructions=prebuilt.agent_instructions,
                additional_instructions=prebuilt.additional_instructions,
                
                llm_provider_id=llm_provider_id,
                llm_model_id=llm_model_id,
                
                tool_id=tool_id,
                tool_type=required_tools[0].tool_type if required_tools else 'local',
                
                memory_plugin=prebuilt.memory_plugin,
                
                features=prebuilt.features,
                safe_ai_settings=prebuilt.safe_ai_settings,
                
                Examples=prebuilt.examples,
                
                knowledge_base_ids=[],
                
                deployment_method='local',
                import_source='prebuilt',
                
                del_flg=False,
            )
            
            session.add(agent)
            session.flush()  # Get agent_id
            
            # Create McpAgentTools entries (so edit page shows tools)
            for tool in required_tools:
                mcp_tool = McpAgentTools(
                    tenant_id=tenant_id,
                    agent_id=agent.agent_id,
                    tool_name=tool.tool_name,
                    mcp_url=tool.mcp_url,
                    action_tools=tool.action_tools or [],
                    action_tools_description=[],
                )
                session.add(mcp_tool)
            
            # Update grant status
            grant.agent_id = agent.agent_id
            grant.status = 'active'
            grant.activated_at = datetime.utcnow()
            
            session.commit()
            session.refresh(agent)
            
            logger.info(
                "prebuilt_agent_service: activated prebuilt agent %d for tenant %d -> agent_id=%d",
                prebuilt_agent_id, tenant_id, agent.agent_id
            )
            
            return {
                "status": "success",
                "agent_id": agent.agent_id,
                "agent": agent.to_dict()
            }
        
        except Exception as exc:
            session.rollback()
            logger.exception("prebuilt_agent_service: error activating prebuilt agent")
            return {"status": "error", "message": str(exc)}
        
        finally:
            session.close()
    
    # ──────────────────────────────────────────────────────────────────────
    # Helper methods
    # ──────────────────────────────────────────────────────────────────────
    
    def _check_missing_tools(self, session, tenant_id: int, prebuilt_agent_id: int) -> list:
        """
        Check which required tools the tenant has NOT authorized yet.
        
        Returns:
            List of tool names (e.g., ["gmail", "hubspot"])
        """
        # Get required tools
        required_tools = (
            session.query(PrebuiltAgentTools)
            .filter_by(
                prebuilt_agent_id=prebuilt_agent_id,
                is_required=True
            )
            .all()
        )
        
        # Get tenant's authorized tools
        authorized_tools = (
            session.query(ToolAuthorization)
            .filter_by(
                tenant_id=tenant_id,
                del_flag=False
            )
            .all()
        )
        
        authorized_tool_names = {t.tool_name.lower() for t in authorized_tools}
        
        # Find missing
        missing = []
        for req_tool in required_tools:
            tool_name = req_tool.tool_name.lower()
            
            # System tools don't need authorization
            if tool_name in {"system", "llm", "file", "text", "invoke"}:
                continue
            
            if tool_name not in authorized_tool_names:
                missing.append(tool_name)
        
        return missing
    
    def _resolve_llm_ids(self, session, tenant_id: int, provider: str, model: str):
        """Resolve LLM provider_id and model_id for tenant"""
        all_llms = (
            session.query(LLM)
            .filter_by(tenant_id=tenant_id, del_flg=False)
            .all()
        )
        
        provider_id = None
        model_id = None
        
        for llm in all_llms:
            if provider_id is None and llm.provider:
                if llm.provider.base_provider.lower() == provider.lower():
                    provider_id = llm.llm_id
            
            if model_id is None and llm.model_name:
                if llm.model_name.base_model_name.lower() == model.lower():
                    model_id = llm.llm_id
        
        return provider_id, model_id
    
    def _resolve_tool_id(self, session, tool_name: str):
        """Resolve tool_id from tbl_tools"""
        from app.models.tool import Tools
        
        if not tool_name:
            # Fallback to any tool
            tool = session.query(Tools).filter_by(del_flg=False).first()
            return tool.tool_id if tool else 1
        
        tool = (
            session.query(Tools)
            .filter(Tools.tool_name.ilike(tool_name), Tools.del_flg == False)
            .first()
        )
        
        if tool:
            return tool.tool_id
        
        # Fallback
        tool = session.query(Tools).filter_by(del_flg=False).first()
        return tool.tool_id if tool else 1