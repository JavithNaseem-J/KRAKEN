import logging
import re
import sys
from typing import Any

import structlog

_SENSITIVE_LOG_KEYS = frozenset(
    {
        "authorization",
        "body",
        "content",
        "description",
        "error",
        "evidence",
        "exception",
        "file_bytes",
        "file_name",
        "filename",
        "message",
        "message_preview",
        "password",
        "path",
        "payload",
        "query",
        "query_preview",
        "reason",
        "reasoning",
        "result",
        "secret",
        "stack",
        "text",
        "token",
        "upstream",
        "url",
        "user_email",
        "user_name",
    }
)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
_SECRET_RE = re.compile(r"(?i)(bearer\s+|(?:api[_-]?key|secret|token|password)\s*[:=]\s*)[^\s,;]+")


def redact_log_text(value: str) -> str:
    """Remove common personal data and credential shapes from diagnostic text."""
    value = _EMAIL_RE.sub("[REDACTED_PII]", value)
    value = _IP_RE.sub("[REDACTED_PII]", value)
    value = _SSN_RE.sub("[REDACTED_PII]", value)
    value = _CARD_RE.sub("[REDACTED_PII]", value)
    return _SECRET_RE.sub("[REDACTED_SECRET]", value)


def redact_structured_event(logger: Any, method_name: str, event_dict: Any) -> Any:
    """Structlog processor that keeps operational metadata but drops visitor content."""
    if not isinstance(event_dict, dict):
        return event_dict

    def clean(key: str, value: Any) -> Any:
        normalized = key.lower()
        if normalized != "event" and (
            normalized in _SENSITIVE_LOG_KEYS
            or normalized.endswith("_url")
            or any(part in normalized for part in ("api_key", "credential", "upload"))
        ):
            if (
                normalized == "error"
                and isinstance(value, str)
                and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", value)
            ):
                return value
            return "[REDACTED]"
        if isinstance(value, dict):
            return {
                nested_key: clean(str(nested_key), nested_value)
                for nested_key, nested_value in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [clean(key, item) for item in value]
        if isinstance(value, str):
            return redact_log_text(value)
        return value

    return {key: clean(str(key), value) for key, value in event_dict.items()}


def summarize_audit_data(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Retain only non-content action metadata for the bounded audit trail."""
    if value is None:
        return None
    summary: dict[str, Any] = {"fields": sorted(str(key) for key in value)}
    for key in ("action", "success", "simulated", "status", "ticket_id"):
        item = value.get(key)
        if isinstance(item, (bool, int, float)):
            summary[key] = item
        elif isinstance(item, str):
            summary[key] = redact_log_text(item)[:128]
    return summary


def safe_remove_processors_meta(logger: Any, method_name: str, event_dict: Any) -> Any:
    """Safe wrapper around structlog remove_processors_meta to prevent tuple mutation errors."""
    if isinstance(event_dict, dict):
        event_dict.pop("_record", None)
        event_dict.pop("_from_structlog", None)
        return event_dict
    if isinstance(event_dict, tuple):
        try:
            d = dict(event_dict)
            d.pop("_record", None)
            d.pop("_from_structlog", None)
            return d
        except Exception:
            return {}
    return event_dict


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "console",  # "json" | "console"
    service: str = "kraken",
) -> None:
    """
    Configure structlog for the calling service process.

    Args:
        log_level:  Minimum log level (DEBUG, INFO, WARNING, ERROR).
        log_format: "json" for structured JSON (prod) or "console" for colored (dev).
        service:    Service name added to every log line.
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
        redact_structured_event,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    if log_format == "json":
        formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                safe_remove_processors_meta,
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=shared_processors,  # type: ignore[arg-type]
        )
    else:
        formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                safe_remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            foreign_pre_chain=shared_processors,  # type: ignore[arg-type]
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionRenderer(),
            redact_structured_event,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
