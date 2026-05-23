# ===== FILE: nodes/iterator_start_node.py =====
import logging
from engine.base_node import BaseNode
from engine.registry import register_node
from engine.logging_config import setup_logging
from nodes.utils.resolver import resolve_field

logger = setup_logging(__name__, level=logging.DEBUG)

@register_node("IteratorStartNode")
class IteratorStartNode(BaseNode):
    """
    Starts iteration over a list (e.g., text chunks).
    Input: list from previous node (e.g., chunks from TextSplitter)
    Output per iteration: single item (e.g., one chunk)
    """
    def __init__(self, node_id, data):
        self.node_id = node_id
        self.data = data
        self.iteration_index = 0

    def execute(self, context):
        form_data = self.data.get("formData", {})
        input_field = form_data.get("input_field")  # e.g., "chunks"
        batch_size = int(form_data.get("batch_size", 1))

        # Resolve the list to iterate over
        input_list = resolve_field(context, input_field)
        if not isinstance(input_list, list):
            logger.error(f"[IteratorStartNode] Expected list, got {type(input_list)}")
            return {"error": "Input must be a list"}

        total = len(input_list)
        logger.info(f"[IteratorStartNode] Starting iteration over {total} items (batch_size={batch_size})")

        # Store iteration state in context
        context[f"_iterator_{self.node_id}"] = {
            "items": input_list,
            "batch_size": batch_size,
            "total": total,
            "current_batch": []
        }

        # Return first batch
        return self._get_next_batch(context)

    def _get_next_batch(self, context):
        state = context.get(f"_iterator_{self.node_id}", {})
        items = state.get("items", [])
        batch_size = state.get("batch_size", 1)
        index = state.get("index", 0)

        if index >= len(items):
            return {"done": True}  # Signal end

        batch = items[index:index + batch_size]
        context[f"_iterator_{self.node_id}"]["index"] = index + batch_size
        context[f"_iterator_{self.node_id}"]["current_batch"] = batch

        logger.debug(f"[IteratorStartNode] Emitting batch {index // batch_size + 1}: {len(batch)} items")
        return {"batch": batch, "batch_index": index // batch_size}