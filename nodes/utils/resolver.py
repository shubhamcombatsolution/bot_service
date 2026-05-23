# ===== engine/utils/resolver.py =====
import re

from logging_config import setup_logging


logger = setup_logging(__name__, level="DEBUG")




# def resolve_field(context, path):
#     """
#     Universal resolver that supports:
#     1. Direct parent inputs  (context[source_node_id])
#     2. node_outputs by node_id
#     3. node_outputs by node LABEL (alias)
#     4. Nested access a.b.c.0.field
#     5. Case-insensitive & space-insensitive label matching
#     6. Label-to-ID mapping from workflow metadata
#     7. Label-[ID] format extraction (e.g., "Decision Agent-[decisionrouter-7]")
#     """

#     if not path:
#         logger.warning("[Resolver] Empty path provided")
#         return None

#     logger.info(f"[Resolver] 🔍 Resolving path: '{path}'")
#     logger.info(f"[Resolver] Context keys: {list(context.keys())}")

#     parts = path.split(".")
#     logger.info(f"[Resolver] Path parts: {parts}")

#     # ------------------------
#     # 🆕 BRACKET ID EXTRACTION
#     # Extract ID from "Label-[node-id]" format
#     # ------------------------
#     extracted_id = None
#     if '[' in parts[0] and parts[0].endswith(']'):
#         try:
#             # Extract: "Decision Agent-[decisionrouter-7]" -> "decisionrouter-7"
#             extracted_id = parts[0].split('[')[-1].rstrip(']')
#             logger.info(f"[Resolver] 🔍 Extracted ID from brackets: '{extracted_id}'")
#         except Exception as e:
#             logger.warning(f"[Resolver] ⚠️ Failed to extract ID from brackets: {e}")

#     # ------------------------
#     # 1️⃣ Direct context parent input
#     # ------------------------
#     if parts[0] in context:
#         logger.info(f"[Resolver] ✅ Found '{parts[0]}' in direct context")
#         value = _deep_get(context[parts[0]], parts[1:])
#         if value is not None:
#             logger.info(f"[Resolver] ✅ Resolved from direct context: {type(value)}")
#             return value
#         logger.warning(f"[Resolver] ⚠️ Direct context key exists but deep_get returned None")

#     # ------------------------
#     # 2️⃣ node_outputs by node_id (including extracted bracket ID)
#     # ------------------------
#     node_outputs = context.get("node_outputs", {})
#     logger.info(f"[Resolver] node_outputs keys: {list(node_outputs.keys())}")
    
#     # Try exact match first
#     if parts[0] in node_outputs:
#         logger.info(f"[Resolver] ✅ Found '{parts[0]}' in node_outputs by ID")
#         value = _deep_get(node_outputs[parts[0]], parts[1:])
#         if value is not None:
#             logger.info(f"[Resolver] ✅ Resolved from node_outputs by ID: {type(value)}")
#             return value
#         logger.warning(f"[Resolver] ⚠️ node_outputs key exists but deep_get returned None")
    
#     # 🆕 Try extracted bracket ID
#     if extracted_id and extracted_id in node_outputs:
#         logger.info(f"[Resolver] ✅ Found extracted ID '{extracted_id}' in node_outputs")
#         value = _deep_get(node_outputs[extracted_id], parts[1:])
#         if value is not None:
#             logger.info(f"[Resolver] ✅ Resolved from node_outputs using extracted ID: {type(value)}")
#             return value
#         logger.warning(f"[Resolver] ⚠️ Extracted ID exists but deep_get returned None")

#     # ------------------------
#     # 3️⃣ Build label-to-id mapping from workflow metadata
#     # ------------------------
#     label_to_id_map = _build_label_to_id_map(context)
#     logger.debug(f"[Resolver] Label-to-ID map: {label_to_id_map}")

#     # ------------------------
#     # 4️⃣ Try to resolve using label-to-id mapping first
#     # ------------------------
#     normalized_target = parts[0].lower().replace(" ", "")
    
#     if normalized_target in label_to_id_map:
#         actual_node_id = label_to_id_map[normalized_target]
#         logger.info(f"[Resolver] ✅ Mapped label '{parts[0]}' to node_id '{actual_node_id}'")
        
#         if actual_node_id in node_outputs:
#             value = _deep_get(node_outputs[actual_node_id], parts[1:])
#             if value is not None:
#                 logger.info(f"[Resolver] ✅ Resolved via label mapping: {type(value)}")
#                 return value
#             logger.warning(f"[Resolver] ⚠️ Label mapped but deep_get returned None")


#     # ------------------------
#     # 🧯 4.5️⃣ LEGACY BACKWARD-COMPAT LABEL → ID INFERENCE
#     # (supports old label-only paths like EmailFetcher.xxx)
#     # ------------------------
#     for node_id, value in node_outputs.items():
#         # Normalize node_id (emailfetcher-1 → emailfetcher)
#         normalized_node_id = (
#             node_id
#             .lower()
#             .replace("-", "")
#             .replace("_", "")
#         )

#         if normalized_node_id.startswith(normalized_target):
#             logger.warning(
#                 f"[Resolver][LEGACY] Label-only path '{parts[0]}' "
#                 f"resolved via node_id '{node_id}'. "
#                 f"Use 'Label-[{node_id}]' for deterministic behavior."
#             )

#             result = _deep_get(value, parts[1:])
#             if result is not None:
#                 logger.info(
#                     f"[Resolver] ✅ Resolved via LEGACY label→id inference: {type(result)}"
#                 )
#                 return result


#     # ------------------------
#     # 5️⃣ Fallback: node_outputs by LABEL alias (fuzzy matching)
#     # (case-insensitive, spaces removed, prefix matching)
#     # ------------------------
#     logger.info(f"[Resolver] 🔍 Searching by fuzzy label match. Normalized target: '{normalized_target}'")

#     for key, value in node_outputs.items():
#         # 🔧 Strip "-[nodeId]" before normalization
#         label_only = key.split("-[")[0]
#         normalized_label = label_only.lower().replace(" ", "")
        
#         logger.debug(f"[Resolver]   Checking '{key}' (normalized: '{normalized_label}')")
        
#         # Full-match
#         if normalized_label == normalized_target:
#             logger.info(f"[Resolver] ✅ Full label match found: '{key}'")
#             result = _deep_get(value, parts[1:])
#             if result is not None:
#                 logger.info(f"[Resolver] ✅ Resolved from label match: {type(result)}")
#                 return result
#             logger.warning(f"[Resolver] ⚠️ Label matched but deep_get returned None")
    
#         # Prefix match
#         if normalized_label.startswith(normalized_target):
#             logger.info(f"[Resolver] ✅ Prefix label match found: '{key}'")
#             result = _deep_get(value, parts[1:])
#             if result is not None:
#                 logger.info(f"[Resolver] ✅ Resolved from prefix match: {type(result)}")
#                 return result
#             logger.warning(f"[Resolver] ⚠️ Prefix matched but deep_get returned None")

#     logger.error(f"[Resolver] ❌ Cannot resolve path: '{path}'")
#     logger.error(f"[Resolver] Available in context: {list(context.keys())}")
#     logger.error(f"[Resolver] Available in node_outputs: {list(node_outputs.keys())}")
#     logger.error(f"[Resolver] Label-to-ID map: {label_to_id_map}")
#     return None



# def _build_label_to_id_map(context):
#     """
#     Build a normalized label -> node_id mapping from workflow metadata.
#     This allows resolving 'PDF Extractor Node' to 'pdfextractor-3'.
#     """
#     label_map = {}
    
#     workflow = context.get("workflow", {})
#     nodes = workflow.get("nodes", [])
    
#     for node in nodes:
#         node_id = node.get("id")
#         if not node_id:
#             continue
            
#         data = node.get("data", {}) or {}
#         form_data = data.get("formData", {}) or {}
        
#         # Extract label from multiple possible locations
#         label = (
#             form_data.get("agent_name") or
#             form_data.get("label") or
#             data.get("label") or
#             None
#         )
        
#         if label:
#             normalized_label = label.lower().replace(" ", "")
#             label_map[normalized_label] = node_id
#             logger.debug(f"[Resolver] Mapped label '{label}' -> '{node_id}'")
    
#     return label_map


# def _deep_get(obj, keys):
#     """Safely traverse nested dict/list using array of keys."""
#     try:
#         logger.debug(f"[Resolver] _deep_get called with keys: {keys}, obj type: {type(obj)}")
        
#         for i, key in enumerate(keys):
#             if obj is None:
#                 logger.debug(f"[Resolver] _deep_get: obj is None at key '{key}'")
#                 return None

#             # list-index access
#             if isinstance(obj, list) and key.isdigit():
#                 idx = int(key)
#                 if idx < len(obj):
#                     obj = obj[idx]
#                     logger.debug(f"[Resolver] _deep_get: accessed list[{idx}], new type: {type(obj)}")
#                 else:
#                     logger.debug(f"[Resolver] _deep_get: list index {idx} out of range (len={len(obj)})")
#                     return None

#             # dict access
#             elif isinstance(obj, dict):
#                 if key in obj:
#                     obj = obj[key]
#                     logger.debug(f"[Resolver] _deep_get: accessed dict['{key}'], new type: {type(obj)}")
#                 else:
#                     logger.debug(f"[Resolver] _deep_get: key '{key}' not in dict. Available: {list(obj.keys())}")
#                     return None

#             else:
#                 logger.debug(f"[Resolver] _deep_get: Cannot traverse - obj is {type(obj)}, key is '{key}'")
#                 return None

#         logger.debug(f"[Resolver] _deep_get: Successfully resolved. Final type: {type(obj)}")
#         return obj

#     except Exception as e:
#         logger.error(f"[Resolver] _deep_get exception: {e}", exc_info=True)
#         return None









def resolve_field(context, path):
    """
    Universal resolver that supports:
    1. Direct parent inputs  (context[source_node_id])
    2. node_outputs by node_id
    3. node_outputs by node LABEL (alias)
    4. Nested access a.b.c.0.field
    5. Case-insensitive & space-insensitive label matching
    6. Label-to-ID mapping from workflow metadata
    7. Label-[ID] format extraction (e.g., "Decision Agent-[decisionrouter-7]")
    8. 🆕 ARRAY PATH SUPPORT: Accepts list of paths and returns list of resolved values
    
    Args:
        context: The execution context containing node outputs
        path: Either a string path or a list of string paths
        
    Returns:
        - If path is a string: resolved value or None
        - If path is a list: concatenated string of resolved values (None for unresolved paths)
    """
    
    # 🆕 SINGLE-ITEM LIST → behave like string path
    if isinstance(path, list) and len(path) == 1:
        logger.info(
            "[Resolver] 🔁 Single-item path list detected, resolving as scalar path"
        )
        return resolve_field(context, path[0])
        
    # 🆕 HANDLE ARRAY OF PATHS
   
    if isinstance(path, list):
        logger.info(f"[Resolver] 🔍 Resolving array of {len(path)} paths")

        resolved_values = []

        for i, single_path in enumerate(path):
            logger.info(f"[Resolver] 📍 Resolving path [{i}]: '{single_path}'")
            resolved = resolve_field(context, single_path)

            # Skip None / empty values safely
            if resolved is None:
                continue

            # If value itself is a list, flatten it
            if isinstance(resolved, list):
                resolved_values.extend(
                    str(v) for v in resolved if v is not None
                )
            else:
                resolved_values.append(str(resolved))

        if not resolved_values:
            logger.info("[Resolver] ⚠️ No values resolved for array path")
            return None

        # Remove exact duplicates while preserving order to avoid repeated
        # values like "Hi, Hi, Hi, Hi" when multiple mappings point to the
        # same underlying field.
        deduped_values = []
        seen_values = set()
        for value in resolved_values:
            if value in seen_values:
                continue
            seen_values.add(value)
            deduped_values.append(value)

        # 🔥 FINAL CONCATENATION
        concatenated = ", ".join(deduped_values)
        logger.info(f"[Resolver] ✅ Concatenated result: {concatenated}")

        return concatenated

    # ORIGINAL SINGLE PATH LOGIC CONTINUES BELOW
    if not path:
        logger.warning("[Resolver] Empty path provided")
        return None

    logger.info(f"[Resolver] 🔍 Resolving path: '{path}'")
    logger.info(f"[Resolver] Context keys: {list(context.keys())}")

    parts = path.split(".")
    logger.info(f"[Resolver] Path parts: {parts}")

    # ------------------------
    # 🆕 BRACKET ID EXTRACTION
    # Extract ID from "Label-[node-id]" format
    # ------------------------
    extracted_id = None
    if '[' in parts[0] and parts[0].endswith(']'):
        try:
            # Extract: "Decision Agent-[decisionrouter-7]" -> "decisionrouter-7"
            extracted_id = parts[0].split('[')[-1].rstrip(']')
            logger.info(f"[Resolver] 🔍 Extracted ID from brackets: '{extracted_id}'")
        except Exception as e:
            logger.warning(f"[Resolver] ⚠️ Failed to extract ID from brackets: {e}")

    # ------------------------
    # 1️⃣ Direct context parent input
    # ------------------------
    if parts[0] in context:
        logger.info(f"[Resolver] ✅ Found '{parts[0]}' in direct context")
        value = _deep_get(context[parts[0]], parts[1:])
        if value is not None:
            logger.info(f"[Resolver] ✅ Resolved from direct context: {type(value)}")
            return value
        logger.warning(f"[Resolver] ⚠️ Direct context key exists but deep_get returned None")

    # ------------------------
    # 2️⃣ node_outputs by node_id (including extracted bracket ID)
    # ------------------------
    node_outputs = context.get("node_outputs", {})
    logger.info(f"[Resolver] node_outputs keys: {list(node_outputs.keys())}")
    
    # Try exact match first
    if parts[0] in node_outputs:
        logger.info(f"[Resolver] ✅ Found '{parts[0]}' in node_outputs by ID")
        value = _deep_get(node_outputs[parts[0]], parts[1:])
        if value is not None:
            logger.info(f"[Resolver] ✅ Resolved from node_outputs by ID: {type(value)}")
            return value
        logger.warning(f"[Resolver] ⚠️ node_outputs key exists but deep_get returned None")
    
    # 🆕 Try extracted bracket ID
    if extracted_id and extracted_id in node_outputs:
        logger.info(f"[Resolver] ✅ Found extracted ID '{extracted_id}' in node_outputs")
        value = _deep_get(node_outputs[extracted_id], parts[1:])
        if value is not None:
            logger.info(f"[Resolver] ✅ Resolved from node_outputs using extracted ID: {type(value)}")
            return value
        logger.warning(f"[Resolver] ⚠️ Extracted ID exists but deep_get returned None")

    # ------------------------
    # 3️⃣ Build label-to-id mapping from workflow metadata
    # ------------------------
    label_to_id_map = _build_label_to_id_map(context)
    logger.debug(f"[Resolver] Label-to-ID map: {label_to_id_map}")

    # ------------------------
    # 4️⃣ Try to resolve using label-to-id mapping first
    # ------------------------
    normalized_target = _normalize_lookup_key(parts[0])
    
    if normalized_target in label_to_id_map:
        actual_node_id = label_to_id_map[normalized_target]
        logger.info(f"[Resolver] ✅ Mapped label '{parts[0]}' to node_id '{actual_node_id}'")
        
        if actual_node_id in node_outputs:
            value = _deep_get(node_outputs[actual_node_id], parts[1:])
            if value is not None:
                logger.info(f"[Resolver] ✅ Resolved via label mapping: {type(value)}")
                return value
            logger.warning(f"[Resolver] ⚠️ Label mapped but deep_get returned None")


    # ------------------------
    # 🧯 4.5️⃣ LEGACY BACKWARD-COMPAT LABEL → ID INFERENCE
    # (supports old label-only paths like EmailFetcher.xxx)
    # ------------------------
    for node_id, value in node_outputs.items():
        # Normalize node_id (emailfetcher-1 → emailfetcher)
        normalized_node_id = _normalize_lookup_key(node_id)

        if normalized_node_id.startswith(normalized_target):
            logger.warning(
                f"[Resolver][LEGACY] Label-only path '{parts[0]}' "
                f"resolved via node_id '{node_id}'. "
                f"Use 'Label-[{node_id}]' for deterministic behavior."
            )

            result = _deep_get(value, parts[1:])
            if result is not None:
                logger.info(
                    f"[Resolver] ✅ Resolved via LEGACY label→id inference: {type(result)}"
                )
                return result


    # ------------------------
    # 5️⃣ Fallback: node_outputs by LABEL alias (fuzzy matching)
    # (case-insensitive, spaces removed, prefix matching)
    # ------------------------
    logger.info(f"[Resolver] 🔍 Searching by fuzzy label match. Normalized target: '{normalized_target}'")

    for key, value in node_outputs.items():
        # 🔧 Strip "-[nodeId]" before normalization
        label_only = key.split("-[")[0]
        normalized_label = _normalize_lookup_key(label_only)
        
        logger.debug(f"[Resolver]   Checking '{key}' (normalized: '{normalized_label}')")
        
        # Full-match
        if normalized_label == normalized_target:
            logger.info(f"[Resolver] ✅ Full label match found: '{key}'")
            result = _deep_get(value, parts[1:])
            if result is not None:
                logger.info(f"[Resolver] ✅ Resolved from label match: {type(result)}")
                return result
            logger.warning(f"[Resolver] ⚠️ Label matched but deep_get returned None")
        
        # Prefix match
        if normalized_label.startswith(normalized_target):
            logger.info(f"[Resolver] ✅ Prefix label match found: '{key}'")
            result = _deep_get(value, parts[1:])
            if result is not None:
                logger.info(f"[Resolver] ✅ Resolved from prefix match: {type(result)}")
                return result
            logger.warning(f"[Resolver] ⚠️ Prefix matched but deep_get returned None")

    # ------------------------
    # 6️⃣ Fallback: search all node_outputs for single-key fields
    # ------------------------
    if len(parts) == 1:
        logger.info(f"[Resolver] 🔍 Single-key fallback search for '{parts[0]}' across all node_outputs")
        matches = []
        for node_id, value in node_outputs.items():
            found = _find_recursive_key(value, parts[0]) if isinstance(value, (dict, list)) else None
            if found is not None:
                matches.append((node_id, found))

        if matches:
            if len(matches) > 1:
                logger.warning(
                    f"[Resolver] ⚠️ Ambiguous single-key '{parts[0]}' found in multiple node_outputs: {[node_id for node_id, _ in matches]}. Using first match."
                )
            first_match = matches[0]
            logger.info(f"[Resolver] ✅ Single-key fallback resolved '{parts[0]}' from node_outputs['{first_match[0]}']")
            return first_match[1]

    logger.error(f"[Resolver] ❌ Cannot resolve path: '{path}'")
    logger.error(f"[Resolver] Available in context: {list(context.keys())}")
    logger.error(f"[Resolver] Available in node_outputs: {list(node_outputs.keys())}")
    logger.error(f"[Resolver] Label-to-ID map: {label_to_id_map}")
    return None


def _build_label_to_id_map(context):
    label_map = {}
    workflow = context.get("workflow", {})
    nodes = workflow.get("nodes", [])

    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            continue

        data = node.get("data", {}) or {}
        form_data = data.get("formData", {}) or {}

        label = (
            form_data.get("agent_name")
            or form_data.get("label")
            or data.get("label")
            or None
        )

        if label:
            normalized_label = _normalize_lookup_key(label)
            label_map[normalized_label] = node_id
            logger.debug(f"[Resolver] Mapped label '{label}' -> '{node_id}'")

    return label_map


def _deep_get(obj, keys):
    """Safely traverse nested dict/list using array of keys."""
    try:
        logger.debug(f"[Resolver] _deep_get called with keys: {keys}, obj type: {type(obj)}")

        # Backward-compat: trigger nodes often return a single-item list.
        # Allow paths like "slacktrigger-1.message" and "whatsapptrigger-1.message"
        # to resolve against the first event object when no explicit index is provided.
        if isinstance(obj, list) and len(obj) == 1 and keys and not str(keys[0]).isdigit():
            obj = obj[0]
        
        for i, key in enumerate(keys):
            if obj is None:
                logger.debug(f"[Resolver] _deep_get: obj is None at key '{key}'")
                return None

            # list-index access
            if isinstance(obj, list) and key.isdigit():
                idx = int(key)
                if idx < len(obj):
                    obj = obj[idx]
                    logger.debug(f"[Resolver] _deep_get: accessed list[{idx}], new type: {type(obj)}")
                else:
                    logger.debug(f"[Resolver] _deep_get: list index {idx} out of range (len={len(obj)})")
                    return None
            elif isinstance(obj, list):
                if len(obj) == 1:
                    obj = obj[0]
                    logger.debug("[Resolver] _deep_get: collapsed single-item list for implicit field access")
                    if isinstance(obj, dict):
                        if key in obj:
                            obj = obj[key]
                            continue
                        matched_key = _find_compatible_dict_key(obj, key)
                        if matched_key is not None:
                            obj = obj[matched_key]
                            continue
                logger.debug(
                    "[Resolver] _deep_get: list requires numeric index for key '%s' (len=%s)",
                    key,
                    len(obj),
                )
                return None

            # dict access
            elif isinstance(obj, dict):
                if key in obj:
                    obj = obj[key]
                    logger.debug(f"[Resolver] _deep_get: accessed dict['{key}'], new type: {type(obj)}")
                else:
                    matched_key = _find_compatible_dict_key(obj, key)
                    if matched_key is not None:
                        obj = obj[matched_key]
                        logger.debug(
                            f"[Resolver] _deep_get: normalized dict match '{key}' -> '{matched_key}', new type: {type(obj)}"
                        )
                    else:
                        logger.debug(f"[Resolver] _deep_get: key '{key}' not in dict. Available: {list(obj.keys())}")
                        return None

            else:
                logger.debug(f"[Resolver] _deep_get: Cannot traverse - obj is {type(obj)}, key is '{key}'")
                return None

        logger.debug(f"[Resolver] _deep_get: Successfully resolved. Final type: {type(obj)}")
        return obj

    except Exception as e:
        logger.error(f"[Resolver] _deep_get exception: {e}", exc_info=True)
        return None


def _find_recursive_key(data, target_key):
    normalized_target = _normalize_lookup_key(target_key)

    if isinstance(data, dict):
        for key, value in data.items():
            if _normalize_lookup_key(key) == normalized_target:
                return value
            found = _find_recursive_key(value, target_key)
            if found is not None:
                return found

    elif isinstance(data, list):
        for item in data:
            found = _find_recursive_key(item, target_key)
            if found is not None:
                return found

    return None


def _normalize_lookup_key(value):
    if value is None:
        return ""
    return re.sub(r"[\s_-]+", "", str(value).strip().lower())


def _find_compatible_dict_key(data, target_key):
    if not isinstance(data, dict):
        return None

    normalized_target = _normalize_lookup_key(target_key)
    if not normalized_target:
        return None

    for existing_key in data.keys():
        if _normalize_lookup_key(existing_key) == normalized_target:
            return existing_key

    return None
