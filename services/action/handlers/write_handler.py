"""
Write Action Handler — writes JSON files to the sandboxed workspace directory.

Safety guarantees (enforced in this order, every time):
  1. validate_write_target()  — path must resolve inside WORKSPACE_ROOT, extension must be .json
  2. backup_if_exists()       — snapshot current file before any overwrite
  3. Atomic write             — write to a .tmp file, then os.replace() to target
                                so a crash mid-write never leaves a corrupt file

No write can bypass these three steps. They are called directly, not via config flags.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from shared.exceptions import ActionExecutionError

from ..safety.backup import backup_if_exists
from ..safety.path_validator import (
    WORKSPACE_ROOT,
    PathTraversalError,
    atomic_write_json,
    validate_write_target,
)

log = structlog.get_logger(__name__)


def write_json_file(target_path: str, content: dict[str, Any]) -> dict[str, Any]:
    """
    Execute write_json_file action safely.

    Payload parameters:
      - target_path (str, required): Relative or absolute path inside data/workspace/
      - content (dict, required): JSON object to write

    Returns:
      dict with resolved_path, bytes_written, backup_path, success flag.
    """
    if not target_path or not isinstance(target_path, str):
        raise ActionExecutionError("write_json_file: target_path is required and must be a string.")

    if content is None or not isinstance(content, dict):
        raise ActionExecutionError(
            "write_json_file: content must be a JSON object (dict).",
            details={"received_type": type(content).__name__},
        )

    # ── Step 1: Validate path (raises on traversal or bad extension) ──────────
    resolved: Path = validate_write_target(target_path)

    # ── Step 2: Backup existing file ──────────────────────────────────────────
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    resolved.parent.mkdir(parents=True, exist_ok=True)

    backup_path = backup_if_exists(resolved)
    if backup_path:
        log.info("write_handler.backup_created", backup=str(backup_path))

    # ── Step 3: Atomic write (tmp → rename) ───────────────────────────────────
    try:
        bytes_written = atomic_write_json(resolved, content)
    except (OSError, ValueError) as exc:
        raise ActionExecutionError(
            f"Failed to write '{target_path}': {exc}",
            details={"resolved_path": str(resolved)},
        ) from exc

    log.info(
        "write_handler.success",
        path=str(resolved),
        bytes=bytes_written,
        backup=str(backup_path) if backup_path else None,
    )

    return {
        "resolved_path": str(resolved),
        "bytes_written": bytes_written,
        "backup_path": str(backup_path) if backup_path else None,
        "success": True,
    }
