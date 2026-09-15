import asyncio
import textwrap

import structlog

from src.agent.state import GraphState
from src.utils.config import get_settings
from src.utils.http_client import create_async_http_client, service_headers

log = structlog.get_logger(__name__)
settings = get_settings()
_PERSISTENCE_TIMEOUT_SECONDS = 2.0


async def _persist_memory(
    http,
    session_id: str,
    user_id: str,
    messages: list[dict[str, str]],
    user_message: str,
    final_answer: str,
    action_name: str,
    risk_level: str | None,
    approval_status: str | None,
    store_episodic: bool = True,
) -> None:
    """Persist session and episodic memory via the memory service."""
    log.info("memory_writer.persist_start", session_id=session_id)
    try:
        from src.utils.http_client import post_with_retry

        # 1. Update short-term session memory
        await post_with_retry(
            http,
            f"{settings.memory_url}/session/{session_id}",
            {"messages": messages},
            headers=service_headers(trace_id=session_id),
        )

        if not store_episodic:
            log.info("memory_writer.public_episodic_skipped", session_id=session_id)
            return

        # 2. Store episodic memory (summarised interaction)
        short_answer = textwrap.shorten(final_answer, width=500, placeholder="...")
        episode_content = (
            f"User asked: {user_message}\nAction taken: {action_name}\nAnswer: {short_answer}"
        )
        await post_with_retry(
            http,
            f"{settings.memory_url}/long-term",
            {
                "session_id": session_id,
                "user_id": user_id,
                "content": episode_content,
                "metadata": {
                    "action_name": action_name,
                    "risk_level": risk_level,
                    "approval": approval_status,
                },
            },
            headers=service_headers(trace_id=session_id),
        )
        log.info("memory_writer.persist_done", session_id=session_id)
    except Exception as exc:
        log.error("memory_writer.persist_error", session_id=session_id, error=str(exc))


async def memory_writer_node(state: GraphState) -> dict:
    """Schedule best-effort persistence without delaying graph completion."""

    session_id = state.get("session_id", "")
    user_id = state.get("user_id", "system")
    messages = state.get("messages", [])
    final_answer = state.get("final_answer", "")
    user_message = state.get("user_message", "")
    action_name = state.get("selected_action") or "auto_respond"
    risk_level = state.get("risk_level")
    approval = state.get("approval_status")

    log.info("memory_writer.start", session_id=session_id)

    async def persist() -> None:
        try:
            async with create_async_http_client(
                timeout_seconds=_PERSISTENCE_TIMEOUT_SECONDS
            ) as http:
                await _persist_memory(
                    http,
                    session_id,
                    user_id,
                    messages,
                    user_message,
                    final_answer,
                    action_name,
                    risk_level,
                    approval,
                    store_episodic=not bool(state.get("public_session_id")),
                )
        except Exception as exc:
            log.warning("memory_writer.persistence_failed", session_id=session_id, error=str(exc))

    task = asyncio.create_task(persist(), name=f"memory-persist:{session_id}")

    def report_background_failure(completed: asyncio.Task[None]) -> None:
        try:
            completed.result()
        except asyncio.CancelledError:
            log.info("memory_writer.persistence_cancelled", session_id=session_id)
        except Exception as exc:  # pragma: no cover - defensive task supervision
            log.error(
                "memory_writer.persistence_task_failed", session_id=session_id, error=str(exc)
            )

    task.add_done_callback(report_background_failure)

    return {}
