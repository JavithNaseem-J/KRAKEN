"""
Base loader module providing container-safe data path resolution
and generic file loading logic for knowledge sources.
"""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)


def resolve_data_dir(source_name: str) -> Path:
    """
    Resolve data directory for a given knowledge source name ('tickets', 'sla', 'faq').
    Checks KNOWLEDGE_DATA_DIR env var first, then repo-root path, and falls back to container path.
    """
    if custom := os.getenv("KNOWLEDGE_DATA_DIR"):
        return Path(custom) / source_name

    # Try local repo root path (parents[3] when in services/knowledge/loaders/base.py)
    repo_path = Path(__file__).resolve().parents[3] / "data" / "knowledge" / source_name
    if repo_path.exists():
        return repo_path

    # Fallback for Docker container layout (/app/data/knowledge/<source_name>)
    container_path = Path("/app/data/knowledge") / source_name
    return container_path


def load_structured_chunks(
    data_dir: Path,
    allowed_suffixes: set[str],
    record_to_text: Callable[[dict[str, Any]], str],
    id_prefix: str,
) -> list[dict[str, Any]]:
    """
    Generic loader for JSON and CSV structured knowledge files.
    """
    if not data_dir.exists():
        log.warning("loader.dir_missing", dir=str(data_dir))
        return []

    files = [p for p in data_dir.glob("*") if p.suffix.lower() in allowed_suffixes]
    if not files:
        log.warning("loader.no_files_found", dir=str(data_dir), suffixes=list(allowed_suffixes))
        return []

    chunks: list[dict[str, Any]] = []
    for file_path in sorted(files):
        try:
            records: list[dict[str, Any]] = []
            if file_path.suffix.lower() == ".json":
                content = json.loads(file_path.read_text(encoding="utf-8"))
                records = content if isinstance(content, list) else [content]
            elif file_path.suffix.lower() == ".csv":
                with file_path.open(encoding="utf-8") as f:
                    records = list(csv.DictReader(f))

            for idx, item in enumerate(records):
                if text := record_to_text(item):
                    doc_id = item.get("id") or f"{id_prefix}_{file_path.stem}_{idx + 1}"
                    chunks.append(
                        {
                            "id": doc_id,
                            "document": text,
                            "metadata": {
                                "source": id_prefix,
                                "file": file_path.name,
                                "raw": item,
                            },
                        }
                    )
        except Exception as exc:
            log.error("loader.file_error", file=file_path.name, error=str(exc))

    log.info("loader.complete", source=id_prefix, total_chunks=len(chunks))
    return chunks
