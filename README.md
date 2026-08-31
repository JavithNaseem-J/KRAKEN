# KRAKEN — Knowledge Retrieval & Autonomous Knowledge Execution Network

[![CI](https://github.com/JavithNaseem-J/Autonomous-Knowledge-Execution-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/JavithNaseem-J/Autonomous-Knowledge-Execution-Agent/actions/workflows/ci.yml)

KRAKEN is a production-grade autonomous AI agent system built with FastAPI, LangGraph, PostgreSQL (Audit & Ticket Store), Redis, and Qdrant (Knowledge RAG, Semantic Cache & Episodic Memory). It handles complex cybersecurity and IT support queries, performs hybrid vector RAG over domain knowledge, executes safe actions autonomously, and routes high-risk operations through a Human-in-the-Loop (HITL) approval queue with an append-only cryptographic audit trail.

The [production demo design](docs/superpowers/specs/2026-08-24-production-demo-design.md) records the public deployment boundaries, safety model, and acceptance contract.

---

## 🌟 Key Architecture & Security Features

- **Consolidated Monolith Architecture**: Edge API Gateway and in-process subsystems (Orchestrator, Knowledge, Action, Approval, Memory, Audit) run in a single process with robust in-process ASGI routing and zero internal TCP listeners.
- **LangGraph State Machine**: ReAct agent orchestrator with state persistence, checkpointer recovery, and concurrency limits.
- **Human-in-the-Loop (HITL) Security**: Automated risk-classification that pauses CRITICAL actions for human review via CSRF-protected Web UI and API endpoints.
- **Append-Only Cryptographic Audit Trail**: Every executed action is signed into a SHA-256 hash-chain stored in PostgreSQL with keyset-paginated verification.
- **Unified Qdrant Vector Engine**: Qdrant Cloud Inference, grounded knowledge RAG, versioned semantic caching, and session-private uploads.
- **Public Demo Isolation**: Signed one-hour anonymous sessions, server-validated personas, synthetic ticket overlays, query/write quotas, and no browser credentials.
- **Private Model Deliberation**: Model reasoning is untracked agent state and is excluded from public APIs, SSE events, browser storage, caches, approvals, action requests, and audit records.
- **Production Observability**: Prometheus `/metrics`, structured redacted logs, trace IDs, and execution timing without prompt or model-output capture.

---

## Prerequisites

- **Python 3.12+**
- **uv** (or pip)
- **Docker** (optional for a local containerized run)
- **Groq API Key** (or any OpenAI-compatible LLM endpoint)

---

## Quickstart

### Option A: Local Python Standalone

```bash
# 1. Clone repository and navigate into directory
git clone https://github.com/JavithNaseem-J/Autonomous-Knowledge-Execution-Agent.git
cd Autonomous-Knowledge-Execution-Agent

# 2. Install dependencies with uv
uv sync --all-extras

# 3. Configure environment variables
cp .env.example .env
# Set Groq, Qdrant, Redis, Postgres, HITL, and demo-session secrets.

# 4. Start the application
python main.py
```

### Option B: Local Docker Image

```bash
# Build the same unified image used in production
docker build -t kraken:local .

# Run the React UI and API together using your local environment file
docker run --rm -p 8000:8000 --env-file .env -e PORT=8000 kraken:local
```

In another terminal, verify the running application:

```bash
python scripts/acceptance.py --base-url http://127.0.0.1:8000
python tests/evals/eval_harness.py --base-url http://localhost:8000
```

The production Docker image serves the React UI and API together at [http://localhost:8000](http://localhost:8000). A separate Vite server on port 5173 is optional during frontend development.

---

## Subsystem Architecture Overview

| Subsystem | Scope / Endpoint | Description |
|-----------|------------------|-------------|
| **Gateway** | `:8000` (`src.api.gateway:app`) | Edge API Gateway, API Key Auth, Sliding-Window Rate Limiter, Prompt Guard |
| **Orchestrator** | In-Process / `/run` | LangGraph ReAct Agent with checkpoint persistence and HITL interrupt |
| **Knowledge** | In-Process / `/retrieve` | Qdrant Cloud Inference RAG with shared and session-private scopes |
| **Action** | In-Process / `/execute` | Session-isolated synthetic ticket and containment adapters |
| **Approval** | In-Process & `:8000/approve/*` | Human-in-the-Loop (HITL) Approval Queue, Details & Decision endpoints |
| **Memory** | In-Process / `/session` | Short-term Redis Session Memory & Long-term Qdrant Episodic Memory |
| **Audit** | In-Process / `/log` | Cryptographically chained, append-only PostgreSQL Audit Log |

Public agent responses contain the final answer, action result, grounded sources, cache metadata, timing, and trace ID. They intentionally do not include model reasoning. Approval details use registry-derived `risk_level` and deterministic `approval_reason` fields.

---

## Development Commands

```bash
uv sync --all-extras
uv run pytest tests/unit -q
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
uv run mypy src scripts
cd frontend-react
npm ci
npm test
npm run lint
npm run build
```

---

## Production Deployment

GitHub Actions deploys only the exact `main` commit that completed CI successfully. Render automatic deployment must remain disabled because the deployment workflow calls the secret Render hook with that tested commit SHA.

Before the first deployment of this version:

1. Set `GATEWAY_API_KEYS` in Render to a JSON object whose keys are unique secrets and whose values contain `user_id` and `role`, for example `{"replace-with-a-random-secret":{"user_id":"portfolio-owner","role":"admin"}}`.
2. Confirm the GitHub production environment contains `RENDER_DEPLOY_HOOK_URL` and that the URL is never committed or logged.
3. Confirm the Render service Auto-Deploy setting is **Off**; `render.yaml` also declares `autoDeploy: false`.
4. After deployment, compare the Render commit with the `deploy_sha` shown by the successful deployment workflow.
