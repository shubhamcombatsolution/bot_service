import logging
import requests

logger = logging.getLogger(__name__)


# --------------------------------------------------
# OpenAI (SDK)
# --------------------------------------------------

def verify_openai(api_key: str) -> bool:
    try:
        logger.info("Starting OpenAI API key verification")

        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.models.list()

        logger.info("OpenAI verification successful")

        return True

    except Exception as e:
        logger.warning(f"OpenAI verification failed: {e}")
        return False


# --------------------------------------------------
# Anthropic (REST)
# --------------------------------------------------

def verify_anthropic(api_key: str) -> bool:
    try:
        logger.info("Starting Anthropic API key verification")

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }

        url = "https://api.anthropic.com/v1/models"

        logger.debug(f"Calling Anthropic API: {url}")

        r = requests.get(url, headers=headers, timeout=5)

        logger.info(f"Anthropic response status: {r.status_code}")

        if r.status_code == 200:
            logger.info("Anthropic verification successful")
            return True

        logger.warning(f"Anthropic verification failed with status {r.status_code}")
        return False

    except Exception as e:
        logger.warning(f"Anthropic verification failed: {e}")
        return False


# --------------------------------------------------
# Gemini (REST)
# --------------------------------------------------

def verify_gemini(api_key: str) -> bool:
    try:
        logger.info("Starting Gemini API key verification")

        url = f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"

        logger.debug(f"Calling Gemini API: {url}")

        r = requests.get(url, timeout=5)

        logger.info(f"Gemini response status: {r.status_code}")

        if r.status_code == 200:
            logger.info("Gemini verification successful")
            return True

        logger.warning(f"Gemini verification failed with status {r.status_code}")
        return False

    except Exception as e:
        logger.warning(f"Gemini verification failed: {e}")
        return False


# --------------------------------------------------
# HuggingFace (REST)
# --------------------------------------------------

def verify_huggingface(api_key: str) -> bool:
    try:
        logger.info("Starting HuggingFace API key verification")

        headers = {"Authorization": f"Bearer {api_key}"}

        url = "https://huggingface.co/api/whoami-v2"

        logger.debug(f"Calling HuggingFace API: {url}")

        r = requests.get(url, headers=headers, timeout=5)

        logger.info(f"HuggingFace response status: {r.status_code}")

        if r.status_code == 200:
            logger.info("HuggingFace verification successful")
            return True

        logger.warning(f"HuggingFace verification failed with status {r.status_code}")
        return False

    except Exception as e:
        logger.warning(f"HuggingFace verification failed: {e}")
        return False


# --------------------------------------------------
# Mistral (REST)
# --------------------------------------------------

def verify_mistral(api_key: str) -> bool:
    try:
        logger.info("Starting Mistral API key verification")

        headers = {"Authorization": f"Bearer {api_key}"}

        url = "https://api.mistral.ai/v1/models"

        logger.debug(f"Calling Mistral API: {url}")

        r = requests.get(url, headers=headers, timeout=5)

        logger.info(f"Mistral response status: {r.status_code}")

        if r.status_code == 200:
            logger.info("Mistral verification successful")
            return True

        logger.warning(f"Mistral verification failed with status {r.status_code}")
        return False

    except Exception as e:
        logger.warning(f"Mistral verification failed: {e}")
        return False


# --------------------------------------------------
# Perplexity (REST)
# --------------------------------------------------

def verify_perplexity(api_key: str) -> bool:
    try:
        logger.info("Starting Perplexity API key verification")

        headers = {"Authorization": f"Bearer {api_key}"}

        url = "https://api.perplexity.ai/models"

        logger.debug(f"Calling Perplexity API: {url}")

        r = requests.get(url, headers=headers, timeout=5)

        logger.info(f"Perplexity response status: {r.status_code}")

        if r.status_code == 200:
            logger.info("Perplexity verification successful")
            return True

        logger.warning(f"Perplexity verification failed with status {r.status_code}")
        return False

    except Exception as e:
        logger.warning(f"Perplexity verification failed: {e}")
        return False


# --------------------------------------------------
# xAI (REST)
# --------------------------------------------------

def verify_xai(api_key: str) -> bool:
    try:
        logger.info("Starting xAI API key verification")

        headers = {"Authorization": f"Bearer {api_key}"}

        url = "https://api.x.ai/v1/models"

        logger.debug(f"Calling xAI API: {url}")

        r = requests.get(url, headers=headers, timeout=5)

        logger.info(f"xAI response status: {r.status_code}")

        if r.status_code == 200:
            logger.info("xAI verification successful")
            return True

        logger.warning(f"xAI verification failed with status {r.status_code}")
        return False

    except Exception as e:
        logger.warning(f"xAI verification failed: {e}")
        return False


# --------------------------------------------------
# Strategy Mapping
# --------------------------------------------------

VERIFICATION_STRATEGIES = {

    "OpenAI": verify_openai,
    "Anthropic": verify_anthropic,
    "Google DeepMind": verify_gemini,
    "Hugging Face": verify_huggingface,
    "Mistral AI": verify_mistral,
    "Perplexity": verify_perplexity,
    "xAI": verify_xai,
}


# --------------------------------------------------
# Main Router
# --------------------------------------------------

def verify_llm_key(provider: str, api_key: str):

    logger.info(f"Verifying API key for provider: {provider}")

    strategy = VERIFICATION_STRATEGIES.get(provider)

    if not strategy:
        logger.warning(f"Provider not supported: {provider}")
        return {
            "valid": False,
            "error": f"Provider '{provider}' is not supported yet"
        }

    try:

        result = strategy(api_key)

        if result:
            logger.info(f"API key verification successful for provider: {provider}")
            return {
                "valid": True,
                "error": None
            }

        logger.warning(f"API key verification failed for provider: {provider}")

        return {
            "valid": False,
            "error": "Invalid API key"
        }

    except Exception as e:

        logger.exception(f"Unexpected verification error for provider {provider}: {e}")

        return {
            "valid": False,
            "error": str(e)
        }