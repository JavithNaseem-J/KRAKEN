"""
Pre-write file backup utility.

Before any agent write is committed, this module snapshots the target file
(if it exists) into a timestamped .bak file inside the same directory.
This gives a one-step rollback path without requiring git or a database.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path


def backup_if_exists(target: Path) -> Path | None:
    """
    If `target` exists, copy it to `target.stem_<timestamp>.bak.json`.

    Args:
        target: The validated absolute path that is about to be written.

    Returns:
        Path of the backup file if one was created, else None.
    """
    if not target.exists():
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_name = f"{target.stem}_{timestamp}.bak{target.suffix}"
    backup_path = target.parent / backup_name

    shutil.copy2(target, backup_path)
    return backup_path
