import concurrent.futures
import textwrap

import httpx
import structlog

from services.orchestrator.graph.state import GraphState
from shared.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

# Module-level connection pool & thread pool for fire-and-forget background execution
_http_client = httpx.Client(timeout=10.0)
_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=5)


def shutdown_thread_pool() -> None:
    """Shutdown the background memory writer thread pool on app shutdown."""
    log.info("memory_writer.shutdown_pool")
    _thread_pool.shutdown(wait=False)
    _http_client.close()


def _persist_memory_task(
    session_id: str,
    user_id: str,
    messages: list[dict[str, str]],
    user_message: str,
    final_answer: str,
    action_name: str,
    risk_level: str | None,
    approval_status: str | None,
) -> None:
    """Helper executed in background thread to avoid blocking graph execution."""
    log.info("memory_writer.background_start", session_id=session_id)
    try:
        headers = {"X-Service-Token": settings.hitl_service_token}

        # ── 1. Update short-term session memory ───────────────────────────
        resp1 = _http_client.post(
            f"{settings.memory_url}/session/{session_id}/append",
            json={"messages": messages},
            headers=headers,
        )
        resp1.raise_for_status()

        # ── 2. Store episodic memory (summarised interaction) ─────────────
        short_answer = textwrap.shorten(final_answer, width=500, placeholder="...")
        episode_content = (
            f"User asked: {user_message}\n"
            f"Action taken: {action_name}\n"
            f"Answer: {short_answer}"
        )
        resp2 = _http_client.post(
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
            headers=headers,
        )
        resp2.raise_for_status()
        log.info("memory_writer.background_done", session_id=session_id)
    except Exception as exc:
        log.error("memory_writer.background_error", session_id=session_id, error=str(exc))


def memory_writer_node(state: GraphState) -> dict:
    """
    Persist session and episodic memory in the background (fire-and-forget).
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

    # Dispatch to background thread pool
    _thread_pool.submit(
        _persist_memory_task,
        session_id,
        user_id,
        messages,
        user_message,
        final_answer,
        action_name,
        risk_level,
        approval,
    )

    # Return immediately to avoid blocking the user
    return {}
