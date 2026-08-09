from __future__ import annotations

from typing import Any

import structlog

from shared.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()


def get_langfuse_callback_handler() -> list[Any]:
    """
    Return a list containing the Langfuse CallbackHandler if credentials are set.
    Returns an empty list if credentials are not configured or missing, ensuring offline fallback.
    """
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return []
    if (
        "your-public-key" in settings.langfuse_public_key
        or "your-secret-key" in settings.langfuse_secret_key
    ):
        return []

    try:
        from langfuse.langchain import CallbackHandler

        handler = CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        log.info("observability.langfuse_enabled", host=settings.langfuse_host)
        return [handler]
    except Exception as exc:
        log.warning("observability.langfuse_failed", error=str(exc))
        return []
