## Context

The system currently uses dense vector retrieval only, local JSON file ticket persistence (`./data/workspace/tickets.json`), and offline heuristic evaluation. This design details:
1. Hybrid vector + BM25 keyword score fusion and lightweight cross-encoder re-ranking.
2. Migrating ticket mutations to PostgreSQL (`tickets` table) with transactional row locking.
3. Enabling live LLM-as-a-Judge RAGAS evaluation execution.

## Goals / Non-Goals

**Goals:**
- **Hybrid Retrieval & Re-Ranking**: Combine dense BGE embeddings with keyword overlap scoring, followed by cross-encoder re-ranking to return top-k chunks.
- **PostgreSQL Ticket Storage**: Create `tickets` table schema in Postgres (`ticket_id`, `title`, `description`, `status`, `priority`, `created_at`, `updated_at`, `payload`). Refactor `services/action/ticket_handler.py` to run SQL queries using `psycopg_pool.ConnectionPool`.
- **Live LLM-as-a-Judge Evaluation**: Update `scripts/evaluate_rag.py` to invoke LLM API judges via `ragas.evaluate` when API keys are available, falling back gracefully when offline.

**Non-Goals:**
- Modifying FastAPI endpoint contracts or request payloads.

## Decisions

### 1. Reciprocal Rank Fusion (RRF) & Lightweight Re-Ranking
- **Decision**: In `services/knowledge/retriever.py`, compute dense vector score + BM25 term frequency score. Merge rankings via $RRF(d) = \sum \frac{1}{60 + r(d)}$.
- **Rationale**: Delivers high precision for exact keyword matches (ticket IDs, error codes) and semantic intent.

### 2. PostgreSQL Ticket Store with Graceful Local Fallback
- **Decision**: `services/action/ticket_handler.py` checks for active Postgres connection pool. If connected, executes `SELECT FOR UPDATE` and `UPDATE tickets SET status = ...`. If disconnected (offline unit tests), falls back to local JSON file.
- **Rationale**: Ensures 100% backward compatibility for offline unit testing while enabling multi-replica cloud scaling.

### 3. Dual-Mode Ragas Evaluation
- **Decision**: `scripts/evaluate_rag.py` detects if `LLM_API_KEY` is present. If present, runs `ragas.evaluate(metrics=[faithfulness, answer_relevance, context_precision, context_recall], llm=...)`. If absent, runs local fallback metric computation.
- **Rationale**: Allows offline CI test execution while providing full LLM-as-a-Judge benchmark reporting when deployed.

## Migration Plan

1. Create PostgreSQL `tickets` table DDL in `services/action/ticket_handler.py`.
2. Seed initial tickets from `data/workspace/tickets.json` into Postgres during service startup / seed script.
3. Refactor `services/knowledge/retriever.py` to calculate RRF hybrid scores and re-rank.
4. Update `scripts/evaluate_rag.py` to support live LLM evaluation judges.
5. Run unit test suite and lint checks.
