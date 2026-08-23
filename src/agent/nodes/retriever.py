"""
Retriever Node — calls the knowledge service and fetches episodic memories.

Retry strategy: tenacity with exponential backoff and async sleep —
no thread-blocking waits during backoff.
  - 3 attempts, 0.5s → 1s → 2s
  - On exhaustion: returns graceful error state, empty chunks
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from src.agent.state import GraphState
from src.utils.auth import resolve_user_role
from src.utils.config import get_settings
from src.utils.constants import TICKET_ID_REGEX
from src.utils.http_client import internal_request, post_with_retry, service_headers
from src.utils.models.knowledge import KnowledgeSource, RetrievalRequest

log = structlog.get_logger(__name__)
settings = get_settings()


async def _fetch_knowledge(
    client: httpx.AsyncClient,
    request_payload: dict,
    session_id: str,
) -> list[dict[str, Any]]:
    """Fetch knowledge chunks from the knowledge service. Retried by tenacity."""
    resp = await post_with_retry(
        client,
        f"{settings.knowledge_url}/retrieve",
        request_payload,
        headers=service_headers(trace_id=session_id),
    )
    return resp.json().get("chunks", [])


async def retriever_node(state: GraphState) -> dict:
    """
    Call knowledge service /retrieve and store chunks in state.
    Queries all three sources by default.

    Uses an async httpx client so retries yield control via asyncio.sleep
    instead of blocking the worker thread with time.sleep.
    """
    session_id = state.get("session_id", "")
    user_message = state.get("user_message", "")

    log.info("retriever.start", session_id=session_id, query=user_message[:80])

    # Enterprise Data Isolation: Search ticket database ONLY if an explicit Ticket ID
    # is present in the query (e.g. TCK-1001). General queries search ONLY shared FAQ & SLA docs.
    ticket_id_present = bool(TICKET_ID_REGEX.search(user_message))
    if ticket_id_present:
        target_sources = list(KnowledgeSource)
    else:
        target_sources = [KnowledgeSource.FAQ, KnowledgeSource.SLA]

    user_role = resolve_user_role(state.get("user_id") or "public")

    request_payload = RetrievalRequest(
        query=user_message,
        sources=target_sources,
        top_k=settings.retrieval_top_k,
        session_id=session_id,
        user_role=user_role,
    ).model_dump(mode="json")

    chunks: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        # ── Retrieve knowledge chunks ──────────────────────────────────────────
        try:
            chunks = await _fetch_knowledge(client, request_payload, session_id)
        except Exception as exc:
            log.error("retriever.error", session_id=session_id, error=str(exc))
            return {
                "retrieved_chunks": [],
                "error": "Knowledge retrieval is temporarily unavailable, please try again.",
            }

        # ── Query long-term episodic memory if user_id present ─────────────────
        user_id = state.get("user_id", "")
        if user_id:
            try:
                mem_resp = await internal_request(
                    "POST",
                    f"{settings.memory_url}/long-term/search",
                    json_payload={"query": user_message, "user_id": user_id, "top_k": 3},
                    headers=service_headers(trace_id=session_id),
                    client=client,
                )
                episodes = mem_resp.json().get("results", [])
                for ep in episodes:
                    chunks.append(
                        {
                            "id": ep.get("id", "episodic_memory"),
                            "content": f"Past Experience / Episodic Memory: {ep.get('content', '')}",
                            "source": "episodic_memory",
                            "relevance_score": ep.get("similarity", ep.get("score", 0.8)),
                            "metadata": ep.get("metadata", {}),
                        }
                    )
                log.info("retriever.episodic_memory_fetched", count=len(episodes))
            except Exception as exc:
                log.warning("retriever.episodic_memory_search_failed", error=str(exc))

    log.info("retriever.done", session_id=session_id, chunks=len(chunks))
    return {"retrieved_chunks": chunks}
