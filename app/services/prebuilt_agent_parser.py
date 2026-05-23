"""
prebuilt_agent_parser.py

Parses uploaded agent files for Super Admin prebuilt agent import.
Handles JSON and ZIP formats.

KEY DIFFERENCE from regular agent_parser.py:
  - Does NOT expect or parse credentials
  - Only extracts tool names and action_tools
  - No credential validation needed
"""

import json
import logging
import zipfile
import io

logger = logging.getLogger(__name__)


class PrebuiltAgentParser:
    """
    Parses agent configuration files for Super Admin prebuilt agent system.
    NO credential handling - only agent structure and tool requirements.
    """

    def parse(self, file) -> dict:
        """
        Parse uploaded file and extract agent config (without credentials).
        
        Args:
            file: FileStorage object (Flask) or file-like object
            
        Returns:
            Agent configuration dict (single agent) or list of dicts (multi-agent)
            
        Raises:
            ValueError: If file format is invalid
        """
        filename = getattr(file, "filename", "")
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

        logger.debug("prebuilt_agent_parser: parsing file '%s' (ext=%s)", filename, ext)

        if ext == "json":
            return self._parse_json(file)
        elif ext == "zip":
            return self._parse_zip(file)
        else:
            raise ValueError(
                f"Unsupported file type: .{ext}. "
                "Supported formats: .json, .zip"
            )

    def _parse_json(self, file) -> dict:
        """Parse a single JSON file"""
        try:
            content = file.read()
            if isinstance(content, bytes):
                content = content.decode("utf-8")
            
            data = json.loads(content)
            logger.debug("prebuilt_agent_parser: JSON parsed successfully")
            
            # Strip credentials if accidentally included
            data = self._strip_credentials(data)
            
            return data
        except json.JSONDecodeError as e:
            logger.error("prebuilt_agent_parser: JSON decode error - %s", e)
            raise ValueError(f"Invalid JSON format: {e}")
        except Exception as e:
            logger.exception("prebuilt_agent_parser: unexpected JSON parse error")
            raise ValueError(f"Failed to parse JSON: {e}")

    def _parse_zip(self, file):
        """
        Parse a ZIP archive containing agent configs.
        
        Supports:
          - Single agent: agent.json at root
          - Multi-agent: Multiple .zip files inside
        """
        try:
            zip_bytes = file.read()
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                names = zf.namelist()
                logger.debug("prebuilt_agent_parser: ZIP contains %d files", len(names))

                # Single agent with agent.json at root
                if "agent.json" in names:
                    logger.debug("prebuilt_agent_parser: found agent.json at root")
                    content = zf.read("agent.json").decode("utf-8")
                    data = json.loads(content)
                    data = self._strip_credentials(data)
                    return data

                # Multi-agent bundle (nested ZIPs)
                inner_zips = [n for n in names if n.endswith(".zip")]
                if inner_zips:
                    logger.debug(
                        "prebuilt_agent_parser: found %d inner ZIPs (multi-agent)",
                        len(inner_zips)
                    )
                    agents = []
                    for inner_zip_name in inner_zips:
                        inner_bytes = zf.read(inner_zip_name)
                        with zipfile.ZipFile(io.BytesIO(inner_bytes), "r") as inner_zf:
                            if "agent.json" in inner_zf.namelist():
                                content = inner_zf.read("agent.json").decode("utf-8")
                                data = json.loads(content)
                                data = self._strip_credentials(data)
                                agents.append(data)
                    
                    if not agents:
                        raise ValueError("No agent.json found in inner ZIP files")
                    
                    return agents

                raise ValueError(
                    "ZIP must contain either 'agent.json' at root or "
                    "multiple inner .zip files with agent.json"
                )

        except zipfile.BadZipFile:
            raise ValueError("Invalid ZIP file format")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in ZIP: {e}")
        except Exception as e:
            logger.exception("prebuilt_agent_parser: ZIP parse error")
            raise ValueError(f"Failed to parse ZIP: {e}")

    def _strip_credentials(self, data):
        """
        Remove any credential data from agent config.
        Prebuilt agents should NOT contain credentials.
        
        Args:
            data: Agent config dict or list of dicts
            
        Returns:
            Cleaned data (single dict or list)
        """
        if isinstance(data, list):
            return [self._strip_credentials_single(agent) for agent in data]
        return self._strip_credentials_single(data)

    def _strip_credentials_single(self, agent_data: dict) -> dict:
        """Strip credentials from a single agent config"""
        # Make a copy to avoid mutating original
        cleaned = agent_data.copy()
        
        # Remove credentials from tools
        tools = cleaned.get("tools", [])
        if isinstance(tools, list):
            cleaned_tools = []
            for tool in tools:
                if isinstance(tool, dict):
                    cleaned_tool = {
                        "tool_name": tool.get("tool_name"),
                        "tool_type": tool.get("tool_type", "local"),
                        "action_tools": tool.get("action_tools", []),
                    }
                    # Remove credentials, mcp_url, mcp_json
                    # Keep only tool name, type, and actions
                    cleaned_tools.append(cleaned_tool)
            cleaned["tools"] = cleaned_tools
        
        logger.debug(
            "prebuilt_agent_parser: stripped credentials from '%s'",
            agent_data.get("agent_name", "unnamed")
        )
        
        return cleaned
