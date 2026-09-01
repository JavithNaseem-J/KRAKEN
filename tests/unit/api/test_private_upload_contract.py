from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api import gateway
from src.utils.knowledge.ingest import (
    cleanup_expired_private_points,
    ingest_uploaded_file_async,
)
from src.utils.knowledge.retriever import KnowledgeRetriever
from src.utils.logging import redact_structured_event, summarize_audit_data
from src.utils.models.knowledge import KnowledgeSource, RetrievalRequest


def test_logs_and_audits_exclude_upload_content_paths_and_pii() -> None:
    event = redact_structured_event(
        None,
        "error",
        {
            "event": "upload.failed",
            "query_preview": "private prompt",
            "filename": "C:\\Users\\visitor\\private.txt",
            "client_ip": "203.0.113.42",
            "actor": "visitor@example.com",
        },
    )
    assert event["event"] == "upload.failed"
    assert event["query_preview"] == "[REDACTED]"
    assert event["filename"] == "[REDACTED]"
    assert event["client_ip"] == "[REDACTED_PII]"
    assert event["actor"] == "[REDACTED_PII]"

    summary = summarize_audit_data(
        {
            "description": "Contact visitor@example.com about C:\\private\\notes.txt",
            "evidence": "raw upload text",
        }
    )
    assert summary == {"fields": ["description", "evidence"]}


@pytest.mark.asyncio
async def test_upload_ingestion_marks_private_untrusted_scope() -> None:
    class Embedder:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1] * 384 for _ in texts]

    class Client:
        points: list[Any] = []

        async def upsert(self, *, collection_name: str, points: list[Any]) -> None:
            self.points = points

    client = Client()
    count = await ingest_uploaded_file_async(
        client=client,  # type: ignore[arg-type]
        embedder=Embedder(),  # type: ignore[arg-type]
        filename="notes.md",
        file_bytes=b"VPN troubleshooting evidence",
        public_session_id="private-session",
        expires_at=12345.0,
    )

    payload = client.points[0].payload
    assert count == 1
    assert payload["scope"] == "private-session"
    assert payload["expires_at"] == 12345.0
    assert payload["untrusted_evidence"] is True


@pytest.mark.asyncio
async def test_private_upload_cannot_be_retrieved_by_another_session() -> None:
    hit = SimpleNamespace(
        id="private-point",
        score=0.99,
        payload={
            "content": "Private launch code alpha",
            "source": "faq",
            "document_id": "private.md",
            "scope": "session-a",
            "allowed_roles": ["public"],
            "collection_version": "v2",
            "dataset_generation": "northstar-v1",
            "untrusted_evidence": True,
            "metadata": {},
        },
    )
    client = AsyncMock()
    client.query_points.return_value = SimpleNamespace(points=[hit])
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1] * 384
    retriever = KnowledgeRetriever(client=client, embedder=embedder)

    own_result = await retriever.retrieve(
        RetrievalRequest(
            query="Private launch code alpha",
            sources=[KnowledgeSource.FAQ],
            session_id="session-a",
            user_role="end_user",
        )
    )
    other_result = await retriever.retrieve(
        RetrievalRequest(
            query="Private launch code alpha",
            sources=[KnowledgeSource.FAQ],
            session_id="session-b",
            user_role="end_user",
        )
    )

    assert own_result.total_retrieved == 1
    assert other_result.total_retrieved == 0


@pytest.mark.asyncio
async def test_expired_private_vectors_are_deleted() -> None:
    client = AsyncMock()
    client.scroll.return_value = ([SimpleNamespace(id="expired-point")], None)

    assert await cleanup_expired_private_points(client) == 1
    assert client.delete.await_count == 1
    assert client.delete.await_args.kwargs["points_selector"].points == ["expired-point"]


def test_gateway_enforces_upload_type_size_and_count(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict[str, Any]] = []

    async def fake_internal_request(*args: Any, **kwargs: Any) -> httpx.Response:
        captured.append(kwargs)
        return httpx.Response(
            200,
            json={"status": "success", "filename": "notes.md", "chunks_ingested": 1},
        )

    monkeypatch.setattr(gateway, "internal_request", fake_internal_request)
    client = TestClient(gateway.app)
    session = client.post("/v1/session").json()
    headers = {"X-CSRF-Token": session["csrf_token"]}

    assert (
        client.post(
            "/v1/knowledge/upload",
            files={"file": ("bad.exe", b"MZ", "application/octet-stream")},
            headers=headers,
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/v1/knowledge/upload",
            files={"file": ("bad.pdf", b"not pdf", "application/pdf")},
            headers=headers,
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/v1/knowledge/upload",
            files={"file": ("large.txt", b"x" * (2 * 1024 * 1024 + 1), "text/plain")},
            headers=headers,
        ).status_code
        == 413
    )

    for index in range(3):
        response = client.post(
            "/v1/knowledge/upload",
            files={"file": (f"notes-{index}.md", b"private evidence", "text/markdown")},
            headers=headers,
        )
        assert response.status_code == 200
    assert (
        client.post(
            "/v1/knowledge/upload",
            files={"file": ("fourth.md", b"private evidence", "text/markdown")},
            headers=headers,
        ).status_code
        == 429
    )
    assert captured[0]["data"]["public_session_id"] == session["session_id"]
