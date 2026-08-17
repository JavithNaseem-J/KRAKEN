"""
Shared CORS configuration helper for FastAPI services.
"""

from __future__ import annotations

from typing import Any

from src.utils.config import get_settings

settings = get_settings()


def cors_middleware_kwargs() -> dict[str, Any]:
    """
    Return kwargs for FastAPI CORSMiddleware based on Settings.cors_allowed_origins.
    """
    allowed_cors_origins = [
        origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()
    ]

    if "*" in allowed_cors_origins:
        cors_kwargs: dict[str, Any] = {
            "allow_origins": ["*"],
            "allow_credentials": False,
        }
    else:
        cors_kwargs = {
            "allow_origins": allowed_cors_origins,
            "allow_origin_regex": r"https://.*\.onrender\.com|http://localhost:.*",
            "allow_credentials": True,
        }

    cors_kwargs["allow_methods"] = ["*"]
    cors_kwargs["allow_headers"] = ["*"]
    return cors_kwargs
