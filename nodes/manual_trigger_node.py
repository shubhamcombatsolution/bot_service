from typing import Dict, Any

from engine.base_node import BaseNode
from engine.registry import register_node
from logging_config import setup_logging


logger = setup_logging("ManualTriggerNode", level="DEBUG")


@register_node("ManualTriggerNode")
class ManualTriggerNode(BaseNode):
    is_trigger_node = True

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"[MANUAL_TRIGGER] Executing node={self.node_id}")

        payload = inputs.get("inputData")
        if isinstance(payload, dict):
            query = (
                payload.get("query")
                or payload.get("user_query")
                or payload.get("message")
                or payload.get("description")
                or ""
            )
            return {
                **payload,
                "node_id": self.node_id,
                "node_type": "ManualTriggerNode",
                "query": query,
                "user_query": query,
                "message": query,
            }

        query = (
            inputs.get("query")
            or inputs.get("user_query")
            or inputs.get("message")
            or ""
        )

        return {
            "node_id": self.node_id,
            "node_type": "ManualTriggerNode",
            "query": query,
            "user_query": query,
            "message": query,
            "status": "success",
        }
