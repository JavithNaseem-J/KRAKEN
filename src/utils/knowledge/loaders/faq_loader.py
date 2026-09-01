from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import structlog

from src.utils.models.knowledge import FAQDocument

from .base import resolve_data_dir

log = structlog.get_logger(__name__)

# Chunking constants
MAX_CHUNK_SIZE = 1200  # characters — balances section continuity vs. embedding model context

FAQ_DIR = resolve_data_dir("faq")
_METADATA_PATTERN = re.compile(r"^<!-- kraken-metadata: (\{.*\}) -->\s*", re.DOTALL)


def _clean_text(text: str) -> str:
    """Normalize excess whitespace and line breaks."""
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _chunk_markdown(text: str, max_chunk_size: int = MAX_CHUNK_SIZE) -> list[tuple[str, str]]:
    """
    Split markdown text by headers (#, ##, ###) while preserving section titles and tables.
    Returns a list of (chunk_content, section_title) tuples.
    """
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title = "General"
    current_lines: list[str] = []

    header_regex = re.compile(r"^(#{1,3})\s+(.+)$")

    for line in lines:
        match = header_regex.match(line)
        if match:
            if current_lines and any(line_item.strip() for line_item in current_lines):
                sections.append((current_title, current_lines))
                current_lines = []
            current_title = match.group(2).strip()
            current_lines.append(line)
        else:
            current_lines.append(line)

    if current_lines and any(line_item.strip() for line_item in current_lines):
        sections.append((current_title, current_lines))

    chunks: list[tuple[str, str]] = []
    for title, sec_lines in sections:
        sec_text = "\n".join(sec_lines).strip()
        if not sec_text:
            continue

        if len(sec_text) <= max_chunk_size:
            chunks.append((sec_text, title))
        else:
            paragraphs = [p.strip() for p in re.split(r"\n{2,}", sec_text) if p.strip()]
            current_parts: list[str] = []
            current_len = 0

            for para in paragraphs:
                if current_len + len(para) + 2 > max_chunk_size and current_parts:
                    chunk_body = "\n\n".join(current_parts)
                    chunks.append((chunk_body, title))
                    current_parts = [f"### {title}\n(continued)\n\n" + para]
                    current_len = len(current_parts[0])
                else:
                    current_parts.append(para)
                    current_len += len(para) + 2

            if current_parts:
                chunks.append(("\n\n".join(current_parts), title))

    return chunks if chunks else [(_clean_text(text), "General")]


def _chunk_text(text: str, chunk_size: int = 1000) -> list[str]:
    """Split plain text or PDF text into paragraphs up to chunk_size."""
    text = _clean_text(text)
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) + 2 > chunk_size and current_parts:
            chunks.append("\n\n".join(current_parts))
            current_parts = [para]
            current_len = len(para)
        else:
            current_parts.append(para)
            current_len += len(para) + 2

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks


def _load_pdf(path: Path) -> str:
    """Extract text from PDF using pypdf."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
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


def _extract_metadata(text: str) -> tuple[str, dict[str, Any]]:
    """Read the generator's JSON metadata comment without adding a YAML dependency."""
    match = _METADATA_PATTERN.match(text)
    if not match:
        return text, {}
    try:
        metadata = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid kraken-metadata JSON comment.") from exc
    return text[match.end() :], metadata if isinstance(metadata, dict) else {}


def load_faq_chunks() -> list[dict[str, Any]]:
    """
    Load all FAQ/Policy documents and return Qdrant-ready chunk dicts with structured section metadata.

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

        if file_path.suffix.lower() == ".md":
            raw, document_metadata = _extract_metadata(_load_text(file_path))
            if not raw.strip():
                log.warning("faq_loader.empty_file", file=file_path.name)
                continue
            section_chunks = _chunk_markdown(raw)
        else:
            raw = (
                _load_pdf(file_path)
                if file_path.suffix.lower() == ".pdf"
                else _load_text(file_path)
            )
            document_metadata = {}
            if not raw.strip():
                log.warning("faq_loader.empty_file", file=file_path.name)
                continue
            section_chunks = [
                (c, file_path.stem.replace("_", " ").title()) for c in _chunk_text(raw)
            ]

        doc_id = str(
            document_metadata.get("document_id")
            or hashlib.blake2b(file_path.name.encode(), digest_size=6).hexdigest()
        )
        faq_doc = FAQDocument(
            doc_id=doc_id,
            title=file_path.stem.replace("_", " ").title(),
            content=raw[:200],
            category="policy",
        )

        for i, (chunk_text, section_title) in enumerate(section_chunks):
            chunk_id = f"faq_{doc_id}_{i:04d}"
            all_chunks.append(
                {
                    "id": chunk_id,
                    "document": chunk_text,
                    "metadata": {
                        "source": "faq",
                        "file": file_path.name,
                        "title": faq_doc.title,
                        "section_title": section_title,
                        "category": faq_doc.category,
                        "chunk_index": i,
                        "total_chunks": len(section_chunks),
                        **document_metadata,
                    },
                    "allowed_roles": document_metadata.get("allowed_roles"),
                    "untrusted_evidence": bool(document_metadata.get("untrusted_evidence", False)),
                }
            )

        log.info("faq_loader.done", file=file_path.name, chunks=len(section_chunks))

    log.info("faq_loader.complete", total_chunks=len(all_chunks), files=len(files))
    return all_chunks
