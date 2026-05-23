# engine/langgraph_urls.py

# Gmail / Trigger URLs
# GMAIL_CREDENTIALS_URL = "https://api.jnanic.com/tool/Gmail/credentials"

# # Decision Agent
# DECISION_AGENT_URL = "http://langgraph.jnanic.com/decision_agent"


# # Decision Agent
# CREATE_AGENT_URL = "http://langgraph.jnanic.com/create_agent"


# LANGGRAPH_ANALYZE_URL = "http://langgraph.jnanic.com/analyze_task_parameters"



import os

def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

LANGGRAPH_SERVICE_URL = require_env("LANGGRAPH_SERVICE_URL")
BOT_BUILDER_SERVICE_URL = require_env("BOT_BUILDER_SERVICE_URL")
BB_SERVICE_URL = require_env("BB_SERVICE_URL")

LANGGRAPH_ANALYZE_URL = f"{LANGGRAPH_SERVICE_URL}/analyze_task_parameters"
CREATE_AGENT_URL = f"{LANGGRAPH_SERVICE_URL}/create_agent"
DECISION_AGENT_URL = f"{LANGGRAPH_SERVICE_URL}/decision_agent"
GMAIL_CREDENTIALS_URL = f"{BB_SERVICE_URL}/tool/Gmail/credentials"


