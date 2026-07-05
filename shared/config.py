"""
Centralised configuration for all AKEA services.
Every service imports get_settings() — never reads env vars directly.
All fields added here must also appear in .env.example.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_provider: str = "groq"
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-oss-120b"
    llm_fallback_model: str = "llama-3.1-70b-versatile"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096
    llm_timeout_seconds: int = 60

    # ── Embeddings (Local HuggingFace via Langchain) ─────────────────────────
    embedding_model: str = "BAAI/bge-small-en"
    embedding_device: str = "cpu"
    retrieval_top_k: int = 5

    # ── Databases ────────────────────────────────────────────────────────────
    postgres_url: str = "postgresql+asyncpg://agent:agent@localhost:5432/akea"
    # psycopg3 sync DSN for PostgresSaver (langgraph-checkpoint-postgres)
    postgres_sync_url: str = "postgresql://agent:agent@localhost:5432/akea"
    redis_url: str = "redis://localhost:6379/0"
    chroma_persist_dir: str = "./data/chroma"

    @field_validator("postgres_url")
    @classmethod
    def validate_postgres_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "postgres_url must start with 'postgresql+asyncpg://' for asyncpg compatibility."
            )
        return v

    # ── Service Ports ────────────────────────────────────────────────────────
    gateway_port: int = 8000
    orchestrator_port: int = 8001
    knowledge_port: int = 8002
    action_port: int = 8003
    approval_port: int = 8004
    memory_port: int = 8005
    audit_port: int = 8006

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
    gateway_rate_limit_requests: int = 10
    gateway_rate_limit_window_seconds: int = 60

    # ── HITL Approval ────────────────────────────────────────────────────────
    approval_timeout_seconds: int = 900  # 15 minutes
    # External or human-accessible URL of the approval service
    approval_base_url: str = "http://localhost:8004"
    # Shared secret the approval service sends as X-Service-Token header
    # on every /approval-callback request. Must match in both services.
    hitl_service_token: str = "change-me-in-production"

    # ── Observability ────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "console"  # "console" | "json"
    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_project: str = "akea"


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Call this everywhere instead of Settings()."""
    return Settings()
