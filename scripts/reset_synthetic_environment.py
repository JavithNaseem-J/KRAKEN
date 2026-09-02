from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.config import get_settings  # noqa: E402
from src.utils.synthetic_reset import (  # noqa: E402
    ACTIVE_STATE,
    QDRANT_TARGETS,
    RESETTING_STATE,
    RUNTIME_GENERATION_KEY,
    RUNTIME_STATE_KEY,
    ResetCoordinator,
    ResetError,
    ResetPlan,
    build_reset_plan,
)


class LiveResetOperations:
    """Allowlisted reset operations for KRAKEN-owned synthetic state."""

    def __init__(self, repo_root: Path = ROOT) -> None:
        self.settings = get_settings()
        self.repo_root = repo_root.resolve()
        self._corpus: Any | None = None

    def _postgres_pool(self) -> Any:
        from psycopg_pool import ConnectionPool

        return ConnectionPool(
            conninfo=self.settings.postgres_sync_url,
            timeout=10,
            kwargs={"prepare_threshold": None},
        )

    def _require_providers(self) -> None:
        missing = [
            name
            for name, value in {
                "POSTGRES_SYNC_URL": self.settings.postgres_sync_url,
                "REDIS_URL": self.settings.redis_url,
                "QDRANT_URL": self.settings.qdrant_url,
            }.items()
            if not value
        ]
        if missing:
            raise ResetError("Reset execution requires: " + ", ".join(missing))
        if self.settings.qdrant_collection_name != "kraken_knowledge":
            raise ResetError(
                "Reset execution requires QDRANT_COLLECTION_NAME=kraken_knowledge; "
                "the legacy collection is plan/cleanup-only"
            )

    def _validate_plan(self, plan: ResetPlan) -> None:
        if self.settings.qdrant_collection_name not in QDRANT_TARGETS:
            raise ResetError("Qdrant collection is outside the KRAKEN allowlist")
        if tuple(plan.qdrant_collections) != QDRANT_TARGETS:
            raise ResetError("Qdrant reset targets do not match the code-owned allowlist")
        if self.settings.synthetic_dataset_generation != plan.target_generation:
            raise ResetError(
                "Configured SYNTHETIC_DATASET_GENERATION must equal the target generation"
            )
        for raw_path in plan.generated_paths:
            path = Path(raw_path).resolve()
            if self.repo_root not in path.parents:
                raise ResetError(f"Generated path escapes repository root: {path}")

    async def inspect(self, plan: ResetPlan) -> dict[str, Any]:
        self._validate_plan(plan)
        result: dict[str, Any] = {
            "postgres": "not_configured",
            "redis": "not_configured",
            "qdrant": "not_configured",
            "generated_files": self._count_generated(plan),
            "targets": {
                "postgres_tables": len(plan.postgres_targets),
                "redis_patterns": len(plan.redis_patterns),
                "qdrant_collections": len(plan.qdrant_collections),
                "generated_paths": len(plan.generated_paths),
            },
        }
        if self.settings.postgres_sync_url:
            try:
                result["postgres"] = await asyncio.to_thread(self._postgres_counts, plan)
            except Exception as exc:
                result["postgres"] = {"status": "unavailable", "error": exc.__class__.__name__}
        if self.settings.redis_url:
            try:
                result["redis"] = await self._redis_counts(plan)
            except Exception as exc:
                result["redis"] = {"status": "unavailable", "error": exc.__class__.__name__}
        if self.settings.qdrant_url:
            try:
                result["qdrant"] = await self._qdrant_counts(plan)
            except Exception as exc:
                result["qdrant"] = {"status": "unavailable", "error": exc.__class__.__name__}
        return result

    async def invalidate(self, plan: ResetPlan) -> dict[str, Any]:
        self._require_providers()

        def operation() -> dict[str, Any]:
            with (
                self._postgres_pool() as pool,
                pool.connection() as conn,
                conn.cursor() as cur,
            ):
                cur.execute(
                    "SELECT value FROM kraken_runtime_metadata WHERE key = %s",
                    (RUNTIME_GENERATION_KEY,),
                )
                row = cur.fetchone()
                observed = str(row[0]) if row else None
                if observed not in {plan.expected_generation, plan.target_generation}:
                    raise ResetError("PostgreSQL generation does not match the expected value")
                cur.execute(
                    """
                        INSERT INTO kraken_runtime_metadata (key, value, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
                        """,
                    (RUNTIME_STATE_KEY, RESETTING_STATE),
                )
                conn.commit()
            return {"state": RESETTING_STATE, "observed_generation": observed}

        return await asyncio.to_thread(operation)

    async def clear_postgres(self, plan: ResetPlan) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            deleted: dict[str, int] = {}
            generations = tuple(dict.fromkeys((plan.expected_generation, plan.target_generation)))
            with (
                self._postgres_pool() as pool,
                pool.connection() as conn,
                conn.cursor() as cur,
            ):
                for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                    cur.execute(
                        f"""
                        DELETE FROM {table}
                        WHERE EXISTS (
                            SELECT 1 FROM unnest(%s::text[]) AS owned(generation)
                            WHERE left(thread_id, length(owned.generation) + 1)
                                = owned.generation || '_'
                        )
                        """,
                        (list(generations),),
                    )
                    deleted[table] = cur.rowcount
                cur.execute(
                    "DELETE FROM audit_log WHERE dataset_generation = ANY(%s)",
                    (list(generations),),
                )
                deleted["audit_log"] = cur.rowcount
                cur.execute(
                    "DELETE FROM tickets WHERE payload->>'dataset_generation' = ANY(%s)",
                    (list(generations),),
                )
                deleted["tickets"] = cur.rowcount
                conn.commit()
            return {"deleted": deleted}

        return await asyncio.to_thread(operation)

    async def clear_redis(self, plan: ResetPlan) -> dict[str, Any]:
        from src.utils.http_client import create_async_redis_client

        client = create_async_redis_client(self.settings.redis_url)
        removed = 0
        try:
            for pattern in plan.redis_patterns:
                keys = [key async for key in client.scan_iter(match=pattern, count=500)]
                if keys:
                    removed += int(await client.delete(*keys))
        finally:
            await client.aclose()
        return {"deleted_keys": removed}

    async def clear_qdrant(self, plan: ResetPlan) -> dict[str, Any]:
        from src.utils.cache import create_async_qdrant_client

        client = create_async_qdrant_client()
        deleted: list[str] = []
        try:
            for collection in plan.qdrant_collections:
                if await client.collection_exists(collection):
                    await client.delete_collection(collection)
                    deleted.append(collection)
        finally:
            await client.close()
        return {"deleted_collections": deleted, "deleted_count": len(deleted)}

    async def clear_generated(self, plan: ResetPlan) -> dict[str, Any]:
        removed = 0
        for raw_path in plan.generated_paths:
            path = Path(raw_path).resolve()
            if self.repo_root not in path.parents:
                raise ResetError(f"Refusing to remove path outside repository: {path}")
            if path.is_dir():
                shutil.rmtree(path)
                removed += 1
            elif path.exists():
                path.unlink()
                removed += 1
        return {"removed_paths": removed}

    async def generate(self, plan: ResetPlan) -> dict[str, Any]:
        from src.utils.synthetic_data import GenerationConfig, build_corpus, write_corpus

        self._corpus = build_corpus(GenerationConfig(generation=plan.target_generation))
        written = write_corpus(self._corpus, data_root=self.repo_root / "data")
        return {"written_files": len(written)}

    async def validate(self, plan: ResetPlan) -> dict[str, Any]:
        from src.utils.synthetic_data import load_manifest

        manifest = load_manifest(self.repo_root / "data")
        if manifest.generation != plan.target_generation:
            raise ResetError("Generated manifest does not match target generation")
        if manifest.counts != {
            "tickets": 500,
            "documents": 30,
            "scenarios": 75,
            "sla_levels": 4,
        }:
            raise ResetError("Generated manifest counts are incomplete")
        return {"counts": manifest.counts, "checksums": manifest.checksums}

    async def seed_postgres(self, plan: ResetPlan) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            from src.utils.db.tickets import seed_tickets

            ticket_path = self.repo_root / "data/knowledge/tickets/synthetic_tickets.json"
            tickets = json.loads(ticket_path.read_text(encoding="utf-8"))
            with (
                self._postgres_pool() as pool,
                pool.connection() as conn,
            ):
                count = seed_tickets(conn, tickets, update_on_conflict=True, activate=False)
            return {"seeded_tickets": count}

        return await asyncio.to_thread(operation)

    async def ingest_qdrant(self, plan: ResetPlan) -> dict[str, Any]:
        from qdrant_client.models import Distance, VectorParams

        from src.utils.cache import create_async_qdrant_client
        from src.utils.knowledge.ingest import run_ingest_async
        from src.utils.memory.long_term import EPISODIC_MEMORY_COLLECTION

        embedder = None
        if not self.settings.qdrant_cloud_inference_enabled:
            from src.utils.embedder import get_embedder

            embedder = get_embedder()
        client = create_async_qdrant_client()
        try:
            counts = await run_ingest_async(client, embedder)
            if not await client.collection_exists(EPISODIC_MEMORY_COLLECTION):
                await client.create_collection(
                    collection_name=EPISODIC_MEMORY_COLLECTION,
                    vectors_config=VectorParams(
                        size=(
                            self.settings.qdrant_inference_dim
                            if self.settings.qdrant_cloud_inference_enabled
                            else self.settings.embedding_dim
                        ),
                        distance=Distance.COSINE,
                    ),
                )
        finally:
            await client.close()
        return {"ingested": counts, "generation": plan.target_generation}

    async def smoke(self, plan: ResetPlan) -> dict[str, Any]:
        counts = await self._active_counts(plan.target_generation)
        if counts["postgres_tickets"] != 500 or counts["qdrant_points"] < 1:
            raise ResetError("Capability smoke checks did not find the complete target generation")
        return counts

    async def activate(self, plan: ResetPlan) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            with (
                self._postgres_pool() as pool,
                pool.connection() as conn,
                conn.cursor() as cur,
            ):
                for key, value in (
                    (RUNTIME_GENERATION_KEY, plan.target_generation),
                    (RUNTIME_STATE_KEY, ACTIVE_STATE),
                ):
                    cur.execute(
                        """
                        INSERT INTO kraken_runtime_metadata (key, value, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
                        """,
                        (key, value),
                    )
                conn.commit()
            return {"generation": plan.target_generation, "state": ACTIVE_STATE}

        return await asyncio.to_thread(operation)

    async def verify(self, plan: ResetPlan) -> dict[str, Any]:
        counts = await self._active_counts(plan.target_generation)

        def metadata() -> dict[str, str]:
            with (
                self._postgres_pool() as pool,
                pool.connection() as conn,
                conn.cursor() as cur,
            ):
                cur.execute(
                    "SELECT key, value FROM kraken_runtime_metadata WHERE key = ANY(%s)",
                    ([RUNTIME_GENERATION_KEY, RUNTIME_STATE_KEY],),
                )
                return {str(row[0]): str(row[1]) for row in cur.fetchall()}

        observed = await asyncio.to_thread(metadata)
        if observed != {
            RUNTIME_GENERATION_KEY: plan.target_generation,
            RUNTIME_STATE_KEY: ACTIVE_STATE,
        }:
            raise ResetError("Runtime metadata is not active for the target generation")
        if counts["postgres_tickets"] != 500 or counts["qdrant_points"] < 1:
            raise ResetError("Final generation verification failed")
        return {**counts, "state": ACTIVE_STATE, "generation": plan.target_generation}

    def _postgres_counts(self, plan: ResetPlan) -> dict[str, int | str | None]:
        counts: dict[str, int | str | None] = {}
        with (
            self._postgres_pool() as pool,
            pool.connection() as conn,
            conn.cursor() as cur,
        ):
            cur.execute(
                "SELECT COUNT(*) FROM tickets WHERE payload->>'dataset_generation' = %s",
                (plan.expected_generation,),
            )
            ticket_row = cur.fetchone()
            counts["tickets"] = int(ticket_row[0]) if ticket_row else 0
            cur.execute(
                "SELECT COUNT(*) FROM audit_log WHERE dataset_generation = %s",
                (plan.expected_generation,),
            )
            audit_row = cur.fetchone()
            counts["audit_events"] = int(audit_row[0]) if audit_row else 0
            cur.execute(
                "SELECT value FROM kraken_runtime_metadata WHERE key = %s",
                (RUNTIME_GENERATION_KEY,),
            )
            row = cur.fetchone()
            counts["active_generation"] = str(row[0]) if row else None
        return counts

    async def _redis_counts(self, plan: ResetPlan) -> dict[str, int]:
        from src.utils.http_client import create_async_redis_client

        client = create_async_redis_client(self.settings.redis_url)
        counts: dict[str, int] = {}
        try:
            for pattern in plan.redis_patterns:
                counts[pattern] = len(
                    [key async for key in client.scan_iter(match=pattern, count=500)]
                )
        finally:
            await client.aclose()
        return counts

    async def _qdrant_counts(self, plan: ResetPlan) -> dict[str, int]:
        from src.utils.cache import create_async_qdrant_client

        client = create_async_qdrant_client()
        counts: dict[str, int] = {}
        try:
            for collection in plan.qdrant_collections:
                if await client.collection_exists(collection):
                    counts[collection] = int((await client.count(collection, exact=True)).count)
                else:
                    counts[collection] = 0
        finally:
            await client.close()
        return counts

    async def _active_counts(self, generation: str) -> dict[str, int]:
        def postgres_count() -> int:
            with (
                self._postgres_pool() as pool,
                pool.connection() as conn,
                conn.cursor() as cur,
            ):
                cur.execute(
                    "SELECT COUNT(*) FROM tickets WHERE payload->>'dataset_generation' = %s",
                    (generation,),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0

        from qdrant_client.models import FieldCondition, Filter, MatchValue

        from src.utils.cache import create_async_qdrant_client

        postgres_tickets = await asyncio.to_thread(postgres_count)
        client = create_async_qdrant_client()
        try:
            qdrant_points = int(
                (
                    await client.count(
                        self.settings.qdrant_collection_name,
                        count_filter=Filter(
                            must=[
                                FieldCondition(
                                    key="dataset_generation", match=MatchValue(value=generation)
                                )
                            ]
                        ),
                        exact=True,
                    )
                ).count
            )
        finally:
            await client.close()
        return {"postgres_tickets": postgres_tickets, "qdrant_points": qdrant_points}

    @staticmethod
    def _count_generated(plan: ResetPlan) -> int:
        count = 0
        for raw_path in plan.generated_paths:
            path = Path(raw_path)
            if path.is_dir():
                count += sum(1 for candidate in path.rglob("*") if candidate.is_file())
            elif path.is_file():
                count += 1
        return count


async def main_async() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Plan, execute, or verify the allowlisted KRAKEN synthetic reset."
    )
    parser.add_argument("mode", choices=("plan", "execute", "verify"), nargs="?", default="plan")
    parser.add_argument("--expected-generation", default=settings.synthetic_dataset_generation)
    parser.add_argument("--target-generation", default=settings.synthetic_dataset_generation)
    parser.add_argument("--confirmation", default="")
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "reports" / "synthetic-reset" / "latest.json",
    )
    args = parser.parse_args()

    plan = build_reset_plan(
        expected_generation=args.expected_generation,
        target_generation=args.target_generation,
        repo_root=ROOT,
    )
    operations = LiveResetOperations(ROOT)
    if args.mode == "verify":
        details = await operations.verify(plan)
        print(json.dumps(details, indent=2))
        return 0
    coordinator = ResetCoordinator(operations, report_path=args.report)
    report = await coordinator.run(
        plan,
        execute=args.mode == "execute",
        confirmation=args.confirmation,
    )
    print(json.dumps(report.as_dict(), indent=2))
    if args.mode == "plan":
        print(f"Execution confirmation: {plan.confirmation_phrase}")
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(main_async()))
    except ResetError as exc:
        print(f"reset refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
