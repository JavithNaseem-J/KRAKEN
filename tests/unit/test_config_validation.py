"""
Unit tests for Settings model_validators in shared/config.py.

Validates that:
  - Default HITL token is rejected in ALL environments (including dev / unset).
  - Short (< 32 char) tokens are rejected in all environments.
  - A strong (>= 32 char) unique token passes in all environments.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.config import Settings

# A valid token that satisfies all requirements
_STRONG_TOKEN = "a" * 32
_SHORT_TOKEN = "short-but-not-32-chars"
_DEFAULT_TOKEN = "change-me-in-production"


def _make_settings(**overrides) -> Settings:
    """Helper: build Settings with minimal required overrides, bypassing .env."""
    base = {
        "postgres_url": "postgresql+asyncpg://u:p@db.example.com:5432/akea",
        "postgres_sync_url": "postgresql://u:p@db.example.com:5432/akea",
        "redis_url": "rediss://cache.example.com:6379",
        "orchestrator_url": "https://orchestrator.example.com",
        "knowledge_url": "https://knowledge.example.com",
        "action_url": "https://action.example.com",
        "approval_url": "https://approval.example.com",
        "memory_url": "https://memory.example.com",
        "audit_url": "https://audit.example.com",
        "hitl_service_token": _STRONG_TOKEN,
    }
    base.update(overrides)
    return Settings.model_validate(base)


# ── Default token tests ────────────────────────────────────────────────────────


class TestDefaultTokenRejected:
    def test_default_token_rejected_in_prod(self):
        with pytest.raises(ValidationError, match="shipped default"):
            _make_settings(hitl_service_token=_DEFAULT_TOKEN, environment="prod")

    def test_default_token_rejected_in_staging(self):
        with pytest.raises(ValidationError, match="shipped default"):
            _make_settings(hitl_service_token=_DEFAULT_TOKEN, environment="staging")

    def test_default_token_rejected_in_dev(self):
        """Dev environment must NOT bypass weak-token validation."""
        with pytest.raises(ValidationError, match="shipped default"):
            _make_settings(hitl_service_token=_DEFAULT_TOKEN, environment="dev")

    def test_default_token_rejected_when_env_is_unset(self):
        """When ENVIRONMENT is omitted (defaults to 'dev'), token is still rejected."""
        # 'environment' is not provided — defaults to 'dev' per config.py line 19
        with pytest.raises(ValidationError, match="shipped default"):
            _make_settings(hitl_service_token=_DEFAULT_TOKEN)


# ── Short token tests ─────────────────────────────────────────────────────────


class TestShortTokenRejected:
    def test_short_token_rejected_in_prod(self):
        with pytest.raises(ValidationError, match="too short"):
            _make_settings(hitl_service_token=_SHORT_TOKEN, environment="prod")

    def test_short_token_rejected_in_dev(self):
        with pytest.raises(ValidationError, match="too short"):
            _make_settings(hitl_service_token=_SHORT_TOKEN, environment="dev")

    def test_empty_token_rejected(self):
        with pytest.raises(ValidationError, match="too short"):
            _make_settings(hitl_service_token="")

    def test_31_char_token_rejected(self):
        with pytest.raises(ValidationError, match="too short"):
            _make_settings(hitl_service_token="x" * 31)


# ── Strong token tests ────────────────────────────────────────────────────────


class TestStrongTokenAccepted:
    def test_exactly_32_char_token_passes(self):
        settings = _make_settings(hitl_service_token="x" * 32, environment="dev")
        assert len(settings.hitl_service_token) == 32

    def test_long_hex_token_passes_in_prod(self):
        token = "764956947b16ff326b581b0ff99ab445be6b5b4b0baef608a65c27c175ba6d85"
        settings = _make_settings(hitl_service_token=token, environment="prod")
        assert settings.hitl_service_token == token

    def test_long_hex_token_passes_in_dev(self):
        token = "764956947b16ff326b581b0ff99ab445be6b5b4b0baef608a65c27c175ba6d85"
        settings = _make_settings(hitl_service_token=token, environment="dev")
        assert settings.hitl_service_token == token
