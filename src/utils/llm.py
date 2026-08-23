"""
LLM factory for the orchestrator.

Returns a singleton ChatOpenAI instance configured for any OpenAI-compatible
provider (Groq, NVIDIA NIM, OpenAI, etc.) via environment variables.

Design:
  - Provider-agnostic: only base_url + api_key + model change per provider.
  - temperature=0.0 for deterministic, auditable agent decisions.
  - Automatic retry with backoff on transient 429 rate limits (max_retries=4).
  - Model fallback support if primary model fails.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.utils.config import get_settings


def validate_llm_config() -> None:
    """Eagerly validate LLM settings at startup to fail-fast."""
    s = get_settings()
    if not s.llm_api_key or s.llm_api_key.strip() in ("", "your_api_key_here"):
        raise ValueError(
            "llm_api_key must be configured in environment variables to call the LLM service."
        )


@lru_cache(maxsize=1)
def get_llm() -> Any:
    """
    Return a cached LLM instance with fallback support configured.
    Always uses temperature=0.0 for deterministic, auditable decisions.
    """
    validate_llm_config()
    s = get_settings()

    primary = ChatOpenAI(
        model=s.llm_model,
        base_url=s.llm_base_url,
        api_key=SecretStr(s.llm_api_key),
        temperature=s.llm_temperature,
        max_tokens=s.llm_max_tokens,  # type: ignore[call-arg]
        timeout=s.llm_timeout_seconds,
        max_retries=4,
    )

    if s.llm_fallback_model:
        fallback = ChatOpenAI(
            model=s.llm_fallback_model,
            base_url=s.llm_base_url,
            api_key=SecretStr(s.llm_api_key),
            temperature=s.llm_temperature,
            max_tokens=s.llm_max_tokens,  # type: ignore[call-arg]
            timeout=s.llm_timeout_seconds,
            max_retries=4,
        )
        return primary.with_fallbacks([fallback])

    return primary
