from flask import jsonify, g
from flask_jwt_extended import get_jwt
from functools import wraps
from app.models.agent import Agent
from app.models.knowledge_base import KnowledgeBase
from app.models.llm import LLM
from datetime import datetime, timedelta
from sqlalchemy import func, case
from app.models import db, Agent, Conversation,AgentVersion
from app.models.agent import AgentStatusEnum


import logging

logger = logging.getLogger(__name__)


def validate_agent_access(allowed_status=None):

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):

            agent_id = kwargs.get("agent_id")

            if not agent_id:
                logger.warning("Agent ID missing in request")
                return jsonify({"error": "Agent ID required"}), 400

            claims = get_jwt()
            tenant_id = claims.get("tenant_id")

            if not tenant_id:
                logger.warning("Tenant ID missing in JWT")
                return jsonify({"error": "Unauthorized"}), 401

            agent = Agent.query.filter_by(
                agent_id=agent_id,
                tenant_id=tenant_id,
                del_flg=False
            ).first()

            if not agent:
                logger.warning(
                    f"Agent not found | agent_id={agent_id} | tenant_id={tenant_id}"
                )
                return jsonify({"error": "Agent not found"}), 404

            if allowed_status and agent.agent_status not in allowed_status:
                logger.warning(
                    f"Invalid status | agent_id={agent_id} | status={agent.agent_status}"
                )
                return jsonify({"error": "Agent not in editable state"}), 400

            g.agent = agent
            return func(*args, **kwargs)

        return wrapper
    return decorator

def update_agent_behaviour(agent, data):
    instructions = data.get("agent_instructions")
    mode = data.get("instruction_mode")
    agent_type = data.get("agent_type")

    if instructions is not None:
        agent.agent_instructions = instructions.strip()

    if mode is not None:
        agent.instruction_mode = mode

    if agent_type is not None:
        agent.agent_type = agent_type
        
        
def process_agent_kb_ids(session, agent, kb_ids_raw):
    """
    Validates KB IDs:
    - Must be int or list of ints
    - Must exist
    - Must belong to same tenant
    - Must not be soft deleted
    - Rejects if any invalid
    """

    if kb_ids_raw is None:
        return None, "knowledge_base_ids is required"

    # Normalize to list
    if isinstance(kb_ids_raw, list):
        raw_ids = kb_ids_raw
    else:
        raw_ids = [kb_ids_raw]

    # Validate integer conversion
    try:
        incoming_ids = [int(kb_id) for kb_id in raw_ids]
    except (TypeError, ValueError):
        return None, "knowledge_base_ids must be integer or list of integers"

    if not incoming_ids:
        return [], None

    # Validate existence + tenant scope
    valid_kbs = session.query(KnowledgeBase).filter(
        KnowledgeBase.knowledge_base_id.in_(incoming_ids),
        KnowledgeBase.tenant_id == agent.tenant_id,
        KnowledgeBase.del_flg == False
    ).all()

    valid_ids = [kb.knowledge_base_id for kb in valid_kbs]

    # Reject if any invalid
    if set(incoming_ids) != set(valid_ids):
        invalid_ids = list(set(incoming_ids) - set(valid_ids))
        return None, f"Invalid or unauthorized KB IDs: {invalid_ids}"

    return valid_ids, None

def build_guardrails_payload(data):
    return {
        "restrictions": data.get("restrictions", []),
        "response_behavior": data.get("response_behavior"),
        "response_length": data.get("response_length"),
        "escalation_rules": data.get("escalation_rules", [])
    }
    
def validate_llm(session, tenant_id, model_id):

    if not model_id:
        return None

    return session.query(LLM).filter_by(
        llm_id=model_id,
        tenant_id=tenant_id
    ).first()


# -----------------------
# DELTA CALCULATION
# -----------------------
def compute_delta(current, previous, timeframe="yesterday"):
    if previous == 0:
        return {
            "value": 0.0,
            "direction": "neutral",
            "label": f"No change from {timeframe}"
        }

    delta = ((current - previous) / previous) * 100
    direction = (
        "up" if delta > 0 else
        "down" if delta < 0 else
        "neutral"
    )

    label_map = {
        "up": f"Up from {timeframe}",
        "down": f"Down from {timeframe}",
        "neutral": f"No change from {timeframe}"
    }

    return {
        "value": round(abs(delta), 1),
        "direction": direction,
        "label": label_map[direction]
    }

# -----------------------
# MAIN DASHBOARD BUILDER
# -----------------------
def build_agent_dashboard_analytics(tenant_id):
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)

    # -----------------------
    # TOTAL AGENTS
    # -----------------------
    total_agents = db.session.query(func.count()).filter(
        Agent.tenant_id == tenant_id,
        Agent.del_flg == False
    ).scalar() or 0

    agents_yesterday = db.session.query(func.count()).filter(
        Agent.tenant_id == tenant_id,
        Agent.del_flg == False,
        func.date(Agent.created_at) <= yesterday
    ).scalar() or 0

    # -----------------------
    # LIVE AGENTS
    # -----------------------
    live_agents = db.session.query(func.count()).filter(
        Agent.tenant_id == tenant_id,
        Agent.del_flg == False,
        Agent.agent_status == AgentStatusEnum.LIVE
    ).scalar() or 0

    live_agents_last_week = db.session.query(func.count()).filter(
        Agent.tenant_id == tenant_id,
        Agent.del_flg == False,
        Agent.agent_status == AgentStatusEnum.LIVE,
        func.date(Agent.created_at) <= last_week
    ).scalar() or 0

    # -----------------------
    # MESSAGES (Conversations)
    # -----------------------
    total_messages = db.session.query(
        func.count(Conversation.conversation_id)
    ).filter(
        Conversation.tenant_id == tenant_id
    ).scalar() or 0

    messages_yesterday = db.session.query(
        func.count(Conversation.conversation_id)
    ).filter(
        Conversation.tenant_id == tenant_id,
        func.date(Conversation.created_at) <= yesterday
    ).scalar() or 0

    # -----------------------
    # USERS (Not Available Yet)
    # -----------------------
    total_users = 0
    users_yesterday = 0

    # -----------------------
    # RETURN FINAL STRUCTURE
    # -----------------------
    return {
        "total_agents": {
            "count": total_agents,
            "delta": compute_delta(
                total_agents,
                agents_yesterday,
                "yesterday"
            )
        },
        "live_agents": {
            "count": live_agents,
            "delta": compute_delta(
                live_agents,
                live_agents_last_week,
                "past week"
            )
        },
        "total_messages": {
            "count": total_messages,
            "delta": compute_delta(
                total_messages,
                messages_yesterday,
                "yesterday"
            )
        },
        "total_users": {
            "count": total_users,
            "delta": compute_delta(
                total_users,
                users_yesterday,
                "yesterday"
            )
        }
    }
    
    

def build_agent_snapshot(agent: Agent) -> dict:
    return {
        "agent_id": agent.agent_id,
        "agent_name": agent.agent_name,
        "agent_description": agent.agent_description,
        "agent_type": agent.agent_type,
        "persona_style": agent.persona_style,
        "agent_instructions": agent.agent_instructions,
        "instruction_mode": agent.instruction_mode,
        "knowledge_base_ids": agent.knowledge_base_ids,
        "guardrails": agent.guardrails,
        "llm_provider_id": getattr(agent, "llm_provider_id", agent.llm_model_id),
        "llm_model_id": agent.llm_model_id,
        "temperature": agent.temperature,
        "max_tokens": agent.max_tokens,
        "memory_mode": agent.memory_mode,
        "greeting_message": agent.greeting_message,
        "language": agent.language,
        "timezone": agent.timezone,
        "tone": agent.tone,
        "emoji_mode": agent.emoji_mode,
        "availability_mode": agent.availability_mode,
        "additional_instructions": agent.additional_instructions,
        "Examples": agent.Examples,
        "deployment_method": agent.deployment_method
    }
    

def resolve_agent_config(agent: Agent):

    if agent.agent_status == AgentStatusEnum.LIVE:
        version = AgentVersion.query.get(agent.published_version_id) if agent.published_version_id else None
        if version and version.snapshot:
            return {"is_test_mode": False, **version.snapshot}
        # Fallback: agent is Live but no snapshot yet — build from current agent data
        return {"is_test_mode": False, **build_agent_snapshot(agent)}

    elif agent.agent_status == AgentStatusEnum.CREATED:
        return {"is_test_mode": True, **build_agent_snapshot(agent)}

    else:
        raise PermissionError("Agent not deployable")
