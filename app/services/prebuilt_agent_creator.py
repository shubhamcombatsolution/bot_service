"""
prebuilt_agent_creator.py

Creates prebuilt agent records in tbl_prebuilt_agents.
NO credentials stored - only agent structure and tool requirements.
"""

import logging
from datetime import datetime

from app.models.prebuilt_agent import PrebuiltAgent
from app.models.prebuilt_agent_tools import PrebuiltAgentTools
from app.database.DatabaseOperationPostgreSQL import db_session
import json


logger = logging.getLogger(__name__)


class PrebuiltAgentCreator:
    """
    Creates prebuilt agent templates in the database.
    Used by Super Admin to add new prebuilt agents.
    """
    def ensure_json(self, obj, default):
        if isinstance(obj, str):
            try:
                return json.loads(obj)
            except:
                return default
        return obj or default
    def create(self, data: dict, created_by_user_id: int = None) -> dict:

        session = next(db_session())

        try:
            logger.info("[CREATOR] Step 1: Start create")

            # ---------------- BASIC DATA ----------------
            logger.info(f"[CREATOR] Incoming keys: {list(data.keys())}")
            logger.info(f"[CREATOR] Agent name: {data.get('agent_name')}")

            # ---------------- LLM ----------------
            llm_cfg = data.get("llm", {})
            logger.info(f"[CREATOR] LLM config: {llm_cfg}")

            provider = (llm_cfg.get("provider") or "").strip().lower()
            model = (llm_cfg.get("model") or "").strip()

            # ---------------- MEMORY ----------------
            memory_cfg = data.get("memory") or {}
            logger.info(f"[CREATOR] Memory config: {memory_cfg}")

            # ---------------- TOOLS ----------------
            tools_list = data.get("tools") or []
            logger.info(f"[CREATOR] Tools count: {len(tools_list)}")

            required_tools = [
                {
                    "tool_name": tool.get("tool_name"),
                    "action_tools": tool.get("action_tools", []),
                }
                for tool in tools_list
            ]

            logger.info(f"[CREATOR] Required tools prepared: {len(required_tools)}")

            # ---------------- CATEGORY ----------------
            category = data.get("category", "General")
            tags = data.get("tags", [])
            logger.info(f"[CREATOR] Category={category}, Tags={tags}")

            # ---------------- CREATE OBJECT ----------------
            logger.info("[CREATOR] Step 2: Creating DB object")

            prebuilt_agent = PrebuiltAgent(
                agent_name=data.get("agent_name", "").strip(),
                agent_description=data.get("agent_description", "").strip(),
                agent_role=data.get("agent_role", "").strip(),
                agent_instructions=data.get("agent_instructions", "").strip(),

                category=category,
                tags=tags,
                is_featured=data.get("is_featured", False),

                llm_provider=provider,
                llm_model=model,

                features=self.ensure_json(data.get("features"), {}),
                safe_ai_settings=self.ensure_json(data.get("safe_ai_settings"), {}),

                memory_enabled=memory_cfg.get("enabled", False),
                memory_type=memory_cfg.get("type"),

                required_tools=required_tools,

                knowledge_base_config=self.ensure_json(data.get("knowledge_base_config"), {}),
                additional_instructions=data.get("additional_instructions"),
                examples=data.get("examples"),

                created_by=created_by_user_id,
            )

            session.add(prebuilt_agent)

            logger.info("[CREATOR] Step 3: Before flush")

            session.flush()

            logger.info(f"[CREATOR] Step 4: Flush done, ID={prebuilt_agent.prebuilt_agent_id}")

            # ---------------- INSERT TOOLS ----------------
            logger.info("[CREATOR] Step 5: Inserting tools")

            for tool in tools_list:
                tool_name = (tool.get("tool_name") or "").strip().lower()
                if not tool_name:
                    continue

                logger.info(f"[CREATOR] Adding tool: {tool_name}")

                tool_row = PrebuiltAgentTools(
                    prebuilt_agent_id=prebuilt_agent.prebuilt_agent_id,
                    tool_name=tool_name,
                    tool_type=tool.get("tool_type", "local"),
                    action_tools=tool.get("action_tools") or [],
                    mcp_url=tool.get("mcp_url"),
                    is_required=tool_name not in {"system", "llm", "text", "file", "invoke"},
                )

                session.add(tool_row)

            logger.info("[CREATOR] Step 6: Before commit")

            session.commit()

            logger.info("[CREATOR] Step 7: Commit successful")

            session.refresh(prebuilt_agent)

            return {
                "status": "success",
                "prebuilt_agent_id": prebuilt_agent.prebuilt_agent_id,
                "prebuilt_agent": prebuilt_agent.to_dict(),
            }

        except Exception as exc:
            logger.exception(f"[CREATOR ERROR] {str(exc)}")
            session.rollback()
            return {
                "status": "error",
                "message": f"Failed to create prebuilt agent: {str(exc)}"
            }

        finally:
            session.close()
