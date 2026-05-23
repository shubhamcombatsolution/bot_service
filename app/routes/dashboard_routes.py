from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from app.models import CustomBotNew, Agent, LLM, BotDiagram
from app.services.redis_service import RedisService
import logging


dashboard_blueprint = Blueprint("dashboard", __name__)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


redis_service = RedisService()
CACHE_TTL = 60


@dashboard_blueprint.route("/", methods=["GET"])
@dashboard_blueprint.route("/dashboard", methods=["GET"])
@jwt_required()
def get_dashboard():
    tenant_id = None

    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            logger.warning("Dashboard access failed - missing tenant_id")
            return jsonify({
                "status": "error",
                "message": "Tenant ID not found in token"
            }), 401

        cache_key = f"dashboard:{tenant_id}"

        # Cache Check
        cached = redis_service.get(cache_key)
        if cached:
            logger.info(f"Dashboard cache hit | tenant={tenant_id}")
            return jsonify({
                "status": "success",
                "message": "Dashboard fetched (cache)",
                "data": cached
            }), 200

        logger.info(f"Dashboard cache miss | tenant={tenant_id}")

        # Build Data
        dashboard_data = build_dashboard_data(tenant_id)

        # Cache Store
        redis_service.set(cache_key, dashboard_data, ttl=CACHE_TTL)

        logger.info(f"Dashboard generated & cached | tenant={tenant_id}")

        return jsonify({
            "status": "success",
            "message": "Dashboard fetched successfully",
            "data": dashboard_data
        }), 200

    except Exception:
        logger.exception(f"Dashboard error | tenant={tenant_id}")
        return jsonify({
            "status": "error",
            "message": "Failed to fetch dashboard",
            "data": {}
        }), 500


def build_dashboard_data(tenant_id):
    latest_bots = CustomBotNew.query.filter_by(
        tenant_id=tenant_id, del_flg=False
    ).order_by(CustomBotNew.created_at.desc()).limit(4).all()

    latest_agents = Agent.query.filter_by(
        tenant_id=tenant_id, del_flg=False
    ).order_by(Agent.created_at.desc()).limit(4).all()

    latest_models = LLM.query.filter_by(
        tenant_id=tenant_id, del_flg=False
    ).order_by(LLM.created_at.desc()).limit(4).all()

    latest_workflows = BotDiagram.query.filter_by(
        tenant_id=tenant_id, del_flg=False
    ).order_by(BotDiagram.created_at.desc()).limit(4).all()

    return {
        "latest": {
            "bots": [
                {
                    "bot_id": b.bot_id,
                    "bot_name": b.bot_name,
                    "status": b.bot_status.value if hasattr(b.bot_status, "value") else b.bot_status,
                    "created_at": b.created_at.isoformat() if b.created_at else None
                } for b in latest_bots
            ],
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "agent_name": a.agent_name,
                    "created_at": a.created_at.isoformat() if a.created_at else None
                } for a in latest_agents
            ],
            "models": [
                {
                    "llm_id": m.llm_id,
                    "model_name": (
                        m.base_llm.base_model_name
                        if getattr(m, "base_llm", None) and hasattr(m.base_llm, "base_model_name")
                        else None
                    ),
                    "provider": (
                        m.base_llm.base_provider
                        if getattr(m, "base_llm", None) and hasattr(m.base_llm, "base_provider")
                        else None
                    ),
                    "model_type": (
                        m.base_llm.base_model_type
                        if getattr(m, "base_llm", None) and hasattr(m.base_llm, "base_model_type")
                        else None
                    ),
                    "created_at": m.created_at.isoformat() if m.created_at else None
                } for m in latest_models
            ],
            "workflows": [
                {
                    "diagram_id": w.diagram_id,
                    "created_at": w.created_at.isoformat() if w.created_at else None
                } for w in latest_workflows
            ]
        }
    }
