"""
LLM factory for the orchestrator.

Returns a singleton ChatOpenAI instance configured for any OpenAI-compatible
provider (Groq, NVIDIA NIM, etc.) via environment variables.

Design:
  - Provider-agnostic: only base_url + api_key + model change per provider.
  - temperature=0.0 for deterministic, auditable agent decisions.
  - Separate instances for reasoning vs. planning allow tuning per task.
"""

from functools import lru_cache
from typing import Any

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from shared.config import get_settings


def validate_llm_config() -> None:
    """Eagerly validate LLM settings at startup to fail-fast."""
    s = get_settings()
    if not s.llm_api_key or s.llm_api_key.strip() in ("", "your_api_key_here"):
        raise ValueError(
            "llm_api_key must be configured in environment variables to call the LLM service."
        )


@lru_cache(maxsize=1)
def get_llm() -> Runnable[Any, Any]:
    """
    Return a cached LLM instance with fallback support configured.
    Always uses temperature=0.0 for deterministic, auditable decisions.
    """
    validate_llm_config()
    s = get_settings()

    primary = ChatOpenAI(
        model=s.llm_model,
        base_url=s.llm_base_url,
        api_key=s.llm_api_key,
        temperature=s.llm_temperature,
        max_tokens=s.llm_max_tokens,
        timeout=s.llm_timeout_seconds,
    )

    if s.llm_fallback_model:
        fallback = ChatOpenAI(
            model=s.llm_fallback_model,
            base_url=s.llm_base_url,
            api_key=s.llm_api_key,
            temperature=s.llm_temperature,
            max_tokens=s.llm_max_tokens,
            timeout=s.llm_timeout_seconds,
        )
        return primary.with_fallbacks([fallback])

    return primary
