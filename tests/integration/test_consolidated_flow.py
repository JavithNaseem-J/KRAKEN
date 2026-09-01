"""
Integration gate for the consolidated KRAKEN runtime.

Boots the single gateway app (``src.api.gateway:app``) with REAL lifespans via
TestClient — every subsystem lifespan runs, initializing real app.state
(approval queue, audit store, memory stores, knowledge retriever, agent graph).

Offline by construction:
  - Redis is fakeredis (shared FakeServer).
  - Postgres is absent: MemorySaver checkpointer, in-memory approval map,
    degraded audit/memory stores (fail-open by design).
  - Qdrant is the in-memory client; the embedder is the zero-vector fallback.
  - The LLM is mocked at ``get_llm`` in every node that uses it.

Run with:  pytest tests/integration -m integration
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import fakeredis
import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

API_KEY = "itest-public-key-0123456789abcdef"
AUTH = {"X-API-Key": API_KEY}


# ── Fake LLM (mocked at get_llm) ──────────────────────────────────────────────
class _LLMScript:
    """Per-test scripted LLM behaviour; tests pick a script before each request."""

    def __init__(self) -> None:
        self.decision_payload: dict[str, Any] = {}
        self.answer = "Mocked final answer."

    def set_safe(self) -> None:
        self.decision_payload = {
            "selected_action": "auto_respond",
            "selected_actions": [],
            "action_payload": {
                "ticket_id": None,
                "response_text": "Mocked safe response backed by the knowledge base.",
                "evidence": "Mock evidence cited verbatim from a knowledge chunk.",
            },
            "evidence": "Mock evidence cited verbatim from a knowledge chunk.",
            "explanation": "Mocked step-by-step explanation.",
        }
        self.answer = "Mocked SAFE answer composed by the responder."

    def set_critical(self) -> None:
        self.decision_payload = {
            "selected_action": "escalate",
            "selected_actions": [],
            "action_payload": {
                "ticket_id": "TCK-24001",
                "reason": "Critical RCE vulnerability confirmed on TCK-24001.",
            },
            "evidence": "CVE-2026-0001 remote code execution confirmed in TCK-24001.",
            "explanation": "Critical vulnerability requires senior security review.",
        }
        self.answer = "Mocked post-approval answer confirming execution."


SCRIPT = _LLMScript()


class _FakeStructuredLLM:
    async def ainvoke(self, messages: Any, **kwargs: Any) -> Any:
        from src.agent.nodes.decider import DecisionOutput

        return DecisionOutput(**SCRIPT.decision_payload)


class _FakeLLM:
    def with_structured_output(self, schema: Any, method: str | None = None, **kwargs: Any) -> Any:
        return _FakeStructuredLLM()

    async def ainvoke(self, messages: Any, **kwargs: Any) -> AIMessage:
        return AIMessage(content=SCRIPT.answer)


def _fake_get_llm() -> _FakeLLM:
    return _FakeLLM()


def _make_redis_factory(server: fakeredis.FakeServer):
    def factory(url: str, **kwargs: Any) -> fakeredis.aioredis.FakeRedis:
        return fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)

    return factory


# ── Fixture: consolidated app with real lifespans ─────────────────────────────
@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    from src.api.gateway import app

    SCRIPT.set_safe()
    server = fakeredis.FakeServer()
    with (
        patch(
            "src.utils.http_client.create_async_redis_client",
            _make_redis_factory(server),
        ),
        patch("src.agent.nodes.decider.get_llm", _fake_get_llm),
        patch("src.agent.nodes.reasoner.get_llm", _fake_get_llm),
        patch("src.agent.nodes.responder.get_llm", _fake_get_llm),
        TestClient(app) as c,
    ):
        c.timeout = 60.0
        yield c


def _start_public_session_as(client: TestClient, persona: str) -> dict[str, Any]:
    session_response = client.post("/v1/session")
    assert session_response.status_code == 201, session_response.text
    session = session_response.json()
    transition = client.post(
        "/v1/session/persona",
        json={"persona": persona, "csrf_token": session["csrf_token"]},
    )
    assert transition.status_code == 200, transition.text
    return session


@pytest.mark.integration
class TestConsolidatedFlow:
    def test_health_ok_and_ready_names_all_subsystems(self, client: TestClient) -> None:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        ready = client.get("/ready", headers=AUTH)
        assert ready.status_code == 503, ready.text
        body = ready.json()
        assert body["status"] == "degraded"
        assert set(body["capabilities"]) == {
            "synthetic_dataset",
            "groq",
            "qdrant_storage",
            "qdrant_inference",
            "redis",
            "postgres",
            "semantic_cache",
            "hitl_checkpoints",
        }

    def test_run_happy_path_returns_query_response(self, client: TestClient) -> None:
        SCRIPT.set_safe()
        resp = client.post(
            "/v1/run",
            json={
                "message": "How do I reset my VPN password?",
                "session_id": "itest-safe-1",
                "user_id": "synthetic-operator-1",
            },
            headers=AUTH,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "answer" in data
        assert data["session_id"] == "itest-safe-1"
        assert data["action_taken"] == "auto_respond"
        assert data["action_result"]["success"] is True

    def test_hitl_approve_path_resumes_graph(self, client: TestClient) -> None:
        SCRIPT.set_critical()
        session = _start_public_session_as(client, "tier1_analyst")
        session_headers = {"X-CSRF-Token": session["csrf_token"]}
        with patch("src.api.action.execute_escalate") as handler:
            resp = client.post(
                "/v1/run",
                json={
                    "message": "Please escalate ticket TCK-24001, critical RCE confirmed.",
                    "session_id": "browser-value-is-not-trusted",
                },
                headers=session_headers,
            )
            assert resp.status_code == 200, resp.text
            paused = resp.json()
            assert paused.get("status") == "pending_approval"
            approval_id = paused["approval_id"]
            assert approval_id

            details = client.get(f"/approve/{approval_id}/details")
            assert details.status_code == 200, details.text
            payload = details.json()
            assert payload["action_name"] == "escalate"
            assert payload["payload"]["ticket_id"] == "TCK-24001"
            assert payload["synthetic"] is True
            assert payload["dataset_generation"] == "northstar-v1"
            assert payload["csrf_token"]

            transition = client.post(
                "/v1/session/persona",
                json={
                    "persona": "incident_commander",
                    "csrf_token": session["csrf_token"],
                },
            )
            assert transition.status_code == 200, transition.text

            decision = client.post(
                f"/approve/{approval_id}/decision",
                data={
                    "decision": "approve",
                    "csrf_token": payload["csrf_token"],
                    "session_csrf_token": session["csrf_token"],
                },
                headers={"Accept": "application/json"},
            )
            assert decision.status_code == 200, decision.text
            final = decision.json()["agent_response"]
            assert final["action_result"]["success"] is True
            assert final["action_result"]["result"]["ticket_id"] == "TCK-24001"
            handler.assert_not_called()
        client.cookies.clear()

    def test_hitl_reject_path_cancels_action(self, client: TestClient) -> None:
        SCRIPT.set_critical()
        session = _start_public_session_as(client, "tier1_analyst")
        session_headers = {"X-CSRF-Token": session["csrf_token"]}
        with patch("src.api.action.execute_escalate") as handler:
            resp = client.post(
                "/v1/run",
                json={
                    "message": "Escalate ticket TCK-24001 immediately.",
                    "session_id": "browser-value-is-not-trusted",
                },
                headers=session_headers,
            )
            assert resp.status_code == 200, resp.text
            paused = resp.json()
            assert paused.get("status") == "pending_approval"
            approval_id = paused["approval_id"]

            details = client.get(f"/approve/{approval_id}/details")
            assert details.status_code == 200, details.text
            csrf = details.json()["csrf_token"]

            transition = client.post(
                "/v1/session/persona",
                json={
                    "persona": "incident_commander",
                    "csrf_token": session["csrf_token"],
                },
            )
            assert transition.status_code == 200, transition.text

            decision = client.post(
                f"/approve/{approval_id}/decision",
                data={
                    "decision": "reject",
                    "csrf_token": csrf,
                    "session_csrf_token": session["csrf_token"],
                },
                headers={"Accept": "application/json"},
            )
            assert decision.status_code == 200, decision.text
            final = decision.json()["agent_response"]
            assert final["action_result"]["cancelled"] is True
            handler.assert_not_called()
        client.cookies.clear()

    def test_run_stream_ends_with_done_event(self, client: TestClient) -> None:
        SCRIPT.set_safe()
        events: list[dict[str, Any]] = []
        with client.stream(
            "POST",
            "/v1/run/stream",
            json={
                "message": "How do I set up two-factor authentication?",
                "session_id": "itest-stream-1",
                "user_id": "synthetic-operator-1",
            },
            headers=AUTH,
        ) as resp:
            assert resp.status_code == 200
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[len("data: ") :]))

        assert events, "no SSE events received"
        nodes = [e.get("node") for e in events]
        assert "done" in nodes
        done = events[-1]
        assert done["node"] == "done"
        assert done["status"] == "end"
        assert "response" in done
        assert done["response"]["answer"]
        assert done["response"]["session_id"] == "itest-stream-1"

    def test_run_stream_invalid_payload_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/run/stream",
            json={"message": "hello", "session_id": "bad session id!"},
            headers=AUTH,
        )
        assert resp.status_code == 422
        assert "error" in resp.json()
