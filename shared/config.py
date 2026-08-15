from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Environment ───────────────────────────────────────────────────────────
    environment: Literal["dev", "staging", "prod"] = "dev"

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"
    llm_fallback_model: str = "llama-3.1-8b-instant"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096
    llm_timeout_seconds: int = 60

    # ── Embeddings (Cloud API or Local HuggingFace) ───────────────────────────
    embedding_provider: Literal["cloud", "openai", "local"] = "cloud"
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_device: str = "cpu"
    embedding_dim: int = 0
    retrieval_top_k: int = 5

    # ── Databases ────────────────────────────────────────────────────────────
    # Leave empty to run in degraded/in-memory mode (no persistent storage).
    # Set to a real connection string for production-grade Postgres persistence.
    postgres_url: str = ""
    # psycopg3 sync DSN for PostgresSaver (langgraph-checkpoint-postgres)
    postgres_sync_url: str = ""
    postgres_keepalives: int = 1
    postgres_keepalives_idle: int = 30
    postgres_keepalives_interval: int = 10
    postgres_keepalives_count: int = 5
    postgres_max_idle_time: float = 300.0
    # Leave empty to run with no Redis (rate-limiting and caching will be degraded).
    redis_url: str = ""
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection_name: str = "kraken_knowledge"

    # ── Observability & Caching ──────────────────────────────────────────────
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    semantic_cache_enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def resolve_api_keys(cls, values: dict) -> dict:
        if isinstance(values, dict):
            import os

            llm_key = (
                values.get("llm_api_key")
                or os.getenv("LLM_API_KEY")
                or os.getenv("GROQ_API_KEY")
                or os.getenv("OPENAI_API_KEY")
                or ""
            )
            values["llm_api_key"] = llm_key.strip()
            if not values.get("embedding_api_key"):
                values["embedding_api_key"] = (
                    os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY") or llm_key.strip()
                )
            if not values.get("embedding_dim"):
                model_name = str(values.get("embedding_model", "text-embedding-3-small")).lower()
                if "3-small" in model_name or "ada" in model_name:
                    values["embedding_dim"] = 1536
                else:
                    values["embedding_dim"] = 384
        return values

    @field_validator("postgres_url")
    @classmethod
    def validate_postgres_url(cls, v: str) -> str:
        # Empty string = no Postgres configured (degraded / in-memory mode)
        if v == "":
            return v
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "postgres_url must start with 'postgresql+asyncpg://' for asyncpg compatibility."
            )
        return v

    # ── Orchestrator Concurrency ──────────────────────────────────────────────
    orchestrator_max_concurrency: int = 5
    orchestrator_workers: int = 4

    # ── Internal Service URLs (overridden per-container in docker-compose) ───
    orchestrator_url: str = "http://localhost:8001"
    knowledge_url: str = "http://localhost:8002"
    action_url: str = "http://localhost:8003"
    approval_url: str = "http://localhost:8004"
    memory_url: str = "http://localhost:8005"
    audit_url: str = "http://localhost:8006"

    gateway_api_keys: str = (
        "dev-key-alice-longer-secure-key:alice,dev-key-bob-longer-secure-key:bob"
    )
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:3000,https://*.onrender.com,*"
    gateway_rate_limit_requests: int = 60
    gateway_rate_limit_window_seconds: int = 60

    # ── HITL Approval ────────────────────────────────────────────────────────
    approval_timeout_seconds: int = 900  # 15 minutes
    # External or human-accessible URL of the approval service
    approval_base_url: str = "http://localhost:8004"
    # Shared secret the approval service sends as X-Service-Token header
    # on every /approval-callback request. Must match in both services.
    hitl_service_token: str = "change-me-in-production"
    orchestrator_service_token: str = ""
    approval_service_token: str = ""
    action_service_token: str = ""
    knowledge_service_token: str = ""
    memory_service_token: str = ""
    audit_service_token: str = ""

    @model_validator(mode="after")
    def validate_production_secrets(self) -> Settings:
        default_token = "change-me-in-production"
        if self.hitl_service_token == default_token:
            raise ValueError(
                "hitl_service_token is still set to the shipped default "
                "('change-me-in-production'). Set a unique HITL_SERVICE_TOKEN of "
                "at least 32 characters in your environment or secrets manager."
            )
        if len(self.hitl_service_token) < 32:
            raise ValueError(
                f"hitl_service_token is too short ({len(self.hitl_service_token)} chars). "
                "It must be at least 32 characters."
            )

        # Validate per-service tokens if specified
        for name in [
            "orchestrator_service_token",
            "approval_service_token",
            "action_service_token",
            "knowledge_service_token",
            "memory_service_token",
            "audit_service_token",
        ]:
            val = getattr(self, name)
            if val and (val == default_token or len(val) < 32):
                raise ValueError(f"{name} is invalid. It must be at least 32 characters long.")
        return self

    @model_validator(mode="after")
    def validate_no_local_hosts(self) -> Settings:
        """Fail fast in non-dev environments when any URL still points to a local host.

        Optional backing services (postgres, redis, qdrant) use empty string as their
        'not configured' sentinel — KRAKEN will boot in degraded/in-memory mode for
        those services. Only non-empty URLs are checked so cloud deployments without
        optional services still boot successfully.

        Required inter-service URLs (orchestrator, knowledge, action, approval, memory,
        audit) are always checked because Render injects them via `fromService`.
        """
        from urllib.parse import urlparse

        if self.environment == "dev":
            return self

        local_hostnames: frozenset[str] = frozenset(
            {
                "localhost",
                "127.0.0.1",
                "0.0.0.0",
                "postgres",
                "redis",
            }
        )

        # All URLs to check — empty string means "not configured", skip.
        all_fields: dict[str, str] = {
            "postgres_url": self.postgres_url,
            "postgres_sync_url": self.postgres_sync_url,
            "redis_url": self.redis_url,
            "orchestrator_url": self.orchestrator_url,
            "knowledge_url": self.knowledge_url,
            "action_url": self.action_url,
            "approval_url": self.approval_url,
            "memory_url": self.memory_url,
            "audit_url": self.audit_url,
        }

        offenders: list[str] = []
        for field_name, url in all_fields.items():
            if not url:
                continue  # Empty = not configured, service runs in degraded mode
            try:
                hostname = urlparse(url).hostname or ""
            except Exception:  # noqa: BLE001
                hostname = ""
            if hostname in local_hostnames:
                offenders.append(f"  {field_name} = {url!r}  (host: {hostname!r})")

        if offenders:
            raise ValueError(
                f"Local/compose hostnames are not allowed in environment={self.environment!r}. "
                "All service URLs must point to cloud-managed endpoints. "
                "Offending fields:\n" + "\n".join(offenders)
            )
        return self

    # ── Observability ────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "console"  # "console" | "json"


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Call this everywhere instead of Settings()."""
    return Settings()
