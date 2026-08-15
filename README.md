# KRAKEN — Knowledge Retrieval & Autonomous Knowledge Execution Network

[![CI](https://github.com/JavithNaseem-J/Autonomous-Knowledge-Execution-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/JavithNaseem-J/Autonomous-Knowledge-Execution-Agent/actions/workflows/ci.yml)

KRAKEN is a production-grade, microservice-based autonomous AI agent built with FastAPI, LangGraph, PostgreSQL (pgvector + PostgresSaver), Redis, and Qdrant Cloud. It handles complex cybersecurity support queries, performs RAG over domain knowledge, executes safe actions autonomously, and routes high-risk operations through a Human-in-the-Loop (HITL) approval queue with an append-only cryptographic audit trail.

For a detailed topology and sequence diagrams of the HITL workflow, see the [System Architecture Documentation](docs/architecture.md).

---

## 🌟 Key Architecture & Security Features

- **Microservice Architecture**: 7 decoupled microservices communicating asynchronously over HTTP with timing-attack safe service tokens.
- **LangGraph State Machine**: ReAct agent orchestrator with state persistence, checkpointer recovery, and concurrency limits.
- **Human-in-the-Loop (HITL) Security**: Automated risk-classification that pauses CRITICAL actions for human review via CSRF-protected Web UI.
- **Append-Only Cryptographic Audit Trail**: Every executed action is signed into a SHA-256 hash-chain stored in PostgreSQL with keyset-paginated verification.
- **Qdrant Vector RAG**: Hybrid search combining dense embeddings (BAAI/bge-small-en), keyword frequency RRF fusion, and payload-filtered ticket isolation.
- **Production Observability**: OpenTelemetry tracing, Prometheus `/metrics` endpoints, and Langfuse LLM monitoring.

## Prerequisites

- **Python 3.12+**
- **Docker & Docker Compose**
- **Groq API Key** (or any OpenAI-compatible LLM endpoint)

---

## Quickstart

Follow these 5 commands to spin up the full 7-service stack:

```bash
# 1. Clone the repository and navigate into the directory
cd Autonomous-Knowledge-Execution-Agent

# 2. Configure environment variables
cp .env.example .env
# Edit .env to set your LLM_API_KEY (e.g. gsk_...) and a unique
# HITL_SERVICE_TOKEN (>= 32 chars; generate with:
#   python -c "import secrets; print(secrets.token_hex(32))")
# The app refuses to start with the default/short token — in EVERY environment.

# 2b. (Recommended) Install the secret-scanning pre-commit hook
pip install pre-commit && pre-commit install
# gitleaks will now block any commit that contains a live credential.

# 3. Start all microservices in detached mode
make up

# 4. Ingest domain knowledge (FAQ, SLA policies, sample tickets) into Qdrant Cloud
make ingest

# 5. Run the end-to-end evaluation harness
make eval
```

Once running, access the React web frontend chat UI at [http://localhost:5173](http://localhost:5173) or gateway at [http://localhost:8000](http://localhost:8000).

---

## Service Topology Overview

| Service | Port | Description |
|---------|------|-------------|
| **Gateway** | `:8000` | Edge API Gateway, API Key Auth, Sliding-Window Rate Limiter |
| **Orchestrator** | `:8001` | Core Intelligence — LangGraph ReAct Agent with State Persistence |
| **Knowledge** | `:8002` | Vector Store RAG engine (Qdrant Cloud + BAAI/bge-small-en embeddings) |
| **Action** | `:8003` | Ticket Management & Safe Workspace Execution Sandbox |
| **Approval** | `:8004` | Human-in-the-Loop (HITL) Approval Queue & Form |
| **Memory** | `:8005` | Short-term Redis Session Memory & Long-term pgvector Memory |
| **Audit** | `:8006` | Append-Only PostgreSQL Audit Log Service |

---

## Development Commands

```bash
make install-dev  # Install development dependencies
make test         # Run pytest unit test suite
make lint         # Run ruff check
make format       # Run ruff format
make type-check   # Run mypy type checker across shared/ and services/
make status       # Run health aggregator across all 7 microservices
make down         # Stop containers and remove network
```
