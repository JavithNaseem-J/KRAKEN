from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

import structlog

from src.utils.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

_embedder_instance: BGEEmbedder | None = None
_embedder_lock = threading.Lock()


class ZeroVectorEmbedder:
    """Lightweight zero-vector fallback embedder when no API keys are set and local models are unconfigured."""

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim
        log.error(
            "embedder.zero_vector_fallback_active",
            dim=dim,
            message="ZeroVectorEmbedder is active. Embeddings will be zero vectors; retrieval will return empty or default results.",
        )

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
        self._query_cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._model: Any

        log.info("embedder.loading", provider=provider, model=model_name)

        if provider in ("cloud", "openai") and (settings.embedding_api_key or settings.llm_api_key):
            from langchain_openai import OpenAIEmbeddings
            from pydantic import SecretStr

            api_key = settings.embedding_api_key or settings.llm_api_key
            base_url = settings.embedding_base_url or None

            self._model = OpenAIEmbeddings(
                model=model_name,
                api_key=SecretStr(api_key),
                base_url=base_url,
            )
            log.info("embedder.cloud_api_ready", model=model_name)
        elif provider in ("cloud", "openai"):
            log.warning("embedder.no_api_key_provided_using_zero_vector_fallback")
            dim = settings.embedding_dim
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
                self._model = ZeroVectorEmbedder(dim=settings.embedding_dim)

        self.model_name = model_name
        self.device = device

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string using bounded OrderedDict LRU cache."""
        with self._cache_lock:
            if text in self._query_cache:
                self._query_cache.move_to_end(text)
                return self._query_cache[text]

        embedding = list(self._model.embed_query(text))
        with self._cache_lock:
            if text in self._query_cache:
                self._query_cache.move_to_end(text)
                return self._query_cache[text]
            if len(self._query_cache) >= 1024:
                self._query_cache.popitem(last=False)
            self._query_cache[text] = embedding
            return embedding

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document strings."""
        return [list(d) for d in self._model.embed_documents(texts)]


def get_embedder() -> BGEEmbedder:
    """Thread-safe singleton factory for BGEEmbedder instance."""
    global _embedder_instance
    if _embedder_instance is None:
        with _embedder_lock:
            if _embedder_instance is None:
                _embedder_instance = BGEEmbedder()
    return _embedder_instance
