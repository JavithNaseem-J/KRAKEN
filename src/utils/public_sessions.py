from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.utils.config import Settings, get_settings
from src.utils.models.public import OperationalPersona, PublicSessionResponse


class PublicSessionError(ValueError):
    pass


class PublicSessionExpiredError(PublicSessionError):
    pass


@dataclass(slots=True)
class PublicSession:
    session_id: str
    csrf_token: str
    persona: OperationalPersona
    dataset_generation: str
    actor_id: str
    created_at: float
    expires_at: float
    write_count: int = 0
    upload_ids: set[str] = field(default_factory=set)


_ACTORS: dict[OperationalPersona, str] = {
    OperationalPersona.END_USER: "user",
    OperationalPersona.TIER1_ANALYST: "alice",
    OperationalPersona.INCIDENT_COMMANDER: "bob",
    OperationalPersona.ADMIN: "admin",
}


class PublicSessionManager:
    """Signed public identity with bounded, generation-scoped state.

    Managed-service persistence can replace the storage methods without changing
    the gateway contract. The fallback is intentionally bounded and expires all
    mutable state with the session.
    """

    def __init__(self, settings: Settings | None = None, *, clock: Any = time.time) -> None:
        self.settings = settings or get_settings()
        self._clock = clock
        self._sessions: dict[str, PublicSession] = {}
        self._revoked: dict[str, float] = {}
        self._queries: dict[str, deque[float]] = defaultdict(deque)
        self._max_sessions = 10_000
        self._redis: Any | None = None
        if self.settings.redis_url:
            from src.utils.http_client import create_async_redis_client

            self._redis = create_async_redis_client(self.settings.redis_url)

    @staticmethod
    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    def _signature(self, value: str) -> str:
        digest = hmac.new(
            self.settings.public_session_secret.encode("utf-8"),
            value.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return self._b64(digest)

    def _cookie_value(self, session: PublicSession) -> str:
        payload = (
            f"{self.settings.synthetic_dataset_generation}."
            f"{session.session_id}.{int(session.expires_at)}"
        )
        return f"{payload}.{self._signature(payload)}"

    def _verified_cookie(self, cookie_value: str | None) -> tuple[str, int]:
        if not cookie_value:
            raise PublicSessionError("Public session is required.")
        try:
            generation, session_id, expiry_text, supplied = cookie_value.split(".", 3)
            expiry = int(expiry_text)
        except (TypeError, ValueError) as exc:
            raise PublicSessionError("Invalid public session.") from exc
        if generation != self.settings.synthetic_dataset_generation:
            raise PublicSessionError("Session belongs to an inactive dataset generation.")
        payload = f"{generation}.{session_id}.{expiry}"
        if not hmac.compare_digest(supplied, self._signature(payload)):
            raise PublicSessionError("Invalid public session.")
        if expiry <= float(self._clock()):
            raise PublicSessionExpiredError("Public session expired.")
        return session_id, expiry

    def create(
        self, persona: OperationalPersona = OperationalPersona.TIER1_ANALYST
    ) -> tuple[PublicSession, str]:
        self.cleanup()
        if len(self._sessions) >= self._max_sessions:
            oldest = min(self._sessions.values(), key=lambda item: item.created_at)
            self._sessions.pop(oldest.session_id, None)

        now = float(self._clock())
        generation = self.settings.synthetic_dataset_generation
        session = PublicSession(
            session_id=f"{generation}_{secrets.token_urlsafe(24)}",
            csrf_token=secrets.token_urlsafe(32),
            persona=persona,
            actor_id=_ACTORS[persona],
            dataset_generation=generation,
            created_at=now,
            expires_at=now + self.settings.public_session_ttl_seconds,
        )
        self._sessions[session.session_id] = session
        return session, self._cookie_value(session)

    def resolve(self, cookie_value: str | None) -> PublicSession:
        session_id, expiry = self._verified_cookie(cookie_value)

        now = float(self._clock())
        session = self._sessions.get(session_id)
        if expiry <= now:
            raise PublicSessionExpiredError("Public session expired.")
        if session is None:
            raise PublicSessionError("Public session is not in the local cache.")
        if session.expires_at <= now:
            self._sessions.pop(session_id, None)
            raise PublicSessionExpiredError("Public session expired.")
        if self._revoked.get(session_id, 0) > now:
            raise PublicSessionError("Invalid public session.")
        return session

    async def persist(self, session: PublicSession) -> None:
        if self._redis is None:
            return
        payload = {
            "session_id": session.session_id,
            "csrf_token": session.csrf_token,
            "persona": session.persona.value,
            "actor_id": session.actor_id,
            "created_at": session.created_at,
            "expires_at": session.expires_at,
            "write_count": session.write_count,
            "upload_ids": sorted(session.upload_ids),
            "dataset_generation": session.dataset_generation,
        }
        try:
            ttl = max(1, int(session.expires_at - float(self._clock())))
            await self._redis.set(
                f"kraken:{self.settings.synthetic_dataset_generation}:public:session:{session.session_id}",
                json.dumps(payload),
                ex=ttl,
            )
        except Exception:
            return

    async def restore(self, cookie_value: str | None) -> PublicSession:
        session_id, _ = self._verified_cookie(cookie_value)
        if self._redis is None:
            raise PublicSessionError("Invalid public session.")
        try:
            raw = await self._redis.get(
                f"kraken:{self.settings.synthetic_dataset_generation}:public:session:{session_id}"
            )
            if not raw:
                raise PublicSessionError("Invalid public session.")
            data = json.loads(raw)
            if data.get("dataset_generation") != self.settings.synthetic_dataset_generation:
                raise PublicSessionError("Session belongs to an inactive dataset generation.")
            session = PublicSession(
                session_id=str(data["session_id"]),
                csrf_token=str(data["csrf_token"]),
                persona=OperationalPersona(str(data["persona"])),
                actor_id=str(data["actor_id"]),
                dataset_generation=str(data["dataset_generation"]),
                created_at=float(data["created_at"]),
                expires_at=float(data["expires_at"]),
                write_count=int(data.get("write_count", 0)),
                upload_ids=set(data.get("upload_ids", [])),
            )
            self._sessions[session_id] = session
            return session
        except PublicSessionError:
            raise
        except Exception as exc:
            raise PublicSessionError("Invalid public session.") from exc

    async def revoke_remote(self, session: PublicSession) -> None:
        self.revoke(session)
        if self._redis is None:
            return
        try:
            await self._redis.delete(
                f"kraken:{self.settings.synthetic_dataset_generation}:public:session:{session.session_id}"
            )
        except Exception:
            return

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()

    def require_csrf(self, session: PublicSession, token: str | None) -> None:
        if not token or not hmac.compare_digest(session.csrf_token, token):
            raise PublicSessionError("Invalid CSRF proof.")

    def transition(self, session: PublicSession, persona: OperationalPersona) -> PublicSession:
        session.persona = persona
        session.actor_id = _ACTORS[persona]
        return session

    def revoke(self, session: PublicSession) -> None:
        self._sessions.pop(session.session_id, None)
        self._revoked[session.session_id] = session.expires_at

    def check_query_limit(self, client_ip: str) -> tuple[bool, int, int]:
        now = float(self._clock())
        cutoff = now - self.settings.public_query_window_seconds
        timestamps = self._queries[client_ip]
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if len(timestamps) >= self.settings.public_query_limit:
            retry_after = max(
                1, int(timestamps[0] + self.settings.public_query_window_seconds - now)
            )
            return False, 0, retry_after
        timestamps.append(now)
        return True, self.settings.public_query_limit - len(timestamps), 0

    def consume_write(self, session: PublicSession) -> tuple[bool, int]:
        if session.write_count >= self.settings.public_write_limit:
            return False, max(1, int(session.expires_at - float(self._clock())))
        session.write_count += 1
        return True, max(0, self.settings.public_write_limit - session.write_count)

    def cleanup(self) -> None:
        now = float(self._clock())
        for session_id, session in list(self._sessions.items()):
            if session.expires_at <= now:
                self._sessions.pop(session_id, None)
        for session_id, expiry in list(self._revoked.items()):
            if expiry <= now:
                self._revoked.pop(session_id, None)
        if len(self._queries) > 5_000:
            cutoff = now - self.settings.public_query_window_seconds
            for client_ip, timestamps in list(self._queries.items()):
                if not timestamps or timestamps[-1] <= cutoff:
                    self._queries.pop(client_ip, None)

    def response(self, session: PublicSession) -> PublicSessionResponse:
        return PublicSessionResponse(
            session_id=session.session_id,
            csrf_token=session.csrf_token,
            persona=session.persona,
            actor_id=session.actor_id,
            expires_at=datetime.fromtimestamp(session.expires_at, tz=UTC),
            query_limit=self.settings.public_query_limit,
            write_limit=self.settings.public_write_limit,
            dataset_generation=self.settings.synthetic_dataset_generation,
        )
