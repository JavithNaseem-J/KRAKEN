"""
Memory Writer Node — fire-and-forget async task for persisting session and episodic memory.

Uses asyncio.create_task so the main graph execution is not blocked while
memory writes are in flight. The shared async httpx client from app.state.http
is used rather than creating a second standalone client and thread pool.
"""

import asyncio
import textwrap

import structlog

from shared.config import get_settings
from shared.http_client import create_async_http_client, service_headers

from ..state import GraphState

log = structlog.get_logger(__name__)
settings = get_settings()


async def _persist_memory_task(
    http,
    session_id: str,
    user_id: str,
    messages: list[dict[str, str]],
    user_message: str,
    final_answer: str,
    action_name: str,
    risk_level: str | None,
    approval_status: str | None,
) -> None:
    """Async background task that persists session and episodic memory via the memory service."""
    log.info("memory_writer.background_start", session_id=session_id)
    try:
        # ── 1. Update short-term session memory ───────────────────────────
        resp1 = await http.post(
            f"{settings.memory_url}/session/{session_id}",
            json={"messages": messages},
            headers=service_headers(trace_id=session_id),
        )
        resp1.raise_for_status()

        # ── 2. Store episodic memory (summarised interaction) ─────────────
        short_answer = textwrap.shorten(final_answer, width=500, placeholder="...")
        episode_content = (
            f"User asked: {user_message}\nAction taken: {action_name}\nAnswer: {short_answer}"
        )
        resp2 = await http.post(
            f"{settings.memory_url}/long-term",
            json={
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
        resp2.raise_for_status()
        log.info("memory_writer.background_done", session_id=session_id)
    except Exception as exc:
        log.error("memory_writer.background_error", session_id=session_id, error=str(exc))


async def memory_writer_node(state: GraphState) -> dict:
    """
    Persist session and episodic memory in the background (fire-and-forget).

    Schedules an async task on the current event loop so graph execution
    returns immediately without blocking.
    """

    session_id = state.get("session_id", "")
    user_id = state.get("user_id", "system")
    messages = state.get("messages", [])
    final_answer = state.get("final_answer", "")
    user_message = state.get("user_message", "")
    action_name = state.get("selected_action", "auto_respond")
    risk_level = state.get("risk_level")
    approval = state.get("approval_status")

    log.info("memory_writer.start", session_id=session_id)

    async def _write() -> None:
        async with create_async_http_client() as http:
            await _persist_memory_task(
                http,
                session_id,
                user_id,
                messages,
                user_message,
                final_answer,
                action_name,
                risk_level,
                approval,
            )

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_write())
        task.add_done_callback(
            lambda t: log.error(
                "memory_writer.task_exception", session_id=session_id, error=str(t.exception())
            )
            if not t.cancelled() and t.exception()
            else None
        )
    except Exception as exc:
        log.warning("memory_writer.task_scheduling_failed", error=str(exc))

    return {}
