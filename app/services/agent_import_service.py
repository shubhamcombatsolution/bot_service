# """
# agent_import_service.py
# Orchestrates:  parse  →  validate  →  create
# """

# import logging

# from .agent_parser    import AgentParser
# # from .agent_validator import AgentValidator
# from .agent_creator   import AgentCreator




# # agent_import_service.py

# from app.services.agent_validator import AgentValidator
# from app.database.DatabaseOperationPostgreSQL import db_session

# def validate_agent(data: dict, tenant_id: int):
#     """Validate agent with tenant context for credential checking"""
    
#     session = next(db_session())
#     try:
#         # Initialize validator with tenant context
#         validator = AgentValidator(tenant_id=tenant_id, session=session)
        
#         # Validate
#         # result = validator.validate(data)
#         result = validator.validate(data)
#         return result
#     finally:
#         session.close()

# logger = logging.getLogger(__name__)

# # Maps file extension to a human-readable source label stored on the Agent row
# _SOURCE_MAP = {
#     ".json": "json",
#     ".zip":  "zip",
#     ".py":   "python",
#     ".js":   "javascript",
# }


# class AgentImportService:

#     def __init__(self, tenant_id: int):
#         self.tenant_id = tenant_id
#         self.parser    = AgentParser()
#         # self.validator = AgentValidator()
#         validator = AgentValidator(tenant_id=tenant_id, session=session)
#         self.creator   = AgentCreator()

#     # ──────────────────────────────────────────────────────────────────────
#     # Public API
#     # ──────────────────────────────────────────────────────────────────────

#     def validate(self, file) -> dict:
#         """
#         Dry-run: parse + validate only.  No DB writes.
#         Returns:
#           {"valid": True|False, "errors": [...], "warnings": [...],
#            "preview": {agent_name, agent_description, agent_role, llm, tools_count}}
#         """
#         try:
#             data = self.parser.parse(file)
#         except ValueError as exc:
#             return {
#                 "valid":    False,
#                 "errors":   [str(exc)],
#                 "warnings": [],
#                 "preview":  None,
#             }
#         except Exception as exc:
#             logger.exception("agent_import_service.validate: unexpected parse error")
#             return {
#                 "valid":    False,
#                 "errors":   [f"Unexpected parse error: {exc}"],
#                 "warnings": [],
#                 "preview":  None,
#             }

#         # result = self.validator.validate(data)

#         # # Build a safe preview for the UI (no credentials exposed)
#         # if result["valid"]:
#         #     result["preview"] = self._build_preview(data)

#         # return result



#         # --------------------------------------------------
#         # ⭐ MULTI-AGENT SUPPORT
#         # --------------------------------------------------
#         if isinstance(data, list):
#             results = []
#             overall_valid = True

#             for idx, agent_data in enumerate(data):
#                 res = self.validator.validate(agent_data)

#                 if res["valid"]:
#                     res["preview"] = self._build_preview(agent_data)
#                 else:
#                     overall_valid = False

#                 results.append({
#                     "index": idx,
#                     **res,
#                 })

#             return {
#                 "valid": overall_valid,
#                 "multi_agent": True,
#                 "count": len(results),
#                 "results": results,
#                 "preview": None,
#             }

#         # --------------------------------------------------
#         # ⭐ SINGLE AGENT (existing behavior)
#         # --------------------------------------------------
#         result = self.validator.validate(data)

#         if result["valid"]:
#             result["preview"] = self._build_preview(data)

#         return result






#     def import_agent(self, file) -> dict:
#         """
#         Full pipeline:  parse → validate → create.
#         Returns:
#           {"status": "success", "agent_id": <int>, "agent": {...}}
#           or
#           {"status": "error",   "errors": [...], "warnings": [...]}
#         """
#         # ── Parse ──
#         try:
#             filename = getattr(file, "filename", "")
#             ext = _get_ext(filename)
#             data = self.parser.parse(file)
#             # data["_import_source"] = _SOURCE_MAP.get(ext, "json")
#             source = _SOURCE_MAP.get(ext, "json")
#         except ValueError as exc:
#             return {"status": "error", "errors": [str(exc)], "warnings": []}
#         except Exception as exc:
#             logger.exception("agent_import_service.import_agent: parse error")
#             return {
#                 "status":   "error",
#                 "errors":   [f"File parse error: {exc}"],
#                 "warnings": [],
#             }

#         # ── Validate ──
#         # validation = self.validator.validate(data)
#         # if not validation["valid"]:
#             # return {
#                 # "status":   "error",
#                 # "errors":   validation["errors"],
#                 # "warnings": validation["warnings"],
#             # }
# # 
#         # ── Create ──
#         # result = self.creator.create(data, self.tenant_id)
# # 
#         # if result["status"] == "error":
#             # return {
#                 # "status":   "error",
#                 # "errors":   [result.get("message", "Unknown error during creation.")],
#                 # "warnings": validation["warnings"],
#             # }
# # 
#         # return {
#             # "status":   "success",
#             # "agent_id": result["agent_id"],
#             # "agent":    result["agent"],
#             # "warnings": validation["warnings"],   # pass non-blocking warnings through
#         # }




#                 # --------------------------------------------------
#         # ⭐ MULTI-AGENT IMPORT
#         # --------------------------------------------------
#         if isinstance(data, list):
#             created = []
#             failed = []

#             for idx, agent_data in enumerate(data):
#                 # agent_data["_import_source"] = _SOURCE_MAP.get(ext, "json")
#                 agent_data["_import_source"] = source

#                 validation = self.validator.validate(agent_data)
#                 if not validation["valid"]:
#                     failed.append({
#                         "index": idx,
#                         "errors": validation["errors"],
#                         "warnings": validation["warnings"],
#                     })
#                     continue

#                 result = self.creator.create(agent_data, self.tenant_id)

#                 if result["status"] == "success":
#                     created.append(result)
#                 else:
#                     failed.append({
#                         "index": idx,
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

#         # --------------------------------------------------
#         # ⭐ SINGLE AGENT (existing behavior)
#         # --------------------------------------------------
#         # data["_import_source"] = _SOURCE_MAP.get(ext, "json")
#         data["_import_source"] = source

#         validation = self.validator.validate(data)
#         if not validation["valid"]:
#             return {
#                 "status": "error",
#                 "errors": validation["errors"],
#                 "warnings": validation["warnings"],
#             }

#         result = self.creator.create(data, self.tenant_id)

#         if result["status"] == "error":
#             return {
#                 "status": "error",
#                 "errors": [result.get("message", "Unknown error during creation.")],
#                 "warnings": validation["warnings"],
#             }

#         return {
#             "status": "success",
#             "agent_id": result["agent_id"],
#             "agent": result["agent"],
#             "warnings": validation["warnings"],
#         }










#     # ──────────────────────────────────────────────────────────────────────
#     # Helpers
#     # ──────────────────────────────────────────────────────────────────────

#     def _build_preview(self, data: dict) -> dict:
#         """Return a safe summary dict for the UI confirmation panel."""
#         tools = data.get("tools") or []
#         return {
#             "agent_name":        data.get("agent_name", ""),
#             "agent_description": data.get("agent_description", ""),
#             "agent_role":        (data.get("agent_role") or "")[:200],
#             "llm_provider":      (data.get("llm") or {}).get("provider", ""),
#             "llm_model":         (data.get("llm") or {}).get("model", ""),
#             "memory_type":       (data.get("memory") or {}).get("type"),
#             "memory_enabled":    (data.get("memory") or {}).get("enabled", False),
#             "tools_count":       len(tools),
#             "tool_names":        [t.get("tool_name") for t in tools if t.get("tool_name")],
#             "kb_ids":            (data.get("knowledge_base") or {}).get("ids", []),
#             "kb_names":          (data.get("knowledge_base") or {}).get("names", []),
#             "has_examples":      bool(data.get("Examples")),
#             "features":          data.get("features") or {},
#         }


# def _get_ext(filename: str) -> str:
#     import os
#     return os.path.splitext((filename or "").lower())[1]






"""
agent_import_service.py

Orchestrates the agent import pipeline:
  1. Parse    → Extract agent data from JSON/ZIP/Python files
  2. Validate → Check schema, credentials, expiry, matching
  3. Create   → Insert into database (Agent + ToolAuthorization + McpAgentTools)

Enhanced with:
  - Credential validation against stored DB credentials
  - Token expiry checking
  - Credential mismatch detection
  - Multi-agent bundle support
"""

import logging
from .agent_parser import AgentParser
from .agent_creator import AgentCreator
from app.services.agent_validator import AgentValidator
from app.database.DatabaseOperationPostgreSQL import db_session

logger = logging.getLogger(__name__)

# Maps file extension to a human-readable source label stored on the Agent row
_SOURCE_MAP = {
    ".json": "json",
    ".zip":  "zip",
    ".py":   "python",
    ".js":   "javascript",
}


class AgentImportService:
    """
    Main service for importing external agent configurations.
    
    Handles both single-agent and multi-agent imports with full validation.
    """

    def __init__(self, tenant_id: int):
        """
        Initialize the import service.
        
        Args:
            tenant_id: The tenant ID for database operations and credential validation
            
        Note: 
            AgentValidator is NOT created here because it needs a fresh database 
            session per operation to avoid connection leaks and ensure thread safety.
        """
        self.tenant_id = tenant_id
        self.parser = AgentParser()
        self.creator = AgentCreator()

    # ══════════════════════════════════════════════════════════════════════
    # PUBLIC API
    # ══════════════════════════════════════════════════════════════════════

    def validate(self, file) -> dict:
        """
        Dry-run validation: parse + validate only. No database writes.
        
        This endpoint is called by the frontend to show validation results
        before the user confirms the import.
        
        Args:
            file: FileStorage object (Flask) or UploadFile (FastAPI)
            
        Returns:
            Single agent:
            {
                "valid": True/False,
                "errors": ["error messages..."],
                "warnings": ["warning messages..."],
                "preview": {
                    "agent_name": "...",
                    "llm_provider": "OpenAI",
                    "tools_count": 3,
                    ...
                }
            }
            
            Multi-agent bundle:
            {
                "valid": True/False (all must be valid),
                "multi_agent": True,
                "count": 5,
                "results": [
                    {"index": 0, "valid": True, "errors": [], "preview": {...}},
                    {"index": 1, "valid": False, "errors": ["..."], "preview": None},
                    ...
                ]
            }
        """
        # ──────────────────────────────────────────────────────────────────
        # STEP 1: Parse the uploaded file
        # ──────────────────────────────────────────────────────────────────
        try:
            data = self.parser.parse(file)
            logger.info(
                "agent_import_service.validate: parsed file successfully "
                "(type: %s, count: %d)",
                "multi" if isinstance(data, list) else "single",
                len(data) if isinstance(data, list) else 1
            )
        except ValueError as exc:
            logger.error("agent_import_service.validate: parse failed - %s", exc)
            return {
                "valid": False,
                "errors": [str(exc)],
                "warnings": [],
                "preview": None,
            }
        except Exception as exc:
            logger.exception("agent_import_service.validate: unexpected parse error")
            return {
                "valid": False,
                "errors": [f"Unexpected parse error: {exc}"],
                "warnings": [],
                "preview": None,
            }

        # ──────────────────────────────────────────────────────────────────
        # STEP 2: Validate with enhanced credential checking
        # ──────────────────────────────────────────────────────────────────
        session = next(db_session())
        try:
            # Create validator with tenant context for DB credential lookup
            validator = AgentValidator(
                tenant_id=self.tenant_id, 
                session=session
            )

            # ══════════════════════════════════════════════════════════════
            # MULTI-AGENT SUPPORT
            # ══════════════════════════════════════════════════════════════
            if isinstance(data, list):
                logger.info(
                    "agent_import_service.validate: processing multi-agent bundle "
                    "with %d agents",
                    len(data)
                )
                
                results = []
                overall_valid = True

                for idx, agent_data in enumerate(data):
                    logger.debug(
                        "agent_import_service.validate: validating agent %d/%d",
                        idx + 1, len(data)
                    )
                    
                    res = validator.validate(agent_data)

                    if res["valid"]:
                        res["preview"] = self._build_preview(agent_data)
                        logger.debug(
                            "agent_import_service.validate: agent %d VALID - %s",
                            idx, agent_data.get("agent_name", "unnamed")
                        )
                    else:
                        overall_valid = False
                        logger.warning(
                            "agent_import_service.validate: agent %d INVALID - %d errors",
                            idx, len(res["errors"])
                        )

                    results.append({
                        "index": idx,
                        **res,
                    })

                logger.info(
                    "agent_import_service.validate: multi-agent validation complete - "
                    "overall_valid=%s, passed=%d, failed=%d",
                    overall_valid,
                    sum(1 for r in results if r["valid"]),
                    sum(1 for r in results if not r["valid"])
                )

                return {
                    "valid": overall_valid,
                    "multi_agent": True,
                    "count": len(results),
                    "results": results,
                    "preview": None,
                }

            # ══════════════════════════════════════════════════════════════
            # SINGLE AGENT (standard flow)
            # ══════════════════════════════════════════════════════════════
            logger.info(
                "agent_import_service.validate: processing single agent"
            )
            
            result = validator.validate(data)

            if result["valid"]:
                result["preview"] = self._build_preview(data)
                logger.info(
                    "agent_import_service.validate: VALID - %s",
                    data.get("agent_name", "unnamed")
                )
            else:
                logger.warning(
                    "agent_import_service.validate: INVALID - %d errors, %d warnings",
                    len(result["errors"]), len(result["warnings"])
                )

            return result

        finally:
            session.close()
            logger.debug("agent_import_service.validate: session closed")

    def import_agent(self, file) -> dict:
        """
        Full import pipeline: parse → validate → create.
        
        This endpoint creates the actual database records after validation passes.
        
        Args:
            file: FileStorage object (Flask) or UploadFile (FastAPI)
            
        Returns:
            Single agent success:
            {
                "status": "success",
                "agent_id": 1108,
                "agent": {...agent dict...},
                "warnings": [...]
            }
            
            Single agent failure:
            {
                "status": "error",
                "errors": ["error messages..."],
                "warnings": [...]
            }
            
            Multi-agent bundle:
            {
                "status": "success",  # or "error" if all failed
                "multi_agent": True,
                "created_count": 4,
                "failed_count": 1,
                "created": [
                    {"agent_id": 1108, "agent": {...}},
                    {"agent_id": 1109, "agent": {...}},
                    ...
                ],
                "failed": [
                    {"index": 2, "errors": [...], "warnings": [...]}
                ]
            }
        """
        # ──────────────────────────────────────────────────────────────────
        # STEP 1: Parse the uploaded file
        # ──────────────────────────────────────────────────────────────────
        try:
            filename = getattr(file, "filename", "")
            ext = _get_ext(filename)
            data = self.parser.parse(file)
            source = _SOURCE_MAP.get(ext, "json")
            
            logger.info(
                "agent_import_service.import_agent: parsed file '%s' - "
                "type: %s, source: %s",
                filename,
                "multi" if isinstance(data, list) else "single",
                source
            )
        except ValueError as exc:
            logger.error("agent_import_service.import_agent: parse failed - %s", exc)
            return {"status": "error", "errors": [str(exc)], "warnings": []}
        except Exception as exc:
            logger.exception("agent_import_service.import_agent: parse error")
            return {
                "status": "error",
                "errors": [f"File parse error: {exc}"],
                "warnings": [],
            }

        # ──────────────────────────────────────────────────────────────────
        # STEP 2 & 3: Validate + Create (with fresh session)
        # ──────────────────────────────────────────────────────────────────
        session = next(db_session())
        try:
            validator = AgentValidator(
                tenant_id=self.tenant_id,
                session=session
            )

            # ══════════════════════════════════════════════════════════════
            # MULTI-AGENT IMPORT
            # ══════════════════════════════════════════════════════════════
            if isinstance(data, list):
                logger.info(
                    "agent_import_service.import_agent: importing multi-agent bundle "
                    "with %d agents",
                    len(data)
                )
                
                created = []
                failed = []

                for idx, agent_data in enumerate(data):
                    agent_data["_import_source"] = source
                    agent_name = agent_data.get("agent_name", f"agent_{idx}")

                    logger.debug(
                        "agent_import_service.import_agent: processing agent %d/%d - %s",
                        idx + 1, len(data), agent_name
                    )

                    # Validate
                    validation = validator.validate(agent_data)
                    if not validation["valid"]:
                        logger.warning(
                            "agent_import_service.import_agent: agent %d (%s) "
                            "validation FAILED - %d errors",
                            idx, agent_name, len(validation["errors"])
                        )
                        failed.append({
                            "index": idx,
                            "agent_name": agent_name,
                            "errors": validation["errors"],
                            "warnings": validation["warnings"],
                        })
                        continue

                    # Create
                    result = self.creator.create(agent_data, self.tenant_id)

                    if result["status"] == "success":
                        logger.info(
                            "agent_import_service.import_agent: agent %d (%s) "
                            "created successfully - agent_id=%d",
                            idx, agent_name, result["agent_id"]
                        )
                        created.append(result)
                    else:
                        logger.error(
                            "agent_import_service.import_agent: agent %d (%s) "
                            "creation FAILED - %s",
                            idx, agent_name, result.get("message")
                        )
                        failed.append({
                            "index": idx,
                            "agent_name": agent_name,
                            "errors": [result.get("message")],
                            "warnings": validation["warnings"],
                        })

                logger.info(
                    "agent_import_service.import_agent: multi-agent import complete - "
                    "created=%d, failed=%d",
                    len(created), len(failed)
                )

                return {
                    "status": "success" if created else "error",
                    "multi_agent": True,
                    "created_count": len(created),
                    "failed_count": len(failed),
                    "created": created,
                    "failed": failed,
                }

            # ══════════════════════════════════════════════════════════════
            # SINGLE AGENT (standard flow)
            # ══════════════════════════════════════════════════════════════
            data["_import_source"] = source
            agent_name = data.get("agent_name", "unnamed")

            logger.info(
                "agent_import_service.import_agent: importing single agent - %s",
                agent_name
            )

            # Validate
            validation = validator.validate(data)
            if not validation["valid"]:
                logger.warning(
                    "agent_import_service.import_agent: validation FAILED - "
                    "%d errors, %d warnings",
                    len(validation["errors"]), len(validation["warnings"])
                )
                return {
                    "status": "error",
                    "errors": validation["errors"],
                    "warnings": validation["warnings"],
                }

            # Create
            result = self.creator.create(data, self.tenant_id)

            if result["status"] == "error":
                logger.error(
                    "agent_import_service.import_agent: creation FAILED - %s",
                    result.get("message")
                )
                return {
                    "status": "error",
                    "errors": [result.get("message", "Unknown error during creation.")],
                    "warnings": validation["warnings"],
                }

            logger.info(
                "agent_import_service.import_agent: SUCCESS - "
                "agent_id=%d, name=%s",
                result["agent_id"], agent_name
            )

            return {
                "status": "success",
                "agent_id": result["agent_id"],
                "agent": result["agent"],
                "warnings": validation["warnings"],
            }

        finally:
            session.close()
            logger.debug("agent_import_service.import_agent: session closed")

    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════════════════════════

    def _build_preview(self, data: dict) -> dict:
        """
        Build a safe preview summary for the UI confirmation panel.
        
        This removes sensitive data (credentials) and provides a structured
        summary of what will be imported.
        
        Args:
            data: The validated agent configuration dict
            
        Returns:
            Dictionary with safe preview data (no credentials exposed)
        """
        tools = data.get("tools") or []
        llm = data.get("llm") or {}
        memory = data.get("memory") or {}
        kb = data.get("knowledge_base") or {}
        
        return {
            # Core agent info
            "agent_name": data.get("agent_name", ""),
            "agent_description": data.get("agent_description", ""),
            "agent_role": (data.get("agent_role") or "")[:200],  # Truncate long roles
            
            # LLM configuration
            "llm_provider": llm.get("provider", ""),
            "llm_model": llm.get("model", ""),
            "temperature": llm.get("temperature"),
            "max_tokens": llm.get("max_tokens"),
            
            # Memory settings
            "memory_type": memory.get("type"),
            "memory_enabled": memory.get("enabled", False),
            
            # Tools summary (NO credentials)
            "tools_count": len(tools),
            "tool_names": [
                t.get("tool_name") 
                for t in tools 
                if t.get("tool_name")
            ],
            "tool_types": {
                "local": sum(1 for t in tools if t.get("tool_type") == "local"),
                "mcp": sum(1 for t in tools if t.get("tool_type") == "mcp"),
            },
            
            # Knowledge base summary
            "kb_ids": kb.get("ids", []),
            "kb_names": kb.get("names", []),
            "kb_count": len(kb.get("ids", [])) + len(kb.get("names", [])),
            
            # Additional flags
            "has_examples": bool(data.get("Examples")),
            "has_instructions": bool(data.get("agent_instructions")),
            "features": data.get("features") or {},
            "safe_ai_enabled": bool(data.get("safe_ai_settings")),
        }


# ══════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL HELPER
# ══════════════════════════════════════════════════════════════════════════

def _get_ext(filename: str) -> str:
    """
    Extract file extension from filename.
    
    Args:
        filename: The filename string (e.g., "agent.json", "bundle.zip")
        
    Returns:
        Lowercase extension with dot (e.g., ".json", ".zip")
    """
    import os
    return os.path.splitext((filename or "").lower())[1]