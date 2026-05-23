from flask import Blueprint, request, jsonify
import requests
import json

from engine.utils import prepare_agent_input
from logging_config import setup_logging
from engine.langgraph_urls import LANGGRAPH_ANALYZE_URL


workflow_agent_bp = Blueprint("workflow_agent", __name__)
logger = setup_logging("workflow_agent", level="INFO")




def normalize_for_analyze(payload: dict) -> dict:
    """
    Normalize payload so it passes FastAPI validation
    for analyze_task_parameters.
    """
    normalized = dict(payload)

    # 1️⃣ tenant_id → string
    if "tenant_id" in normalized and normalized["tenant_id"] is not None:
        normalized["tenant_id"] = str(normalized["tenant_id"])

    config = dict(normalized.get("config", {}))

    # 2️⃣ llm_provider enum → string
    llm_provider = config.get("llm_provider")
    if hasattr(llm_provider, "value"):
        config["llm_provider"] = llm_provider.value

    # 3️⃣ tools_config → plain dicts
    tools_config = config.get("tools_config", {})
    clean_tools = {}

    for category, tools in tools_config.items():
        clean_tools[category] = []
        for tool in tools:
            if hasattr(tool, "model_dump"):
                clean_tools[category].append(tool.model_dump())
            else:
                clean_tools[category].append(dict(tool))

    config["tools_config"] = clean_tools

    normalized["config"] = config
    return normalized

@workflow_agent_bp.route("/Analyze_task", methods=["POST"])
def analyze_task():
    try:
        data = request.json or {}

        agent_id = data.get("agent_id")
        task = data.get("task", "")
        use_temp_llm = data.get("use_temp_llm", True)

        if not agent_id:
            return jsonify({"error": "agent_id is required"}), 400
        if not task:
            return jsonify({"error": "task is required"}), 400

        prepared = prepare_agent_input(
            agent_id=agent_id,
            task=task,
            use_temp_llm=use_temp_llm,
            use_temp_mcp_endpoint=True,
        )

        payload = normalize_for_analyze({
            "tenant_id": prepared["tenant_id"],
            "task": task,
            "config": prepared["config"],
        })

        logger.info(
            "📨 Forwarding analyze payload to LangGraph:\n"
            + json.dumps(payload, indent=2, default=str)
        )

        response = requests.post(
            LANGGRAPH_ANALYZE_URL,
            json=payload,
            timeout=60,
            headers={"Content-Type": "application/json"},
        )

        response.raise_for_status()

        return jsonify({
            "status": "success",
            "agent_id": agent_id,
            "tenant_id": payload["tenant_id"],
            "analysis": response.json(),
        })

    except requests.exceptions.RequestException as e:
        logger.exception("❌ LangGraph analyze API failed")
        return jsonify({
            "status": "error",
            "message": "Analyze task request failed",
            "details": str(e),
        }), 502
