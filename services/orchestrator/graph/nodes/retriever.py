import hashlib
import json
import time
from typing import Any

import httpx
import redis
import structlog

from services.orchestrator.graph.state import GraphState
from shared.config import get_settings
from shared.models.knowledge import KnowledgeSource, RetrievalRequest

log = structlog.get_logger(__name__)
settings = get_settings()

# Module-level singletons for connection reuse
_http_client = httpx.Client(timeout=30.0)
_redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

_ALL_SOURCES = [s.value for s in KnowledgeSource]


def retriever_node(state: GraphState) -> dict:
    """
    Call knowledge service /retrieve and store chunks in state.
    Queries all three sources by default.
    Checks exact match cache in Redis first to optimize latency.
    """
    session_id = state.get("session_id", "")
    user_message = state.get("user_message", "")

    log.info("retriever.start", session_id=session_id, query=user_message[:80])

    sources_str = ",".join(sorted([s.value for s in KnowledgeSource]))
    cache_input = f"{user_message}:{sources_str}:{settings.retrieval_top_k}"
    cache_key = f"akea:cache:exact:{hashlib.sha256(cache_input.encode('utf-8')).hexdigest()}"

    # ── Check exact match Redis cache ────────────────────────────────────────
    try:
        cached_data = _redis_client.get(cache_key)
        if cached_data:
            chunks = json.loads(cached_data)
            log.info("retriever.exact_cache_hit", session_id=session_id, chunks=len(chunks))
            return {"retrieved_chunks": chunks}
    except Exception as exc:
        log.warning("retriever.cache_lookup_failed", session_id=session_id, error=str(exc))

    request_payload = RetrievalRequest(
        query=user_message,
        sources=list(KnowledgeSource),
        top_k=settings.retrieval_top_k,
        session_id=session_id,
    ).model_dump(mode="json")

    # ── HTTP Call with 3-time retry loop ──────────────────────────────────────
    max_retries = 3
    last_error = None
    chunks: list[dict[str, Any]] = []

    for attempt in range(1, max_retries + 1):
        try:
            resp = _http_client.post(
                f"{settings.knowledge_url}/retrieve",
                json=request_payload,
                headers={"X-Service-Token": settings.hitl_service_token},
            )
            resp.raise_for_status()
            data = resp.json()
            chunks = data.get("chunks", [])
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            log.warning(
                "retriever.http_attempt_failed",
                session_id=session_id,
                attempt=attempt,
                error=str(exc),
            )
            if attempt < max_retries:
                time.sleep(0.5 * attempt)  # Linear backoff

    if last_error is not None:
        log.error("retriever.error", session_id=session_id, error=str(last_error))
        # Return a clear user-facing error message instead of silently returning empty chunks
        return {
            "retrieved_chunks": [],
            "error": "Knowledge retrieval is temporarily unavailable, please try again.",
        }

    # ── Write to exact match Redis cache (TTL = 10 minutes) ───────────────────
    try:
        _redis_client.set(
            cache_key,
            json.dumps(chunks),
            ex=600,
        )
        log.info("retriever.exact_cache_stored", session_id=session_id)
    except Exception as exc:
        log.warning("retriever.cache_store_failed", session_id=session_id, error=str(exc))

    log.info("retriever.done", session_id=session_id, chunks=len(chunks))
    return {"retrieved_chunks": chunks}
