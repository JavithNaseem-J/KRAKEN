"""
Notifier — prints a human-readable approval notice to the terminal.

Kept separate from queue.py so the terminal output format can be
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
    """
    Print an approval URL to the terminal and return the URL.
    Called immediately after a new approval is enqueued.
    """
    url = f"{approval_base_url.rstrip('/')}/approve/{approval_id}"

    notice = f"""
{"═" * 62}
  ⚠️  HUMAN APPROVAL REQUIRED
{"─" * 62}
  Action   : {action_name}
  Open URL : {url}
  Expires  : in {timeout_minutes} minutes
{"─" * 62}
  Approve or reject at the URL above.
{"═" * 62}
"""
    print(notice, flush=True)
    log.warning(
        "approval.notice",
        approval_id=approval_id,
        action=action_name,
        url=url,
    )
    return url
