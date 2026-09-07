from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from scripts.verify_deployment import verify_deployment


class FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def opener_for(payloads: list[dict]) -> object:
    responses: Iterator[dict] = iter(payloads)

    def open_url(*args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse(next(responses))

    return open_url


def test_verifier_accepts_only_exact_healthy_revision() -> None:
    sha = "a" * 40
    report = verify_deployment(
        "https://kraken.example",
        sha,
        opener=opener_for(
            [
                {"status": "ok"},
                {"status": "ready"},
                {"commit_sha": sha},
            ]
        ),
        monotonic=lambda: 10.0,
    )

    assert report["status"] == "passed"
    assert report["observed_sha"] == sha
    assert report["attempts"] == 1


def test_verifier_reports_wrong_revision_without_leaking_response_fields() -> None:
    expected = "a" * 40
    observed = "b" * 40
    report = verify_deployment(
        "https://kraken.example",
        expected,
        timeout_seconds=0,
        opener=opener_for(
            [
                {"status": "ok", "secret": "hidden"},
                {"status": "ready", "providers": {"token": "hidden"}},
                {"commit_sha": observed, "environment": {"API_KEY": "hidden"}},
            ]
        ),
        monotonic=lambda: 10.0,
    )

    assert report["status"] == "failed"
    assert report["observed_sha"] == observed
    assert report["endpoints"]["version"]["sha_matches"] is False
    assert "hidden" not in json.dumps(report)


@pytest.mark.parametrize(
    "base_url",
    [
        "not-a-url",
        "ftp://kraken.example",
        "https://user:secret@kraken.example",
        "https://kraken.example?token=secret",
    ],
)
def test_verifier_rejects_unsafe_base_urls(base_url: str) -> None:
    with pytest.raises(ValueError):
        verify_deployment(base_url, "a" * 40)


def test_verifier_rejects_short_sha() -> None:
    with pytest.raises(ValueError, match="full 40-character"):
        verify_deployment("https://kraken.example", "abc123")


def test_verifier_retries_read_timeouts_without_exposing_details() -> None:
    def timed_out(*args: object, **kwargs: object) -> FakeResponse:
        raise TimeoutError("socket details must stay private")

    report = verify_deployment(
        "https://kraken.example",
        "a" * 40,
        timeout_seconds=0,
        opener=timed_out,
        monotonic=lambda: 10.0,
    )

    assert report["status"] == "failed"
    assert report["endpoints"]["health"]["error"] == "connection_error"
    assert "socket details" not in json.dumps(report)
