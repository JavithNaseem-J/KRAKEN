# KRAKEN — Knowledge Retrieval & Autonomous Knowledge Execution Network

[![CI](https://github.com/JavithNaseem-J/Autonomous-Knowledge-Execution-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/JavithNaseem-J/Autonomous-Knowledge-Execution-Agent/actions/workflows/ci.yml)

KRAKEN is a production-grade autonomous AI agent system built with FastAPI, LangGraph, PostgreSQL (Audit & Ticket Store), Redis, and Qdrant (Knowledge RAG, Semantic Cache & Episodic Memory). It handles complex cybersecurity and IT support queries, performs hybrid vector RAG over domain knowledge, executes safe actions autonomously, and routes high-risk operations through a Human-in-the-Loop (HITL) approval queue with an append-only cryptographic audit trail.

For a detailed topology and sequence diagrams of the HITL workflow, see the [System Architecture Documentation](docs/architecture.md). For the internal LangGraph reasoning state machine, node contracts, and prompt versioning guide, see the [Agent Pipeline Documentation](docs/agent-pipeline.md).

---

## 🌟 Key Architecture & Security Features

- **Consolidated Monolith Architecture**: Edge API Gateway and in-process subsystems (Orchestrator, Knowledge, Action, Approval, Memory, Audit) run in a single process with robust in-process ASGI routing and zero internal TCP listeners.
- **LangGraph State Machine**: ReAct agent orchestrator with state persistence, checkpointer recovery, and concurrency limits.
- **Human-in-the-Loop (HITL) Security**: Automated risk-classification that pauses CRITICAL actions for human review via CSRF-protected Web UI and API endpoints.
- **Append-Only Cryptographic Audit Trail**: Every executed action is signed into a SHA-256 hash-chain stored in PostgreSQL with keyset-paginated verification.
- **Unified Qdrant Vector Engine**: Qdrant Cloud Inference, grounded knowledge RAG, versioned semantic caching, and session-private uploads.
- **Public Demo Isolation**: Signed one-hour anonymous sessions, server-validated personas, synthetic ticket overlays, query/write quotas, and no browser credentials.
- **Production Observability**: Prometheus `/metrics` endpoints and Langfuse LLM monitoring.

---

## Prerequisites

- **Python 3.12+**
- **uv** (or pip)
- **Docker & Docker Compose** (optional for local containerized run)
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

### Option B: Docker Compose

```bash
# Start the full stack (App + PostgreSQL + Redis + React frontend)
docker compose up -d

# Ingest domain knowledge into vector store
python scripts/ingest_knowledge.py

# Run evaluation harness against the running system
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

---

## Development Commands

```bash
make install-dev  # Install development dependencies with uv sync
make test         # Run pytest unit test suite
make lint         # Run ruff check
make format       # Run ruff format
make type-check   # Run mypy type checker across src/
make status       # Run health check across consolidated app endpoints
make up           # Start Docker Compose services
make down         # Stop containers
```
