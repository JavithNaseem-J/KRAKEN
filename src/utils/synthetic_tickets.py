from __future__ import annotations

import copy
import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from src.utils.config import Settings, get_settings
from src.utils.exceptions import ActionExecutionError

_SEED_FILE = (
    Path(__file__).resolve().parents[2] / "data" / "knowledge" / "tickets" / "synthetic_tickets.json"
)


def fetch_indexed_tickets(
    ticket_id: str | None = None, *, settings: Settings | None = None
) -> list[dict[str, Any]]:
    """Read the indexed seed records when the local corpus is absent."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from src.utils.knowledge import active_generation_conditions

    settings = settings or get_settings()
    if not settings.qdrant_url:
        raise ActionExecutionError("Indexed ticket data is unavailable.")
    conditions = [
        FieldCondition(key="source", match=MatchValue(value="tickets")),
        FieldCondition(key="scope", match=MatchValue(value="shared")),
        *active_generation_conditions(
            settings.knowledge_collection_version, settings.synthetic_dataset_generation
        ),
    ]
    if ticket_id:
        conditions.append(
            FieldCondition(
                key="metadata.ticket_id", match=MatchValue(value=ticket_id.strip().upper())
            )
        )
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=10)
    records: list[dict[str, Any]] = []
    offset = None
    try:
        while True:
            points, offset = client.scroll(
                collection_name=settings.qdrant_collection_name,
                scroll_filter=Filter(must=conditions),
                limit=1 if ticket_id else 256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            records.extend(
                raw
                for point in points
                if isinstance(point.payload, dict)
                and isinstance(raw := point.payload.get("metadata", {}).get("raw"), dict)
            )
            if ticket_id or offset is None:
                return records
    except Exception as exc:
        raise ActionExecutionError("Indexed ticket data is unavailable.") from exc
    finally:
        client.close()


class SyntheticTicketRepository:
    """Immutable seed tickets plus expiring, session-private overlays."""

    def __init__(self, settings: Settings | None = None, *, clock: Any = time.time) -> None:
        self.settings = settings or get_settings()
        self._clock = clock
        self._lock = threading.RLock()
        self._seeds = self._load_seeds()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._redis: Any | None = None
        if self.settings.redis_url:
            import redis

            self._redis = redis.Redis.from_url(
                self.settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
            )

    @staticmethod
    def _load_seeds() -> dict[str, dict[str, Any]]:
        records = json.loads(_SEED_FILE.read_text(encoding="utf-8")) if _SEED_FILE.exists() else []
        result: dict[str, dict[str, Any]] = {}
        for record in records:
            ticket_id = str(record.get("ticket_id") or record.get("id") or "").upper()
            if ticket_id:
                result[ticket_id] = copy.deepcopy(record)
        return result

    def _seed(self, ticket_id: str) -> dict[str, Any] | None:
        if ticket_id not in self._seeds and not _SEED_FILE.exists():
            records = fetch_indexed_tickets(ticket_id, settings=self.settings)
            if records:
                self._seeds[ticket_id] = records[0]
        return self._seeds.get(ticket_id)

    def _scope(self, session_id: str) -> dict[str, Any]:
        self.cleanup()
        now = float(self._clock())
        scope = self._sessions.get(session_id)
        if scope is None and self._redis is not None:
            try:
                raw = self._redis.get(
                    f"kraken:{self.settings.synthetic_dataset_generation}:synthetic:tickets:{session_id}"
                )
                if raw:
                    scope = json.loads(raw)
                    self._sessions[session_id] = scope
            except Exception:
                scope = None
        if scope is None:
            scope = {
                "expires_at": now + self.settings.public_session_ttl_seconds,
                "dataset_generation": self.settings.synthetic_dataset_generation,
                "writes": 0,
                "overlays": {},
                "created": {},
            }
            self._sessions[session_id] = scope
        return scope

    def _persist(self, session_id: str, scope: dict[str, Any]) -> None:
        if self._redis is None:
            return
        try:
            ttl = max(1, int(float(scope["expires_at"]) - float(self._clock())))
            self._redis.set(
                f"kraken:{self.settings.synthetic_dataset_generation}:synthetic:tickets:{session_id}",
                json.dumps(scope),
                ex=ttl,
            )
        except Exception:
            return

    def _consume_write(self, scope: dict[str, Any]) -> None:
        if int(scope["writes"]) >= self.settings.public_write_limit:
            remaining = max(1, int(float(scope["expires_at"]) - float(self._clock())))
            raise ActionExecutionError(
                f"Public write limit reached. Start a new session or retry in {remaining} seconds."
            )
        scope["writes"] = int(scope["writes"]) + 1

    def get(self, session_id: str, ticket_id: str) -> dict[str, Any]:
        normalized = ticket_id.strip().upper()
        with self._lock:
            scope = self._scope(session_id)
            ticket = scope["created"].get(normalized)
            if ticket is None:
                ticket = scope["overlays"].get(normalized) or self._seed(normalized)
            if ticket is None:
                raise ActionExecutionError(f"Ticket '{ticket_id}' not found.")
            return copy.deepcopy(ticket)

    def create(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        required = {
            "user_name": str(payload.get("user_name") or payload.get("user") or "").strip(),
            "category": str(payload.get("category") or "").strip(),
            "priority": str(payload.get("priority") or "").strip().lower(),
            "description": str(payload.get("description") or payload.get("reason") or "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ActionExecutionError("Missing required ticket fields: " + ", ".join(missing))
        if required["priority"] not in {"low", "medium", "high", "critical"}:
            raise ActionExecutionError("priority must be low, medium, high, or critical.")

        with self._lock:
            scope = self._scope(session_id)
            self._consume_write(scope)
            ticket_id = f"SYN-{secrets.token_hex(6).upper()}"
            ticket = {
                "ticket_id": ticket_id,
                "subject": f"{required['category']}: {required['description'][:60]}",
                "status": "open",
                "user": required["user_name"],
                "category": required["category"],
                "priority": required["priority"],
                "description": required["description"],
                "synthetic": True,
                "dataset_generation": self.settings.synthetic_dataset_generation,
            }
            scope["created"][ticket_id] = ticket
            self._persist(session_id, scope)
            return {"success": True, **copy.deepcopy(ticket)}

    def consume_write(self, session_id: str) -> int:
        with self._lock:
            scope = self._scope(session_id)
            self._consume_write(scope)
            self._persist(session_id, scope)
            return max(0, self.settings.public_write_limit - int(scope["writes"]))

    def mutate(
        self,
        session_id: str,
        ticket_id: str,
        *,
        status: str,
        updates: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = ticket_id.strip().upper()
        with self._lock:
            scope = self._scope(session_id)
            current = scope["created"].get(normalized)
            is_created = current is not None
            if current is None:
                current = scope["overlays"].get(normalized) or self._seed(normalized)
            if current is None:
                raise ActionExecutionError(f"Ticket '{ticket_id}' not found.")
            self._consume_write(scope)
            changed = copy.deepcopy(current)
            changed["status"] = status
            changed.update(updates or {})
            changed["synthetic"] = True
            changed["dataset_generation"] = self.settings.synthetic_dataset_generation
            if is_created:
                scope["created"][normalized] = changed
            else:
                scope["overlays"][normalized] = changed
            self._persist(session_id, scope)
            return {
                "success": True,
                "synthetic": True,
                "dataset_generation": self.settings.synthetic_dataset_generation,
                "ticket_id": normalized,
                "status_updated_to": status,
                **(updates or {}),
            }

    def cleanup(self) -> None:
        now = float(self._clock())
        for session_id, scope in list(self._sessions.items()):
            if float(scope["expires_at"]) <= now:
                self._sessions.pop(session_id, None)


synthetic_ticket_repository = SyntheticTicketRepository()
