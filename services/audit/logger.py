"""
Structlog configuration — call configure_logging() once per process in lifespan().

Produces:
  - JSON output in production (LOG_FORMAT=json)
  - Colored console output in development (LOG_FORMAT=console, the default)

All services should call this in their lifespan to get consistent structured logs
with timestamp, log level, service name, and caller info.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "console",  # "json" | "console"
    service: str = "akea",
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
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    if log_format == "json":
        formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=shared_processors,
        )
    else:
        formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            foreign_pre_chain=shared_processors,
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
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
