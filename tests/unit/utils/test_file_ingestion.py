from src.utils.knowledge.ingest import extract_text_from_file_bytes


def test_extract_text_from_txt_and_md():
    raw_md = b"# Confidential Incident Report\n\nExecutive Summary of Incident INC-9002."
    extracted = extract_text_from_file_bytes("report.md", raw_md)
    assert "# Confidential Incident Report" in extracted
    assert "INC-9002" in extracted


def test_extract_text_fallback():
    raw_bytes = b"Plain text log entry: Unauthorized root access attempt."
    extracted = extract_text_from_file_bytes("server.log", raw_bytes)
    assert "Unauthorized root access attempt" in extracted
