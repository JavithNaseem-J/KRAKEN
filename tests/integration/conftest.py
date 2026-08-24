"""
Integration-suite environment isolation.

The environment variables below MUST be set before any ``src.*`` module is
imported, because ``get_settings()`` is lru-cached and every service module
binds ``settings = get_settings()`` at import time. Run this suite in its own
pytest invocation (as CI does):

    pytest tests/integration -m integration

Backed by fakeredis and the built-in in-memory fallbacks (MemorySaver,
in-memory approval map, in-memory Qdrant) — no external service is contacted.
"""

from __future__ import annotations

import os
import sys
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import fakeredis
import fakeredis.aioredis

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

if "src.utils.config" in sys.modules:
    warnings.warn(
        "src.* was imported before the integration conftest set its environment "
        "variables; settings may reflect the developer .env instead of the test "
        "environment. Run the integration suite in its own pytest invocation: "
        "pytest tests/integration -m integration",
        stacklevel=2,
    )

_TEST_HITL_TOKEN = "itest-hitl-token-0123456789abcdef0123456789"
_TEST_API_KEY = "itest-demo-key-0123456789abcdef"

os.environ.update(
    {
        "ENVIRONMENT": "dev",
        # No real credentials — the LLM is mocked at get_llm; embedder falls
        # back to ZeroVectorEmbedder.
        "LLM_API_KEY": "",
        "GROQ_API_KEY": "",
        "OPENAI_API_KEY": "",
        "EMBEDDING_API_KEY": "",
        "EMBEDDING_PROVIDER": "cloud",
        # No backing services — in-memory fallbacks everywhere.
        "POSTGRES_URL": "",
        "POSTGRES_SYNC_URL": "",
        "REDIS_URL": "",
        "QDRANT_URL": "",
        "QDRANT_API_KEY": "",
        "LANGFUSE_PUBLIC_KEY": "",
        "LANGFUSE_SECRET_KEY": "",
        # Zero-vector embeddings make cosine similarity degenerate; keep the
        # semantic cache out of the test path.
        "SEMANTIC_CACHE_ENABLED": "false",
        # Known test secrets (config validation requires >= 32 chars).
        "HITL_SERVICE_TOKEN": _TEST_HITL_TOKEN,
        "GATEWAY_API_KEYS": f"{_TEST_API_KEY}:demo-user-1",
        "LOG_LEVEL": "WARNING",
        "LOG_FORMAT": "console",
    }
)

from src.utils.config import get_settings  # noqa: E402

get_settings.cache_clear()


class OfflineTestEmbedder:
    """Sentinel embedder used by gateway boot tests to prevent model downloads."""

    dim = 1536

    def embed_query(self, text: str) -> list[float]:
        return [0.0] * self.dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dim for _ in texts]


def make_fake_redis_factory(server: fakeredis.FakeServer):
    def factory(url: str, **kwargs: Any) -> fakeredis.aioredis.FakeRedis:
        return fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)

    return factory


@contextmanager
def offline_gateway_lifespan_patches() -> Iterator[dict[str, int]]:
    """Patch true external services for a full gateway lifespan boot."""
    server = fakeredis.FakeServer()
    calls = {"get_embedder": 0}

    def get_offline_embedder() -> OfflineTestEmbedder:
        calls["get_embedder"] += 1
        return OfflineTestEmbedder()

    with (
        patch("src.utils.http_client.create_async_redis_client", make_fake_redis_factory(server)),
        patch("src.utils.embedder.get_embedder", get_offline_embedder),
    ):
        yield calls
