from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api import gateway
from src.utils.config import Settings


def test_spa_root_and_deep_links_share_api_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<main>KRAKEN</main>", encoding="utf-8")
    monkeypatch.setattr(gateway, "FRONTEND_DIST", dist)
    client = TestClient(gateway.app)

    assert client.get("/").text == "<main>KRAKEN</main>"
    assert client.get("/sessions/history").text == "<main>KRAKEN</main>"
    assert client.get("/health").json()["service"] == "gateway"
    assert client.get("/v1/not-a-route").status_code == 401


def test_production_rejects_shipped_or_missing_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment="prod",
            hitl_service_token="test-hitl-token-0123456789abcdef0123456789",
            public_cookie_secure=True,
        )


def test_runtime_manifests_define_one_secret_free_service() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    blueprint = Path("render.yaml").read_text(encoding="utf-8")

    assert "FROM node:" in dockerfile
    assert "/frontend/dist/ /app/frontend-react/dist/" in dockerfile
    assert "HITL_SERVICE_TOKEN=" not in dockerfile
    assert blueprint.count("- type: web") == 1
    assert "env: static" not in blueprint
    assert "VITE_API_KEY" not in blueprint
    assert "value: prod" in blueprint
