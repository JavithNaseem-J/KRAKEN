"""
Memory Writer Node — persists the completed run to long-term and short-term memory.

Runs AFTER the responder node. Does two things:
  1. Appends this turn's messages to Redis short-term memory (for next session pickup).
  2. Stores a summary of the interaction to PostgreSQL episodic memory
     (for cross-session semantic recall).

Non-blocking: failures are logged but never raise — this node must not prevent
the user from receiving their final_answer.
"""
from __future__ import annotations

import httpx
import structlog

from shared.config import get_settings
from services.orchestrator.graph.state import GraphState

log      = structlog.get_logger(__name__)
settings = get_settings()


def memory_writer_node(state: GraphState) -> dict:
    """
    Persist session and episodic memory. Always succeeds (never raises).
    """
    session_id   = state.get("session_id", "")
    user_id      = state.get("user_id", "system")
    messages     = state.get("messages", [])
    final_answer = state.get("final_answer", "")
    reasoning    = state.get("reasoning", "")
    action_name  = state.get("selected_action", "respond_only")

    log.info("memory_writer.start", session_id=session_id)

    try:
        with httpx.Client(timeout=5.0) as client:
            # ── 1. Update short-term session memory ───────────────────────────
            client.post(
                f"{settings.memory_url}/session/{session_id}/append",
                json={"messages": messages},
            )

            # ── 2. Store episodic memory (summarised interaction) ─────────────
            episode_content = (
                f"User asked: {state.get('user_message', '')}\n"
                f"Action taken: {action_name}\n"
                f"Answer: {final_answer[:300]}"   # Truncate to keep embeddings focused
            )
            client.post(
                f"{settings.memory_url}/long-term",
                json={
                    "session_id": session_id,
                    "user_id":    user_id,
                    "content":    episode_content,
                    "metadata": {
                        "action_name":  action_name,
                        "risk_level":   state.get("risk_level"),
                        "approval":     state.get("approval_status"),
                    },
                },
            )

        log.info("memory_writer.done", session_id=session_id)

    except Exception as exc:
        log.error("memory_writer.error", session_id=session_id, error=str(exc))

    # No state changes — this is a side-effect-only node
    return {}
