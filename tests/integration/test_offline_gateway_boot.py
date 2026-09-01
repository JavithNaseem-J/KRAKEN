from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import offline_gateway_lifespan_patches


@pytest.mark.integration
def test_gateway_full_lifespan_boots_offline_without_model_downloads() -> None:
    from src.api.gateway import app

    with offline_gateway_lifespan_patches() as calls, TestClient(app) as client:
        response = client.get(
            "/health",
            headers={"X-API-Key": "itest-public-key-0123456789abcdef"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "gateway"}
    assert calls["get_embedder"] >= 1
