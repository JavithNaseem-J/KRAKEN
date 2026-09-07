from __future__ import annotations

import os
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from src.utils.models.public import BuildInfo

_DEVELOPMENT_SHA = "0" * 40
_DEVELOPMENT_BUILD_TIME = "1970-01-01T00:00:00Z"
_DEFAULT_BUILD_TIME_FILE = Path("/app/build-time.txt")


def application_version() -> str:
    try:
        return version("kraken")
    except PackageNotFoundError:
        return "0.1.0"


def load_build_info(environment: str) -> BuildInfo:
    commit_sha = (
        os.getenv("KRAKEN_COMMIT_SHA", "").strip() or os.getenv("RENDER_GIT_COMMIT", "").strip()
    )
    build_time = os.getenv("KRAKEN_BUILD_TIME", "").strip() or _read_build_time()

    if environment == "prod":
        if not commit_sha or commit_sha == _DEVELOPMENT_SHA:
            raise ValueError(
                "Production build identity requires KRAKEN_COMMIT_SHA or RENDER_GIT_COMMIT."
            )
        if not build_time or build_time == _DEVELOPMENT_BUILD_TIME:
            raise ValueError("Production build identity requires KRAKEN_BUILD_TIME.")
    else:
        commit_sha = commit_sha or _DEVELOPMENT_SHA
        build_time = build_time or _DEVELOPMENT_BUILD_TIME

    return BuildInfo(
        service="kraken",
        application_version=application_version(),
        commit_sha=commit_sha,
        build_time=_parse_build_time(build_time),
    )


def _read_build_time() -> str:
    configured_path = os.getenv("KRAKEN_BUILD_TIME_FILE", "").strip()
    path = Path(configured_path) if configured_path else _DEFAULT_BUILD_TIME_FILE
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _parse_build_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("build_time must be an ISO-8601 timestamp") from exc
