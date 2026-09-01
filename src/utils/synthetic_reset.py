from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

RESET_GUARD_ENV = "ALLOW_SYNTHETIC_DATA_RESET"
RUNTIME_GENERATION_KEY = "synthetic_dataset_generation"
RUNTIME_STATE_KEY = "synthetic_dataset_state"
ACTIVE_STATE = "active"
RESETTING_STATE = "resetting"

POSTGRES_TARGETS: tuple[str, ...] = (
    "tickets",
    "audit_log",
    "checkpoints",
    "checkpoint_writes",
    "checkpoint_blobs",
    "kraken_runtime_metadata",
)
REDIS_TARGET_PATTERNS: tuple[str, ...] = (
    "kraken:{generation}:*",
    "kraken:semantic-cache:exact:*",
    "kraken:semantic-cache:v2:exact:*",
)
QDRANT_TARGETS: tuple[str, ...] = (
    "akea_knowledge",
    "kraken_knowledge",
    "kraken_semantic_cache",
    "kraken_semantic_cache_v2",
    "kraken_episodic_memory",
)
GENERATED_TARGETS: tuple[str, ...] = (
    "data/knowledge/faq",
    "data/knowledge/tickets/synthetic_tickets.json",
    "data/knowledge/sla/sla_rules.json",
    "data/synthetic",
    "data/workspace/tickets.json",
)


class ResetError(RuntimeError):
    """Raised when a synthetic reset is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class ResetPlan:
    expected_generation: str
    target_generation: str
    postgres_targets: tuple[str, ...]
    redis_patterns: tuple[str, ...]
    qdrant_collections: tuple[str, ...]
    generated_paths: tuple[str, ...]
    confirmation_phrase: str


@dataclass(slots=True)
class PhaseResult:
    name: str
    status: str
    duration_ms: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResetReport:
    mode: str
    expected_generation: str
    target_generation: str
    started_at: float
    status: str = "running"
    phases: list[PhaseResult] = field(default_factory=list)
    manifest_checksums: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return _redact(asdict(self))

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2) + "\n", encoding="utf-8")
        path.with_suffix(".txt").write_text(self.human_summary(), encoding="utf-8")

    def human_summary(self) -> str:
        lines = [
            "KRAKEN synthetic environment reset",
            f"Mode: {self.mode}",
            f"Status: {self.status}",
            f"Generation: {self.expected_generation} -> {self.target_generation}",
            "Phases:",
        ]
        lines.extend(
            f"- {phase.name}: {phase.status} ({phase.duration_ms} ms)" for phase in self.phases
        )
        return "\n".join(lines) + "\n"


class ResetOperations(Protocol):
    async def inspect(self, plan: ResetPlan) -> dict[str, Any]: ...

    async def invalidate(self, plan: ResetPlan) -> dict[str, Any]: ...

    async def clear_postgres(self, plan: ResetPlan) -> dict[str, Any]: ...

    async def clear_redis(self, plan: ResetPlan) -> dict[str, Any]: ...

    async def clear_qdrant(self, plan: ResetPlan) -> dict[str, Any]: ...

    async def clear_generated(self, plan: ResetPlan) -> dict[str, Any]: ...

    async def generate(self, plan: ResetPlan) -> dict[str, Any]: ...

    async def validate(self, plan: ResetPlan) -> dict[str, Any]: ...

    async def seed_postgres(self, plan: ResetPlan) -> dict[str, Any]: ...

    async def ingest_qdrant(self, plan: ResetPlan) -> dict[str, Any]: ...

    async def smoke(self, plan: ResetPlan) -> dict[str, Any]: ...

    async def activate(self, plan: ResetPlan) -> dict[str, Any]: ...

    async def verify(self, plan: ResetPlan) -> dict[str, Any]: ...


def confirmation_phrase(target_generation: str) -> str:
    return f"RESET KRAKEN TO {target_generation}"


def build_reset_plan(
    *, expected_generation: str, target_generation: str, repo_root: Path
) -> ResetPlan:
    expected = _validate_generation(expected_generation, "expected generation")
    target = _validate_generation(target_generation, "target generation")
    root = repo_root.resolve()
    generated_paths: list[str] = []
    for relative in GENERATED_TARGETS:
        candidate = (root / relative).resolve()
        if candidate != root and root not in candidate.parents:
            raise ResetError(f"Generated target escapes repository root: {relative}")
        generated_paths.append(str(candidate))
    return ResetPlan(
        expected_generation=expected,
        target_generation=target,
        postgres_targets=POSTGRES_TARGETS,
        redis_patterns=tuple(
            pattern.format(generation=expected) for pattern in REDIS_TARGET_PATTERNS
        ),
        qdrant_collections=QDRANT_TARGETS,
        generated_paths=tuple(generated_paths),
        confirmation_phrase=confirmation_phrase(target),
    )


class ResetCoordinator:
    def __init__(self, operations: ResetOperations, *, report_path: Path | None = None) -> None:
        self.operations = operations
        self.report_path = report_path

    async def run(
        self,
        plan: ResetPlan,
        *,
        execute: bool = False,
        confirmation: str = "",
        environment: Mapping[str, str] | None = None,
    ) -> ResetReport:
        report = ResetReport(
            mode="execute" if execute else "plan",
            expected_generation=plan.expected_generation,
            target_generation=plan.target_generation,
            started_at=time.time(),
        )
        await self._phase(report, "preflight", self.operations.inspect, plan)
        if not execute:
            report.status = "planned"
            self._write(report)
            return report

        resolved_environment = os.environ if environment is None else environment
        self._require_execution_guard(plan, confirmation, resolved_environment)
        phases = (
            ("invalidate", self.operations.invalidate),
            ("clear_postgres", self.operations.clear_postgres),
            ("clear_redis", self.operations.clear_redis),
            ("clear_qdrant", self.operations.clear_qdrant),
            ("clear_generated", self.operations.clear_generated),
            ("generate", self.operations.generate),
            ("validate", self.operations.validate),
            ("seed_postgres", self.operations.seed_postgres),
            ("ingest_qdrant", self.operations.ingest_qdrant),
            ("capability_smoke", self.operations.smoke),
            ("activate", self.operations.activate),
            ("verify", self.operations.verify),
        )
        try:
            for name, operation in phases:
                details = await self._phase(report, name, operation, plan)
                if name == "validate":
                    checksums = details.get("checksums", {})
                    if isinstance(checksums, dict):
                        report.manifest_checksums = {
                            str(key): str(value) for key, value in checksums.items()
                        }
            report.status = "complete"
        except Exception:
            report.status = "failed"
            self._write(report)
            raise
        self._write(report)
        return report

    @staticmethod
    def _require_execution_guard(
        plan: ResetPlan, confirmation: str, environment: Mapping[str, str]
    ) -> None:
        if environment.get(RESET_GUARD_ENV, "").lower() != "true":
            raise ResetError(f"{RESET_GUARD_ENV}=true is required for execution")
        if confirmation != plan.confirmation_phrase:
            raise ResetError(f"Confirmation must exactly match: {plan.confirmation_phrase}")

    async def _phase(
        self,
        report: ResetReport,
        name: str,
        operation: Any,
        plan: ResetPlan,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            details = await operation(plan)
        except Exception as exc:
            report.phases.append(
                PhaseResult(
                    name=name,
                    status="failed",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    details={"error": exc.__class__.__name__},
                )
            )
            raise
        safe_details = _redact(details if isinstance(details, dict) else {})
        report.phases.append(
            PhaseResult(
                name=name,
                status="complete",
                duration_ms=int((time.perf_counter() - started) * 1000),
                details=safe_details,
            )
        )
        self._write(report)
        return safe_details

    def _write(self, report: ResetReport) -> None:
        if self.report_path is not None:
            report.write(self.report_path)


def _validate_generation(value: str, label: str) -> str:
    import re

    normalized = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,31}", normalized):
        raise ResetError(f"Invalid {label}: {value!r}")
    return normalized


def _redact(value: Any) -> Any:
    sensitive = {
        "api_key",
        "authorization",
        "connection_string",
        "cookie",
        "password",
        "record",
        "records",
        "secret",
        "token",
        "url",
    }
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in sensitive else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value
