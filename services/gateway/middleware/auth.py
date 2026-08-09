import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from shared.auth import safe_compare_tokens

log = structlog.get_logger(__name__)

# Endpoints that bypass standard user API key authentication
_BYPASS_PATHS = {"/", "/health", "/docs", "/openapi.json"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Validates X-API-Key header on all non-health requests.
    Sets request.state.user_id for downstream use.
    Uses timing-attack safe comparisons.
    """

    def __init__(self, app, api_keys: dict[str, str]) -> None:
        """
        Args:
            api_keys: Mapping of {api_key: user_id}.
        """
        super().__init__(app)
        self._keys = api_keys

    async def dispatch(self, request: Request, call_next):
        # Skip auth for bypassed endpoints (health, docs, and special approval callbacks)
        if request.url.path in _BYPASS_PATHS:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "").strip()

        if not api_key:
            log.warning("auth.missing_key", path=request.url.path)
            return JSONResponse(
                status_code=401,
                content={"error": "Missing X-API-Key header."},
                headers={"WWW-Authenticate": "ApiKey realm='KRAKEN Gateway'"},
            )

        # Constant-time lookup check to prevent timing attacks
        matched_user_id = None
        for registered_key, user_id in self._keys.items():
            if safe_compare_tokens(registered_key, api_key):
                matched_user_id = user_id
                break

        if matched_user_id is None:
            log.warning("auth.invalid_key", path=request.url.path)
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid API key."},
                headers={"WWW-Authenticate": "ApiKey realm='KRAKEN Gateway'"},
            )

        # Store user_id for rate limiter and audit log
        request.state.user_id = matched_user_id
        return await call_next(request)


def parse_api_keys(raw: str) -> dict[str, str]:
    """
    Parse and validate GATEWAY_API_KEYS env var.
    Fails fast on startup if the configuration is empty, malformed, or contains weak keys.

    Format: "key1:user1,key2:user2"
    Returns: {"key1": "user1", "key2": "user2"}
    """
    if not raw or not raw.strip():
        raise ValueError(
            "GATEWAY_API_KEYS is empty. The gateway requires at least one registered API key."
        )

    result: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if ":" not in pair:
            raise ValueError(f"Malformed key pair: '{pair}'. Must be in format 'api_key:user_id'.")
        key, user = pair.split(":", 1)
        key_str = key.strip()
        user_str = user.strip()

        if not key_str or not user_str:
            raise ValueError(f"Malformed key pair: '{pair}'. Key or User ID cannot be empty.")

        # Security enforcement: keys must be at least 16 characters for sufficient entropy
        if len(key_str) < 16:
            raise ValueError(
                f"Insecure API key detected for user '{user_str}'. "
                "API keys must be at least 16 characters long."
            )

        result[key_str] = user_str

    if not result:
        raise ValueError("No valid API keys parsed from GATEWAY_API_KEYS configuration.")

    return result
