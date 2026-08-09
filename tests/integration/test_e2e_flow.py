"""
End-to-end integration tests for AKEA microservices.
Verifies request flow across API Gateway, Orchestrator, Action, and Audit services.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from services.action.main import app as action_app
from services.gateway.main import app as gateway_app
from services.orchestrator.main import app as orchestrator_app


@pytest.fixture
def integration_clients():
    """Setup FastAPI TestClients for gateway, orchestrator, and action services."""
    with (
        TestClient(gateway_app) as gw_client,
        TestClient(orchestrator_app) as orch_client,
        TestClient(action_app) as action_client,
    ):
        yield {
            "gateway": gw_client,
            "orchestrator": orch_client,
            "action": action_client,
        }


class TestE2EFlow:
    def test_gateway_liveness_and_readiness(self, integration_clients) -> None:
        client = integration_clients["gateway"]
        res_health = client.get("/health")
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "ok"

    def test_gateway_to_orchestrator_flow(self, integration_clients) -> None:
        gw_client = integration_clients["gateway"]

        mock_query_response = {
            "session_id": "integration-sess-1",
            "answer": "Password reset steps for GlobalProtect VPN...",
            "action_taken": "auto_respond",
            "confidence": 0.95,
            "reasoning": "Answer found in SLA documentation.",
            "evidence": ["VPN SLA Section 4"],
            "execution_time_sec": 0.25,
        }

        with patch("services.gateway.main._proxy") as mock_proxy:
            mock_proxy.return_value = JSONResponse(content=mock_query_response, status_code=200)

            res = gw_client.post(
                "/v1/run",
                json={
                    "session_id": "integration-sess-1",
                    "user_id": "alice",
                    "message": "How do I reset my VPN password?",
                },
                headers={"X-API-Key": "dev-key-alice-longer-secure-key"},
            )
            assert res.status_code == 200
            assert res.json()["action_taken"] == "auto_respond"
            assert "VPN" in res.json()["answer"]
