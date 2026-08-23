# Contributing to KRAKEN

## Service Lifespan Pattern

Each API module in `src/api/` owns its own FastAPI `lifespan` context manager rather than sharing a common factory.

**Why:** KRAKEN services are independently deployable units. A shared `create_service_app()` factory would couple their startup sequencing, making it harder to add service-specific initialization steps (e.g., a custom readiness probe, a service-specific warm-up call) without touching shared infrastructure.

**Pattern** (see `src/api/action.py` as the canonical example):

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(log_level=settings.log_level, log_format=settings.log_format, service="<name>")
    log.info("<name>.startup")

    app.state.http = create_async_http_client()
    yield

    await app.state.http.aclose()
    log.info("<name>.shutdown")
```

**What belongs in lifespan:**
- `configure_logging()` — always first
- Shared `httpx.AsyncClient` on `app.state.http`
- Any service-specific warm-up (e.g., DB ping, cache init)

**What does NOT belong in lifespan:**
- Business logic
- Request-scoped state

---

## Prompt Management

All system prompts and prompt templates are strictly isolated from node logic files:

- **Location**: Prompts live in `src/prompts/`, organized as versioned modules (e.g., `reasoner_v1.py`, `decider_v1.py`, `responder_v1.py`).
- **Registry**: `src/prompts/registry.py` maintains the active version manifest (`ACTIVE_VERSIONS`) and exports the `@lru_cache`-backed `get_prompt(node_name, prompt_key)` loader.
- **Rule**: Never hardcode prompts or prompt strings inside `src/agent/nodes/*.py`.
- **Modifying Prompts**: Create a new versioned file (e.g., `decider_v2.py`), update `ACTIVE_VERSIONS["decider"]`, run `pytest tests/unit/agent/test_prompt_registry.py`, and restart the application service.

For complete node contracts and prompt architecture, see [Agent Pipeline](docs/agent-pipeline.md).

---

*This file is maintained as part of the KRAKEN codebase hygiene spec (`openspec/specs/codebase-hygiene`).*
