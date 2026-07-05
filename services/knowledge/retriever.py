"""
Unified multi-source knowledge retriever.

Queries all requested ChromaDB collections in parallel (asyncio.gather),
merges results, deduplicates by chunk ID, and ranks by relevance score.

Design decisions:
  - Parallel fan-out per source: reduces total latency vs. sequential queries
  - Relevance score = 1 - cosine_distance (ChromaDB returns distances, not similarities)
  - Graceful degradation: if one source fails, others still return results
  - top_k applies per-source so all sources get equal representation before final ranking
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from shared.models.knowledge import (
    KnowledgeChunk,
    KnowledgeSource,
    RetrievalRequest,
    RetrievalResult,
)

if TYPE_CHECKING:
    import chromadb

log = structlog.get_logger(__name__)


# ChromaDB returns cosine DISTANCE (0 = identical, 2 = opposite)
# We convert to similarity score (1 = identical, 0 = unrelated)
def _distance_to_score(distance: float) -> float:
    return max(0.0, 1.0 - distance)


def _source_to_collection_name(source: KnowledgeSource) -> str:
    return f"akea_{source.value}"


class KnowledgeRetriever:
    """
    Queries ChromaDB collections for all requested knowledge sources.
    Instantiated once at service startup and shared across all requests.
    """

    def __init__(
        self,
        client: chromadb.ClientAPI,
        collections: dict[str, chromadb.Collection],
    ) -> None:
        self._client = client
        self._collections = collections

    def _query_source(
        self,
        source: KnowledgeSource,
        query: str,
        top_k: int,
    ) -> list[KnowledgeChunk]:
        """
        Query a single ChromaDB collection.
        Returns empty list (not an exception) if the source has no documents
        or if the collection query fails — this enables graceful degradation.
        """
        collection_name = _source_to_collection_name(source)
        collection = self._collections.get(collection_name)

        if collection is None:
            log.warning("retriever.collection_missing", source=source.value)
            return []

        try:
            count = collection.count()
            if count == 0:
                log.info("retriever.collection_empty", source=source.value)
                return []

            # Clamp top_k to the number of available documents
            effective_k = min(top_k, count)

            results = collection.query(
                query_texts=[query],
                n_results=effective_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            log.error("retriever.query_error", source=source.value, error=str(exc))
            return []

        chunks: list[KnowledgeChunk] = []
        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        ids = (results.get("ids") or [[]])[0]

        for doc, meta, dist, chunk_id in zip(documents, metadatas, distances, ids, strict=False):
            chunks.append(
                KnowledgeChunk(
                    content=doc,
                    source=source,
                    document_id=str(
                        meta.get("file", meta.get("ticket_id", meta.get("rule_id", "")))
                    ),
                    chunk_id=chunk_id,
                    metadata=dict(meta or {}),
                    relevance_score=_distance_to_score(dist),
                )
            )

        return chunks

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """
        Fan out to all requested sources concurrently, merge, and rank.
        """
        log.info(
            "retriever.retrieve",
            query=request.query[:80],
            sources=[s.value for s in request.sources],
            top_k=request.top_k,
            session_id=request.session_id,
        )

        # ── Check semantic cache in ChromaDB ──────────────────────────────────
        query_cache = self._collections.get("query_cache")
        if query_cache is not None:
            try:
                cache_results = query_cache.query(
                    query_texts=[request.query],
                    n_results=1,
                    include=["documents", "metadatas", "distances"],
                )
                distances = (cache_results.get("distances") or [[]])[0]
                metadatas = (cache_results.get("metadatas") or [[]])[0]
                if (
                    distances and distances[0] <= 0.05
                ):  # cosine distance <= 0.05 means similarity >= 0.95
                    meta = metadatas[0]
                    chunks_json = meta.get("chunks_json", "")
                    if chunks_json:
                        import json

                        cached_chunks_data = json.loads(chunks_json)
                        cached_chunks = [
                            KnowledgeChunk(
                                content=c["content"],
                                source=KnowledgeSource(c["source"]),
                                document_id=c["document_id"],
                                chunk_id=c["chunk_id"],
                                metadata=c["metadata"],
                                relevance_score=c["relevance_score"],
                            )
                            for c in cached_chunks_data
                        ]
                        log.info(
                            "retriever.semantic_cache_hit",
                            query=request.query[:80],
                            distance=distances[0],
                        )
                        return RetrievalResult(
                            chunks=cached_chunks,
                            query=request.query,
                            total_retrieved=len(cached_chunks),
                            sources_queried=request.sources,
                        )
            except Exception as exc:
                log.warning("retriever.semantic_cache_lookup_failed", error=str(exc))

        # Run all source queries concurrently in a thread pool
        # (ChromaDB is sync — we offload to avoid blocking the event loop)
        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(
                None,
                self._query_source,
                source,
                request.query,
                request.top_k,
            )
            for source in request.sources
        ]

        results: list[list[KnowledgeChunk]] = await asyncio.gather(*tasks)

        # Flatten + deduplicate by chunk_id
        seen: set[str] = set()
        all_chunks: list[KnowledgeChunk] = []
        for source_chunks in results:
            for chunk in source_chunks:
                if chunk.chunk_id not in seen:
                    seen.add(chunk.chunk_id)
                    all_chunks.append(chunk)

        # Sort by relevance score descending
        all_chunks.sort(key=lambda c: c.relevance_score, reverse=True)

        # Save to semantic query cache
        if query_cache is not None and all_chunks:
            try:
                import json
                import uuid

                chunks_data = [
                    {
                        "content": c.content,
                        "source": c.source.value,
                        "document_id": c.document_id,
                        "chunk_id": c.chunk_id,
                        "metadata": c.metadata,
                        "relevance_score": c.relevance_score,
                    }
                    for c in all_chunks[:10]  # Cache top 10 chunks to avoid metadata bloat
                ]
                query_cache.upsert(
                    ids=[str(uuid.uuid4())],
                    documents=[request.query],
                    metadatas=[{"chunks_json": json.dumps(chunks_data)}],
                )
                log.info("retriever.semantic_cache_stored", query=request.query[:80])
            except Exception as exc:
                log.warning("retriever.semantic_cache_store_failed", error=str(exc))

        log.info(
            "retriever.done",
            total_chunks=len(all_chunks),
            sources_queried=[s.value for s in request.sources],
        )

        return RetrievalResult(
            chunks=all_chunks,
            query=request.query,
            total_retrieved=len(all_chunks),
            sources_queried=request.sources,
        )
