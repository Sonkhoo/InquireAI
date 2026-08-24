"""
Shared LLM initialization for the AI service.

All Groq model access goes through these factories so model names,
temperatures, and reasoning effort are configured in one place,
sourced from Settings.
"""

from functools import lru_cache

from groq import Groq
from langchain_groq import ChatGroq
from pydantic import SecretStr

from app.config import get_settings


@lru_cache
def get_primary_model() -> str:
    """Configured Groq model name shared across call sites."""
    return get_settings().enrich_model

@lru_cache
def get_secondary_model() -> str:
    """Configured secondary Groq model name shared across call sites."""
    return get_settings().secondary_model

@lru_cache
def get_groq_client() -> Groq:
    """Raw Groq SDK client — used where fine-grained error handling is
    needed (e.g. enrich.py's retry mapping around RateLimitError)."""
    return Groq(api_key=get_settings().GROQ_API_KEY)


@lru_cache
def get_primary_llm() -> ChatGroq:
    """Main generation LLM — synthesis / final answers."""
    return ChatGroq(
        model=get_settings().enrich_model,
        temperature=0,
        reasoning_effort="medium",
        api_key=_groq_api_key(),
    )


def _groq_api_key() -> SecretStr:
    return SecretStr(get_settings().GROQ_API_KEY)

@lru_cache
def get_secondary_llm() -> ChatGroq:
    """Secondary LLM — used for fallback or alternative generation."""
    return ChatGroq(
        model=get_settings().secondary_model,
        temperature=0,
        reasoning_effort="medium",
        api_key=_groq_api_key(),
    )