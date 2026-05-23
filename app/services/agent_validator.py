# """
# agent_validator.py

# Validates a parsed agent config dict.
# Returns:
#   {
#     "valid":       True | False,
#     "errors":      [...],
#     "warnings":    [...],
#     "parsed_data": {...}   # original dict (with action_tools validated), only if valid
#   }

# Key rules:
#   - User supplies action_tools per tool  →  we validate them (not inject statically)
#   - Credentials required vary by tool    →  only access_token + refresh_token + maybe id
#   - System-level tools (system, file, text, llm, invoke) need NO credentials
# """

# import logging

# logger = logging.getLogger(__name__)
# import os
# import requests
# TOOL_VALIDATION_ENDPOINT = os.getenv(
#     "TOOL_VALIDATION_ENDPOINT",
#     "http://bba-bot-builder:7000/tools/validate"

# )

# # ──────────────────────────────────────────────────────────────
# # Core field constants
# # ──────────────────────────────────────────────────────────────
# REQUIRED_CORE_FIELDS = ["agent_name", "agent_description", "agent_role"]
# REQUIRED_LLM_FIELDS  = ["provider", "model"]
# VALID_MEMORY_TYPES   = {"short_term", "long_term", None}
# VALID_PROVIDERS      = {"openai", "anthropic", "groq", "mistral", "ollama", "azure"}

# VALID_FEATURE_KEYS = {
#     "soundNatural", "thinkBack", "stayOnTopic", "explainClearly",
# }
# VALID_SAFE_AI_KEYS = {
#     "harmfulContent", "harmfulThreshold",
#     "maliciousInstructions", "maliciousThreshold",
#     "allowedTopics", "allowedKeywords",
#     "blockedTopics", "blockedKeywords",
#     "secrets", "secretKeywords",
#     "keywordsEnabled", "keywordList", "keywordsAction",
# }

# # ──────────────────────────────────────────────────────────────
# # MASTER TOOL → VALID ACTIONS MAP
# # Used ONLY for validating user-supplied action_tools.
# # We do NOT inject all actions automatically — the user decides.
# # ──────────────────────────────────────────────────────────────
# TOOL_ACTION_MAP = {
#     "hubspot": [
#         "get_contact_by_email",
#         "create_contact",
#         "update_contact",
#         "list_hubspot_contacts",
#         "search_hubspot_contact",
#         "create_company",
#         "list_companies",
#         "get_companies_by_domain",
#         "create_deal",
#         "get_deal",
#         "update_deal",
#         "create_note",
#         "search",
#         "get_company",
#         "find_company",
#         "association_query",
#     ],
#     "invoke": [
#         "webhook_invoker",
#     ],
#     "system": [
#         "get_datetime",
#         "parse_json",
#         "calculator_basic",
#     ],
#     "llm": [
#         "make_decision",
#         "evaluate_condition",
#         "extract_field",
#     ],
#     "text": [
#         "splitter",
#     ],
#     "file": [
#         "read_excel",
#         "read_pdf",
#         "create_pdf",
#     ],
#     "gmaps": [
#         "commute_time",
#         "nearby_facilities",
#     ],
#     "gmail": [
#         "send_gmail",
#         "draft_gmail",
#         "list_gmail_messages",
#         "read_gmail_messages",
#         "download_gmail_attachment",
#         "search_gmail_messages",
#         "get_email_from_token",
#         "mark_as_read",
#         "mark_as_unread",
#         "modify_gmail_labels",
#         "delete_gmail_messages",
#         "read_unread_gmail_messages",
#     ],
#     "gcalendar": [
#         "create_event",
#         "list_event",
#         "update_event",
#         "delete_event",
#         "get_free_busy",
#     ],
#     "gsheets": [
#         "list_spreadsheets",
#         "list_sheets",
#         "get_metadata",
#         "duplicate_sheet",
#         "read_spreadsheet",
#         "write_spreadsheet",
#         "append_spreadsheet",
#         "create_sheet",
#         "clear_spreadsheet",
#     ],
# }

# # Set of all supported tool names for quick existence check
# SUPPORTED_TOOLS = set(TOOL_ACTION_MAP.keys())

# # ──────────────────────────────────────────────────────────────
# # TOKEN / CREDENTIAL REQUIREMENTS PER TOOL
# #
# # Three categories:
# #
# # 1. NO_AUTH_TOOLS  — system-level, no tokens at all
# #    (system, file, text, llm, invoke)
# #
# # 2. OAUTH_TOOLS    — need access_token + refresh_token
# #    (gmail, gcalendar, gsheets)
# #    token_json stored by OAuth callback also has: expiry, scopes,
# #    client_id, client_secret, token_uri — those are set automatically
# #    by the OAuth flow, so we only require the two essentials for import.
# #
# # 3. API_KEY_TOOLS  — need their specific key fields
# #    (hubspot → access_token + refresh_token + hub_id)
# #    (gmaps   → api_key)
# #
# # Dict maps tool_name → list of REQUIRED token_json keys.
# # Empty list  = no credentials needed (NO_AUTH_TOOLS).
# # ──────────────────────────────────────────────────────────────

# # Tools that run locally, no external auth needed
# NO_AUTH_TOOLS = {"system", "file", "text", "llm", "invoke"}

# TOOL_CREDENTIAL_REQUIREMENTS = {
#     # ── No credentials ──────────────────────────────────────
#     "system":    [],
#     "file":      [],
#     "text":      [],
#     "llm":       [],
#     "invoke":    [],

#     # ── HubSpot: access_token + refresh_token + hub_id ──────
#     # hub_id identifies the HubSpot portal (required for API calls)
#     "hubspot":   ["access_token", "refresh_token", "hub_id"],

#     # ── Google OAuth tools: access_token + refresh_token ────
#     # expiry / scopes / client_id are stored by the OAuth callback
#     # but are not required during import — they get refreshed at runtime
#     "gmail":     ["access_token", "refresh_token"],
#     "gcalendar": ["access_token", "refresh_token"],
#     "gsheets":   ["access_token", "refresh_token"],

#     # ── Google Maps: API key (no OAuth) ─────────────────────
#     "gmaps":     ["api_key"],
# }








# # ============================================================
# # Internal credential validator (calls your backend)
# # ============================================================

# class InternalCredentialValidator:

#     @staticmethod
#     def validate(tool_name: str, credentials: dict):
#         try:
#             payload = {
#                 "tool_name": tool_name,
#                 "credentials": credentials,
#             }

#             resp = requests.post(
#                 TOOL_VALIDATION_ENDPOINT,
#                 json=payload,
#                 timeout=6,
#             )

#             if resp.status_code != 200:
#                 return False, f"endpoint returned {resp.status_code}"

#             data = resp.json()
#             return data.get("valid", False), data.get("message", "")

#         except Exception as e:
#             return False, str(e)










# # ──────────────────────────────────────────────────────────────
# # Validator
# # ──────────────────────────────────────────────────────────────


# class AgentValidator:

#     def validate(self, data: dict) -> dict:
#         errors   = []
#         warnings = []

#         self._check_core_fields(data, errors)
#         self._check_llm(data, errors, warnings)
#         self._check_memory(data, warnings)
#         self._check_tools(data, errors, warnings)
#         self._check_features(data, warnings)

#         is_valid = len(errors) == 0
#         logger.debug(
#             "agent_validator: valid=%s errors=%d warnings=%d",
#             is_valid, len(errors), len(warnings),
#         )
#         return {
#             "valid":       is_valid,
#             "errors":      errors,
#             "warnings":    warnings,
#             "parsed_data": data if is_valid else None,
#         }

#     # ────────────────────────────────────────────────────────
#     # Core / LLM / Memory checks (unchanged logic)
#     # ────────────────────────────────────────────────────────

#     def _check_core_fields(self, data: dict, errors: list):
#         for field in REQUIRED_CORE_FIELDS:
#             value = data.get(field)
#             if not value or (isinstance(value, str) and not value.strip()):
#                 errors.append(f"Missing required field: '{field}'")

#         if data.get("agent_name") and len(data["agent_name"]) > 100:
#             errors.append(
#                 f"'agent_name' exceeds 100 characters "
#                 f"(current: {len(data['agent_name'])})."
#             )

#     def _check_llm(self, data: dict, errors: list, warnings: list):
#         llm = data.get("llm")
#         if not llm or not isinstance(llm, dict):
#             errors.append(
#                 "Missing 'llm' block. "
#                 'Required: {"provider": "openai", "model": "gpt-4-turbo"}'
#             )
#             return

#         for field in REQUIRED_LLM_FIELDS:
#             if not llm.get(field):
#                 errors.append(f"'llm.{field}' is required.")

#         provider = (llm.get("provider") or "").lower()
#         if provider and provider not in VALID_PROVIDERS:
#             warnings.append(
#                 f"'llm.provider' value '{provider}' is not in the known list "
#                 f"{sorted(VALID_PROVIDERS)}. Ensure it exists in tbl_llm."
#             )

#         temperature = llm.get("temperature")
#         if temperature is not None:
#             try:
#                 t = float(temperature)
#                 if not (0.0 <= t <= 1.0):
#                     errors.append(f"'llm.temperature' must be 0.0–1.0, got {t}.")
#             except (TypeError, ValueError):
#                 errors.append(f"'llm.temperature' must be a number, got '{temperature}'.")

#     def _check_memory(self, data: dict, warnings: list):
#         memory = data.get("memory")
#         if memory is None:
#             warnings.append(
#                 "'memory' block not set — agent will have no memory. "
#                 'Add: {"enabled": true, "type": "short_term"}'
#             )
#             return
#         if not isinstance(memory, dict):
#             warnings.append("'memory' should be a dict.")
#             return
#         mem_type = memory.get("type")
#         if mem_type is not None and mem_type not in VALID_MEMORY_TYPES:
#             warnings.append(
#                 f"'memory.type' '{mem_type}' not recognised. "
#                 f"Use: {sorted([t for t in VALID_MEMORY_TYPES if t])}."
#             )

#     # ────────────────────────────────────────────────────────
#     # Tools check  ←  main logic change
#     # ────────────────────────────────────────────────────────

#     def _check_tools(self, data: dict, errors: list, warnings: list):
#         tools = data.get("tools")

#         if tools is None or (isinstance(tools, list) and len(tools) == 0):
#             errors.append(
#                 "At least one tool is required. "
#                 "Add a 'tools' array. "
#                 f"Supported tools: {sorted(SUPPORTED_TOOLS)}."
#             )
#             return

#         if not isinstance(tools, list):
#             errors.append("'tools' must be a list.")
#             return

#         for idx, tool in enumerate(tools):
#             label = f"tools[{idx}]"

#             if not isinstance(tool, dict):
#                 errors.append(f"{label} must be an object.")
#                 continue

#             tool_name = (tool.get("tool_name") or "").strip().lower()
#             tool_type = (tool.get("tool_type") or "local").lower()

#             if not tool_name:
#                 errors.append(f"{label}: 'tool_name' is required.")
#                 continue

#             # ── 1. Check tool is supported by the platform ──────────
#             if tool_name not in SUPPORTED_TOOLS:
#                 errors.append(
#                     f"{label}: tool '{tool_name}' is not supported. "
#                     f"Supported tools: {sorted(SUPPORTED_TOOLS)}."
#                 )
#                 continue  # no point checking actions / creds for unknown tool

#             if tool_type not in ("local", "mcp"):
#                 errors.append(
#                     f"{label} ('{tool_name}'): 'tool_type' must be 'local' or 'mcp', "
#                     f"got '{tool_type}'."
#                 )

#             # ── 2. Validate user-supplied action_tools ──────────────
#             self._check_action_tools(tool, tool_name, label, errors, warnings)

#             # ── 3. Validate credentials ─────────────────────────────
#             if tool_type == "local":
#                 self._check_credentials(tool, tool_name, label, errors, warnings)
#             elif tool_type == "mcp":
#                 self._check_mcp_fields(tool, tool_name, label, errors)

#     def _check_action_tools(
#         self, tool: dict, tool_name: str, label: str,
#         errors: list, warnings: list
#     ):
#         """
#         User MUST supply action_tools.
#         We validate every action they listed is valid for the tool.
#         We do NOT inject actions automatically.
#         """
#         user_actions = tool.get("action_tools")
#         valid_actions = TOOL_ACTION_MAP[tool_name]  # always present (tool already validated)

#         # action_tools not provided at all
#         if user_actions is None or (isinstance(user_actions, list) and len(user_actions) == 0):
#             errors.append(
#                 f"{label} ('{tool_name}'): 'action_tools' is required and cannot be empty. "
#                 f"Valid actions for '{tool_name}': {valid_actions}."
#             )
#             return

#         if not isinstance(user_actions, list):
#             errors.append(f"{label} ('{tool_name}'): 'action_tools' must be a list.")
#             return

#         # Check each supplied action is a known action for this tool
#         invalid_actions = [a for a in user_actions if a not in valid_actions]
#         if invalid_actions:
#             errors.append(
#                 f"{label} ('{tool_name}'): invalid action(s) {invalid_actions}. "
#                 f"Valid actions for '{tool_name}': {valid_actions}."
#             )

#         # Normalise to lowercase strings in-place so creator uses clean values
#         tool["action_tools"] = [str(a).strip() for a in user_actions if str(a).strip() in valid_actions]

#         logger.debug(
#             "agent_validator: '%s' action_tools validated → %s",
#             tool_name, tool["action_tools"],
#         )

#     def _check_credentials(
#         self, tool: dict, tool_name: str, label: str,
#         errors: list, warnings: list
#     ):
#         """
#         Validates credentials based on what each tool actually needs.

#         NO_AUTH_TOOLS  → skip entirely, no credentials needed.
#         OAuth tools    → access_token + refresh_token.
#         HubSpot        → access_token + refresh_token + hub_id.
#         Gmaps          → api_key.
#         """
#         # System-level tools — no credentials at all
#         if tool_name in NO_AUTH_TOOLS:
#             if tool.get("credentials"):
#                 warnings.append(
#                     f"{label} ('{tool_name}'): credentials are not required "
#                     "for this tool and will be ignored."
#                 )
#             return

#         required_keys = TOOL_CREDENTIAL_REQUIREMENTS.get(tool_name)

#         # Tool has no entry in requirements map → warn, store as-is
#         if required_keys is None:
#             warnings.append(
#                 f"{label} ('{tool_name}'): no credential template registered. "
#                 "Credentials will be stored as-is."
#             )
#             return

#         # Tool is registered but needs no credentials (already handled above,
#         # but kept for safety)
#         if len(required_keys) == 0:
#             return

#         creds = tool.get("credentials")
#         if not creds or not isinstance(creds, dict):
#             errors.append(
#                 f"{label} ('{tool_name}'): 'credentials' object is required. "
#                 f"Must contain: {required_keys}."
#             )
#             return

#         missing = [k for k in required_keys if not creds.get(k)]
#         if missing:
#             errors.append(
#                 f"{label} ('{tool_name}'): missing credential field(s): {missing}. "
#                 f"Required: {required_keys}."
#             )
#             return 
        
#         # =========================================================
#         # 🚀 REAL RUNTIME VALIDATION VIA INTERNAL ENDPOINT
#         # =========================================================

#         try:
#             is_valid, message = InternalCredentialValidator.validate(
#                 tool_name,
#                 creds
#             )

#             if not is_valid:
#                 warnings.append(
#                     f"{label} ('{tool_name}'): credential validation failed — {message}"
#                 )
#             else:
#                 logger.debug(
#                     "Credentials validated successfully for tool '%s'",
#                     tool_name
#                 )

#         except Exception as e:
#             warnings.append(
#                 f"{label} ('{tool_name}'): validation check error — {str(e)}"
#             )


#     def _check_mcp_fields(self, tool: dict, tool_name: str, label: str, errors: list):
#         for field in ("mcp_url", "tool_name"):
#             if not tool.get(field):
#                 errors.append(
#                     f"{label} ('{tool_name}'): MCP tool requires '{field}'."
#                 )

#     # ────────────────────────────────────────────────────────
#     # Features / Safe AI  (warnings only)
#     # ────────────────────────────────────────────────────────

#     def _check_features(self, data: dict, warnings: list):
#         features = data.get("features")
#         if features and isinstance(features, dict):
#             unknown = set(features.keys()) - VALID_FEATURE_KEYS
#             if unknown:
#                 warnings.append(
#                     f"Unknown feature key(s) {sorted(unknown)} will be stored but ignored."
#                 )

#         safe_ai = data.get("safe_ai_settings")
#         if safe_ai and isinstance(safe_ai, dict):
#             unknown = set(safe_ai.keys()) - VALID_SAFE_AI_KEYS
#             if unknown:
#                 warnings.append(
#                     f"Unknown safe_ai_settings key(s) {sorted(unknown)} will be stored but ignored."
#                 )


























"""
agent_validator.py (ENHANCED VERSION with Credential Matching & Expiry Validation)

Validates a parsed agent config dict.
Returns:
  {
    "valid":       True | False,
    "errors":      [...],
    "warnings":    [...],
    "parsed_data": {...}
  }

Key rules:
  - User supplies action_tools per tool
  - Credentials are validated against stored DB credentials
  - Expiry dates are checked
  - Specific errors for expired vs mismatched credentials
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Core field constants
# ──────────────────────────────────────────────────────────────
REQUIRED_CORE_FIELDS = ["agent_name", "agent_description", "agent_role"]
REQUIRED_LLM_FIELDS  = ["provider", "model"]
VALID_MEMORY_TYPES   = {"short_term", "long_term", None}
VALID_PROVIDERS      = {"openai", "anthropic", "groq", "mistral", "ollama", "azure"}

VALID_FEATURE_KEYS = {
    "soundNatural", "thinkBack", "stayOnTopic", "explainClearly",
}
VALID_SAFE_AI_KEYS = {
    "harmfulContent", "harmfulThreshold",
    "maliciousInstructions", "maliciousThreshold",
    "allowedTopics", "allowedKeywords",
    "blockedTopics", "blockedKeywords",
    "secrets", "secretKeywords",
    "keywordsEnabled", "keywordList", "keywordsAction",
}

# ──────────────────────────────────────────────────────────────
# MASTER TOOL → VALID ACTIONS MAP
# ──────────────────────────────────────────────────────────────
TOOL_ACTION_MAP = {
    "hubspot": [
        "get_contact_by_email", "create_contact", "update_contact",
        "list_hubspot_contacts", "search_hubspot_contact",
        "create_company", "list_companies", "get_companies_by_domain",
        "create_deal", "get_deal", "update_deal", "create_note",
        "search", "get_company", "find_company", "association_query",
    ],
    "invoke": ["webhook_invoker"],
    "system": ["get_datetime", "parse_json", "calculator_basic"],
    "llm": ["make_decision", "evaluate_condition", "extract_field"],
    "text": ["splitter"],
    "file": ["read_excel", "read_pdf", "create_pdf"],
    "gmaps": ["commute_time", "nearby_facilities"],
    "gmail": [
        "send_gmail", "draft_gmail", "list_gmail_messages",
        "read_gmail_messages", "download_gmail_attachment","read_gmail_message_full",
        "search_gmail_messages", "get_email_from_token",
        "mark_as_read", "mark_as_unread", "modify_gmail_labels",
        "delete_gmail_messages", "read_unread_gmail_messages",
    ],
    "gcalendar": [
        "create_event", "list_event", "update_event",
        "delete_event", "get_free_busy",
    ],
    "gsheets": [
        "list_spreadsheets", "list_sheets", "get_metadata",
        "duplicate_sheet", "read_spreadsheet", "write_spreadsheet",
        "append_spreadsheet", "create_sheet", "clear_spreadsheet",
    ],
}

SUPPORTED_TOOLS = set(TOOL_ACTION_MAP.keys())
NO_AUTH_TOOLS = {"system", "file", "text", "llm", "invoke"}

TOOL_CREDENTIAL_REQUIREMENTS = {
    "system": [], "file": [], "text": [], "llm": [], "invoke": [],
    "hubspot": ["access_token", "refresh_token", "hub_id"],
    "gmail": ["access_token", "refresh_token"],
    "gcalendar": ["access_token", "refresh_token"],
    "gsheets": ["access_token", "refresh_token"],
    "gmaps": ["api_key"],
}


# ──────────────────────────────────────────────────────────────
# Validator
# ──────────────────────────────────────────────────────────────

class AgentValidator:

    def __init__(self, tenant_id: int = None, session=None):
        """
        Initialize validator with tenant context for credential validation.
        
        Args:
            tenant_id: The tenant ID for DB credential lookup
            session: SQLAlchemy session for database queries
        """
        self.tenant_id = tenant_id
        self.session = session

    def validate(self, data: dict) -> dict:
        errors   = []
        warnings = []

        self._check_core_fields(data, errors)
        self._check_llm(data, errors, warnings)
        self._check_memory(data, warnings)
        self._check_tools(data, errors, warnings)
        self._check_features(data, warnings)

        is_valid = len(errors) == 0
        logger.debug(
            "agent_validator: valid=%s errors=%d warnings=%d",
            is_valid, len(errors), len(warnings),
        )
        return {
            "valid":       is_valid,
            "errors":      errors,
            "warnings":    warnings,
            "parsed_data": data if is_valid else None,
        }

    # ────────────────────────────────────────────────────────
    # Core / LLM / Memory checks
    # ────────────────────────────────────────────────────────

    def _check_core_fields(self, data: dict, errors: list):
        for field in REQUIRED_CORE_FIELDS:
            value = data.get(field)
            if not value or (isinstance(value, str) and not value.strip()):
                errors.append(f"Missing required field: '{field}'")

        if data.get("agent_name") and len(data["agent_name"]) > 100:
            errors.append(
                f"'agent_name' exceeds 100 characters "
                f"(current: {len(data['agent_name'])})."
            )

    def _check_llm(self, data: dict, errors: list, warnings: list):
        llm = data.get("llm")
        if not llm or not isinstance(llm, dict):
            errors.append(
                "Missing 'llm' block. "
                'Required: {"provider": "openai", "model": "gpt-4-turbo"}'
            )
            return

        for field in REQUIRED_LLM_FIELDS:
            if not llm.get(field):
                errors.append(f"'llm.{field}' is required.")

        provider = (llm.get("provider") or "").lower()
        if provider and provider not in VALID_PROVIDERS:
            warnings.append(
                f"'llm.provider' value '{provider}' is not in the known list "
                f"{sorted(VALID_PROVIDERS)}. Ensure it exists in tbl_llm."
            )

        temperature = llm.get("temperature")
        if temperature is not None:
            try:
                t = float(temperature)
                if not (0.0 <= t <= 1.0):
                    errors.append(f"'llm.temperature' must be 0.0–1.0, got {t}.")
            except (TypeError, ValueError):
                errors.append(f"'llm.temperature' must be a number, got '{temperature}'.")

    def _check_memory(self, data: dict, warnings: list):
        memory = data.get("memory")
        if memory is None:
            warnings.append(
                "'memory' block not set — agent will have no memory. "
                'Add: {"enabled": true, "type": "short_term"}'
            )
            return
        if not isinstance(memory, dict):
            warnings.append("'memory' should be a dict.")
            return
        mem_type = memory.get("type")
        if mem_type is not None and mem_type not in VALID_MEMORY_TYPES:
            warnings.append(
                f"'memory.type' '{mem_type}' not recognised. "
                f"Use: {sorted([t for t in VALID_MEMORY_TYPES if t])}."
            )

    # ────────────────────────────────────────────────────────
    # Tools check with ENHANCED credential validation
    # ────────────────────────────────────────────────────────

    def _check_tools(self, data: dict, errors: list, warnings: list):
        tools = data.get("tools")

        if tools is None or (isinstance(tools, list) and len(tools) == 0):
            errors.append(
                "At least one tool is required. "
                "Add a 'tools' array. "
                f"Supported tools: {sorted(SUPPORTED_TOOLS)}."
            )
            return

        if not isinstance(tools, list):
            errors.append("'tools' must be a list.")
            return

        for idx, tool in enumerate(tools):
            label = f"tools[{idx}]"

            if not isinstance(tool, dict):
                errors.append(f"{label} must be an object.")
                continue

            tool_name = (tool.get("tool_name") or "").strip().lower()
            tool_type = (tool.get("tool_type") or "local").lower()

            if not tool_name:
                errors.append(f"{label}: 'tool_name' is required.")
                continue

            # 1. Check tool is supported
            if tool_name not in SUPPORTED_TOOLS:
                errors.append(
                    f"{label}: tool '{tool_name}' is not supported. "
                    f"Supported tools: {sorted(SUPPORTED_TOOLS)}."
                )
                continue

            if tool_type not in ("local", "mcp"):
                errors.append(
                    f"{label} ('{tool_name}'): 'tool_type' must be 'local' or 'mcp', "
                    f"got '{tool_type}'."
                )

            # 2. Validate action_tools
            self._check_action_tools(tool, tool_name, label, errors, warnings)

            # 3. ENHANCED credential validation with DB comparison
            if tool_type == "local":
                self._check_credentials_enhanced(tool, tool_name, label, errors, warnings)
            elif tool_type == "mcp":
                self._check_mcp_fields(tool, tool_name, label, errors)

    def _check_action_tools(
        self, tool: dict, tool_name: str, label: str,
        errors: list, warnings: list
    ):
        """Validate user-supplied action_tools"""
        user_actions = tool.get("action_tools")
        valid_actions = TOOL_ACTION_MAP[tool_name]

        if user_actions is None or (isinstance(user_actions, list) and len(user_actions) == 0):
            errors.append(
                f"{label} ('{tool_name}'): 'action_tools' is required and cannot be empty. "
                f"Valid actions for '{tool_name}': {valid_actions}."
            )
            return

        if not isinstance(user_actions, list):
            errors.append(f"{label} ('{tool_name}'): 'action_tools' must be a list.")
            return

        invalid_actions = [a for a in user_actions if a not in valid_actions]
        if invalid_actions:
            errors.append(
                f"{label} ('{tool_name}'): invalid action(s) {invalid_actions}. "
                f"Valid actions for '{tool_name}': {valid_actions}."
            )

        tool["action_tools"] = [str(a).strip() for a in user_actions if str(a).strip() in valid_actions]

        logger.debug(
            "agent_validator: '%s' action_tools validated → %s",
            tool_name, tool["action_tools"],
        )

    def _check_credentials_enhanced(
        self, tool: dict, tool_name: str, label: str,
        errors: list, warnings: list
    ):
        """
        ENHANCED credential validation with:
        1. Field presence check
        2. DB credential comparison
        3. Expiry validation
        4. Specific error messages
        """
        # System-level tools need no credentials
        if tool_name in NO_AUTH_TOOLS:
            if tool.get("credentials"):
                warnings.append(
                    f"{label} ('{tool_name}'): credentials are not required "
                    "for this tool and will be ignored."
                )
            return

        required_keys = TOOL_CREDENTIAL_REQUIREMENTS.get(tool_name)

        if required_keys is None:
            warnings.append(
                f"{label} ('{tool_name}'): no credential template registered. "
                "Credentials will be stored as-is."
            )
            return

        if len(required_keys) == 0:
            return

        creds = tool.get("credentials")
        if not creds or not isinstance(creds, dict):
            errors.append(
                f"{label} ('{tool_name}'): 'credentials' object is required. "
                f"Must contain: {required_keys}."
            )
            return

        # ──────────────────────────────────────────────────────────────
        # STEP 1: Check required fields are present
        # ──────────────────────────────────────────────────────────────
        missing = [k for k in required_keys if not creds.get(k)]
        if missing:
            errors.append(
                f"{label} ('{tool_name}'): missing credential field(s): {missing}. "
                f"Required: {required_keys}."
            )
            return  # Can't proceed without required fields

        # ──────────────────────────────────────────────────────────────
        # STEP 2: Compare with stored credentials (if tenant context provided)
        # ──────────────────────────────────────────────────────────────
        if self.tenant_id and self.session:
            self._validate_against_stored_credentials(
                tool, tool_name, label, creds, errors, warnings
            )
        else:
            logger.debug(
                "agent_validator: no tenant_id/session provided, "
                "skipping DB credential comparison for '%s'",
                tool_name
            )

    def _validate_against_stored_credentials(
        self, tool: dict, tool_name: str, label: str,
        provided_creds: dict, errors: list, warnings: list
    ):
        """
        Compare provided credentials with stored DB credentials.
        Check for:
        1. Credential mismatch
        2. Token expiry
        """
        from app.models.tool_authorization import ToolAuthorization

        try:
            # Query stored credentials
            stored = (
                self.session.query(ToolAuthorization)
                .filter_by(
                    tenant_id=self.tenant_id,
                    tool_name=tool_name,
                    del_flag=False
                )
                .first()
            )

            if not stored:
                # First-time setup - no stored credentials yet
                logger.info(
                    "agent_validator: no stored credentials found for tenant=%d tool='%s' "
                    "(first-time import - allowing)",
                    self.tenant_id, tool_name
                )
                return

            stored_token_json = stored.token_json or {}

            # ──────────────────────────────────────────────────────────────
            # VALIDATION 1: Check Expiry (if present)
            # ──────────────────────────────────────────────────────────────
            expiry_str = stored_token_json.get("expiry") or provided_creds.get("expiry")
            
            if expiry_str:
                try:
                    # Parse expiry (format: "2026-02-09T08:51:43.553611Z" or "2026-02-09T08:51:43Z")
                    expiry_dt = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)
                    
                    if expiry_dt < now:
                        errors.append(
                            f"{label} ('{tool_name}'): ❌ CREDENTIALS EXPIRED. "
                            f"Token expired on {expiry_str}. "
                            f"Please reconnect the tool via OAuth to get fresh tokens."
                        )
                        return  # Stop validation - expired tokens are invalid
                        
                except (ValueError, AttributeError) as e:
                    warnings.append(
                        f"{label} ('{tool_name}'): could not parse expiry date '{expiry_str}': {e}"
                    )

            # ──────────────────────────────────────────────────────────────
            # VALIDATION 2: Compare Credentials
            # ──────────────────────────────────────────────────────────────
            mismatches = []

            # Compare access_token
            if "access_token" in provided_creds:
                stored_access = stored_token_json.get("access_token", "").strip()
                provided_access = provided_creds.get("access_token", "").strip()
                
                if stored_access and provided_access and stored_access != provided_access:
                    mismatches.append("access_token")

            # Compare refresh_token
            if "refresh_token" in provided_creds:
                stored_refresh = stored_token_json.get("refresh_token", "").strip()
                provided_refresh = provided_creds.get("refresh_token", "").strip()
                
                if stored_refresh and provided_refresh and stored_refresh != provided_refresh:
                    mismatches.append("refresh_token")

            # Compare hub_id (HubSpot specific)
            if "hub_id" in provided_creds:
                stored_hub_id = stored_token_json.get("hub_id")
                provided_hub_id = provided_creds.get("hub_id")
                
                if stored_hub_id and provided_hub_id and stored_hub_id != provided_hub_id:
                    mismatches.append("hub_id")

            # Compare api_key (Gmaps specific)
            if "api_key" in provided_creds:
                stored_api_key = stored_token_json.get("api_key", "").strip()
                provided_api_key = provided_creds.get("api_key", "").strip()
                
                if stored_api_key and provided_api_key and stored_api_key != provided_api_key:
                    mismatches.append("api_key")

            if mismatches:
                errors.append(
                    f"{label} ('{tool_name}'): ❌ CREDENTIALS MISMATCH. "
                    f"The following fields don't match stored credentials: {mismatches}. "
                    f"Either use the currently connected credentials or reconnect the tool with new ones."
                )
                return

            # ──────────────────────────────────────────────────────────────
            # VALIDATION 3: All checks passed
            # ──────────────────────────────────────────────────────────────
            logger.info(
                "agent_validator: ✅ credentials validated successfully for tenant=%d tool='%s'",
                self.tenant_id, tool_name
            )

        except Exception as e:
            logger.error(
                "agent_validator: error comparing credentials for tool '%s': %s",
                tool_name, e, exc_info=True
            )
            warnings.append(
                f"{label} ('{tool_name}'): could not validate credentials against DB: {str(e)}"
            )

    def _check_mcp_fields(self, tool: dict, tool_name: str, label: str, errors: list):
        for field in ("mcp_url", "tool_name"):
            if not tool.get(field):
                errors.append(
                    f"{label} ('{tool_name}'): MCP tool requires '{field}'."
                )

    # ────────────────────────────────────────────────────────
    # Features / Safe AI
    # ────────────────────────────────────────────────────────

    def _check_features(self, data: dict, warnings: list):
        features = data.get("features")
        if features and isinstance(features, dict):
            unknown = set(features.keys()) - VALID_FEATURE_KEYS
            if unknown:
                warnings.append(
                    f"Unknown feature key(s) {sorted(unknown)} will be stored but ignored."
                )

        safe_ai = data.get("safe_ai_settings")
        if safe_ai and isinstance(safe_ai, dict):
            unknown = set(safe_ai.keys()) - VALID_SAFE_AI_KEYS
            if unknown:
                warnings.append(
                    f"Unknown safe_ai_settings key(s) {sorted(unknown)} will be stored but ignored."
                )


