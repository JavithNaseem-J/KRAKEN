from __future__ import annotations

from typing import Any

import structlog

from src.utils.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()


_langfuse_client: Any = None


def get_langfuse_client() -> Any:
    """Return the singleton Langfuse client instance if credentials are valid."""
    global _langfuse_client
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    if (
        "your-public-key" in settings.langfuse_public_key
        or "your-secret-key" in settings.langfuse_secret_key
    ):
        return None

    if _langfuse_client is not None:
        return _langfuse_client

    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        log.info("observability.langfuse_client_initialized", host=settings.langfuse_host)
        return _langfuse_client
    except Exception as exc:
        log.warning("observability.langfuse_init_failed", error=str(exc))
        return None


def get_langfuse_callback_handler() -> list[Any]:
    """
    Return a list containing the Langfuse CallbackHandler.
    Returns an empty list if credentials are not configured or missing, ensuring offline fallback.
    """
    client = get_langfuse_client()
    if not client:
        return []

    try:
        from langfuse.langchain import CallbackHandler

        handler = CallbackHandler(public_key=settings.langfuse_public_key)
        return [handler]
    except Exception as exc:
        log.warning("observability.langfuse_handler_failed", error=str(exc))
        return []


def flush_langfuse() -> None:
    """Flush all pending Langfuse observability events to the remote API before application exit."""
    client = get_langfuse_client()
    if client:
        try:
            client.flush()
            log.info("observability.langfuse_flushed")
        except Exception as exc:
            log.warning("observability.langfuse_flush_failed", error=str(exc))
