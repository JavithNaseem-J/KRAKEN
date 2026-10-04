from __future__ import annotations

import time
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

import structlog
from langchain_core.exceptions import OutputParserException
from langchain_openai import ChatOpenAI
from openai import BadRequestError
from pydantic import SecretStr, ValidationError

from src.utils.config import get_settings
from src.utils.exceptions import LLMProviderUnavailableError

log = structlog.get_logger(__name__)


def visible_chunk_text(chunk: Any) -> str:
    """Extract visible text while ignoring structured tool or reasoning chunks."""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    )


class ProviderCircuitBreaker:
    def __init__(self) -> None:
        self._open_until = 0.0

    async def invoke(self, runnable: Any, messages: list[Any]) -> Any:
        now = time.monotonic()
        if now < self._open_until:
            raise LLMProviderUnavailableError("LLM provider circuit is temporarily open.")
        try:
            result = await runnable.ainvoke(messages)
            self._open_until = 0.0
            return result
        except (OutputParserException, ValidationError) as exc:
            log.warning("llm.output_invalid", error=exc.__class__.__name__)
            raise
        except BadRequestError:
            log.warning("llm.request_rejected", status_code=400)
            raise
        except Exception as exc:
            self._open_until = now + get_settings().provider_circuit_breaker_seconds
            log.warning("llm.provider_call_failed", provider_error=exc.__class__.__name__)
            raise LLMProviderUnavailableError("LLM provider is temporarily unavailable.") from exc

    async def stream(self, runnable: Any, messages: list[Any]) -> AsyncIterator[Any]:
        now = time.monotonic()
        if now < self._open_until:
            raise LLMProviderUnavailableError("LLM provider circuit is temporarily open.")
        try:
            async for chunk in runnable.astream(messages):
                yield chunk
            self._open_until = 0.0
        except (OutputParserException, ValidationError) as exc:
            log.warning("llm.output_invalid", error=exc.__class__.__name__)
            raise
        except BadRequestError:
            log.warning("llm.request_rejected", status_code=400)
            raise
        except Exception as exc:
            self._open_until = now + get_settings().provider_circuit_breaker_seconds
            log.warning("llm.provider_stream_failed", provider_error=exc.__class__.__name__)
            raise LLMProviderUnavailableError("LLM provider is temporarily unavailable.") from exc


_provider_breaker = ProviderCircuitBreaker()


async def invoke_llm(runnable: Any, messages: list[Any]) -> Any:
    return await _provider_breaker.invoke(runnable, messages)


async def stream_llm(runnable: Any, messages: list[Any]) -> AsyncIterator[Any]:
    """Yield provider chunks while applying the shared circuit-breaker policy."""
    async for chunk in _provider_breaker.stream(runnable, messages):
        yield chunk


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
        max_retries=1,
    )

    if s.llm_fallback_model:
        fallback = ChatOpenAI(
            model=s.llm_fallback_model,
            base_url=s.llm_base_url,
            api_key=SecretStr(s.llm_api_key),
            temperature=s.llm_temperature,
            max_tokens=s.llm_max_tokens,  # type: ignore[call-arg]
            timeout=s.llm_timeout_seconds,
            max_retries=1,
        )
        return primary.with_fallbacks([fallback])

    return primary
