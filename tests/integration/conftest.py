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

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import fakeredis
import fakeredis.aioredis
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

_TEST_HITL_TOKEN = "itest-hitl-token-0123456789abcdef0123456789"
_TEST_API_KEY = "itest-demo-key-0123456789abcdef"

_INTEGRATION_ENV = {
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
    # Zero-vector embeddings make cosine similarity degenerate; keep the
    # semantic cache out of the test path.
    "SEMANTIC_CACHE_ENABLED": "false",
    # Known test secrets (config validation requires >= 32 chars).
    "HITL_SERVICE_TOKEN": _TEST_HITL_TOKEN,
    "GATEWAY_API_KEYS": json.dumps(
        {
            _TEST_API_KEY: {
                "user_id": "demo-user-1",
                "role": "tier1_analyst",
            }
        }
    ),
    "LOG_LEVEL": "WARNING",
    "LOG_FORMAT": "console",
}

from src.utils.config import get_settings  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolated_integration_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Apply integration credentials per test without contaminating unit-test collection."""
    for name, value in _INTEGRATION_ENV.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class OfflineTestEmbedder:
    """Sentinel embedder used by gateway boot tests to prevent model downloads."""

    dim = 384

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
