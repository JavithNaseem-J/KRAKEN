from __future__ import annotations

import json
import re
from dataclasses import dataclass

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = structlog.get_logger(__name__)

# Prompt injection patterns (case-insensitive)
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(your|all)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a\s+)?", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+are", re.IGNORECASE),
    re.compile(r"act\s+as\s+if", re.IGNORECASE),
    re.compile(r"new\s+persona", re.IGNORECASE),
    re.compile(r"override\s+(all\s+)?(safety\s+guidelines|system)", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*:", re.IGNORECASE),
    re.compile(r"<\s*\|im_start\|\s*>", re.IGNORECASE),
    re.compile(r"\[\s*INST\s*\]", re.IGNORECASE),
]

# PII regex patterns
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,16}\b")

OPERATOR_ROLES: frozenset[str] = frozenset(
    {
        "operator",
        "tier1_analyst",
        "incident_commander",
        "security_lead",
        "admin",
        "soc_tier1",
        "soc_tier2",
    }
)


@dataclass(frozen=True)
class PromptGuardResult:
    blocked: bool
    sanitized_text: str
    detected_injection: bool = False
    redacted_pii: bool = False


def is_operator_role(role: str | None) -> bool:
    """Return True when a role has operator-level request privileges."""
    return (role or "").strip().lower() in OPERATOR_ROLES


def check_prompt_injection(text: str) -> bool:
    """Return True if prompt injection patterns are detected."""
    return any(pattern.search(text) for pattern in PROMPT_INJECTION_PATTERNS)


def sanitize_pii(text: str) -> str:
    """Redact sensitive PII values with [REDACTED_PII]."""
    text = SSN_PATTERN.sub("[REDACTED_PII]", text)
    text = CREDIT_CARD_PATTERN.sub("[REDACTED_PII]", text)
    return text


def guard_message(text: str, operator_role: str | None = None) -> PromptGuardResult:
    """Evaluate prompt safety and return sanitized text for forwarding."""
    detected_injection = check_prompt_injection(text)
    sanitized = sanitize_pii(text)
    return PromptGuardResult(
        blocked=detected_injection and not is_operator_role(operator_role),
        sanitized_text=sanitized,
        detected_injection=detected_injection,
        redacted_pii=sanitized != text,
    )


class PromptGuardMiddleware(BaseHTTPMiddleware):
    """
    Middleware checking incoming JSON payloads for prompt injection attacks
    and masking PII strings before requests reach upstream services.

    Requests carrying X-Operator-Role: operator bypass the injection block but
    still have the pattern match logged as a warning.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in ("/v1/run", "/v1/run/stream") and request.method == "POST":
            operator_role = request.headers.get("X-Operator-Role")
            try:
                body_bytes = await request.body()
                if body_bytes:
                    payload = json.loads(body_bytes)
                    message = payload.get("message", "")
                    if isinstance(message, str) and message:
                        guard_result = guard_message(message, operator_role)
                        if guard_result.detected_injection:
                            truncated = message[:120] + ("..." if len(message) > 120 else "")
                            if not guard_result.blocked:
                                log.warning(
                                    "gateway.prompt_injection_operator_bypass",
                                    path=request.url.path,
                                    query_preview=truncated,
                                    trace_id=getattr(request.state, "trace_id", None),
                                )
                            else:
                                log.warning(
                                    "gateway.prompt_injection_blocked",
                                    path=request.url.path,
                                    query_preview=truncated,
                                    trace_id=getattr(request.state, "trace_id", None),
                                )
                                return JSONResponse(
                                    status_code=400,
                                    content={
                                        "error": "Request blocked: potential prompt injection detected."
                                    },
                                )

                        if guard_result.redacted_pii:
                            payload["message"] = guard_result.sanitized_text
                            log.info("gateway.pii_redacted", path=request.url.path)
                            new_bytes = json.dumps(payload).encode("utf-8")
                            request._body = new_bytes
            except Exception as exc:
                log.warning("gateway.prompt_guard_error", error=str(exc))

        return await call_next(request)
