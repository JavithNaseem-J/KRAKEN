"""
PromptGuardMiddleware — Edge gateway security middleware for prompt injection detection
and PII sanitization.
"""

from __future__ import annotations

import json
import re

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = structlog.get_logger(__name__)

# Prompt injection patterns (case-insensitive)
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*:", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a\s+DAN", re.IGNORECASE),
    re.compile(r"override\s+(all\s+)?safety\s+guidelines", re.IGNORECASE),
    re.compile(r"<\s*\|im_start\|\s*>", re.IGNORECASE),
    re.compile(r"\[\s*INST\s*\]", re.IGNORECASE),
]

# PII regex patterns
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


def check_prompt_injection(text: str) -> bool:
    """Return True if prompt injection patterns are detected."""
    return any(pattern.search(text) for pattern in PROMPT_INJECTION_PATTERNS)


def sanitize_pii(text: str) -> str:
    """Redact sensitive PII values with [REDACTED_PII]."""
    text = SSN_PATTERN.sub("[REDACTED_PII]", text)
    text = CREDIT_CARD_PATTERN.sub("[REDACTED_PII]", text)
    return text


class PromptGuardMiddleware(BaseHTTPMiddleware):
    """
    Middleware checking /v1/run incoming JSON payloads for prompt injection attacks
    and masking PII strings before requests reach upstream services.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path == "/v1/run" and request.method == "POST":
            try:
                body_bytes = await request.body()
                if body_bytes:
                    payload = json.loads(body_bytes)
                    message = payload.get("message", "")
                    if isinstance(message, str) and message:
                        if check_prompt_injection(message):
                            log.warning("gateway.prompt_injection_blocked", path=request.url.path)
                            return JSONResponse(
                                status_code=400,
                                content={
                                    "error": "Security violation: prompt injection pattern detected."
                                },
                            )

                        sanitized_message = sanitize_pii(message)
                        if sanitized_message != message:
                            payload["message"] = sanitized_message
                            log.info("gateway.pii_redacted", path=request.url.path)
                            new_bytes = json.dumps(payload).encode("utf-8")
                            request._body = new_bytes
            except Exception as exc:
                log.warning("gateway.prompt_guard_error", error=str(exc))

        return await call_next(request)
