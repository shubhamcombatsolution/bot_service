import re
from typing import Any, Dict, Optional


_PATH_PATTERN = re.compile(r"^[A-Za-z0-9_\-\[\]]+(?:\.[A-Za-z0-9_\-\[\]]+)+$")
_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^{}]+)\s*\}\}|\{([^{}]+)\}")


def normalize_phone(value: Any) -> str:
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _deep_get(value: Any, path: str) -> Any:
    if value is None or not path:
        return value

    current = value
    for key in path.split("."):
        if isinstance(current, list) and key.isdigit():
            index = int(key)
            if 0 <= index < len(current):
                current = current[index]
            else:
                return None
        elif isinstance(current, dict):
            current = current.get(key)
        else:
            return None

        if current is None:
            return None

    return current


def resolve_context_path(context: Dict[str, Any], path: str) -> Any:
    if not path or not isinstance(context, dict):
        return None

    # 1) Explicit node_outputs path.
    if path.startswith("node_outputs."):
        value = _deep_get(context, path)
        if value is not None:
            return value

    # 2) Direct path in full context.
    value = _deep_get(context, path)
    if value is not None:
        return value

    # 3) Resolve against node_outputs by node id alias.
    node_outputs = context.get("node_outputs")
    if not isinstance(node_outputs, dict):
        return None

    if "." in path:
        first, remaining = path.split(".", 1)
        if first in node_outputs:
            value = _deep_get(node_outputs.get(first), remaining)
            if value is not None:
                return value

    # 4) Try each node output object.
    for _, output in reversed(list(node_outputs.items())):
        if isinstance(output, list):
            for item in reversed(output):
                value = _deep_get(item, path)
                if value is not None:
                    return value
            continue

        value = _deep_get(output, path)
        if value is not None:
            return value

    return None


def _is_wrapped_literal(token: str) -> bool:
    token = (token or "").strip()
    return (
        len(token) >= 2
        and ((token[0] == "'" and token[-1] == "'") or (token[0] == '"' and token[-1] == '"'))
    )


def _unquote_literal(token: str) -> str:
    token = (token or "").strip()
    if _is_wrapped_literal(token):
        return token[1:-1]
    return token


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _resolve_expression(context: Dict[str, Any], expression: str) -> Any:
    """
    Resolve expression parts with JS-like fallback semantics:
    - pathA || pathB || 'literal fallback'
    """
    expr = (expression or "").strip()
    if not expr:
        return None

    # Fast path for simple path/literal
    if "||" not in expr:
        if _is_wrapped_literal(expr):
            return _unquote_literal(expr)
        resolved = resolve_context_path(context, expr)
        if _is_present(resolved):
            return resolved

        # Backward compatibility for older workflow templates that expect
        # agent output shape *.output.llm_response while runtime now often stores
        # final text directly at *.output (string).
        if ".output.llm_response" in expr:
            parent_expr = expr.replace(".output.llm_response", ".output")
            parent_val = resolve_context_path(context, parent_expr)
            if isinstance(parent_val, str) and parent_val.strip():
                return parent_val
            if isinstance(parent_val, dict):
                for key in ("llm_response", "response", "text", "message"):
                    v = parent_val.get(key)
                    if _is_present(v):
                        return v
        return resolved

    for part in expr.split("||"):
        token = (part or "").strip()
        if not token:
            continue

        if _is_wrapped_literal(token):
            literal = _unquote_literal(token)
            if _is_present(literal):
                return literal
            continue

        resolved = resolve_context_path(context, token)
        if _is_present(resolved):
            return resolved

        # Backward compatibility for legacy templates in OR chains:
        # genericagent-x.output.llm_response || ...
        if ".output.llm_response" in token:
            parent_expr = token.replace(".output.llm_response", ".output")
            parent_val = resolve_context_path(context, parent_expr)
            if isinstance(parent_val, str) and parent_val.strip():
                return parent_val
            if isinstance(parent_val, dict):
                for key in ("llm_response", "response", "text", "message"):
                    value = parent_val.get(key)
                    if _is_present(value):
                        return value

    return None


def resolve_dynamic_value(value: Any, context: Dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: resolve_dynamic_value(v, context) for k, v in value.items()}

    if isinstance(value, list):
        return [resolve_dynamic_value(item, context) for item in value]

    if not isinstance(value, str):
        return value

    raw = value.strip()
    if not raw:
        return value

    matches = list(_PLACEHOLDER_PATTERN.finditer(value))
    if matches:
        # If the entire value is a single placeholder, return original type.
        if len(matches) == 1 and matches[0].span() == (0, len(value)):
            path = (matches[0].group(1) or matches[0].group(2) or "").strip()
            resolved = _resolve_expression(context, path)
            return value if resolved is None else resolved

        rendered = value
        for match in matches:
            path = (match.group(1) or match.group(2) or "").strip()
            resolved = _resolve_expression(context, path)
            replacement = "" if resolved is None else str(resolved)
            rendered = rendered.replace(match.group(0), replacement)
        return rendered

    if _PATH_PATTERN.match(raw):
        resolved = resolve_context_path(context, raw)
        if resolved is not None:
            return resolved

    return value


def resolve_form_data(form_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(form_data, dict):
        return {}

    return {key: resolve_dynamic_value(value, context) for key, value in form_data.items()}


def _extract_text_candidate(value: Any) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None

    if isinstance(value, list):
        for item in reversed(value):
            candidate = _extract_text_candidate(item)
            if candidate:
                return candidate
        return None

    if isinstance(value, dict):
        preferred_keys = [
            "llm_response",
            "agent_output",
            "user_query",
            "text",
            "output",
            "response",
            "answer",
            "message",
            "content",
            "final_answer",
        ]

        for key in preferred_keys:
            if key in value:
                candidate = _extract_text_candidate(value.get(key))
                if candidate:
                    return candidate

        for nested in value.values():
            candidate = _extract_text_candidate(nested)
            if candidate:
                return candidate

    return None


def infer_whatsapp_recipient(context: Dict[str, Any]) -> str:
    candidate_paths = [
        "phone",
        "parameters.phone",
        "parameters.from",
        "latest_whatsapp_event.phone",
        "latest_whatsapp_event.metadata.from",
        "latest_whatsapp_event.metadata.from_phone",
        "reply_event.latest_whatsapp_event.metadata.from",
        "reply_event.latest_whatsapp_event.metadata.from_phone",
        "reply_event.latest_whatsapp_event.phone",
        "reply_event.whatsapp_events.0.phone",
        "reply_event.whatsapp_events.0.metadata.from",
        "reply_event.whatsapp_events.0.metadata.from_phone",
        "whatsapp_events.0.phone",
        "whatsapp_events.0.metadata.from",
        "whatsapp_events.0.metadata.from_phone",
        "metadata.from",
        "metadata.from_phone",
        "await.from",
        "to",
    ]

    for path in candidate_paths:
        phone = normalize_phone(resolve_context_path(context, path))
        if phone:
            return phone

    node_outputs = context.get("node_outputs")
    if isinstance(node_outputs, dict):
        for _, output in reversed(list(node_outputs.items())):
            if isinstance(output, list) and output:
                candidate = output[-1]
            else:
                candidate = output

            if not isinstance(candidate, dict):
                continue

            phone = normalize_phone(
                _deep_get(candidate, "metadata.from")
                or _deep_get(candidate, "metadata.from_phone")
                or _deep_get(candidate, "await.from")
                or candidate.get("to")
            )
            if phone:
                return phone

    return ""


def infer_whatsapp_message_text(context: Dict[str, Any]) -> str:
    node_outputs = context.get("node_outputs")
    if isinstance(node_outputs, dict):
        for _, output in reversed(list(node_outputs.items())):
            # Skip inbound trigger event arrays when choosing outbound reply text.
            if (
                isinstance(output, list)
                and output
                and isinstance(output[0], dict)
                and output[0].get("trigger_type") == "whatsapp"
            ):
                continue

            # Handle direct string output from agent
            if isinstance(output, str) and output.strip():
                return output.strip()

            candidate = _extract_text_candidate(output)
            if candidate:
                return candidate

    candidate_paths = [
        "message",
        "parameters.message",
        "parameters.user_query",
        "latest_whatsapp_event.message",
        "latest_whatsapp_event.user_query",
        "latest_whatsapp_event.content.text",
        "reply_event.latest_whatsapp_event.message",
        "reply_event.latest_whatsapp_event.user_query",
        "reply_event.latest_whatsapp_event.content.text",
        "whatsapp_events.0.message",
        "whatsapp_events.0.user_query",
        "whatsapp_events.0.content.text",
        "user_query",
    ]

    for path in candidate_paths:
        candidate = _extract_text_candidate(resolve_context_path(context, path))
        if candidate:
            return candidate

    return ""


def infer_media_id(context: Dict[str, Any]) -> str:
    candidate_paths = [
        "media_id",
        "response.id",
        "result.media_id",
        "latest_whatsapp_event.content.media.id",
        "whatsapp_events.0.content.media.id",
    ]

    for path in candidate_paths:
        media_id = resolve_context_path(context, path)
        if media_id:
            return str(media_id)

    node_outputs = context.get("node_outputs")
    if isinstance(node_outputs, dict):
        for _, output in reversed(list(node_outputs.items())):
            media_id = (
                _deep_get(output, "media_id")
                or _deep_get(output, "response.id")
                or _deep_get(output, "result.media_id")
            )
            if media_id:
                return str(media_id)

    return ""


def infer_whatsapp_phone_number_id(context: Dict[str, Any]) -> str:
    candidate_paths = [
        "phone_number_id",
        "latest_whatsapp_event.metadata.phone_number_id",
        "reply_event.latest_whatsapp_event.metadata.phone_number_id",
        "reply_event.whatsapp_events.0.metadata.phone_number_id",
        "whatsapp_events.0.metadata.phone_number_id",
        "metadata.phone_number_id",
    ]

    for path in candidate_paths:
        value = resolve_context_path(context, path)
        if value:
            normalized = "".join(ch for ch in str(value) if ch.isdigit())
            if normalized:
                return normalized

    node_outputs = context.get("node_outputs")
    if isinstance(node_outputs, dict):
        for _, output in reversed(list(node_outputs.items())):
            candidate = output[-1] if isinstance(output, list) and output else output
            if not isinstance(candidate, dict):
                continue

            value = _deep_get(candidate, "metadata.phone_number_id")
            if value:
                normalized = "".join(ch for ch in str(value) if ch.isdigit())
                if normalized:
                    return normalized

    return ""


def get_tenant_id(inputs: Dict[str, Any], form_data: Optional[Dict[str, Any]] = None) -> Optional[int]:
    form_data = form_data or {}

    tenant_id = (
        inputs.get("tenant_id")
        or (inputs.get("workflow") or {}).get("tenant_id")
        or form_data.get("tenant_id")
    )

    if tenant_id is None:
        return None

    try:
        return int(tenant_id)
    except (TypeError, ValueError):
        return None
