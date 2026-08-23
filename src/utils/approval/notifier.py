"""
Notifier — emits a structured approval notice via structlog.

Kept separate from queue.py so the output format can be
changed without touching Redis logic.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


def print_approval_notice(
    approval_id: str,
    action_name: str,
    approval_base_url: str,
    timeout_minutes: int = 15,
) -> str:
    """Emit a structured approval-required notice and return the URL.

    Called immediately after a new approval is enqueued. The structured log
    event carries all fields needed for alerting/routing in log aggregators.
    """
    url = f"{approval_base_url.rstrip('/')}/approve/{approval_id}"

    log.warning(
        "approval.notice_banner",
        approval_id=approval_id,
        action=action_name,
        url=url,
        expires_minutes=timeout_minutes,
    )
    return url
