from __future__ import annotations

import threading
from collections import OrderedDict
from unittest.mock import MagicMock

from src.utils.embedder import BGEEmbedder, ZeroVectorEmbedder


def test_zero_vector_embedder() -> None:
    embedder = ZeroVectorEmbedder(dim=384)
    vec = embedder.embed_query("test query")
    assert len(vec) == 384
    assert all(x == 0.0 for x in vec)

    docs = embedder.embed_documents(["doc 1", "doc 2"])
    assert len(docs) == 2
    assert len(docs[0]) == 384


def test_bge_embedder_lru_cache_eviction() -> None:
    embedder = object.__new__(BGEEmbedder)
    mock_model = MagicMock()
    mock_model.embed_query.side_effect = lambda text: [float(hash(text) % 100)] * 384
    embedder._model = mock_model
    embedder._query_cache = OrderedDict()
    embedder._cache_lock = threading.Lock()

    # Insert 1024 unique items
    for i in range(1024):
        embedder.embed_query(f"query_{i}")

    assert len(embedder._query_cache) == 1024
    assert "query_0" in embedder._query_cache
    assert "query_1023" in embedder._query_cache

    # Access query_0 so it becomes most recently used
    embedder.embed_query("query_0")

    # Insert 1025th unique item -> should evict query_1 (oldest), keeping query_0
    embedder.embed_query("query_1024")

    assert len(embedder._query_cache) == 1024
    assert "query_0" in embedder._query_cache
    assert "query_1" not in embedder._query_cache
    assert "query_1024" in embedder._query_cache
