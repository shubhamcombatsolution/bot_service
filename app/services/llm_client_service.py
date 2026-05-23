import logging

from app.services.encryption_utils import decrypt_value
from app.database.DatabaseOperationPostgreSQL import db_session

from app.models.agent import Agent
from app.models.llm import LLM
from app.models.basellm import BaseLLM

logger = logging.getLogger(__name__)


# --------------------------------------------------
# Provider Client Factory Functions
# --------------------------------------------------

def create_openai_client(api_key: str, model: str, temperature: float, max_tokens: int):

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens
    )


def create_anthropic_client(api_key: str, model: str, temperature: float, max_tokens: int):

    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens
    )


# --------------------------------------------------
# Strategy Mapping
# --------------------------------------------------

LLM_CLIENT_STRATEGIES = {
    "OpenAI": create_openai_client,
    "Anthropic": create_anthropic_client,
}


# --------------------------------------------------
# Main Resolver
# --------------------------------------------------

def get_llm_for_agent(agent_id: int):
    """
    Returns the correct LangChain LLM client for the agent.
    """

    session = next(db_session())

    try:

        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            del_flg=False
        ).first()

        if not agent:
            raise ValueError("Agent not found")

        if not agent.llm_model_id:
            raise ValueError("Agent does not have LLM configured")

        llm_config = session.query(LLM).filter_by(
            llm_id=agent.llm_model_id,
            del_flg=False
        ).first()

        if not llm_config:
            raise ValueError("LLM configuration not found")

        base_llm = session.query(BaseLLM).get(llm_config.base_llm_id)

        if not base_llm:
            raise ValueError("Base LLM not found")

        provider = base_llm.base_provider
        model_name = base_llm.base_model_name

        api_key = decrypt_value(llm_config.llm_secret_key)

        temperature = llm_config.temperature or 0.7
        max_tokens = llm_config.max_output_tokens or 1000

        # --------------------------------------------------
        # Strategy selection
        # --------------------------------------------------

        strategy = LLM_CLIENT_STRATEGIES.get(provider)

        if not strategy:
            raise ValueError(f"Unsupported provider: {provider}")

        return strategy(
            api_key=api_key,
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens
        )

    finally:
        session.close()
