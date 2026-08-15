"""
Async knowledge ingestion helper.

Provides service-internal chunk upsert logic for Qdrant Cloud / in-memory collections.
Used directly by POST /ingest and knowledge administration flows.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import structlog
from qdrant_client.models import PointStruct

from shared.config import get_settings
from shared.models.knowledge import KnowledgeChunkPayload, KnowledgeSource

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient

    from shared.embedder import BGEEmbedder

log = structlog.get_logger(__name__)
settings = get_settings()


async def upsert_chunks_async(
    client: AsyncQdrantClient,
    embedder: BGEEmbedder,
    chunks: list[dict[str, Any]],
    source_name: str,
) -> int:
    """Batch embed and upsert chunks into Qdrant collection using AsyncQdrantClient."""
    if not chunks:
        log.warning("ingest.empty_source", source=source_name)
        return 0

    doc_texts = [c["document"] for c in chunks]
    vectors = embedder.embed_documents(doc_texts)

    points: list[PointStruct] = []
    for c, vector in zip(chunks, vectors, strict=True):
        raw_id = c.get("id")
        try:
            point_uuid = str(uuid.UUID(str(raw_id)))
        except ValueError:
            point_uuid = (
                str(uuid.uuid5(uuid.NAMESPACE_DNS, str(raw_id))) if raw_id else str(uuid.uuid4())
            )

        meta = c.get("metadata", {})
        doc_id = str(meta.get("file") or meta.get("ticket_id") or meta.get("rule_id") or c.get("id") or "unknown")

        payload_obj = KnowledgeChunkPayload(
            content=c["document"],
            source=KnowledgeSource(source_name),
            document_id=doc_id,
            chunk_id=str(c.get("id") or point_uuid),
            title=str(meta.get("title") or meta.get("subject") or ""),
            category=str(meta.get("category") or "general"),
            metadata=meta,
        )

        points.append(
            PointStruct(
                id=point_uuid,
                vector=vector,
                payload=payload_obj.model_dump(),
            )
        )

    await client.upsert(
        collection_name=settings.qdrant_collection_name,
        points=points,
    )
    log.info("ingest.upserted", source=source_name, count=len(points))
    return len(points)


async def ensure_collection(
    client: AsyncQdrantClient,
    collection_name: str,
    vector_size: int | None = None,
) -> bool:
    """Ensure the Qdrant collection exists with the specified vector dimension."""
    from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

    dim = vector_size or settings.embedding_dim
    if not await client.collection_exists(collection_name):
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        log.info("qdrant.collection_created", collection=collection_name, vector_size=dim)
    else:
        info = await client.get_collection(collection_name=collection_name)
        vectors = info.config.params.vectors
        existing_size = getattr(vectors, "size", None)
        if isinstance(vectors, dict):
            existing_size = vectors.get("size")
        if existing_size and existing_size != dim:
            log.error(
                "qdrant.dimension_mismatch",
                collection=collection_name,
                existing_dim=existing_size,
                configured_dim=dim,
            )

    try:
        await client.create_payload_index(
            collection_name=collection_name,
            field_name="source",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception as exc:
        log.debug("qdrant.payload_index_exists_or_error", error=str(exc))

    return True


async def run_ingest_async(client: AsyncQdrantClient, embedder: BGEEmbedder) -> dict[str, int]:
    """Execute full knowledge loading and ingestion for all three sources."""
    from .loaders.faq_loader import load_faq_chunks
    from .loaders.sla_loader import load_sla_chunks
    from .loaders.ticket_loader import load_ticket_chunks

    await ensure_collection(client, settings.qdrant_collection_name, vector_size=settings.embedding_dim)

    counts: dict[str, int] = {}

    faq_chunks = load_faq_chunks()
    counts["faq"] = await upsert_chunks_async(
        client, embedder, faq_chunks, KnowledgeSource.FAQ.value
    )

    ticket_chunks = load_ticket_chunks()
    counts["tickets"] = await upsert_chunks_async(
        client, embedder, ticket_chunks, KnowledgeSource.TICKETS.value
    )

    sla_chunks = load_sla_chunks()
    counts["sla"] = await upsert_chunks_async(
        client, embedder, sla_chunks, KnowledgeSource.SLA.value
    )

    return counts
