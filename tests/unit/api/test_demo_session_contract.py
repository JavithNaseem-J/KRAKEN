from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.api.gateway import _proxy, app
from src.utils.config import Settings
from src.utils.demo_sessions import DemoSessionError, DemoSessionExpiredError, DemoSessionManager
from src.utils.models.demo import CapabilityState, CapabilityStatus, ReadinessResponse


def test_frontend_source_has_no_compiled_privileged_credentials() -> None:
    persona_source = Path("frontend-react/src/context/PersonaContext.tsx").read_text(
        encoding="utf-8"
    )
    assert "VITE_API_KEY" not in persona_source
    assert "dev-key-analyst-default" not in persona_source
    assert "dev-key-admin-default" not in persona_source


def test_demo_session_bootstrap_sets_signed_cookie() -> None:
    client = TestClient(app)
    response = client.post("/v1/demo/session")

    assert response.status_code == 201
    body = response.json()
    assert body["demo_mode"] is True
    assert body["expires_at"]
    assert body["csrf_token"]
    assert "kraken_demo_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_session_owned_resource_rejects_other_session() -> None:
    first = TestClient(app)
    second = TestClient(app)
    first_session = first.post("/v1/demo/session").json()
    second.post("/v1/demo/session")
    response = second.get(f"/v1/demo/sessions/{first_session['session_id']}")

    assert response.status_code == 404


def test_expired_session_is_rejected() -> None:
    clock = SimpleNamespace(now=1_000.0)
    manager = DemoSessionManager(
        Settings(
            environment="test",
            hitl_service_token="test-hitl-token-0123456789abcdef0123456789",
            demo_session_secret="test-demo-secret-0123456789abcdef0123456789",
            demo_session_ttl_seconds=60,
        ),
        clock=lambda: clock.now,
    )
    _, cookie = manager.create()
    clock.now += 61

    with pytest.raises(DemoSessionExpiredError):
        manager.resolve(cookie)


def test_modified_signature_and_query_limit_are_rejected() -> None:
    manager = DemoSessionManager(
        Settings(
            environment="test",
            hitl_service_token="test-hitl-token-0123456789abcdef0123456789",
            demo_session_secret="test-demo-secret-0123456789abcdef0123456789",
            demo_query_limit=2,
        )
    )
    _, cookie = manager.create()
    with pytest.raises(DemoSessionError, match="Invalid demo session"):
        manager.resolve(cookie[:-1] + ("A" if cookie[-1] != "A" else "B"))
    assert manager.check_query_limit("198.51.100.1")[:2] == (True, 1)
    assert manager.check_query_limit("198.51.100.1")[:2] == (True, 0)
    assert manager.check_query_limit("198.51.100.1")[0] is False


def test_csrf_persona_reset_and_role_header_are_server_owned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Limiter:
        async def check(self, _: str) -> tuple[bool, int, int]:
            return True, 19, 0

    async def echo_proxy(
        request: object, upstream_url: str, body: dict, **_: object
    ) -> JSONResponse:
        return JSONResponse(body)

    app.state.limiter = Limiter()
    monkeypatch.setattr("src.api.gateway._proxy", echo_proxy)
    client = TestClient(app)
    session = client.post("/v1/demo/session").json()

    denied = client.post("/v1/demo/persona", json={"persona": "admin", "csrf_token": "x" * 16})
    assert denied.status_code == 403
    changed = client.post(
        "/v1/demo/persona",
        json={"persona": "admin", "csrf_token": session["csrf_token"]},
    )
    assert changed.status_code == 200

    echoed = client.post(
        "/v1/run",
        json={"message": "How do I use VPN?", "session_id": "browser-chosen"},
        headers={"X-CSRF-Token": session["csrf_token"], "X-Operator-Role": "end_user"},
    )
    assert echoed.json()["metadata"]["operator_role"] == "admin"
    assert echoed.json()["metadata"]["execution_id"]
    assert echoed.json()["user_id"] == "admin"
    assert echoed.json()["session_id"] == session["session_id"]

    reset = client.post("/v1/demo/session/reset", json={"csrf_token": session["csrf_token"]})
    assert reset.status_code == 200
    assert reset.json()["session_id"] != session["session_id"]


def test_readiness_reports_required_provider_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def degraded(_: object) -> ReadinessResponse:
        names = {
            "groq",
            "qdrant_storage",
            "qdrant_inference",
            "redis",
            "postgres",
            "semantic_cache",
            "hitl_checkpoints",
        }
        return ReadinessResponse(
            status=CapabilityState.DEGRADED,
            capabilities={name: CapabilityStatus(state=CapabilityState.DEGRADED) for name in names},
        )

    monkeypatch.setattr("src.api.gateway._probe_runtime_capabilities", degraded)
    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert set(body["capabilities"]) >= {
        "groq",
        "qdrant_storage",
        "qdrant_inference",
        "redis",
        "postgres",
        "semantic_cache",
        "hitl_checkpoints",
    }


def test_proxy_preserves_server_validated_actor() -> None:
    upstream = MagicMock()
    upstream.status_code = 200
    upstream.json.return_value = {"ok": True}
    http = MagicMock()
    http.post = AsyncMock(return_value=upstream)
    request = SimpleNamespace(
        headers={},
        state=SimpleNamespace(user_id="anonymous"),
        app=SimpleNamespace(state=SimpleNamespace(http=http)),
    )
    body = {"user_id": "alice", "message": "status"}

    response = asyncio.run(_proxy(request, "http://unregistered.internal/run", body))

    assert response.status_code == 200
    assert http.post.await_args.kwargs["json"]["user_id"] == "alice"


def test_status_poll_is_read_only_and_bound_to_signed_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_urls: list[str] = []

    async def fake_internal_request(method: str, url: str, **_: Any) -> httpx.Response:
        requested_urls.append(f"{method} {url}")
        return httpx.Response(200, json={"status": "running", "session_id": "server-owned"})

    monkeypatch.setattr("src.api.gateway.internal_request", fake_internal_request)
    client = TestClient(app)
    session = client.post("/v1/demo/session").json()
    response = client.get("/v1/demo/status")

    assert response.status_code == 200
    assert requested_urls == [
        f"GET {app.state.demo_sessions.settings.orchestrator_url}/status/{session['session_id']}"
    ]
