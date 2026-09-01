"""Root conftest — puts the repository root on sys.path so tests import ``src.*``.

KRAKEN is a consolidated single-process application: every subsystem lives under
the ``src/`` package (``src/api`` gateway + sub-apps, ``src/agent`` graph,
``src/utils`` shared infrastructure). Unit tests run fully offline with mocks;
integration tests (``tests/integration``) boot the real consolidated app with
fakeredis/in-memory fallbacks and are gated behind the ``integration`` marker.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Project root on sys.path so tests can import shared.* and services.*
sys.path.insert(0, str(Path(__file__).parent.parent))

# Never let a developer .env change unit-test authentication, dimensions, or
# network behavior. Service modules cache Settings at import time.
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "LLM_API_KEY": "",
        "GROQ_API_KEY": "",
        "OPENAI_API_KEY": "",
        "EMBEDDING_API_KEY": "",
        "EMBEDDING_PROVIDER": "cloud",
        "EMBEDDING_DIM": "384",
        "POSTGRES_URL": "",
        "POSTGRES_SYNC_URL": "",
        "REDIS_URL": "",
        "QDRANT_URL": "",
        "QDRANT_API_KEY": "",
        "SEMANTIC_CACHE_ENABLED": "true",
        "HITL_SERVICE_TOKEN": "test-hitl-token-0123456789abcdef0123456789",
        "GATEWAY_API_KEYS": "dev-key-analyst-default:tier1_analyst,dev-key-admin-default:admin",
        "PUBLIC_SESSION_SECRET": "test-public-secret-0123456789abcdef0123456789",
        "PUBLIC_COOKIE_SECURE": "false",
        "SYNTHETIC_DATASET_GENERATION": "northstar-v1",
    }
)

import pytest

from src.utils.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
