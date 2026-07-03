"""
FAQ / Policy knowledge base loader.

Reads all .pdf, .md, and .txt files from data/knowledge/faq/.
Splits each document into overlapping chunks suitable for semantic search.
Returns a list of dicts ready for ChromaDB upsert.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# Chunking constants
CHUNK_SIZE    = 800   # characters — balances context vs. precision
CHUNK_OVERLAP = 100   # characters — preserves sentence continuity across boundaries

FAQ_DIR = Path(__file__).resolve().parents[4] / "data" / "knowledge" / "faq"


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping character-level chunks."""
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks


def _load_pdf(path: Path) -> str:
    """Extract text from PDF using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n\n".join(
            page.extract_text() or "" for page in reader.pages
        )
    except Exception as exc:
        log.error("faq_loader.pdf_error", path=str(path), error=str(exc))
        return ""


def _load_text(path: Path) -> str:
    """Load plain text or markdown."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        log.error("faq_loader.text_error", path=str(path), error=str(exc))
        return ""


def load_faq_chunks() -> list[dict[str, Any]]:
    """
    Load all FAQ/Policy documents and return ChromaDB-ready chunk dicts.

    Returns:
        List of dicts with keys: id, document, metadata
    """
    if not FAQ_DIR.exists():
        log.warning("faq_loader.dir_missing", path=str(FAQ_DIR))
        return []

    supported = {".pdf", ".md", ".txt"}
    files = [f for f in FAQ_DIR.iterdir() if f.suffix.lower() in supported]

    if not files:
        log.warning("faq_loader.no_files", path=str(FAQ_DIR))
        return []

    all_chunks: list[dict[str, Any]] = []

    for file_path in sorted(files):
        log.info("faq_loader.loading", file=file_path.name)

        raw = _load_pdf(file_path) if file_path.suffix.lower() == ".pdf" else _load_text(file_path)
        if not raw.strip():
            log.warning("faq_loader.empty_file", file=file_path.name)
            continue

        chunks = _chunk_text(raw)
        doc_id = hashlib.md5(file_path.name.encode()).hexdigest()[:12]

        for i, chunk in enumerate(chunks):
            chunk_id = f"faq_{doc_id}_{i:04d}"
            all_chunks.append({
                "id":       chunk_id,
                "document": chunk,
                "metadata": {
                    "source":      "faq",
                    "file":        file_path.name,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                },
            })

        log.info("faq_loader.done", file=file_path.name, chunks=len(chunks))

    log.info("faq_loader.complete", total_chunks=len(all_chunks), files=len(files))
    return all_chunks
