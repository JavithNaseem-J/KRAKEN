"""
Long-term episodic memory using PostgreSQL + pgvector.

Stores past agent interactions as embedded vectors so the agent can
retrieve semantically similar past experiences at the start of each run.

Schema (from scripts/init.sql):
  episodic_memory(id, session_id, user_id, timestamp, content, embedding, metadata)
  embedding dim = 384 (BAAI/bge-small-en)

Operations:
  store()  → INSERT with embedding
  search() → cosine similarity search filtered by user_id
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg
import structlog
from langchain_huggingface import HuggingFaceEmbeddings

log = structlog.get_logger(__name__)


class LongTermMemory:
    """
    pgvector-backed episodic memory store.
    Embedding model loaded once at startup — same model as the knowledge service.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        embedding_model: str = "BAAI/bge-small-en",
        device: str = "cpu",
    ) -> None:
        log.info("long_term.loading_embedder", model=embedding_model)
        self._pool = pool
        self._model = HuggingFaceEmbeddings(
            model_name=embedding_model,
            model_kwargs={"device": device},
            encode_kwargs={"normalize_embeddings": True},
        )
        log.info("long_term.embedder_ready")

    def _embed(self, text: str) -> list[float]:
        """Embed a single string, returning a normalised float list."""
        return self._model.embed_query(text)

    async def store(
        self,
        session_id: str,
        user_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Store an episodic memory entry with its embedding.
        Returns the UUID of the inserted row.
        """
        embedding = self._embed(content)
        meta_json = json.dumps(metadata or {})

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO episodic_memory
                    (session_id, user_id, content, embedding, metadata)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                RETURNING id::text
                """,
                session_id,
                user_id,
                content,
                embedding,  # pgvector codec encodes list → '[x,y,z]'
                meta_json,
            )

        memory_id = row["id"]
        log.info("long_term.stored", session_id=session_id, id=memory_id)
        return memory_id

    async def search(
        self,
        query: str,
        user_id: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Retrieve the top_k most similar past memories for this user.
        Results sorted by cosine similarity descending.
        """
        embedding = self._embed(query)
        top_k = max(1, min(top_k, 20))

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id::text,
                    session_id,
                    content,
                    metadata,
                    timestamp,
                    1 - (embedding <=> $1) AS similarity
                FROM episodic_memory
                WHERE user_id = $2
                ORDER BY embedding <=> $1
                LIMIT $3
                """,
                embedding,
                user_id,
                top_k,
            )

        results = [
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"]),
                "timestamp": row["timestamp"].isoformat(),
                "similarity": float(row["similarity"]),
            }
            for row in rows
        ]

        log.info(
            "long_term.search",
            query=query[:60],
            user_id=user_id,
            results=len(results),
        )
        return results
