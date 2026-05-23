"""
prebuilt_agent_validator.py

Validates prebuilt agent configs for Super Admin import.

KEY DIFFERENCE from agent_validator.py:
  - Does NOT validate credentials
  - Does NOT check credential expiry
  - Does NOT compare with stored credentials
  - ONLY validates: schema, LLM config, tool names, action_tools
"""

import logging

logger = logging.getLogger(__name__)

# Core validation constants
REQUIRED_CORE_FIELDS = ["agent_name", "agent_description", "agent_role"]
REQUIRED_LLM_FIELDS = ["provider", "model"]
VALID_MEMORY_TYPES = {"short_term", "long_term", None}
VALID_PROVIDERS = {"openai", "anthropic", "groq", "mistral", "ollama", "azure"}

# Tool action mappings (same as regular validator)
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

# Valid categories for prebuilt agents
VALID_CATEGORIES = {
    "Sales", "Marketing", "Support", "HR", "Finance",
    "Operations", "Analytics", "General", "Custom"
}

# Valid plan levels
VALID_PLAN_LEVELS = {1, 2, 3, 4}  # 1=Free, 2=Pro, 3=Team, 4=Enterprise


class PrebuiltAgentValidator:
    """
    Validates prebuilt agent configurations WITHOUT credential checks.
    Used by Super Admin for importing agent templates.
    """

    def validate(self, data: dict) -> dict:
        """
        Validate prebuilt agent configuration.
        
        Args:
            data: Agent configuration dict
            
        Returns:
            {
                "valid": True/False,
                "errors": [...],
                "warnings": [...],
                "parsed_data": {...}  # Only if valid
            }
        """
        errors = []
        warnings = []

        self._check_core_fields(data, errors)
        self._check_llm(data, errors, warnings)
        self._check_memory(data, warnings)
        self._check_tools_no_credentials(data, errors, warnings)
        self._check_category(data, warnings)
        self._check_plan_level(data, warnings)

        is_valid = len(errors) == 0
        
        logger.debug(
            "prebuilt_agent_validator: valid=%s errors=%d warnings=%d",
            is_valid, len(errors), len(warnings)
        )
        
        return {
            "valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "parsed_data": data if is_valid else None,
        }

    def _check_core_fields(self, data: dict, errors: list):
        """Validate required core fields"""
        for field in REQUIRED_CORE_FIELDS:
            value = data.get(field)
            if not value or (isinstance(value, str) and not value.strip()):
                errors.append(f"Missing required field: '{field}'")

        if data.get("agent_name") and len(data["agent_name"]) > 100:
            errors.append(
                f"'agent_name' exceeds 100 characters (current: {len(data['agent_name'])})"
            )

    def _check_llm(self, data: dict, errors: list, warnings: list):
        """Validate LLM configuration"""
        llm = data.get("llm")
        if not llm or not isinstance(llm, dict):
            errors.append(
                "Missing 'llm' block. Required: "
                '{"provider": "openai", "model": "gpt-4-turbo"}'
            )
            return

        for field in REQUIRED_LLM_FIELDS:
            if not llm.get(field):
                errors.append(f"'llm.{field}' is required")

        provider = (llm.get("provider") or "").lower()
        if provider and provider not in VALID_PROVIDERS:
            warnings.append(
                f"'llm.provider' value '{provider}' is not in the known list "
                f"{sorted(VALID_PROVIDERS)}"
            )

        temperature = llm.get("temperature")
        if temperature is not None:
            try:
                t = float(temperature)
                if not (0.0 <= t <= 1.0):
                    errors.append(f"'llm.temperature' must be 0.0–1.0, got {t}")
            except (TypeError, ValueError):
                errors.append(
                    f"'llm.temperature' must be a number, got '{temperature}'"
                )

    def _check_memory(self, data: dict, warnings: list):
        """Validate memory configuration"""
        memory = data.get("memory")
        if memory is None:
            # Memory is optional for prebuilt agents
            return
        
        if not isinstance(memory, dict):
            warnings.append("'memory' should be a dict")
            return
        
        mem_type = memory.get("type")
        if mem_type is not None and mem_type not in VALID_MEMORY_TYPES:
            warnings.append(
                f"'memory.type' '{mem_type}' not recognised. "
                f"Use: {sorted([t for t in VALID_MEMORY_TYPES if t])}"
            )

    def _check_tools_no_credentials(self, data: dict, errors: list, warnings: list):
        """
        Validate tools WITHOUT checking credentials.
        Only validates: tool_name, action_tools
        """
        tools = data.get("tools")

        if tools is None or (isinstance(tools, list) and len(tools) == 0):
            errors.append(
                "At least one tool is required. "
                f"Supported tools: {sorted(SUPPORTED_TOOLS)}"
            )
            return

        if not isinstance(tools, list):
            errors.append("'tools' must be a list")
            return

        for idx, tool in enumerate(tools):
            label = f"tools[{idx}]"

            if not isinstance(tool, dict):
                errors.append(f"{label} must be an object")
                continue

            tool_name = (tool.get("tool_name") or "").strip().lower()

            if not tool_name:
                errors.append(f"{label}: 'tool_name' is required")
                continue

            # Check tool is supported
            if tool_name not in SUPPORTED_TOOLS:
                errors.append(
                    f"{label}: tool '{tool_name}' is not supported. "
                    f"Supported tools: {sorted(SUPPORTED_TOOLS)}"
                )
                continue

            # Validate action_tools
            self._check_action_tools(tool, tool_name, label, errors, warnings)

            # ⚠️ SKIP credential validation - this is the key difference
            # No _check_credentials() call here!
            
            # Warn if credentials accidentally included
            if tool.get("credentials"):
                warnings.append(
                    f"{label} ('{tool_name}'): Credentials found but will be IGNORED. "
                    "Prebuilt agents do not store credentials."
                )

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
                f"Valid actions for '{tool_name}': {valid_actions}"
            )
            return

        if not isinstance(user_actions, list):
            errors.append(f"{label} ('{tool_name}'): 'action_tools' must be a list")
            return

        invalid_actions = [a for a in user_actions if a not in valid_actions]
        if invalid_actions:
            errors.append(
                f"{label} ('{tool_name}'): invalid action(s) {invalid_actions}. "
                f"Valid actions for '{tool_name}': {valid_actions}"
            )

        # Normalize actions
        tool["action_tools"] = [
            str(a).strip() for a in user_actions if str(a).strip() in valid_actions
        ]

    def _check_category(self, data: dict, warnings: list):
        """Validate category field"""
        category = data.get("category")
        if category and category not in VALID_CATEGORIES:
            warnings.append(
                f"Category '{category}' not in standard list: {sorted(VALID_CATEGORIES)}. "
                "You can still use it, but consider using a standard category."
            )

    def _check_plan_level(self, data: dict, warnings: list):
        """Validate minimum_plan_level field"""
        plan_level = data.get("minimum_plan_level")
        if plan_level is not None:
            if plan_level not in VALID_PLAN_LEVELS:
                warnings.append(
                    f"minimum_plan_level {plan_level} is not valid. "
                    f"Valid levels: {sorted(VALID_PLAN_LEVELS)} "
                    "(1=Free, 2=Pro, 3=Team, 4=Enterprise)"
                )














# """
# prebuilt_agent_validator.py

# Validator for super admin prebuilt agent imports.
# Key difference from regular validator: NO credential validation.
# Only validates structure, not credentials.
# """

# import logging

# logger = logging.getLogger(__name__)

# # Reuse constants from regular validator
# REQUIRED_CORE_FIELDS = ["agent_name", "agent_description", "agent_role"]
# REQUIRED_LLM_FIELDS = ["provider", "model"]
# VALID_MEMORY_TYPES = {"short_term", "long_term", None}
# VALID_PROVIDERS = {"openai", "anthropic", "groq", "mistral", "ollama", "azure"}

# TOOL_ACTION_MAP = {
#     "hubspot": [
#         "get_contact_by_email", "create_contact", "update_contact",
#         "list_hubspot_contacts", "search_hubspot_contact",
#         "create_company", "list_companies", "get_companies_by_domain",
#         "create_deal", "get_deal", "update_deal", "create_note",
#         "search", "get_company", "find_company", "association_query",
#     ],
#     "invoke": ["webhook_invoker"],
#     "system": ["get_datetime", "parse_json", "calculator_basic"],
#     "llm": ["make_decision", "evaluate_condition", "extract_field"],
#     "text": ["splitter"],
#     "file": ["read_excel", "read_pdf", "create_pdf"],
#     "gmaps": ["commute_time", "nearby_facilities"],
#     "gmail": [
#         "send_gmail", "draft_gmail", "list_gmail_messages",
#         "read_gmail_messages", "download_gmail_attachment",
#         "search_gmail_messages", "get_email_from_token",
#         "mark_as_read", "mark_as_unread", "modify_gmail_labels",
#         "delete_gmail_messages", "read_unread_gmail_messages",
#     ],
#     "gcalendar": [
#         "create_event", "list_event", "update_event",
#         "delete_event", "get_free_busy",
#     ],
#     "gsheets": [
#         "list_spreadsheets", "list_sheets", "get_metadata",
#         "duplicate_sheet", "read_spreadsheet", "write_spreadsheet",
#         "append_spreadsheet", "create_sheet", "clear_spreadsheet",
#     ],
# }

# SUPPORTED_TOOLS = set(TOOL_ACTION_MAP.keys())


# class PrebuiltAgentValidator:
#     """
#     Validates prebuilt agent imports from super admin.
    
#     Key differences from AgentValidator:
#     - Does NOT validate credentials (none should be provided)
#     - Does NOT check expiry
#     - Does NOT compare with stored credentials
#     - Only validates structure and tool requirements
#     """
    
#     def validate(self, data: dict) -> dict:
#         """
#         Validate agent structure without credential validation.
        
#         Returns:
#             {
#                 "valid": True/False,
#                 "errors": [...],
#                 "warnings": [...],
#                 "parsed_data": {...}
#             }
#         """
#         errors = []
#         warnings = []
        
#         self._check_core_fields(data, errors)
#         self._check_llm(data, errors, warnings)
#         self._check_memory(data, warnings)
#         self._check_tools_structure_only(data, errors, warnings)
#         self._check_features(data, warnings)
        
#         is_valid = len(errors) == 0
#         logger.debug(
#             "prebuilt_agent_validator: valid=%s errors=%d warnings=%d",
#             is_valid, len(errors), len(warnings),
#         )
#         return {
#             "valid": is_valid,
#             "errors": errors,
#             "warnings": warnings,
#             "parsed_data": data if is_valid else None,
#         }
    
#     def _check_core_fields(self, data: dict, errors: list):
#         """Check required core fields"""
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
#         """Check LLM configuration"""
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
#                 f"{sorted(VALID_PROVIDERS)}."
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
#         """Check memory configuration"""
#         memory = data.get("memory")
#         if memory is None:
#             warnings.append(
#                 "'memory' block not set — agent will have no memory."
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
    
#     def _check_tools_structure_only(self, data: dict, errors: list, warnings: list):
#         """
#         Check tools structure WITHOUT credential validation.
        
#         Key differences from regular validator:
#         - Does NOT check credentials at all
#         - Warns if credentials are provided (shouldn't be)
#         - Only validates tool names and action_tools
#         """
#         tools = data.get("tools")
        
#         if tools is None or (isinstance(tools, list) and len(tools) == 0):
#             errors.append(
#                 "At least one tool is required. "
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
            
#             # Check tool is supported
#             if tool_name not in SUPPORTED_TOOLS:
#                 errors.append(
#                     f"{label}: tool '{tool_name}' is not supported. "
#                     f"Supported tools: {sorted(SUPPORTED_TOOLS)}."
#                 )
#                 continue
            
#             if tool_type not in ("local", "mcp"):
#                 errors.append(
#                     f"{label} ('{tool_name}'): 'tool_type' must be 'local' or 'mcp', "
#                     f"got '{tool_type}'."
#                 )
            
#             # Validate action_tools
#             self._check_action_tools(tool, tool_name, label, errors, warnings)
            
#             # ⚠️ KEY DIFFERENCE: Check that credentials are NOT provided
#             if tool.get("credentials"):
#                 warnings.append(
#                     f"{label} ('{tool_name}'): credentials should NOT be provided "
#                     "in prebuilt agent imports. They will be ignored. "
#                     "Users will connect their own credentials when activating."
#                 )
#                 # Remove credentials from data to avoid storing them
#                 tool.pop("credentials", None)
            
#             # MCP fields check
#             if tool_type == "mcp":
#                 self._check_mcp_fields(tool, tool_name, label, errors)
    
#     def _check_action_tools(
#         self, tool: dict, tool_name: str, label: str,
#         errors: list, warnings: list
#     ):
#         """Validate action_tools array"""
#         user_actions = tool.get("action_tools")
#         valid_actions = TOOL_ACTION_MAP[tool_name]
        
#         if user_actions is None or (isinstance(user_actions, list) and len(user_actions) == 0):
#             errors.append(
#                 f"{label} ('{tool_name}'): 'action_tools' is required and cannot be empty. "
#                 f"Valid actions for '{tool_name}': {valid_actions}."
#             )
#             return
        
#         if not isinstance(user_actions, list):
#             errors.append(f"{label} ('{tool_name}'): 'action_tools' must be a list.")
#             return
        
#         invalid_actions = [a for a in user_actions if a not in valid_actions]
#         if invalid_actions:
#             errors.append(
#                 f"{label} ('{tool_name}'): invalid action(s) {invalid_actions}. "
#                 f"Valid actions for '{tool_name}': {valid_actions}."
#             )
        
#         tool["action_tools"] = [str(a).strip() for a in user_actions if str(a).strip() in valid_actions]
        
#         logger.debug(
#             "prebuilt_agent_validator: '%s' action_tools validated → %s",
#             tool_name, tool["action_tools"],
#         )
    
#     def _check_mcp_fields(self, tool: dict, tool_name: str, label: str, errors: list):
#         """Check MCP tool fields"""
#         for field in ("mcp_url", "tool_name"):
#             if not tool.get(field):
#                 errors.append(
#                     f"{label} ('{tool_name}'): MCP tool requires '{field}'."
#                 )
    
#     def _check_features(self, data: dict, warnings: list):
#         """Check features and safe_ai_settings"""
#         features = data.get("features")
#         if features and isinstance(features, dict):
#             # All features are optional for prebuilt agents
#             pass
        
#         safe_ai = data.get("safe_ai_settings")
#         if safe_ai and isinstance(safe_ai, dict):
#             # All safe_ai settings are optional
#             pass