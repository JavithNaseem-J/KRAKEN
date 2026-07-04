"""
LLM factory for the orchestrator.

Returns a singleton ChatOpenAI instance configured for any OpenAI-compatible
provider (Groq, NVIDIA NIM, etc.) via environment variables.

Design:
  - Provider-agnostic: only base_url + api_key + model change per provider.
  - temperature=0.0 for deterministic, auditable agent decisions.
  - Separate instances for reasoning vs. planning allow tuning per task.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from shared.config import get_settings


@lru_cache(maxsize=1)
def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    """
    Return a cached ChatOpenAI instance.
    Works with Groq, NVIDIA NIM, or any OpenAI-compatible endpoint.
    """
    s = get_settings()
    if not s.llm_api_key or s.llm_api_key.strip() in ("", "your_api_key_here"):
        raise ValueError("llm_api_key must be configured in environment variables to call the LLM service.")
    return ChatOpenAI(
        model=s.llm_model,
        base_url=s.llm_base_url,
        api_key=s.llm_api_key,
        temperature=temperature,
        max_tokens=s.llm_max_tokens,
        timeout=s.llm_timeout_seconds,
    )



def get_structured_llm(schema: type) -> object:
    """
    Return an LLM bound to a Pydantic output schema.
    Used by the decider node for reliable action selection.
    """
    return get_llm().with_structured_output(schema)
