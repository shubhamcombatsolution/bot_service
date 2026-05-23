# ===== FILE: nodes/switch_node.py =====
import json
from engine.base_node import BaseNode
from engine.registry import register_node
import re
from engine.base_node import BaseNode
from engine.logging_config import setup_logging
from nodes.utils.resolver import resolve_field
import logging
import os
from logging_config import setup_logging


logger = setup_logging(__name__, level="DEBUG")



@register_node("SwitchNode")
class SwitchNode(BaseNode):
    def __init__(self, node_id, data):
        self.node_id = node_id
        self.data = data
    def execute(self, context):
        form_data = self.data.get("formData", {})
        
        # This is the field path in context that contains the decision
        switch_field = form_data.get("switch_field")  # e.g., "MailClassifier.tool_output_parameters.0.structuredContent.result.decision"
        
        # These are your conditions — MUST use node IDs, not labels!
        conditions = form_data.get("conditions", [])  # → [{"value": "RFQ_FLOW", "target": "genericagent-123"}, ...]
        default_target = form_data.get("default_target")  # → "genericagent-fallback-999"

        # Resolve the actual decision value (RFQ_FLOW / QUOTATION_FLOW)
        switch_value = resolve_field(context, switch_field)

        logger.info(f"[SwitchNode] Resolved switch value: {switch_value}")

        # Clean and extract decision if wrapped in JSON
        if isinstance(switch_value, str):
            cleaned = re.sub(r"```(?:json)?", "", switch_value).strip()
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict) and "decision" in parsed:
                    switch_value = parsed["decision"]
                elif isinstance(parsed, dict) and "raw_output" in parsed:
                    switch_value = json.loads(parsed["raw_output"]).get("decision")
            except:
                switch_value = cleaned
        elif isinstance(switch_value, dict):
            switch_value = switch_value.get("decision") or switch_value.get("raw_output", "")

        switch_value = str(switch_value).strip().upper()

        logger.info(f"[SwitchNode] Final normalized decision: {switch_value}")

        # Match against conditions using exact string match
        for condition in conditions:
            if condition["value"].strip().upper() == switch_value:
                target_node_id = condition["target"]  # ← This MUST be node ID like "genericagent-123"
                logger.info(f"[SwitchNode] MATCHED → Routing to node ID: {target_node_id}")
                return {
                    "branch": target_node_id,      # ← Return NODE ID
                    "switch_value": switch_value
                }

        # Default fallback
        logger.warning(f"[SwitchNode] No match for '{switch_value}', using default: {default_target}")
        return {
            "branch": default_target,  # ← This must also be a node ID
            "switch_value": switch_value
        }

    # def execute(self, context):
    #     """Executes switch logic to decide next branch dynamically."""
    #     form_data = self.data.get("formData", {})
    #     switch_field = form_data.get("switch_field")
    #     conditions = form_data.get("conditions", [])
    #     default_target = form_data.get("default_target")

    #     # Extract the switch value
    #     switch_value = self._resolve_field(context, switch_field)
    #     logger.info(f"[SwitchNode] Raw switch value: {switch_value}")

    #     # --- STEP 1: Clean and parse if it's wrapped in markdown or invalid JSON ---
    #     if isinstance(switch_value, str):
    #         cleaned = re.sub(r"```(?:json)?", "", switch_value).strip()
    #         try:
    #             parsed = json.loads(cleaned)
    #             # if parsed has a key "decision", use that value
    #             if isinstance(parsed, dict) and "decision" in parsed:
    #                 switch_value = parsed["decision"]
    #         except json.JSONDecodeError:
    #             # not a JSON, just keep the cleaned text
    #             switch_value = cleaned

    #     logger.info(f"[SwitchNode] Normalized switch value: {switch_value}")

    #     # --- STEP 2: Match the switch_value against conditions ---
    #     for condition in conditions:
    #         if condition["value"].lower() == str(switch_value).lower():
    #             logger.info(f"[SwitchNode] Matched branch: {condition['target']}")
    #             return {
    #                 "branch": condition["target"],
    #                 "switch_value": switch_value,
    #             }

    #     # --- STEP 3: Fallback ---
    #     logger.info(f"[SwitchNode] No match found, using default branch: {default_target}")
    #     return {
    #         "branch": default_target,
    #         "switch_value": switch_value,
    #     }


    def _resolve_field(self, context, path):
        if not path:
            return None
        
        parts = path.split(".")
    
        # 1️⃣ FIRST: direct parent inputs
        if parts[0] in context:
            try:
                return self._deep_get(context[parts[0]], parts[1:])
            except:
                pass
    
        # 2️⃣ SECOND: node_outputs by node_id
        node_outputs = context.get("node_outputs", {})
        if parts[0] in node_outputs:
            try:
                return self._deep_get(node_outputs[parts[0]], parts[1:])
            except:
                pass
    
        # 3️⃣ THIRD: node_outputs by LABEL alias
        for key, value in node_outputs.items():
            normalized = key.lower().replace(" ", "")
            if normalized == parts[0].lower().replace(" ", ""):
                try:
                    return self._deep_get(value, parts[1:])
                except:
                    pass
    
        logger.error(f"[SwitchNode] Cannot resolve path: {path}")
        return None
    
    
    def _deep_get(self, obj, keys):
        """Safely traverse nested dict/list using a list of keys"""
        for key in keys:
            if isinstance(obj, list):
                key = int(key)
                obj = obj[key]
            else:
                obj = obj.get(key)
        return obj

    # def _resolve_field(self, context, path):
    #     if not path:
    #         return None
    #     try:
    #         parts = path.split(".")
    #         value = context
    #         for p in parts:
    #             if isinstance(value, dict):
    #                 value = value.get(p)
    #             elif isinstance(value, list) and p.isdigit():
    #                 value = value[int(p)]
    #             else:
    #                 raise KeyError(p)
    #         return value
    #     except Exception as e:
    #         logger.error(f"[SwitchNode] Failed to resolve path '{path}': {e}")
    #         return None
    # def _resolve_field(self, context, path):
    #     """
    #     Fetches nested value from context using dot notation.
    #     Supports both dicts and lists, e.g.:
    #     'genericagent-13.tool_output_parameters.1.structuredContent.result.status'
    #     """
    #     try:
    #         parts = path.split(".")
    #         value = context
    #         for p in parts:
    #             if isinstance(value, dict):
    #                 value = value.get(p)
    #             elif isinstance(value, list):
    #                 # handle list index
    #                 if p.isdigit():
    #                     idx = int(p)
    #                     if 0 <= idx < len(value):
    #                         value = value[idx]
    #                     else:
    #                         raise IndexError(f"List index out of range: {p}")
    #                 else:
    #                     raise TypeError(f"Expected integer index for list, got key '{p}'")
    #             else:
    #                 raise TypeError(f"Cannot resolve '{p}' in non-iterable type {type(value).__name__}")
    #         return value
    #     except Exception as e:
    #         logger.warning(f"[SwitchNode] Failed to resolve field '{path}': {e}")
    #         return None

       