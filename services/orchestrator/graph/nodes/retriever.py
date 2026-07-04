"""
Retriever Node — calls the knowledge service to fetch relevant chunks.

Fan-out across all three sources (FAQ, Tickets, SLA) in a single HTTP call.
The knowledge service handles the parallel fan-out internally.

On failure: logs the error, sets state["error"], returns empty chunks so
the graph can still attempt to reason with whatever it has.
"""
from __future__ import annotations

from typing import Any

import httpx
import structlog

from shared.config import get_settings
from shared.models.knowledge import KnowledgeSource, RetrievalRequest
from services.orchestrator.graph.state import GraphState

log = structlog.get_logger(__name__)
settings = get_settings()

_ALL_SOURCES = [s.value for s in KnowledgeSource]


def retriever_node(state: GraphState) -> dict:
    """
    Call knowledge service /retrieve and store chunks in state.
    Queries all three sources by default — the reasoner filters by relevance.
    """
    session_id = state.get("session_id", "")
    user_message = state.get("user_message", "")

    log.info("retriever.start", session_id=session_id, query=user_message[:80])

    request_payload = RetrievalRequest(
        query=user_message,
        sources=list(KnowledgeSource),
        top_k=5,
        session_id=session_id,
    ).model_dump(mode="json")

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{settings.knowledge_url}/retrieve",
                json=request_payload,
            )
            resp.raise_for_status()
            data = resp.json()

        chunks: list[dict[str, Any]] = data.get("chunks", [])
        log.info("retriever.done", session_id=session_id, chunks=len(chunks))
        return {"retrieved_chunks": chunks}

    except Exception as exc:
        log.error("retriever.error", session_id=session_id, error=str(exc))
        return {
            "retrieved_chunks": [],
            "error": f"Knowledge retrieval failed: {exc}",
        }
