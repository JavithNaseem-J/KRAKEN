## Context

Removing OpenTelemetry (`opentelemetry-*`), `pgvector`, and legacy microservice boilerplate directories (`services/`, `shared/`) to establish a clean, production-grade AI Agent codebase under `src/`.

## Goals / Non-Goals

**Goals:**
- Remove OpenTelemetry code and standardize 100% on Langfuse for tracing.
- Remove `pgvector` reference in favor of Qdrant.
- Delete legacy microservices folders (`services/`, `shared/`).
- Verify 100% test pass rate across unit test suite.

**Non-Goals:**
- Removing offline benchmark tools or altering core agent graph nodes.

## Decisions

### Decision 1: Single Observability Provider (Langfuse)
Langfuse provides complete prompt tracing, token billing/cost metrics, LangGraph node steps, and human-in-the-loop state. OpenTelemetry is completely removed.

### Decision 2: Standardize Vector Storage on Qdrant
Qdrant is the designated vector database. Remove `pgvector` dependencies.

### Decision 3: Remove Legacy Microservices Folders
All active code resides in `src/` (`src/agent`, `src/tools`, `src/models`, `src/prompts`, `src/utils`, `src/api`). Delete obsolete `services/` and `shared/` folders.
