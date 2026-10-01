import structlog

from src.agent.state import GraphState
from src.utils.background_tasks import background_tasks
from src.utils.config import get_settings
from src.utils.http_client import create_async_http_client, service_headers

log = structlog.get_logger(__name__)
settings = get_settings()
_PERSISTENCE_TIMEOUT_SECONDS = 2.0


async def _persist_memory(
    http,
    session_id: str,
    messages: list[dict[str, str]],
) -> None:
    """Persist session history via the memory service."""
    log.info("memory_writer.persist_start", session_id=session_id)
    try:
        from src.utils.http_client import post_with_retry

        await post_with_retry(
            http,
            f"{settings.memory_url}/session/{session_id}",
            {"messages": messages},
            headers=service_headers(trace_id=session_id),
        )

        log.info("memory_writer.persist_done", session_id=session_id)
    except Exception as exc:
        log.error("memory_writer.persist_error", session_id=session_id, error=str(exc))


async def memory_writer_node(state: GraphState) -> dict:
    """Schedule best-effort persistence without delaying graph completion."""

    session_id = state.get("session_id", "")
    messages = state.get("messages", [])

    log.info("memory_writer.start", session_id=session_id)

    async def persist() -> None:
        try:
            async with create_async_http_client(
                timeout_seconds=_PERSISTENCE_TIMEOUT_SECONDS
            ) as http:
                await _persist_memory(http, session_id, messages)
        except Exception as exc:
            log.warning("memory_writer.persistence_failed", session_id=session_id, error=str(exc))

    background_tasks.schedule(
        persist(), task_name=f"memory-persist:{session_id}", session_id=session_id
    )

    return {}
