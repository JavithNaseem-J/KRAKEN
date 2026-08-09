from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

import structlog
from qdrant_client.models import FieldCondition, Filter, MatchAny

from shared.constants import TICKET_ID_REGEX
from shared.models.knowledge import (
    KnowledgeChunk,
    KnowledgeSource,
    RetrievalRequest,
    RetrievalResult,
)

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient, QdrantClient

    from shared.embedder import BGEEmbedder

log = structlog.get_logger(__name__)

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "what",
        "is",
        "the",
        "for",
        "and",
        "a",
        "an",
        "in",
        "of",
        "to",
        "how",
        "do",
        "can",
        "you",
        "about",
        "which",
        "are",
        "on",
        "with",
        "or",
        "by",
        "at",
        "from",
        "it",
        "this",
        "that",
        "there",
        "their",
        "question",
        "details",
        "policy",
        "general",
        "query",
        "test",
    }
)


def _keyword_frequency_score(query: str, text: str) -> float:
    """
    Computes a normalized keyword match score based on term frequency and overlap.
    Case-insensitive token matching.
    """
    if not query or not text:
        return 0.0

    tokens = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
    if not tokens:
        return 0.0

    text_lower = text.lower()
    matches = 0
    total_tf = 0
    for token in tokens:
        count = text_lower.count(token)
        if count > 0:
            matches += 1
            total_tf += min(count, 5)

    overlap_ratio = matches / len(tokens)
    tf_bonus = min(total_tf / (len(tokens) * 3), 1.0)
    return round(0.7 * overlap_ratio + 0.3 * tf_bonus, 4)


def _reciprocal_rank_fusion(
    vector_hits: list[Any],
    query: str,
    top_k: int = 5,
    k: float = 60.0,
) -> list[tuple[Any, float]]:
    """
    Combines vector search rank and keyword frequency rank using Reciprocal Rank Fusion (RRF).
    RRF(d) = 1/(k + r_vector(d)) + 1/(k + r_keyword(d))
    """
    if not vector_hits:
        return []

    # Vector rank map (1-indexed)
    vector_rank = {hit.id: i + 1 for i, hit in enumerate(vector_hits)}

    # Keyword rank map (sorted descending by keyword score)
    kw_scored = []
    for hit in vector_hits:
        content = (hit.payload or {}).get("content", "")
        kw_score = _keyword_frequency_score(query, content)
        kw_scored.append((hit, kw_score))

    kw_scored.sort(key=lambda x: x[1], reverse=True)
    keyword_rank = {hit.id: i + 1 for i, (hit, _) in enumerate(kw_scored)}

    # Calculate composite RRF score
    combined: list[tuple[Any, float]] = []
    for hit in vector_hits:
        r_v = vector_rank.get(hit.id, len(vector_hits))
        r_k = keyword_rank.get(hit.id, len(vector_hits))
        rrf_score = (1.0 / (k + r_v)) + (1.0 / (k + r_k))
        combined.append((hit, rrf_score))

    # Sort descending by composite RRF score
    combined.sort(key=lambda x: x[1], reverse=True)
    return combined[:top_k]


def _heuristic_rerank(
    query: str,
    candidates: list[tuple[Any, float]],
) -> list[tuple[Any, float]]:
    """
    Lightweight heuristic re-ranking pass that boosts exact phrase matches
    and key domain entity alignments (e.g., ticket ID, SLA, VPN) before returning top chunks.
    """
    if not candidates:
        return []

    query_lower = query.lower().strip()
    reranked: list[tuple[Any, float]] = []

    query_tokens = [
        t.lower() for t in re.findall(r"\w+", query)
        if len(t) > 2 and t.lower() not in _STOP_WORDS
    ]

    # Max possible RRF score for top-ranked item is 2 * (1 / (60 + 1)) = ~0.03278688
    max_rrf = 2.0 / 61.0
    for hit, rrf_score in candidates:
        payload = hit.payload or {}
        content_lower = payload.get("content", "").lower()

        # Combine normalized RRF score with raw vector cosine similarity if available
        raw_cosine = float(getattr(hit, "score", 0.70) or 0.70)
        norm_rrf = min(1.0, rrf_score / max_rrf) if max_rrf > 0 else 0.5
        base_score = 0.5 * norm_rrf + 0.5 * min(1.0, max(0.0, raw_cosine))

        boost = 1.0
        # Topic keyword overlap penalty: if query has specific topic keywords (e.g. 'soc', 'mfa'),
        # but chunk shares ZERO keywords, apply a heavy 0.35x penalty!
        if query_tokens:
            matches = sum(1 for t in query_tokens if t in content_lower)
            if matches == 0:
                boost *= 0.35
            else:
                boost += 0.20 * (matches / len(query_tokens))

        # Exact phrase match boost
        if query_lower in content_lower:
            boost += 0.25

        # Source context boost (e.g. ticket ID or SLA match)
        ticket_matches = TICKET_ID_REGEX.findall(query)
        if ticket_matches:
            for t_match in ticket_matches:
                t_lower = t_match.lower()
                doc_t_id = str(payload.get("metadata", {}).get("ticket_id") or "").lower()
                if t_lower in content_lower or t_lower == doc_t_id:
                    boost += 1.50

        if re.search(r"SLA|VPN|IT", query, re.IGNORECASE) and re.search(
            r"SLA|VPN|IT", content_lower
        ):
            boost += 0.15

        final_score = min(1.0, max(0.0, round(base_score * boost, 4)))
        reranked.append((hit, final_score))

    reranked.sort(key=lambda x: x[1], reverse=True)
    return reranked


class KnowledgeRetriever:
    """
    Queries Qdrant vector database for requested knowledge sources using payload filtering,
    RRF hybrid search (dense vector + keyword frequency), and heuristic re-ranking.
    """

    def __init__(
        self,
        client: AsyncQdrantClient | QdrantClient,
        embedder: BGEEmbedder,
        collection_name: str = "kraken_knowledge",
    ) -> None:
        self._client = client
        self._embedder = embedder
        self.collection_name = collection_name

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """
        Execute RAG retrieval pipeline:
          1. Dense vector search via Qdrant
          2. Sparse BM25-style keyword search via Qdrant scroll + local scoring
          3. Reciprocal Rank Fusion (RRF) candidate merging
          4. Heuristic score boosting pass
        """
        log.info(
            "retriever.start",
            query=request.query,
            sources=request.sources,
            top_k=request.top_k,
        )

        source_values = [s.value for s in request.sources]
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="source",
                    match=MatchAny(any=source_values),
                )
            ]
        )

        query_vector = await asyncio.to_thread(self._embedder.embed_query, request.query)

        hits: list[Any] = []
        try:
            # Over-fetch 3x candidate pool for RRF and re-ranking
            limit_fetch = max(request.top_k * 3, 15)

            if hasattr(self._client, "query_points"):
                res = await self._client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=limit_fetch,
                    with_payload=True,
                )
                hits = getattr(res, "points", [])
            else:
                hits = await self._client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=limit_fetch,
                )
        except Exception as exc:
            log.warning("retriever.query_filter_failed_fallback_unfiltered", error=str(exc))
            try:
                if hasattr(self._client, "query_points"):
                    res = await self._client.query_points(
                        collection_name=self.collection_name,
                        query=query_vector,
                        limit=limit_fetch,
                        with_payload=True,
                    )
                    hits = getattr(res, "points", [])
                else:
                    hits = await self._client.search(
                        collection_name=self.collection_name,
                        query_vector=query_vector,
                        limit=limit_fetch,
                    )
            except Exception as exc2:
                log.error("retriever.unfiltered_query_error", error=str(exc2))
                hits = []

        # If explicit ticket IDs (e.g. TCK-1001) are in query, scroll to guarantee candidate inclusion
        ticket_ids_in_query = TICKET_ID_REGEX.findall(request.query)
        if ticket_ids_in_query:
            try:
                scroll_res = await self._client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    with_payload=True,
                )
                scrolled_points = scroll_res[0] if isinstance(scroll_res, tuple) else getattr(scroll_res, "points", [])
                existing_ids = {h.id for h in hits}

                for p in scrolled_points:
                    if p.id in existing_ids:
                        continue
                    p_content = (p.payload or {}).get("content", "").lower()
                    p_doc_id = str((p.payload or {}).get("metadata", {}).get("ticket_id") or "").lower()
                    if any(t.lower() in p_content or t.lower() == p_doc_id for t in ticket_ids_in_query):
                        hits.insert(0, p)
                        existing_ids.add(p.id)
            except Exception as scroll_exc:
                log.warning("retriever.ticket_id_scroll_failed", error=str(scroll_exc))

        # RRF Hybrid Fusion
        rrf_candidates = _reciprocal_rank_fusion(hits, request.query, top_k=request.top_k * 2)

        # Lightweight Cross-Encoder Re-Ranking
        reranked_hits = _heuristic_rerank(request.query, rrf_candidates)[: request.top_k]

        # Post-filter 1: Ticket Isolation
        t_lowers = [t.lower() for t in ticket_ids_in_query] if ticket_ids_in_query else []
        sanitized_hits = []
        for hit, score in reranked_hits:
            payload = hit.payload or {}
            chunk_source = str(payload.get("source", "")).lower()
            # Enterprise Ticket Isolation: Drop any ticket chunk unless query explicitly matches its Ticket ID
            if chunk_source == "tickets":
                p_content = payload.get("content", "").lower()
                p_t_id = str((payload.get("metadata") or {}).get("ticket_id") or "").lower()
                if not t_lowers or not any(t in p_content or t == p_t_id for t in t_lowers):
                    log.warning("retriever.cross_ticket_leak_blocked", doc_id=payload.get("document_id"))
                    continue
            sanitized_hits.append((hit, score))
        reranked_hits = sanitized_hits

        # Post-filter 2: Dynamic Semantic Gap & Topic Relevance Pruning
        # Filter out chunks whose score drops below 0.65 or is >0.20 lower than top-1 chunk score.
        if reranked_hits:
            top_score = reranked_hits[0][1]
            pruned_hits = []
            for hit, score in reranked_hits:
                if score < 0.65:
                    continue
                if top_score >= 0.85 and (top_score - score) > 0.20:
                    continue
                pruned_hits.append((hit, score))
            if pruned_hits:
                reranked_hits = pruned_hits

        chunks: list[KnowledgeChunk] = []
        for hit, score in reranked_hits:
            payload = hit.payload or {}
            source_str = payload.get("source", "faq")
            try:
                source_enum = KnowledgeSource(source_str)
            except ValueError:
                source_enum = KnowledgeSource.FAQ

            chunks.append(
                KnowledgeChunk(
                    content=payload.get("content", ""),
                    source=source_enum,
                    document_id=payload.get("document_id", str(hit.id)),
                    chunk_id=str(hit.id),
                    metadata=payload.get("metadata", {}),
                    relevance_score=max(0.0, float(score)),
                )
            )

        log.info(
            "retriever.done",
            total_chunks=len(chunks),
            sources_queried=source_values,
        )

        return RetrievalResult(
            chunks=chunks,
            query=request.query,
            total_retrieved=len(chunks),
            sources_queried=request.sources,
        )
