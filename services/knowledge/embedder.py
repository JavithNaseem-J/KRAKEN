"""
BGE Embedder — wraps BAAI/bge-small-en from sentence-transformers.

Implements ChromaDB's EmbeddingFunction interface so it can be passed
directly to collection.get_or_create_collection(embedding_function=...).

Design decisions:
  - Model loaded ONCE at startup via the singleton in lifespan()
  - normalize_embeddings=True is mandatory (cosine similarity requires unit vectors)
  - device defaults to "cpu" — adequate for 50-55 docs, no GPU required
"""

from __future__ import annotations

import structlog
from chromadb import Documents, EmbeddingFunction, Embeddings
from langchain_huggingface import HuggingFaceEmbeddings

log = structlog.get_logger(__name__)

EMBEDDING_DIM = 384  # bge-small-en output dimension


class BGEEmbedder(EmbeddingFunction[Documents]):
    """
    ChromaDB-compatible embedding function wrapping langchain_huggingface.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en", device: str = "cpu") -> None:
        log.info("embedder.loading", model=model_name, device=device)
        self._model = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": device},
            encode_kwargs={"normalize_embeddings": True},
        )
        self.model_name = model_name
        self.device = device
        log.info("embedder.ready", model=model_name)

    def __call__(self, input: Documents) -> Embeddings:  # noqa: A002
        """Embed a batch of text strings. Called automatically by ChromaDB."""
        return self._model.embed_documents(list(input))  # type: ignore[return-value]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string (used by the retriever directly)."""
        return self._model.embed_query(text)
