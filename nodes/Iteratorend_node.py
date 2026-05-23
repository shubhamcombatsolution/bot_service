# ===== FILE: nodes/iterator_end_node.py =====
import logging
from engine.base_node import BaseNode
from engine.registry import register_node
from engine.logging_config import setup_logging

logger = setup_logging(__name__, level=logging.DEBUG)

@register_node("IteratorEndNode")
class IteratorEndNode(BaseNode):
    """
    Collects all outputs from nodes inside the iterator loop.
    Runs only after IteratorStart says "done".
    """
    def __init__(self, node_id, data):
        self.node_id = node_id
        self.data = data
        self.collected = []

    def execute(self, context):
        iterator_id = self.data.get("formData", {}).get("iterator_start_id")
        if not iterator_id:
            logger.error("[IteratorEndNode] Missing iterator_start_id")
            return {"error": "iterator_start_id required"}

        state = context.get(f"_iterator_{iterator_id}", {})
        if not state:
            logger.warning("[IteratorEndNode] No iterator state found")
            return {"results": self.collected}

        # Check if we're in a batch
        batch_output = context.get("node_output")  # Output from last node in loop
        if batch_output and not batch_output.get("done"):
            # Collect current batch result
            self.collected.append(batch_output)
            return {"continue": True}  # Tell engine to continue loop

        # Final run: iteration done
        results = self.collected
        logger.info(f"[IteratorEndNode] Iteration complete. Collected {len(results)} batch results.")

        # Optional: Flatten if batch_size > 1
        form_data = self.data.get("formData", {})
        if form_data.get("flatten", True):
            flat = []
            for batch in results:
                if isinstance(batch, dict) and "batch" in batch:
                    flat.extend(batch["batch"])
                else:
                    flat.append(batch)
            results = flat

        # Clean up
        context.pop(f"_iterator_{iterator_id}", None)
        self.collected = []

        return {"results": results, "total_batches": len(results)}