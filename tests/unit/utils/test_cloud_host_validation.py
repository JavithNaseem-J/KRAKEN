"""
Unit tests for Settings.validate_no_local_hosts (shared/config.py).

Validates that:
  - localhost / 127.0.0.1 / compose hostnames are REJECTED in 'prod' and 'staging'
    when explicitly set to a local URL
  - Empty string URLs are allowed (means "not configured", service runs in degraded mode)
  - They are ALLOWED in 'dev' (local development bypass)
  - Cloud hostnames always pass in 'prod'
  - Multiple offenders are reported in one error
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.utils.config import Settings

# A strong token that passes the HITL validator
_TOKEN = "a" * 32

# Cloud-valid URLs for all checked fields.
_CLOUD_URLS = {
    "postgres_url": "postgresql+asyncpg://u:p@db.example.com:5432/akea",
    "postgres_sync_url": "postgresql://u:p@db.example.com:5432/akea",
    "redis_url": "rediss://cache.example.com:6379",
    "qdrant_url": "https://qdrant.example.com",
    "qdrant_api_key": "qdrant-test-key",
    "llm_api_key": "groq-test-key",
    "orchestrator_url": "https://orchestrator.akea.internal",
    "knowledge_url": "https://knowledge.akea.internal",
    "action_url": "https://action.akea.internal",
    "approval_url": "https://approval.akea.internal",
    "memory_url": "https://memory.akea.internal",
    "audit_url": "https://audit.akea.internal",
    "gateway_api_keys": "server-only-test-key:tier1_analyst",
    "demo_session_secret": "demo-session-secret-0123456789abcdef",
    "demo_cookie_secure": True,
}


def _make_settings(environment: str, **url_overrides) -> Settings:
    """Build Settings bypassing .env, injecting the given URLs and environment."""
    fields = {**_CLOUD_URLS, "hitl_service_token": _TOKEN, "environment": environment}
    fields.update(url_overrides)
    return Settings.model_validate(fields)


# ── Dev bypass ────────────────────────────────────────────────────────────────


class TestDevBypass:
    def test_localhost_allowed_in_dev(self) -> None:
        """Localhost postgres/redis URLs are valid in dev — no validation error."""
        settings = _make_settings(
            "dev",
            postgres_url="postgresql+asyncpg://u:p@localhost:5432/akea",
            postgres_sync_url="postgresql://u:p@localhost:5432/akea",
            redis_url="redis://localhost:6379/0",
        )
        assert settings.environment == "dev"

    def test_compose_hostnames_allowed_in_dev(self) -> None:
        """Docker-compose hostnames (postgres, redis) are valid in dev."""
        settings = _make_settings(
            "dev",
            postgres_url="postgresql+asyncpg://u:p@postgres:5432/akea",
            redis_url="redis://redis:6379/0",
        )
        assert settings.environment == "dev"

    def test_127_allowed_in_dev(self) -> None:
        settings = _make_settings(
            "dev",
            redis_url="redis://127.0.0.1:6379/0",
        )
        assert settings.environment == "dev"


# ── Prod / staging enforcement ────────────────────────────────────────────────


class TestProdEnforcement:
    def test_localhost_postgres_rejected_in_prod(self) -> None:
        with pytest.raises(ValidationError, match="Local/compose hostnames"):
            _make_settings(
                "prod",
                postgres_url="postgresql+asyncpg://u:p@localhost:5432/akea",
                postgres_sync_url="postgresql://u:p@localhost:5432/akea",
            )

    def test_localhost_redis_rejected_in_prod(self) -> None:
        with pytest.raises(ValidationError, match="Local/compose hostnames"):
            _make_settings("prod", redis_url="redis://localhost:6379/1")

    def test_127_rejected_in_prod(self) -> None:
        with pytest.raises(ValidationError, match="Local/compose hostnames"):
            _make_settings("prod", redis_url="redis://127.0.0.1:6379/0")

    def test_compose_postgres_hostname_rejected_in_prod(self) -> None:
        with pytest.raises(ValidationError, match="Local/compose hostnames"):
            _make_settings(
                "prod",
                postgres_url="postgresql+asyncpg://u:p@postgres:5432/akea",
                postgres_sync_url="postgresql://u:p@postgres:5432/akea",
            )

    def test_compose_redis_hostname_rejected_in_prod(self) -> None:
        with pytest.raises(ValidationError, match="Local/compose hostnames"):
            _make_settings("prod", redis_url="redis://redis:6379/0")

    def test_localhost_service_url_rejected_in_prod(self) -> None:
        with pytest.raises(ValidationError, match="Local/compose hostnames"):
            _make_settings("prod", orchestrator_url="http://localhost:8001")

    def test_localhost_rejected_in_staging(self) -> None:
        with pytest.raises(ValidationError, match="Local/compose hostnames"):
            _make_settings("staging", redis_url="redis://localhost:6379/1")

    def test_empty_redis_url_rejected_in_prod(self) -> None:
        with pytest.raises(ValidationError, match="redis_url"):
            _make_settings("prod", redis_url="")

    def test_empty_postgres_url_rejected_in_prod(self) -> None:
        with pytest.raises(ValidationError, match="postgres_url"):
            _make_settings("prod", postgres_url="", postgres_sync_url="")

    def test_multiple_offenders_reported_together(self) -> None:
        """All offending fields must appear in a single ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            _make_settings(
                "prod",
                postgres_url="postgresql+asyncpg://u:p@localhost:5432/akea",
                postgres_sync_url="postgresql://u:p@localhost:5432/akea",
                redis_url="redis://localhost:6379/1",
            )
        msg = str(exc_info.value)
        assert "postgres_url" in msg
        assert "redis_url" in msg


# ── Cloud URLs always pass ──────────────────────────────────────────────────────────────────────────


class TestCloudUrlsPass:
    def test_rds_postgres_passes_in_prod(self) -> None:
        settings = _make_settings(
            "prod",
            postgres_url="postgresql+asyncpg://u:p@db.us-east-1.rds.amazonaws.com:5432/akea",
            postgres_sync_url="postgresql+asyncpg://u:p@db.us-east-1.rds.amazonaws.com:5432/akea",
        )
        assert "amazonaws" in settings.postgres_url

    def test_elasticache_redis_passes_in_prod(self) -> None:
        settings = _make_settings(
            "prod",
            redis_url="rediss://u:p@akea.cache.amazonaws.com:6379/0",
        )
        assert "amazonaws" in settings.redis_url

    def test_cloud_service_urls_pass_in_prod(self) -> None:
        settings = _make_settings("prod")
        assert settings.environment == "prod"
        assert "localhost" not in settings.orchestrator_url
