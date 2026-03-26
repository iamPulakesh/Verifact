import logging
from typing import Optional
from langchain_groq import ChatGroq

try:
    from langchain_sambanova import ChatSambaNova
except ImportError:
    ChatSambaNova = None

try:
    from langchain_cerebras import ChatCerebras
except ImportError:
    ChatCerebras = None

try:
    from langchain_fireworks import ChatFireworks
except ImportError:
    ChatFireworks = None

from app.config import settings

logger = logging.getLogger(__name__)

def get_llm(provider: Optional[str] = None, model: Optional[str] = None):

    provider = provider or getattr(settings, "LLM_PROVIDER", "groq")
    
    if provider == "sambanova" and ChatSambaNova:
        resolved_model = model or settings.SAMBANOVA_MODEL
        logger.info("[LLM] Provider=%s Model=%s", provider, resolved_model)
        return ChatSambaNova(
            model=resolved_model,
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            sambanova_api_key=settings.SAMBANOVA_API_KEY,
        )

    if provider == "cerebras" and ChatCerebras:
        resolved_model = model or settings.CEREBRAS_MODEL
        logger.info("[LLM] Provider=%s Model=%s", provider, resolved_model)
        return ChatCerebras(
            model=resolved_model,
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            api_key=settings.CEREBRAS_API_KEY,
        )

    if provider == "fireworks" and ChatFireworks:
        resolved_model = model or settings.FIREWORKS_MODEL
        logger.info("[LLM] Provider=%s Model=%s", provider, resolved_model)
        return ChatFireworks(
            model=resolved_model,
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            api_key=settings.FIREWORKS_API_KEY,
        )

    resolved_model = model or settings.LLM_MODEL
    logger.info("[LLM] Provider=groq Model=%s", resolved_model)
    return ChatGroq(
        model=resolved_model,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        api_key=settings.GROQ_API_KEY,
    )
