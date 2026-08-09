"""
Shared authentication dependencies for AKEA services.

Enforces timing-attack safe service token validation across all microservice endpoints.
"""

from __future__ import annotations

import secrets

import structlog
from fastapi import Header, HTTPException, status

from shared.config import get_settings

log = structlog.get_logger(__name__)


def safe_compare_tokens(token1: str, token2: str) -> bool:
    """Perform constant-time token comparison to prevent timing attacks."""
    if not token1 or not token2:
        return False
    return secrets.compare_digest(token1, token2)


def verify_service_token(
    x_service_token: str | None = Header(None, alias="X-Service-Token"),
) -> str:
    """
    FastAPI dependency: Enforce high-privilege inter-service token authentication.
    Uses constant-time comparison (secrets.compare_digest) to prevent timing attacks.
    """
    settings = get_settings()
    token = x_service_token or ""

    valid_tokens = [
        t
        for t in [
            settings.hitl_service_token,
            settings.orchestrator_service_token,
            settings.approval_service_token,
            settings.action_service_token,
            settings.knowledge_service_token,
            settings.memory_service_token,
            settings.audit_service_token,
        ]
        if t and len(t) >= 32
    ]

    if not token or not any(safe_compare_tokens(token, vt) for vt in valid_tokens):
        log.warning("auth.service_token_validation_failed")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing service token.",
        )
    return token
