from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import structlog
from qdrant_client.models import PointStruct

from src.utils.config import get_settings
from src.utils.models.knowledge import KnowledgeChunkPayload, KnowledgeSource

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient

    from src.utils.embedder import BGEEmbedder

log = structlog.get_logger(__name__)
settings = get_settings()


async def upsert_chunks_async(
    client: AsyncQdrantClient,
    embedder: BGEEmbedder,
    chunks: list[dict[str, Any]],
    source_name: str,
    default_allowed_roles: list[str] | None = None,
) -> int:
    """Batch embed and upsert chunks into Qdrant collection using AsyncQdrantClient."""
    if not chunks:
        log.warning("ingest.empty_source", source=source_name)
        return 0

    doc_texts = [c.get("document") or c.get("content", "") for c in chunks]
    vectors = embedder.embed_documents(doc_texts)

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

        payload_obj = KnowledgeChunkPayload(
            content=c["document"],
            source=KnowledgeSource(source_name),
            document_id=doc_id,
            chunk_id=str(c.get("id") or point_uuid),
            title=str(meta.get("title") or meta.get("subject") or ""),
            category=str(meta.get("category") or "general"),
            allowed_roles=chunk_roles,
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
    """Extract plain text from uploaded PDF, Docx, Markdown, or plain text bytes."""
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
            log.warning("ingest.pdf_extraction_fallback", error=str(exc))
        return file_bytes.decode("utf-8", errors="ignore")

    elif ext == "docx":
        try:
            import io

            import docx

            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception as exc:
            log.warning("ingest.docx_extraction_fallback", error=str(exc))
        return file_bytes.decode("utf-8", errors="ignore")

    return file_bytes.decode("utf-8", errors="ignore")


async def ingest_uploaded_file_async(
    client: AsyncQdrantClient,
    embedder: BGEEmbedder,
    filename: str,
    file_bytes: bytes,
    allowed_roles: list[str] | None = None,
) -> int:
    """
    Parse an uploaded document file, split into semantic chunks, embed,
    and upsert into Qdrant with associated RBAC allowed_roles.
    """
    raw_text = extract_text_from_file_bytes(filename, file_bytes)
    if not raw_text.strip():
        log.warning("ingest.uploaded_file_empty", filename=filename)
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
                "metadata": {
                    "file": filename,
                    "document_id": doc_id,
                    "title": filename,
                    "category": "user_uploaded",
                    "chunk_index": idx,
                    "allowed_roles": roles,
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
        await client.create_payload_index(
            collection_name=collection_name,
            field_name="metadata.ticket_id",
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

    await ensure_collection(
        client, settings.qdrant_collection_name, vector_size=settings.embedding_dim
    )

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
