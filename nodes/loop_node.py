
from engine.base_node import BaseNode
from engine.registry import register_node
from nodes.utils.resolver import resolve_field
from logging_config import setup_logging

logger = setup_logging("loop_node", level="DEBUG")


@register_node("LoopNode")
class LoopNode(BaseNode):
    """
    Generic structural loop node.

    Executes downstream nodes repeatedly until all items in iteration_source
    have been processed. Supports:
    - List iteration
    - Batch iteration
    - Continue branch (looping)
    - Done branch (loop complete)
    - Aggregation of results
    """

    def __init__(self, node_id, data):
        super().__init__(node_id, data)
        self.node_id = node_id
        self.form = (data or {}).get("formData", {}) or {}

    # ---------------------------------------------------------------------
    # Resolve list source
    # ---------------------------------------------------------------------
    def _resolve_list(self, context):
        # Literal list is highest priority
        if "literal_list" in self.form and self.form["literal_list"] is not None:
            return list(self.form["literal_list"])

        # Path resolution (most common)
        source_path = self.form.get("iteration_source")
        if source_path:
            resolved = resolve_field(context, source_path)
            if isinstance(resolved, list):
                return resolved
            if isinstance(resolved, dict) and "items" in resolved:
                return resolved["items"]
            if resolved is not None:
                return [resolved]

        # Fallback empty list
        return []

    # ---------------------------------------------------------------------
    # Node Execution
    # ---------------------------------------------------------------------
    def execute(self, context: dict) -> dict:
        """
        Return one of two states:
        1) Continue loop:
           {
             "__loop_requeue__": true,
             "branch": continue_branch,
             loop_variable: {...current item...},
             _loop_index: nextIndex,
             _loop_results: [...],
             _processed_count: n
           }

        2) Loop done:
           {
             "__loop_done__": true,
             "branch": done_branch,
             "results": [...],
             _processed_count: n
           }
        """

        # Previous state (if exists)
        previous_state = context.get("node_outputs", {}).get(self.node_id, {}) or {}

        # Read or compute source list
        if "_loop_source" in previous_state:
            source_list = previous_state["_loop_source"]
        else:
            source_list = self._resolve_list(context)

        # Read loop variables
        index = previous_state.get("_loop_index", 0)
        processed_count = previous_state.get("_processed_count", 0)
        aggregation = previous_state.get("_loop_results", [])
        batch_size = int(self.form.get("batch_size", 1))

        continue_branch = self.form.get("continue_branch")
        done_branch = self.form.get("done_branch")
        loop_var = self.form.get("loop_variable", "item")

        # If loop finished
        if index >= len(source_list):
            return {
                "__loop_done__": True,
                "branch": done_branch,
                "results": aggregation,
                "_processed_count": processed_count
            }

        # Extract current batch
        batch = source_list[index:index + batch_size]
        next_index = index + len(batch)

        # Build context variable for downstream nodes
        iter_payload = batch if batch_size > 1 else batch[0]

        # Loop state update
        new_state = {
            "__loop_requeue__": True,
            "branch": continue_branch,
            loop_var: iter_payload,
            "_loop_source": source_list,
            "_loop_index": next_index,
            "_loop_results": aggregation,
            "_processed_count": processed_count + len(batch),
        }

        return new_state
