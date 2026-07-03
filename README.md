# Autonomous Knowledge Execution Agent (AKEA)

> A production-grade autonomous AI agent that retrieves internal knowledge, reasons over it, and executes actions — with a mandatory Human-in-the-Loop approval gate for all write operations.

---

## Overview

AKEA is a 7-service microservice system built for internal IT helpdesk teams. Given a natural-language request, the agent:

1. **Plans** a sequence of steps to answer it
2. **Retrieves** relevant knowledge from three sources (FAQ, Tickets, SLA rules)
3. **Reasons** over the retrieved chunks using a 120B LLM
4. **Decides** the appropriate action (read a ticket, list tickets, or write a file)
5. **Gates** all write operations behind a human approval step
6. **Executes** the approved action within a strict sandbox
7. **Persists** the interaction to short-term and long-term memory

---

## Architecture

```
External Request
       │
       ▼
┌──────────────┐   Auth + Rate Limit
│   Gateway    │ ──────────────────── Redis
│  :8000       │
└──────┬───────┘
       │
       ▼
┌──────────────┐   LangGraph Agent (7 nodes)
│ Orchestrator │ ──────────────────── MemorySaver
│  :8001       │
└──┬──────┬────┘
   │      │
   ▼      ▼
┌─────┐ ┌────────┐
│Know │ │ Action │
│ledge│ │  :8003 │
│:8002│ └──┬─────┘
└─────┘    │
           ▼ (WRITE only)
     ┌──────────┐   Redis Queue
     │ Approval │ ──────────────── Human Browser UI
     │  :8004   │
     └──────────┘

Shared infrastructure:
  PostgreSQL + pgvector  ← Audit log (append-only) + Episodic memory
  Redis                  ← Session memory + Rate limiting + Approval queue
  ChromaDB               ← Vector knowledge store (FAQ / Tickets / SLA)
```

### Services

| Service | Port | Role |
|---|---|---|
| `gateway` | 8000 | Auth, rate limiting, request routing |
| `orchestrator` | 8001 | LangGraph agent graph execution |
| `knowledge` | 8002 | ChromaDB retrieval (3 sources) |
| `action` | 8003 | Read/write handler with path safety |
| `approval` | 8004 | HITL queue (Redis) + browser approval UI |
| `memory` | 8005 | Redis session + pgvector episodic memory |
| `audit` | 8006 | Append-only PostgreSQL audit log |

---

## Quick Start

### Prerequisites
- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Python 3.11+
- Git

### 1. Clone and configure

```bash
git clone https://github.com/your-org/autonomous-knowledge-execution-agent
cd autonomous-knowledge-execution-agent
cp .env.example .env
```

Edit `.env` and set your API key:
```env
LLM_API_KEY=your_groq_or_nvidia_api_key
LLM_BASE_URL=https://api.groq.com/openai/v1   # or NVIDIA NIM URL
LLM_MODEL=gpt-oss-120b
```

### 2. Install dev dependencies

```bash
make install-dev
```

### 3. Start infrastructure and services

```bash
make up
```

This starts all 7 services + PostgreSQL + Redis + ChromaDB. Wait ~30 seconds for health checks to pass.

### 4. Ingest knowledge base

```bash
make ingest
```

Embeds all documents in `data/knowledge/` into ChromaDB. Run once, or after adding new documents.

### 5. Seed sample data (optional)

```bash
python scripts/seed_data.py
```

Creates 3 sample tickets in `data/knowledge/tickets/sample_tickets.json`.

### 6. Send your first query

```bash
curl -X POST http://localhost:8000/v1/run \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-alice" \
  -d '{"message": "What is the SLA for a critical priority ticket?"}'
```

### 7. Run the test suite

```bash
make test
```

### 8. Run the evaluation harness (requires live system)

```bash
python tests/evals/eval_harness.py --api-key dev-key-alice
```

---

## Knowledge Base Setup

Add your documents to these directories before running `make ingest`:

| Directory | Content | Format |
|---|---|---|
| `data/knowledge/faq/` | IT support policies, procedures, FAQs | `.pdf`, `.md`, `.txt` |
| `data/knowledge/tickets/` | Historical ticket records | `.json`, `.csv` |
| `data/knowledge/sla/` | SLA rules and escalation definitions | `.json` |

**SLA JSON schema:**
```json
{
  "id": "SLA-001",
  "name": "Critical Priority SLA",
  "priority": "critical",
  "response_time_hours": 1,
  "resolution_time_hours": 4,
  "escalation_path": ["L1 Support", "L2 Support", "Manager"],
  "notes": "Optional description"
}
```

---

## API Reference

### `POST /v1/run`

Submit a natural-language query to the agent.

**Headers:**
```
X-API-Key: your-api-key
Content-Type: application/json
```

**Request:**
```json
{
  "message": "What is the SLA for a critical priority ticket?",
  "session_id": "optional-session-uuid"
}
```

**Response (completed run):**
```json
{
  "session_id": "abc-123",
  "answer": "Critical priority tickets have a 1-hour response time...",
  "reasoning": "RELEVANT INFORMATION:\n- ...",
  "action_taken": "respond_only",
  "action_result": null,
  "sources": ["faq", "sla"]
}
```

**Response (HITL triggered — WRITE action):**
```json
{
  "status": "pending_approval",
  "approval_id": "uuid",
  "session_id": "abc-123",
  "message": "A WRITE action requires human approval. Check the approval service."
}
```

When `pending_approval` is returned, open the URL printed in the approval service terminal.

### `POST /v1/approval-callback`

Submit an approval decision after reviewing at the HITL UI.

```json
{
  "approval_id": "uuid-from-pending-response",
  "decision": "approve"
}
```

---

## Security Model

### Write Sandbox

All file writes are restricted to `data/workspace/`. This path is **hardcoded** in `services/action/safety/path_validator.py` and cannot be changed via environment variables or configuration. Every write target is validated with:

1. `Path.resolve()` to canonicalise — no symlink tricks
2. `str(resolved).startswith(str(WORKSPACE_ROOT))` — no directory traversal
3. Extension allowlist: `.json` only — no executable uploads

### Human-in-the-Loop

- **READ actions** (respond_only, read_ticket, read_ticket_list): execute automatically
- **WRITE actions** (write_json_file): unconditionally trigger HITL

The HITL gate cannot be disabled. It is implemented using LangGraph's `interrupt()` function which suspends the graph — the action service is never called until `Command(resume=...)` resumes execution after a human decision.

### Rate Limiting

Sliding window: 10 requests/minute per user (configurable via `GATEWAY_RATE_LIMIT_REQUESTS`).

### Audit Log

Every action is written to the `audit_log` PostgreSQL table. The table has `CREATE RULE` statements that reject `UPDATE` and `DELETE` — the log is append-only at the **database level**, not just the application level.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_API_KEY` | — | API key for LLM provider (required) |
| `LLM_BASE_URL` | Groq URL | OpenAI-compatible base URL |
| `LLM_MODEL` | `gpt-oss-120b` | Model name |
| `LLM_TEMPERATURE` | `0.0` | Temperature for deterministic decisions |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en` | Local embedding model |
| `EMBEDDING_DEVICE` | `cpu` | `cpu` or `cuda` |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |
| `POSTGRES_URL` | see .env.example | PostgreSQL connection URL |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | ChromaDB persistence directory |
| `APPROVAL_TIMEOUT_SECONDS` | `900` | HITL approval timeout (15 minutes) |
| `APPROVAL_PORT` | `8004` | Port printed in terminal approval notice |
| `GATEWAY_API_KEYS` | `dev-key-alice:alice` | API key:user_id pairs (comma-separated) |
| `GATEWAY_RATE_LIMIT_REQUESTS` | `10` | Max requests per window per user |
| `GATEWAY_RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window in seconds |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `console` | `console` (dev) or `json` (prod) |

---

## Development

### Running tests

```bash
make test                    # All tests
make test -k unit            # Unit tests only
make test -k integration     # Integration tests only
```

### Linting and type checking

```bash
make lint         # ruff
make format       # ruff --fix
make type-check   # mypy
```

### Viewing logs

```bash
make logs                          # All services
docker compose logs orchestrator   # Single service
```

### Stopping and cleaning up

```bash
make down       # Stop containers (preserves volumes)
make clean      # Stop + delete volumes (resets all data)
```

---

## Data Flow

```
User Request
  → Gateway (auth + rate limit)
    → Orchestrator /run
      → Planner    (LLM: decompose into steps)
      → Retriever  (HTTP → Knowledge /retrieve → ChromaDB)
      → Reasoner   (LLM: analyse chunks → RELEVANT / GAPS / CONCLUSION)
      → Decider    (LLM structured output → action + payload)
        │
        ├─ SAFE  ──→ Executor → Action /execute → Read Handler
        │                     ↓
        │              Audit /log (fire-and-forget)
        │
        └─ CRITICAL → Executor → Approval /pending (Redis enqueue)
                               → [interrupt() — graph paused]
                               → Human opens browser URL
                               → Human clicks Approve/Reject
                               → Approval /decision
                               → Orchestrator /approval-callback
                               → [Command(resume=) — graph resumes]
                               → Action /execute → Write Handler
                               → (validate → backup → atomic write)
      → Responder  (LLM: compose final answer)
      → MemoryWriter (Redis session + pgvector episode)
    ← Final answer (or pending_approval)
  ← Response with X-RateLimit-* headers
```

---

## Evaluation

Run the golden dataset harness against a live system:

```bash
python tests/evals/eval_harness.py \
  --base-url http://localhost:8000 \
  --api-key dev-key-alice \
  --threshold 0.7
```

The harness scores each case across 4 dimensions:
- **Keyword coverage** — expected terms found in the answer
- **Action match** — correct action type selected
- **HITL correctness** — HITL fired when and only when expected
- **Source coverage** — correct knowledge sources cited

Exit code `0` = all cases pass. Exit code `1` = any case below threshold.

---

## Project Structure

```
.
├── services/
│   ├── gateway/       # Auth, rate limiting, routing
│   ├── orchestrator/  # LangGraph agent (7 nodes)
│   │   └── graph/
│   │       └── nodes/ # planner, retriever, reasoner, decider,
│   │                  # executor, responder, memory_writer
│   ├── knowledge/     # ChromaDB retrieval + /retrieve endpoint
│   │   └── loaders/   # faq_loader, ticket_loader, sla_loader
│   ├── action/        # Read/write handlers + audit integration
│   │   ├── handlers/  # read_handler, write_handler
│   │   └── safety/    # path_validator, backup
│   ├── approval/      # Redis queue + HITL web UI
│   ├── memory/        # Redis short-term + pgvector long-term
│   └── audit/         # Append-only PostgreSQL audit log
├── shared/            # Config, models, exceptions (shared across services)
├── data/
│   ├── knowledge/     # faq/ tickets/ sla/ — source documents
│   └── workspace/     # WRITE SANDBOX — agent can only write here
├── scripts/           # ingest_knowledge.py, seed_data.py, init.sql
├── tests/
│   ├── unit/          # Zero-infra unit tests
│   ├── integration/   # In-memory or mocked infra tests
│   └── evals/         # Golden dataset + eval harness
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | `gpt-oss-120b` via Groq / NVIDIA NIM (OpenAI-compatible API) |
| Agent framework | LangGraph 0.2+ (StateGraph + interrupt/resume for HITL) |
| LLM client | LangChain + `langchain-openai` |
| Embeddings | `BAAI/bge-small-en` via `sentence-transformers` (local CPU, 384-dim) |
| Vector store | ChromaDB (persistent, cosine similarity) |
| Web framework | FastAPI + Uvicorn |
| Async HTTP | `httpx` (async client for inter-service calls) |
| Cache / Queue | Redis 7 (session memory + rate limiting + approval queue) |
| Relational DB | PostgreSQL 16 + `pgvector` (episodic memory + audit log) |
| Serialisation | Pydantic v2 |
| Logging | `structlog` (JSON in prod, colored in dev) |
| Containerisation | Docker Compose |
| Testing | `pytest` + `pytest-asyncio` + `fakeredis` |
| Linting | `ruff` + `mypy` |

---

## License

MIT — see [LICENSE](LICENSE).
