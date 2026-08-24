from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

import structlog
from qdrant_client.models import Document, FieldCondition, Filter, PointIdsList, PointStruct, Range

from src.utils.config import get_settings
from src.utils.models.knowledge import KnowledgeChunkPayload, KnowledgeSource

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient

    from src.utils.embedder import BGEEmbedder

log = structlog.get_logger(__name__)
settings = get_settings()


async def cleanup_expired_private_points(client: AsyncQdrantClient) -> int:
    """Idempotently delete expired session-private vectors."""
    try:
        points, _ = await client.scroll(
            collection_name=settings.qdrant_collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="expires_at", range=Range(lte=time.time()))]
            ),
            limit=256,
            with_payload=False,
            with_vectors=False,
        )
        if not points:
            return 0
        await client.delete(
            collection_name=settings.qdrant_collection_name,
            points_selector=PointIdsList(points=[point.id for point in points]),
        )
        return len(points)
    except Exception as exc:
        log.debug("ingest.expired_cleanup_skipped", error=exc.__class__.__name__)
        return 0


async def upsert_chunks_async(
    client: AsyncQdrantClient,
    embedder: BGEEmbedder | None,
    chunks: list[dict[str, Any]],
    source_name: str,
    default_allowed_roles: list[str] | None = None,
) -> int:
    """Batch embed and upsert chunks into Qdrant collection using AsyncQdrantClient."""
    if not chunks:
        log.warning("ingest.empty_source", source=source_name)
        return 0

    doc_texts = [c.get("document") or c.get("content", "") for c in chunks]
    if settings.qdrant_url and settings.qdrant_cloud_inference_enabled:
        vectors: list[Any] = [
            Document(text=text, model=settings.qdrant_inference_model) for text in doc_texts
        ]
        embedding_model = settings.qdrant_inference_model
    else:
        if embedder is None:
            raise RuntimeError("A local embedder is required when cloud inference is disabled.")
        vectors = embedder.embed_documents(doc_texts)
        embedding_model = settings.embedding_model

    roles = default_allowed_roles or ["public"]

    points: list[PointStruct] = []
    for c, vector in zip(chunks, vectors, strict=True):
        raw_id = c.get("id") or c.get("chunk_id")
        try:
            point_uuid = str(uuid.UUID(str(raw_id)))
        except ValueError:
            point_uuid = (
                str(uuid.uuid5(uuid.NAMESPACE_DNS, str(raw_id))) if raw_id else str(uuid.uuid4())
            )

        meta = c.get("metadata", {})
        doc_id = str(
            meta.get("file")
            or meta.get("file_name")
            or meta.get("ticket_id")
            or meta.get("rule_id")
            or raw_id
            or "unknown"
        )

        chunk_roles = c.get("allowed_roles") or meta.get("allowed_roles") or roles
        scope = str(c.get("scope") or meta.get("demo_session_id") or "shared")

        payload_obj = KnowledgeChunkPayload(
            content=c["document"],
            source=KnowledgeSource(source_name),
            document_id=doc_id,
            chunk_id=str(c.get("id") or point_uuid),
            title=str(meta.get("title") or meta.get("subject") or ""),
            category=str(meta.get("category") or "general"),
            allowed_roles=chunk_roles,
            embedding_model=embedding_model,
            collection_version=settings.knowledge_collection_version,
            scope=scope,
            expires_at=c.get("expires_at") or meta.get("expires_at"),
            untrusted_evidence=bool(c.get("untrusted_evidence", False)),
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


def extract_text_from_file_bytes(filename: str, file_bytes: bytes) -> str:
    """Extract validated PDF, Markdown, or UTF-8 plain text."""
    ext = filename.split(".")[-1].lower() if "." in filename else ""

    if ext == "pdf":
        try:
            import io

            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            text = "\n".join([page.extract_text() or "" for page in reader.pages])
            if text.strip():
                return text
        except Exception as exc:
            raise ValueError("Invalid or unreadable PDF.") from exc

    if ext not in {"txt", "md", "markdown"}:
        raise ValueError("Unsupported upload type.")
    return file_bytes.decode("utf-8", errors="strict")


async def ingest_uploaded_file_async(
    client: AsyncQdrantClient,
    embedder: BGEEmbedder | None,
    filename: str,
    file_bytes: bytes,
    allowed_roles: list[str] | None = None,
    demo_session_id: str | None = None,
    expires_at: float | None = None,
) -> int:
    """
    Parse an uploaded document file, split into semantic chunks, embed,
    and upsert into Qdrant with associated RBAC allowed_roles.
    """
    raw_text = extract_text_from_file_bytes(filename, file_bytes)
    if not raw_text.strip():
        log.warning("ingest.uploaded_file_empty")
        return 0

    roles = allowed_roles or ["public"]
    doc_id = filename.lower().replace(" ", "_")

    # Split document into ~400 character / ~80 word chunks with 80 character overlap
    chunk_size = 400
    overlap = 80
    text_chunks: list[str] = []
    start = 0

    while start < len(raw_text):
        end = min(start + chunk_size, len(raw_text))
        chunk_str = raw_text[start:end].strip()
        if chunk_str:
            text_chunks.append(chunk_str)
        start += chunk_size - overlap

    chunks_data: list[dict[str, Any]] = []
    for idx, text_str in enumerate(text_chunks):
        cid = f"upload_{doc_id}_{idx}"
        chunks_data.append(
            {
                "id": cid,
                "document": text_str,
                "allowed_roles": roles,
                "scope": demo_session_id or "shared",
                "expires_at": expires_at,
                "untrusted_evidence": True,
                "metadata": {
                    "file": filename,
                    "document_id": doc_id,
                    "title": filename,
                    "category": "user_uploaded",
                    "chunk_index": idx,
                    "allowed_roles": roles,
                    "demo_session_id": demo_session_id,
                    "expires_at": expires_at,
                    "untrusted_evidence": True,
                    "embedding_model": settings.qdrant_inference_model,
                    "collection_version": settings.knowledge_collection_version,
                },
            }
        )

    return await upsert_chunks_async(
        client=client,
        embedder=embedder,
        chunks=chunks_data,
        source_name=KnowledgeSource.FAQ.value,
        default_allowed_roles=roles,
    )


async def ensure_collection(
    client: AsyncQdrantClient,
    collection_name: str,
    vector_size: int | None = None,
) -> bool:
    """Ensure the Qdrant collection exists with the specified vector dimension."""
    from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

    dim = vector_size or (
        settings.qdrant_inference_dim
        if settings.qdrant_url and settings.qdrant_cloud_inference_enabled
        else settings.embedding_dim
    )
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

    payload_indexes = {
        "source": PayloadSchemaType.KEYWORD,
        "scope": PayloadSchemaType.KEYWORD,
        "allowed_roles": PayloadSchemaType.KEYWORD,
        "embedding_model": PayloadSchemaType.KEYWORD,
        "collection_version": PayloadSchemaType.KEYWORD,
        "metadata.ticket_id": PayloadSchemaType.KEYWORD,
        "expires_at": PayloadSchemaType.FLOAT,
    }
    for field_name, field_schema in payload_indexes.items():
        try:
            await client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_schema,
            )
        except Exception as exc:
            log.debug(
                "qdrant.payload_index_skipped",
                field=field_name,
                error=exc.__class__.__name__,
            )

    return True


async def run_ingest_async(
    client: AsyncQdrantClient, embedder: BGEEmbedder | None
) -> dict[str, int]:
    """Execute full knowledge loading and ingestion for all three sources."""
    from .loaders.faq_loader import load_faq_chunks
    from .loaders.sla_loader import load_sla_chunks
    from .loaders.ticket_loader import load_ticket_chunks

    await ensure_collection(client, settings.qdrant_collection_name)

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

    try:
        from src.utils.cache import SemanticCache

        cache = SemanticCache(client=client)
        await cache.invalidate()
        log.info("ingest.semantic_cache_invalidated")
    except Exception as exc:
        log.warning("ingest.semantic_cache_invalidation_failed", error=str(exc))

    return counts
