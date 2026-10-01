"""Workspace location and atomic JSON storage used by the ticket adapter."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT: Path = (_PROJECT_ROOT / "data" / "workspace").resolve()


def atomic_write_json(target_path: Path | str, content: Any) -> int:
    """Replace a JSON file atomically and clean up a failed temporary write."""
    path = Path(target_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    json_bytes = json.dumps(content, indent=2, ensure_ascii=False).encode("utf-8")
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(tmp_fd, "wb") as output:
            output.write(json_bytes)
        os.replace(tmp_path, path)
        return len(json_bytes)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
