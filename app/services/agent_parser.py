"""
agent_parser.py
Parses three file types into a normalised agent config dict:
  - agent.json            (flat JSON)
  - agent.zip             (ZIP containing agent.json + optional credentials/ + knowledge_base/)
  - agent_config.py / .js (code file containing AGENT_CONFIG = { ... })
"""

import json
import zipfile
import ast
import re
import os
import logging

logger = logging.getLogger(__name__)


class AgentParser:

    # ------------------------------------------------------------------ #
    #  Public                                                              #
    # ------------------------------------------------------------------ #

    def parse(self, file) -> dict:
        """
        Accept a Werkzeug FileStorage (or any file-like with .filename).
        Returns a normalised dict ready for AgentValidator.
        """
        filename = file.filename.lower() if hasattr(file, "filename") else ""

        if filename.endswith(".json"):
            return self._parse_json(file)
        elif filename.endswith(".zip"):
            return self._parse_zip(file)
        elif filename.endswith(".py") or filename.endswith(".js"):
            return self._parse_code(file)
        else:
            raise ValueError(
                f"Unsupported file type '{filename}'. "
                "Accepted: .json, .zip, .py, .js"
            )

    # ------------------------------------------------------------------ #
    #  Private parsers                                                     #
    # ------------------------------------------------------------------ #

    def _parse_json(self, file) -> dict:
        try:
            raw = file.read()
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("JSON root must be an object / dict.")
            logger.debug("agent_parser: JSON parsed OK, keys=%s", list(data.keys()))
            return data
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc


    # def _parse_json(self, file):
    #     try:
    #         raw = file.read()
    #         data = json.loads(raw)

    #         # ✅ allow single OR multi agent
    #         if isinstance(data, dict):
    #             return data

    #         if isinstance(data, list):
    #             if not data:
    #                 raise ValueError("JSON array is empty.")
    #             logger.info(
    #                 "agent_parser: Detected multi-agent JSON (%d agents)",
    #                 len(data),
    #             )
    #             return data

    #         raise ValueError("JSON root must be an object or array.")

    #     except json.JSONDecodeError as exc:
    #         raise ValueError(f"Invalid JSON: {exc}") from exc





    # def _parse_zip(self, file) -> dict:
    #     """
    #     Expected ZIP layout:
    #         agent.json                     ← REQUIRED
    #         credentials/gmail.json         ← optional (one file per tool)
    #         credentials/hubspot.json
    #         knowledge_base/products.pdf    ← optional KB docs
    #         README.md                      ← ignored
    #     """
    #     try:
    #         with zipfile.ZipFile(file) as zf:
    #             names = zf.namelist()
    #             logger.debug("agent_parser: ZIP contents: %s", names)

    #             # ---------- agent.json is mandatory ----------
    #             if "agent.json" not in names:
    #                 raise ValueError(
    #                     "ZIP must contain 'agent.json' at the root level."
    #                 )

    #             with zf.open("agent.json") as f:
    #                 data = json.load(f)

    #             if not isinstance(data, dict):
    #                 raise ValueError("agent.json root must be an object / dict.")

    #             # ---------- credentials/ folder ----------
    #             # Each file: credentials/<tool_name>.json
    #             # These are merged into the matching tool entry in data["tools"]
    #             credential_files = {}
    #             for name in names:
    #                 if (
    #                     name.startswith("credentials/")
    #                     and name.endswith(".json")
    #                     and name != "credentials/"
    #                 ):
    #                     tool_name = os.path.splitext(os.path.basename(name))[0].lower()
    #                     with zf.open(name) as f:
    #                         credential_files[tool_name] = json.load(f)
    #                         logger.debug(
    #                             "agent_parser: loaded credential file for tool '%s'",
    #                             tool_name,
    #                         )

    #             # Merge credential files into tools list
    #             if credential_files:
    #                 tools = data.get("tools", [])
    #                 for tool in tools:
    #                     tname = tool.get("tool_name", "").lower()
    #                     if tname in credential_files:
    #                         # credential file overrides / fills in what is missing
    #                         tool.setdefault("credentials", {})
    #                         tool["credentials"].update(credential_files[tname])
    #                 data["tools"] = tools

    #             # ---------- knowledge_base/ folder ----------
    #             kb_files = [
    #                 n
    #                 for n in names
    #                 if n.startswith("knowledge_base/") and n != "knowledge_base/"
    #             ]
    #             if kb_files:
    #                 # Store file names so the creator knows what docs to process
    #                 data["_kb_files"] = kb_files
    #                 logger.debug(
    #                     "agent_parser: %d KB file(s) found in ZIP", len(kb_files)
    #                 )

    #             return data

    #     except zipfile.BadZipFile as exc:
    #         raise ValueError(f"Uploaded file is not a valid ZIP archive: {exc}") from exc


    def _parse_zip(self, file):
        """
        Supports:

        Case 1: Single agent zip
            agent.json at root

        Case 2: Multi-agent bundle
            multiple *.zip inside
        """
        try:
            with zipfile.ZipFile(file) as zf:
                names = zf.namelist()
                logger.debug("agent_parser: ZIP contents: %s", names)

                # --------------------------------------------------
                # 🔹 CASE 1 — Direct agent.json present
                # --------------------------------------------------
                # if "agent.json" in names:
                #     return self._extract_single_agent(zf, names)



                json_files = [
                    n for n in names
                    if n.lower().endswith(".json")
                    and not n.startswith("credentials/")
                    and not n.startswith("knowledge_base/")
                ]

                # ⭐ If more than one JSON → treat as multi-agent bundle
                if len(json_files) > 1:
                    logger.info(
                        "agent_parser: Detected multi-agent JSON bundle (%d files)",
                        len(json_files),
                    )

                    agents = []

                    for jf in json_files:
                        try:
                            with zf.open(jf) as f:
                                data = json.load(f)

                            if isinstance(data, dict):
                                agents.append(data)
                            elif isinstance(data, list):
                                agents.extend(data)

                        except Exception as e:
                            logger.exception("Failed parsing %s: %s", jf, e)

                    if not agents:
                        raise ValueError("No valid agent JSON found in ZIP.")

                    return agents
                




                # --------------------------------------------------
                # 🔹 CASE 2 — single agent.json (existing behavior)
                # --------------------------------------------------
                if "agent.json" in names:
                    return self._extract_single_agent(zf, names)


                # --------------------------------------------------
                # 🔹 CASE 2 — Look for nested zip files
                # --------------------------------------------------
                nested_zips = [n for n in names if n.lower().endswith(".zip")]

                if nested_zips:
                    logger.info(
                        "agent_parser: Detected multi-agent bundle (%d zips)",
                        len(nested_zips),
                    )

                    agents = []

                    for nz in nested_zips:
                        try:
                            with zf.open(nz) as nested_file:
                                nested_bytes = nested_file.read()

                            from io import BytesIO

                            with zipfile.ZipFile(BytesIO(nested_bytes)) as inner_zip:
                                inner_names = inner_zip.namelist()

                                if "agent.json" not in inner_names:
                                    logger.warning(
                                        "Skipping %s — no agent.json found", nz
                                    )
                                    continue

                                agent_data = self._extract_single_agent(
                                    inner_zip, inner_names
                                )
                                agents.append(agent_data)

                        except Exception as e:
                            logger.exception("Failed to parse nested zip %s: %s", nz, e)

                    if not agents:
                        raise ValueError(
                            "No valid agent.zip found inside uploaded bundle."
                        )

                    return agents

                # --------------------------------------------------
                # ❌ Nothing valid
                # --------------------------------------------------
                raise ValueError(
                    "ZIP must contain either:\n"
                    "• agent.json at root OR\n"
                    "• nested agent zip files"
                )

        except zipfile.BadZipFile as exc:
            raise ValueError(f"Uploaded file is not a valid ZIP archive: {exc}") from exc


    def _extract_single_agent(self, zf, names):
        """
        Extract one agent from a zipfile.ZipFile object.
        """
    
        # ---------- load agent.json ----------
        with zf.open("agent.json") as f:
            data = json.load(f)
    
        if not isinstance(data, dict):
            raise ValueError("agent.json root must be an object / dict.")
    
        # ---------- credentials ----------
        credential_files = {}
    
        for name in names:
            if (
                name.startswith("credentials/")
                and name.endswith(".json")
                and name != "credentials/"
            ):
                tool_name = os.path.splitext(os.path.basename(name))[0].lower()
                with zf.open(name) as f:
                    credential_files[tool_name] = json.load(f)
                    logger.debug(
                        "agent_parser: loaded credential file for tool '%s'",
                        tool_name,
                    )
    
        # merge credentials
        if credential_files:
            tools = data.get("tools", [])
            for tool in tools:
                tname = tool.get("tool_name", "").lower()
                if tname in credential_files:
                    tool.setdefault("credentials", {})
                    tool["credentials"].update(credential_files[tname])
            data["tools"] = tools
    
        # ---------- knowledge base ----------
        kb_files = [
            n for n in names if n.startswith("knowledge_base/") and n != "knowledge_base/"
        ]
        if kb_files:
            data["_kb_files"] = kb_files
            logger.debug("agent_parser: %d KB file(s) found in ZIP", len(kb_files))
    
        return data
    






    def _parse_code(self, file) -> dict:
        """
        Extracts AGENT_CONFIG = { ... } from a Python or JS file.

        Python  →  uses ast.literal_eval (safe)
        JS      →  uses JSON-like regex extraction (limited subset)
        """
        try:
            src = file.read().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Code file is not valid UTF-8: {exc}") from exc

        filename = getattr(file, "filename", "").lower()

        if filename.endswith(".py"):
            return self._extract_python_config(src)
        else:
            return self._extract_js_config(src)

    # ------------------------------------------------------------------ #
    #  Code extraction helpers                                            #
    # ------------------------------------------------------------------ #

    def _extract_python_config(self, src: str) -> dict:
        """
        Find  AGENT_CONFIG = { ... }  using ast so it handles
        multiline dicts, comments, etc.
        """
        # Locate assignment node in the AST
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            raise ValueError(f"Python syntax error in uploaded file: {exc}") from exc

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "AGENT_CONFIG"
            ):
                try:
                    data = ast.literal_eval(node.value)
                    if not isinstance(data, dict):
                        raise ValueError("AGENT_CONFIG must be a dict.")
                    return data
                except ValueError as exc:
                    raise ValueError(
                        f"AGENT_CONFIG contains unsupported Python expressions: {exc}"
                    ) from exc

        raise ValueError(
            "Python file must define a top-level variable: AGENT_CONFIG = { ... }"
        )

    def _extract_js_config(self, src: str) -> dict:
        """
        Simple extraction for JS / TS config files.
        Looks for:   const AGENT_CONFIG = { ... };
                     export const AGENT_CONFIG = { ... };
                     module.exports = { ... };
        Converts single-quoted strings to double quotes and
        strips trailing commas before JSON-parsing.
        """
        patterns = [
            r"(?:export\s+)?const\s+AGENT_CONFIG\s*=\s*(\{.*?\})\s*;?",
            r"module\.exports\s*=\s*(\{.*?\})\s*;?",
        ]
        for pattern in patterns:
            match = re.search(pattern, src, re.DOTALL)
            if match:
                raw = match.group(1)
                # JS -> JSON conversions
                raw = re.sub(r"'", '"', raw)                        # single → double quotes
                raw = re.sub(r",\s*([}\]])", r"\1", raw)            # trailing commas
                raw = re.sub(r"//[^\n]*", "", raw)                   # line comments
                raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL) # block comments
                try:
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise ValueError("AGENT_CONFIG must be an object.")
                    return data
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Could not parse JS AGENT_CONFIG as JSON: {exc}"
                    ) from exc

        raise ValueError(
            "JS file must define:  const AGENT_CONFIG = { ... }  or  module.exports = { ... }"
        )
