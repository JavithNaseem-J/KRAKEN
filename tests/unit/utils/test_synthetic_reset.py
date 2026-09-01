from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import pytest

import src.utils.synthetic_reset as reset_module
from scripts.reset_synthetic_environment import LiveResetOperations
from src.utils.config import Settings
from src.utils.synthetic_reset import (
    QDRANT_TARGETS,
    REDIS_TARGET_PATTERNS,
    RESET_GUARD_ENV,
    ResetCoordinator,
    ResetError,
    ResetPlan,
    build_reset_plan,
)


class FakeResetOperations:
    def __init__(self, *, fail_ingest_once: bool = False) -> None:
        self.calls: list[str] = []
        self.fail_ingest_once = fail_ingest_once
        self.postgres_generations = {"northstar-v1", "unrelated-v1"}
        self.redis_keys = {
            "kraken:northstar-v1:session:one",
            "kraken:northstar-v1:approval:one",
            "other-service:sentinel",
        }
        self.qdrant_collections = {"kraken_knowledge", "other_service_sentinel"}
        self.active_generation = "northstar-v1"
        self.state = "active"

    async def inspect(self, plan: ResetPlan) -> dict[str, Any]:
        self.calls.append("preflight")
        return {
            "postgres_generations": len(self.postgres_generations),
            "redis_keys": len(self.redis_keys),
            "qdrant_collections": len(self.qdrant_collections),
            "api_key": "must-not-appear",
        }

    async def invalidate(self, plan: ResetPlan) -> dict[str, Any]:
        self.calls.append("invalidate")
        self.state = "resetting"
        return {"state": self.state}

    async def clear_postgres(self, plan: ResetPlan) -> dict[str, Any]:
        self.calls.append("clear_postgres")
        self.postgres_generations.discard(plan.expected_generation)
        self.postgres_generations.discard(plan.target_generation)
        return {"deleted": 1}

    async def clear_redis(self, plan: ResetPlan) -> dict[str, Any]:
        self.calls.append("clear_redis")
        prefixes = {f"kraken:{plan.expected_generation}:", f"kraken:{plan.target_generation}:"}
        self.redis_keys = {
            key for key in self.redis_keys if not any(key.startswith(prefix) for prefix in prefixes)
        }
        return {"deleted_keys": 2}

    async def clear_qdrant(self, plan: ResetPlan) -> dict[str, Any]:
        self.calls.append("clear_qdrant")
        self.qdrant_collections.difference_update(plan.qdrant_collections)
        return {"deleted_count": 1}

    async def clear_generated(self, plan: ResetPlan) -> dict[str, Any]:
        self.calls.append("clear_generated")
        return {"removed_paths": len(plan.generated_paths)}

    async def generate(self, plan: ResetPlan) -> dict[str, Any]:
        self.calls.append("generate")
        return {"written_files": 34}

    async def validate(self, plan: ResetPlan) -> dict[str, Any]:
        self.calls.append("validate")
        return {"checksums": {"tickets": "abc123"}}

    async def seed_postgres(self, plan: ResetPlan) -> dict[str, Any]:
        self.calls.append("seed_postgres")
        self.postgres_generations.add(plan.target_generation)
        return {"seeded_tickets": 500}

    async def ingest_qdrant(self, plan: ResetPlan) -> dict[str, Any]:
        self.calls.append("ingest_qdrant")
        if self.fail_ingest_once:
            self.fail_ingest_once = False
            raise RuntimeError("injected failure")
        self.qdrant_collections.add("kraken_knowledge")
        return {"ingested": 534}

    async def smoke(self, plan: ResetPlan) -> dict[str, Any]:
        self.calls.append("capability_smoke")
        assert plan.target_generation in self.postgres_generations
        assert "kraken_knowledge" in self.qdrant_collections
        return {"passed": 8}

    async def activate(self, plan: ResetPlan) -> dict[str, Any]:
        self.calls.append("activate")
        self.active_generation = plan.target_generation
        self.state = "active"
        return {"generation": self.active_generation, "state": self.state}

    async def verify(self, plan: ResetPlan) -> dict[str, Any]:
        self.calls.append("verify")
        assert self.active_generation == plan.target_generation
        assert self.state == "active"
        return {"tickets": 500, "qdrant_points": 534}


def _plan(tmp_path: Path, *, expected: str = "northstar-v1") -> ResetPlan:
    return build_reset_plan(
        expected_generation=expected,
        target_generation="northstar-v2",
        repo_root=tmp_path,
    )


@pytest.mark.asyncio
async def test_plan_is_preview_only_and_reports_allowlisted_targets(tmp_path: Path) -> None:
    operations = FakeResetOperations()
    report_path = tmp_path / "reset-report.json"
    report = await ResetCoordinator(operations, report_path=report_path).run(_plan(tmp_path))

    assert report.status == "planned"
    assert operations.calls == ["preflight"]
    assert set(_plan(tmp_path).qdrant_collections) == set(QDRANT_TARGETS)
    assert all("FLUSH" not in pattern.upper() for pattern in REDIS_TARGET_PATTERNS)
    assert any(
        Path(path).as_posix().endswith("data/workspace/tickets.json")
        for path in _plan(tmp_path).generated_paths
    )
    report_text = report_path.read_text(encoding="utf-8")
    assert "must-not-appear" not in report_text
    assert "[REDACTED]" in report_text
    assert "Status: planned" in report_path.with_suffix(".txt").read_text(encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment", "confirmation"),
    [
        ({}, "RESET KRAKEN TO northstar-v2"),
        ({RESET_GUARD_ENV: "true"}, "wrong"),
    ],
)
async def test_execute_requires_guard_and_exact_confirmation(
    tmp_path: Path, environment: dict[str, str], confirmation: str
) -> None:
    operations = FakeResetOperations()
    with pytest.raises(ResetError):
        await ResetCoordinator(operations).run(
            _plan(tmp_path),
            execute=True,
            confirmation=confirmation,
            environment=environment,
        )
    assert operations.calls == ["preflight"]


@pytest.mark.asyncio
async def test_execute_preserves_unrelated_sentinels_and_activates_target(tmp_path: Path) -> None:
    operations = FakeResetOperations()
    report = await ResetCoordinator(operations).run(
        _plan(tmp_path),
        execute=True,
        confirmation="RESET KRAKEN TO northstar-v2",
        environment={RESET_GUARD_ENV: "true"},
    )

    assert report.status == "complete"
    assert operations.postgres_generations == {"unrelated-v1", "northstar-v2"}
    assert operations.redis_keys == {"other-service:sentinel"}
    assert operations.qdrant_collections == {"other_service_sentinel", "kraken_knowledge"}
    assert operations.active_generation == "northstar-v2"
    assert [phase.name for phase in report.phases][-2:] == ["activate", "verify"]


@pytest.mark.asyncio
async def test_partial_failure_can_rerun_same_target_idempotently(tmp_path: Path) -> None:
    operations = FakeResetOperations(fail_ingest_once=True)
    coordinator = ResetCoordinator(operations)
    kwargs = {
        "execute": True,
        "confirmation": "RESET KRAKEN TO northstar-v2",
        "environment": {RESET_GUARD_ENV: "true"},
    }
    with pytest.raises(RuntimeError, match="injected failure"):
        await coordinator.run(_plan(tmp_path), **kwargs)
    assert operations.state == "resetting"

    report = await coordinator.run(_plan(tmp_path), **kwargs)
    assert report.status == "complete"
    assert operations.postgres_generations == {"unrelated-v1", "northstar-v2"}


def test_generated_target_outside_repository_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reset_module, "GENERATED_TARGETS", ("../outside",))
    with pytest.raises(ResetError, match="escapes repository root"):
        build_reset_plan(
            expected_generation="northstar-v1",
            target_generation="northstar-v2",
            repo_root=tmp_path,
        )


@pytest.mark.asyncio
async def test_live_allowlisted_cleanup_preserves_service_and_file_sentinels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.keys = {
                "kraken:northstar-v1:session:one",
                "kraken:northstar-v1:semantic-cache:generation",
                "other-service:sentinel",
            }

        async def scan_iter(self, *, match: str, count: int):
            del count
            for key in list(self.keys):
                if fnmatch(key, match):
                    yield key

        async def delete(self, *keys: str) -> int:
            before = len(self.keys)
            self.keys.difference_update(keys)
            return before - len(self.keys)

        async def aclose(self) -> None:
            return None

    class FakeQdrant:
        def __init__(self) -> None:
            self.collections = {"akea_knowledge", "kraken_semantic_cache_v2", "sentinel"}

        async def collection_exists(self, name: str) -> bool:
            return name in self.collections

        async def delete_collection(self, name: str) -> None:
            self.collections.remove(name)

        async def close(self) -> None:
            return None

    redis = FakeRedis()
    qdrant = FakeQdrant()
    monkeypatch.setattr(
        "src.utils.http_client.create_async_redis_client", lambda *args, **kwargs: redis
    )
    monkeypatch.setattr("src.utils.cache.create_async_qdrant_client", lambda: qdrant)

    operations = LiveResetOperations(tmp_path)
    operations.settings = Settings(
        environment="test",
        hitl_service_token="test-hitl-token-0123456789abcdef0123456789",
        redis_url="redis://synthetic.invalid",
        qdrant_url="https://qdrant.synthetic.invalid",
        qdrant_collection_name="kraken_knowledge",
        synthetic_dataset_generation="northstar-v2",
    )
    plan = _plan(tmp_path)
    generated_file = tmp_path / "data/knowledge/faq/old.md"
    generated_file.parent.mkdir(parents=True)
    generated_file.write_text("old", encoding="utf-8")
    sentinel = tmp_path / "unrelated-sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    await operations.clear_redis(plan)
    await operations.clear_qdrant(plan)
    await operations.clear_generated(plan)

    assert redis.keys == {"other-service:sentinel"}
    assert qdrant.collections == {"sentinel"}
    assert sentinel.read_text(encoding="utf-8") == "preserve"
