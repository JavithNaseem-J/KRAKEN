from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from src.api import orchestrator
from src.utils.models.agent import QueryRequest, QueryResponse
from src.utils.semantic_cache_policy import cache_context, is_cache_eligible


class FakeCache:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.get_calls = 0
        self.put_calls = 0

    async def get(self, query: Any, context: dict[str, str]) -> dict[str, Any]:
        self.get_calls += 1
        return self.response

    async def put(
        self,
        query: Any,
        original_query: str,
        response: dict[str, Any],
        context: dict[str, str],
    ) -> None:
        self.put_calls += 1


class FakeGraph:
    streamed = False

    async def aget_state(self, _: dict[str, Any]) -> SimpleNamespace:
        return SimpleNamespace(next=[], values={})

    async def astream_events(self, *args: Any, **kwargs: Any):
        self.streamed = True
        if False:
            yield {}


@pytest.mark.asyncio
async def test_sse_cache_hit_has_explicit_hit_and_one_terminal_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached = QueryResponse(
        session_id="old-session",
        answer="Use the corporate VPN portal.",
        reasoning="Grounded response.",
        sources=["faq"],
        retrieved_chunks=[
            {
                "source": "faq",
                "content": "VPN guidance",
                "relevance_score": 0.9,
            }
        ],
    ).model_dump(mode="json")
    fake_cache = FakeCache(cached)
    fake_graph = FakeGraph()
    orchestrator.app.state.semantic_cache = fake_cache

    async def fake_get_graph(**_: Any) -> tuple[FakeGraph, dict[str, Any]]:
        return fake_graph, {}

    async def fake_cache_query(_: str) -> list[float]:
        return [0.1, 0.2]

    monkeypatch.setattr(orchestrator, "_get_graph", fake_get_graph)
    monkeypatch.setattr(orchestrator, "cache_query", fake_cache_query)

    response = await orchestrator.run_stream(
        QueryRequest(
            session_id="new-session",
            message="How do I use the VPN?",
            metadata={"operator_role": "end_user"},
        )
    )
    chunks = [chunk async for chunk in response.body_iterator]
    payload = "".join(
        chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in chunks
    )
    events = [json.loads(line[6:]) for line in payload.splitlines() if line.startswith("data: ")]

    assert [event["status"] for event in events] == ["cache_hit", "end"]
    assert sum("response" in event for event in events) == 1
    assert events[-1]["response"]["session_id"] == "new-session"
    assert events[-1]["response"]["cache"]["hit"] is True
    assert fake_graph.streamed is False


@pytest.mark.asyncio
async def test_provider_fallback_cache_entry_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached = QueryResponse(
        session_id="old-session",
        answer=(
            "The AI provider is temporarily unavailable, so KRAKEN cannot compose a "
            "grounded answer right now."
        ),
        reasoning="Reasoning is unavailable because the AI provider could not complete the request.",
        retrieved_chunks=[
            {
                "source": "faq",
                "content": "VPN guidance",
                "relevance_score": 0.9,
            }
        ],
    ).model_dump(mode="json")
    fake_cache = FakeCache(cached)
    orchestrator.app.state.semantic_cache = fake_cache

    async def fake_cache_query(_: str) -> list[float]:
        return [0.1, 0.2]

    monkeypatch.setattr(orchestrator, "cache_query", fake_cache_query)

    response, _, _ = await orchestrator._semantic_cache_lookup(
        QueryRequest(
            session_id="new-session",
            message="How do I use the VPN?",
            metadata={"operator_role": "end_user"},
        )
    )

    assert response is None
    assert fake_cache.get_calls == 1


@pytest.mark.asyncio
async def test_provider_fallback_response_is_not_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_cache = FakeCache({})
    orchestrator.app.state.semantic_cache = fake_cache

    async def fake_cache_query(_: str) -> list[float]:
        return [0.1, 0.2]

    monkeypatch.setattr(orchestrator, "cache_query", fake_cache_query)

    await orchestrator._semantic_cache_store(
        QueryRequest(
            session_id="session",
            message="How do I use the VPN?",
            metadata={"operator_role": "end_user"},
        ),
        QueryResponse(
            session_id="session",
            answer=(
                "The AI provider is temporarily unavailable, so KRAKEN cannot compose a "
                "grounded answer right now."
            ),
            reasoning="Reasoning is unavailable because the AI provider could not complete the request.",
            retrieved_chunks=[
                {
                    "source": "faq",
                    "content": "VPN guidance",
                    "relevance_score": 0.9,
                }
            ],
        ),
        None,
        cache_context({"operator_role": "end_user"}).as_payload(),
    )

    assert fake_cache.put_calls == 0


def test_mutations_and_hitl_requests_bypass_cache() -> None:
    assert is_cache_eligible("How do I connect to VPN?", {}) is True
    assert is_cache_eligible("Create a ticket for VPN", {}) is False
    assert is_cache_eligible("Check status", {"hitl_request": True}) is False


def test_private_upload_cache_scope_is_session_specific() -> None:
    context_a = cache_context(
        {
            "operator_role": "end_user",
            "demo_session_id": "session-a",
            "has_private_uploads": True,
        }
    )
    context_b = cache_context(
        {
            "operator_role": "end_user",
            "demo_session_id": "session-b",
            "has_private_uploads": True,
        }
    )

    assert context_a.scope == "session-a"
    assert context_b.scope == "session-b"
    assert context_a.as_payload() != context_b.as_payload()
