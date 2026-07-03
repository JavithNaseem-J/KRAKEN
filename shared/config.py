"""
Centralised configuration for all AKEA services.
Every service imports get_settings() — never reads env vars directly.
"""
from functools import lru_cache
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

    # ── Embeddings (local) ────────────────────────────────────────────────────
    embedding_model: str = "BAAI/bge-small-en"
    embedding_device: str = "cpu"

    # ── Databases ─────────────────────────────────────────────────────────────
    postgres_url: str = "postgresql+asyncpg://agent:agent@localhost:5432/akea"
    redis_url: str = "redis://localhost:6379/0"
    chroma_persist_dir: str = "./data/chroma"

    # ── Service Ports ─────────────────────────────────────────────────────────
    gateway_port: int = 8000
    orchestrator_port: int = 8001
    knowledge_port: int = 8002
    action_port: int = 8003
    approval_port: int = 8004
    memory_port: int = 8005
    audit_port: int = 8006

    # ── Internal Service URLs ─────────────────────────────────────────────────
    # Overridden per-container in docker-compose.yml
    orchestrator_url: str = "http://localhost:8001"
    knowledge_url: str = "http://localhost:8002"
    action_url: str = "http://localhost:8003"
    approval_url: str = "http://localhost:8004"
    memory_url: str = "http://localhost:8005"
    audit_url: str = "http://localhost:8006"

    # ── Security ──────────────────────────────────────────────────────────────
    api_key: str = "dev-key-change-in-production"

    # ── HITL ──────────────────────────────────────────────────────────────────
    approval_timeout_seconds: int = 900  # 15 minutes

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    rate_limit_requests_per_minute: int = 10

    # ── Observability ─────────────────────────────────────────────────────────
    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_project: str = "akea"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Call this everywhere instead of Settings()."""
    return Settings()
