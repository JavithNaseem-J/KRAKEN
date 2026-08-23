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
from pathlib import Path

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
