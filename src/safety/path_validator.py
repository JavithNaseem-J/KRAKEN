"""
Write-target path validator and atomic JSON writer.

SECURITY CONTRACT
─────────────────
WORKSPACE_ROOT is hardcoded — it is NOT read from environment variables,
command-line arguments, or any runtime configuration.

Every write target MUST pass both checks before any file is touched:
  1. The resolved absolute path starts with WORKSPACE_ROOT (no path traversal).
  2. The file extension is in ALLOWED_EXTENSIONS (.json only).

This module has zero external dependencies so it can be unit-tested in isolation.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from src.utils.exceptions import InvalidExtensionError, PathTraversalError

# ── Hardcoded constants — do NOT make these configurable ──────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # repo root
WORKSPACE_ROOT: Path = (_PROJECT_ROOT / "data" / "workspace").resolve()
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".json"})
# ─────────────────────────────────────────────────────────────────────────────


def validate_write_target(target: str) -> Path:
    """
    Validate and resolve a write target path.

    Args:
        target: Relative path string supplied by the agent
                (e.g. "ticket_update.json" or "subdir/result.json").

    Returns:
        Resolved absolute Path guaranteed to be inside WORKSPACE_ROOT.

    Raises:
        PathTraversalError:    Path escapes WORKSPACE_ROOT.
        InvalidExtensionError: Extension not in ALLOWED_EXTENSIONS.
    """
    if not target or not target.strip():
        raise PathTraversalError("Write target cannot be empty or blank.")

    # Resolve relative to workspace — this collapses any ../.. attempts
    try:
        resolved: Path = (WORKSPACE_ROOT / target).resolve()
    except (ValueError, RuntimeError) as exc:
        raise PathTraversalError(f"Cannot resolve path '{target}'.") from exc

    # ── Check 1: containment ──────────────────────────────────────────────────
    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise PathTraversalError(
            f"BLOCKED — '{target}' resolves to '{resolved}', "
            f"which is outside the allowed workspace '{WORKSPACE_ROOT}'."
        ) from exc

    # ── Check 2: extension allowlist ──────────────────────────────────────────
    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise InvalidExtensionError(
            f"BLOCKED — extension '{resolved.suffix}' is not allowed. "
            f"Only {sorted(ALLOWED_EXTENSIONS)} files may be written."
        )

    return resolved


def atomic_write_json(target_path: Path | str, content: Any) -> int:
    """
    Write content as formatted JSON to a target path atomically using a temporary file.
    Guarantees same-filesystem rename and temp file cleanup on error.
    Returns the number of bytes written.
    """
    path = Path(target_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    json_bytes = json.dumps(content, indent=2, ensure_ascii=False).encode("utf-8")

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=".tmp_",
        suffix=".json",
    )
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(json_bytes)
        os.replace(tmp_path, path)
        return len(json_bytes)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def backup_if_exists(target: Path) -> Path | None:
    """
    If `target` exists, copy it to `target.stem_<timestamp>.bak.json`.

    Args:
        target: The validated absolute path that is about to be written.

    Returns:
        Path of the backup file if one was created, else None.
    """
    import shutil
    from datetime import UTC, datetime

    if not target.exists():
        return None

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_name = f"{target.stem}_{timestamp}.bak{target.suffix}"
    backup_path = target.parent / backup_name

    shutil.copy2(target, backup_path)
    return backup_path

