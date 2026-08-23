from __future__ import annotations

from src.utils.knowledge.loaders.faq_loader import (
    _chunk_markdown,
    _chunk_text,
    load_faq_chunks,
)


def test_chunk_markdown_headers_and_tables() -> None:
    sample_md = """# Cybersecurity Policy

## 1. Password Rules
- Minimum 16 characters.
- Passphrase recommended.

| Role | MFA Required | Session Timeout |
|---|---|---|
| Admin | FIDO2 | 15 mins |
| Analyst | Duo Push | 30 mins |

### 1.1 Password Reset
Contact the SecOps helpdesk for emergency resets.
"""
    chunks = _chunk_markdown(sample_md, max_chunk_size=500)
    assert len(chunks) >= 2

    titles = [title for _, title in chunks]
    assert any("1. Password Rules" in t for t in titles)
    assert any("1.1 Password Reset" in t for t in titles)

    # Check table is preserved intact in chunk
    table_chunk = next(c for c, _ in chunks if "| Role |" in c)
    assert "| Admin | FIDO2 | 15 mins |" in table_chunk
    assert "| Analyst | Duo Push | 30 mins |" in table_chunk


def test_chunk_text_paragraph_split() -> None:
    text = "Paragraph 1 line A.\nParagraph 1 line B.\n\nParagraph 2 line A.\n\nParagraph 3 line A."
    chunks = _chunk_text(text, chunk_size=50)
    assert len(chunks) >= 2


def test_load_faq_chunks_has_section_titles() -> None:
    chunks = load_faq_chunks()
    assert len(chunks) > 0
    for chunk in chunks:
        assert "id" in chunk
        assert "document" in chunk
        assert "metadata" in chunk
        assert chunk["metadata"]["source"] == "faq"
        assert "section_title" in chunk["metadata"]
        assert len(chunk["metadata"]["section_title"]) > 0
