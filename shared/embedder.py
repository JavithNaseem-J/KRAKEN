"""
Unified Embedder — supports Cloud API embeddings (OpenAI / Cloud endpoints)
and local HuggingFace models.

Provides vector embedding services for Knowledge and Memory microservices.
"""

from __future__ import annotations

import structlog
from langchain_huggingface import HuggingFaceEmbeddings

from shared.config import get_settings

import threading
from functools import lru_cache

log = structlog.get_logger(__name__)
settings = get_settings()

EMBEDDING_DIM = 384  # Default BAAI/bge-small-en dimension

_embedder_instance: BGEEmbedder | None = None
_embedder_lock = threading.Lock()


class ZeroVectorEmbedder:
    """Lightweight zero-vector fallback embedder when no API keys are set and local PyTorch models are skipped to stay within RAM limits."""

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    def embed_query(self, text: str) -> list[float]:
        return [0.0] * self.dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dim for _ in texts]


class BGEEmbedder:
    """
    Shared embedding wrapper supporting Cloud API embeddings or local models.
    Provides cached embed_query() for single strings and embed_documents() for batches.
    """

    def __init__(self, model_name: str | None = None, device: str | None = None) -> None:
        provider = settings.embedding_provider.lower()
        model_name = model_name or settings.embedding_model
        device = device or settings.embedding_device

        log.info("embedder.loading", provider=provider, model=model_name)

        if provider in ("cloud", "openai") and (settings.embedding_api_key or settings.llm_api_key):
            from langchain_openai import OpenAIEmbeddings

            api_key = settings.embedding_api_key or settings.llm_api_key
            base_url = settings.embedding_base_url or None

            self._model = OpenAIEmbeddings(
                model=model_name,
                openai_api_key=api_key,
                openai_api_base=base_url,
            )
            log.info("embedder.cloud_api_ready", model=model_name)
        elif provider in ("cloud", "openai"):
            log.warning("embedder.no_api_key_provided_using_zero_vector_fallback")
            dim = 1536 if "3-small" in model_name or "ada" in model_name else 384
            self._model = ZeroVectorEmbedder(dim=dim)
        else:
            try:
                from langchain_huggingface import HuggingFaceEmbeddings

                self._model = HuggingFaceEmbeddings(
                    model_name=model_name,
                    model_kwargs={"device": device},
                    encode_kwargs={"normalize_embeddings": True},
                )
                log.info("embedder.local_hf_ready", model=model_name)
            except Exception as exc:
                log.warning("embedder.fallback_zero_vectors", reason=str(exc))
                self._model = ZeroVectorEmbedder(dim=384)

        self.model_name = model_name
        self.device = device

    @lru_cache(maxsize=1024)
    def _cached_embed_query(self, text: str) -> tuple[float, ...]:
        """Internal cached vector generator returning hashable tuple."""
        return tuple(self._model.embed_query(text))

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string using in-memory LRU cache."""
        return list(self._cached_embed_query(text))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document strings."""
        return self._model.embed_documents(texts)


def get_embedder() -> BGEEmbedder:
    """Thread-safe singleton factory for BGEEmbedder instance."""
    global _embedder_instance
    if _embedder_instance is None:
        with _embedder_lock:
            if _embedder_instance is None:
                _embedder_instance = BGEEmbedder()
    return _embedder_instance
