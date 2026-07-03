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

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import structlog

from shared.exceptions import ActionExecutionError
from ..safety.path_validator import WORKSPACE_ROOT, validate_write_target
from ..safety.backup import backup_if_exists

log = structlog.get_logger(__name__)


def write_json_file(target_path: str, content: dict[str, Any]) -> dict[str, Any]:
    """
    Write content as a JSON file inside the workspace sandbox.

    Args:
        target_path: Relative path within WORKSPACE_ROOT (e.g. "ticket_update.json").
        content:     Dict to serialise as JSON.

    Returns:
        Dict with: resolved_path, backup_path (or None), bytes_written.

    Raises:
        PathTraversalError:    Path escapes workspace (from validate_write_target).
        InvalidExtensionError: Extension is not .json (from validate_write_target).
        ActionExecutionError:  Any I/O failure during write.
    """
    if not isinstance(content, dict):
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
        json_bytes = json.dumps(content, indent=2, ensure_ascii=False).encode("utf-8")

        # Write to a temp file in the same directory to ensure same-filesystem rename
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=resolved.parent,
            prefix=".tmp_",
            suffix=".json",
        )
        try:
            with os.fdopen(tmp_fd, "wb") as f:
                f.write(json_bytes)
            os.replace(tmp_path, resolved)   # Atomic on POSIX; best-effort on Windows
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    except (OSError, ValueError) as exc:
        raise ActionExecutionError(
            f"Failed to write '{target_path}': {exc}",
            details={"resolved_path": str(resolved)},
        ) from exc

    log.info(
        "write_handler.success",
        path=str(resolved),
        bytes=len(json_bytes),
        backup=str(backup_path) if backup_path else None,
    )

    return {
        "resolved_path": str(resolved),
        "bytes_written":  len(json_bytes),
        "backup_path":    str(backup_path) if backup_path else None,
        "success":        True,
    }
