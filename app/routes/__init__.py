from flask import Blueprint
from app.routes.bot_plan_routes import bot_plan_blueprint
from app.routes.custom_bot_routes import custom_bot_blueprint
from app.routes.embedding_model_routes import embedding_model_blueprint
from app.routes.llm_routes import llm_blueprint
from app.routes.role_routes import role_blueprint
from app.routes.subscription_routes import subscription_blueprint
from app.routes.super_admin_routes import super_admin_blueprint
from app.routes.tenant_routes import tenant_blueprint
from app.routes.user_routes import user_blueprint
from app.routes.knowledge_base_routes import knowledge_base_blueprint
from app.routes.auth_tools import authTool_blueprint
from app.routes.related_tools import related_tools_blueprint
from app.routes.mcp_tools import mcp_blueprint
from app.routes.mcp_agent_tools import mcp_agents_blueprint
from app.routes.new_routes.custom_bot_routes import custom_bot_blueprint_new
from app.routes.get_tool_credentials_routes import tool_blueprint
from app.routes.langgraph_agent_routes import agent_blueprint
from app.routes.workflow_routes import workflow_blueprint
from app.routes.supplier_details import suppliers_blueprint
from app.routes.rfq_blueprint import rfq_blueprint 
from app.routes.supplier_bp import supplier_bp 
from app.routes.rfq_webhook_routes import rfq_webhook_blueprint
from app.routes.workflow_agent_routes import workflow_agent_bp
from app.routes.calculation_engine_routes import calculation_engine_routes
from app.routes.agent_import_routes import agent_import_blueprint
from app.routes.superadmin_prebuilt_routes import superadmin_prebuilt_blueprint
from app.routes.tenant_prebuilt_routes import tenant_prebuilt_blueprint
from app.routes.prebuilt_agents_routes import prebuilt_agents_blueprint
from app.routes.dashboard_routes import dashboard_blueprint
from app.routes.agent_routes import agents_blueprint
from app.routes.tool_routes import tools_blueprint
from app.routes.multi_agentic_system_routes import multi_agents_blueprint
from app.routes.kb_build_routes import kb_build_blueprint
from app.routes.base_agents_routes import base_agent_blueprint
from app.routes.base_llm_routes import base_llm_blueprint
from app.routes.billing_routes import billing_info
from app.routes.bot_diagrams_routes import bot_diagram_blueprint
from app.routes.chathistory_routes import chat_history_blueprint
from app.routes.contact_us_routes import contact_us_blueprint
from app.routes.plans_routes import plans_subscription
from app.routes.system_embedding_model_routes import system_embedding_model_blueprint
from app.routes.system_llm_routes import system_llm_blueprint
from app.routes.tool_validation_routes import tool_validation_blueprint
from app.routes.webhook_routes import webhook_bp

try:
    from app.routes.whatsapp_routes import whatsapp_bp
except ImportError:
    whatsapp_bp = None
# Create a master blueprint
api_blueprint = Blueprint("api", __name__)
# Register individual blueprints
api_blueprint.register_blueprint(tenant_blueprint, url_prefix="/tenant")
api_blueprint.register_blueprint(user_blueprint, url_prefix="/user")
api_blueprint.register_blueprint(role_blueprint, url_prefix="/roles")
api_blueprint.register_blueprint(bot_plan_blueprint, url_prefix="/bot-plan")
api_blueprint.register_blueprint(subscription_blueprint, url_prefix="/subscription")
api_blueprint.register_blueprint(llm_blueprint, url_prefix="/llm")
api_blueprint.register_blueprint(embedding_model_blueprint, url_prefix="/embedding_model")
api_blueprint.register_blueprint(super_admin_blueprint, url_prefix="/super_admin")
api_blueprint.register_blueprint(custom_bot_blueprint, url_prefix="/custom_bot")    
api_blueprint.register_blueprint(knowledge_base_blueprint, url_prefix="/knowledge_base")
api_blueprint.register_blueprint(authTool_blueprint, url_prefix="/auth_tools")
api_blueprint.register_blueprint(related_tools_blueprint, url_prefix="/related_tools")
api_blueprint.register_blueprint(mcp_blueprint, url_prefix="/mcp_tools")
api_blueprint.register_blueprint(mcp_agents_blueprint, url_prefix="/mcp_agent_tools")
api_blueprint.register_blueprint(tool_blueprint, url_prefix="/tool")
api_blueprint.register_blueprint(agent_blueprint, url_prefix="/agent")
api_blueprint.register_blueprint(workflow_blueprint, url_prefix="/workflow")
api_blueprint.register_blueprint(suppliers_blueprint, url_prefix="/suppliers")
api_blueprint.register_blueprint(rfq_blueprint, url_prefix="/rfq")
api_blueprint.register_blueprint(supplier_bp, url_prefix="/supplier")
# Backward-compatible legacy supplier path support
# api_blueprint.register_blueprint(supplier_bp, url_prefix="/supplier/supplier", name="supplier_bp_legacy")
api_blueprint.register_blueprint(rfq_webhook_blueprint, url_prefix="/rfq/webhook")
api_blueprint.register_blueprint(workflow_agent_bp, url_prefix="/workflow_agent")
api_blueprint.register_blueprint(calculation_engine_routes, url_prefix="/calculation_engine")
api_blueprint.register_blueprint(agent_import_blueprint, url_prefix="/agents/import")
api_blueprint.register_blueprint(superadmin_prebuilt_blueprint)   # /superadmin/prebuilt/*
api_blueprint.register_blueprint(tenant_prebuilt_blueprint)        # /agents/prebuilt/*
api_blueprint.register_blueprint(prebuilt_agents_blueprint)        # /prebuilt-agents/* (legacy browse/clone)
api_blueprint.register_blueprint(custom_bot_blueprint_new, url_prefix="/custom_bot_new")        # /custom_bot_new/* (new custom bot routes)
api_blueprint.register_blueprint(dashboard_blueprint, url_prefix="/dashboard")   
api_blueprint.register_blueprint(agents_blueprint, url_prefix="/agents")   
api_blueprint.register_blueprint(multi_agents_blueprint, url_prefix="/multi_agents")   
api_blueprint.register_blueprint(kb_build_blueprint, url_prefix="/builds")   
api_blueprint.register_blueprint(base_agent_blueprint, url_prefix="/base_agents")
api_blueprint.register_blueprint(base_agent_blueprint, url_prefix="/base_agent", name="base_agent_legacy")
api_blueprint.register_blueprint(base_llm_blueprint, url_prefix="/base_llm")
api_blueprint.register_blueprint(billing_info,url_prefix="/billing")
api_blueprint.register_blueprint(bot_diagram_blueprint, url_prefix="/bot_diagram")
api_blueprint.register_blueprint(chat_history_blueprint, url_prefix="/chat-history")
api_blueprint.register_blueprint(contact_us_blueprint, url_prefix="/contact_us")
api_blueprint.register_blueprint(plans_subscription, url_prefix="/plans")
api_blueprint.register_blueprint(system_embedding_model_blueprint, url_prefix="/system_embedding_model")
api_blueprint.register_blueprint(system_llm_blueprint, url_prefix="/system_llm")
api_blueprint.register_blueprint(tools_blueprint, url_prefix="/tools")
api_blueprint.register_blueprint(tool_validation_blueprint)
api_blueprint.register_blueprint(webhook_bp)
if whatsapp_bp:
    api_blueprint.register_blueprint(whatsapp_bp)
    
