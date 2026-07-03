"""
API key authentication middleware for the gateway.

Validates the X-API-Key header against configured keys.
Maps each API key to a user_id for rate limiting and audit logging.

In production, keys would live in a DB or secret manager.
For the current scope (internal team), env-var configuration is sufficient:
  GATEWAY_API_KEYS = "key1:alice,key2:bob,key3:carol"
  (key:user_id pairs, comma-separated)
"""
from __future__ import annotations

import structlog
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = structlog.get_logger(__name__)

_HEALTH_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Validates X-API-Key header on all non-health requests.
    Sets request.state.user_id for downstream use.
    """

    def __init__(self, app, api_keys: dict[str, str]) -> None:
        """
        Args:
            api_keys: Mapping of {api_key: user_id}.
        """
        super().__init__(app)
        self._keys = api_keys

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health/docs endpoints
        if request.url.path in _HEALTH_PATHS:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "").strip()

        if not api_key:
            log.warning("auth.missing_key", path=request.url.path)
            return JSONResponse(
                status_code=401,
                content={"error": "Missing X-API-Key header."},
            )

        user_id = self._keys.get(api_key)
        if user_id is None:
            log.warning("auth.invalid_key", path=request.url.path)
            return JSONResponse(
                status_code=403,
                content={"error": "Invalid API key."},
            )

        # Store user_id for rate limiter and audit log
        request.state.user_id = user_id
        return await call_next(request)


def parse_api_keys(raw: str) -> dict[str, str]:
    """
    Parse GATEWAY_API_KEYS env var.

    Format: "key1:user1,key2:user2"
    Returns: {"key1": "user1", "key2": "user2"}
    """
    result: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" in pair:
            key, user = pair.split(":", 1)
            result[key.strip()] = user.strip()
    return result
