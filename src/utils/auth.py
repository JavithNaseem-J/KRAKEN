from __future__ import annotations

import json
import secrets
from typing import Any

import structlog
from fastapi import Header, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.utils.config import get_settings

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


def _normalize_key_metadata(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        user_id = str(value.get("user_id") or "default_user").strip()
        role = str(value.get("role") or "user").strip().lower()
        return {"user_id": user_id or "default_user", "role": role or "user"}
    if isinstance(value, str):
        return {"user_id": value.strip() or "default_user", "role": "user"}
    return {"user_id": "default_user", "role": "user"}


def parse_api_keys(raw_keys: str) -> dict[str, dict[str, str]]:
    """Parse canonical JSON or non-privileged legacy comma-separated API keys."""

    if not raw_keys:
        return {}
    try:
        data = json.loads(raw_keys)
        if isinstance(data, dict):
            return {
                str(key).strip(): _normalize_key_metadata(metadata)
                for key, metadata in data.items()
                if str(key).strip()
            }
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    mapping = {}
    for part in raw_keys.split(","):
        part = part.strip()
        if part:
            if ":" in part:
                k, u = part.split(":", 1)
                mapping[k.strip()] = {"user_id": u.strip(), "role": "user"}
            else:
                mapping[part] = {"user_id": "default_user", "role": "user"}
    return mapping


def match_api_key(candidate: str, api_keys: dict[str, dict[str, str]]) -> dict[str, str] | None:
    """Return metadata for a constant-time API-key match."""
    for configured_key, metadata in api_keys.items():
        if safe_compare_tokens(candidate, configured_key):
            return _normalize_key_metadata(metadata)
    return None


class APIKeyMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware to validate API key headers on incoming gateway requests."""

    def __init__(
        self,
        app,
        api_keys: dict[str, dict[str, str]] | None = None,
        api_keys_map: dict[str, dict[str, str]] | None = None,
    ) -> None:
        super().__init__(app)
        self.api_keys_map = api_keys or api_keys_map or {}

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        # Ops probes and the browser-facing HITL approval flow (protected by
        # unguessable approval_id + CSRF token) bypass API-key auth.
        if (
            path in ("/", "/health", "/ready", "/metrics", "/docs", "/openapi.json")
            or path.startswith(("/approve/", "/assets/", "/v1/session"))
            or path in ("/favicon.ico", "/robots.txt")
        ):
            return await call_next(request)
        if not path.startswith(("/v1/", "/approve/")):
            return await call_next(request)

        settings = get_settings()
        if path.startswith("/v1/") and request.cookies.get(settings.public_session_cookie_name):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        if not api_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:]

        if not api_key:
            return JSONResponse(
                {"error": "Missing X-API-Key or Bearer token header."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        current_keys = parse_api_keys(settings.gateway_api_keys)
        valid_keys = {**self.api_keys_map, **current_keys} if self.api_keys_map else current_keys

        metadata = match_api_key(api_key, valid_keys) if api_key else None
        if metadata is not None:
            request.state.user_id = metadata["user_id"]
            request.state.operator_role = metadata["role"]
            return await call_next(request)

        return JSONResponse(
            {"error": "Invalid API key provided."},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )


USER_ROLE_MAP: dict[str, str] = {
    "synthetic-operator-1": "tier1",
    "synthetic-operator-2": "security_lead",
    "synthetic-admin": "admin",
}


def resolve_user_role(user_id: str) -> str:
    """
    Map a user_id to an operational role for RBAC-scoped retrieval.
    Falls back to using the user_id as-is if not found in the mapping.
    """
    normalized = (user_id or "public").lower().strip()
    return USER_ROLE_MAP.get(normalized, normalized)
