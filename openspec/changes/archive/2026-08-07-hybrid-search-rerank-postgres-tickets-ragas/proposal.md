## Why

To achieve enterprise production readiness, AKEA requires: (1) Hybrid search & cross-encoder re-ranking for higher retrieval precision on exact keywords and error codes, (2) A PostgreSQL-backed ticket repository allowing the Action service to scale horizontally without local file lock contention, and (3) Live LLM-as-a-Judge RAGAS evaluation execution to continuously benchmark answer quality against ground truth datasets.

## What Changes

- **Hybrid Search & Re-Ranking**: Implement reciprocal rank fusion (RRF) combining dense BGE vectors and sparse keyword match scores, followed by cross-encoder re-ranking in `services/knowledge/retriever.py`.
- **PostgreSQL Ticket Repository**: Migrate `services/action/ticket_handler.py` ticket mutations from local `./data/workspace/tickets.json` to an ACID-compliant PostgreSQL `tickets` table with row locks (`SELECT FOR UPDATE`).
- **Live LLM-as-a-Judge Evaluation**: Extend `scripts/evaluate_rag.py` to evaluate live RAG outputs using `ragas` with Groq/OpenAI LLM judges for Faithfulness, Answer Relevance, Context Precision, and Context Recall.

## Capabilities

### New Capabilities
- `hybrid-retrieval-reranking`: Sparse + dense vector retrieval fusion and cross-encoder re-ranking.
- `postgres-ticket-store`: PostgreSQL database layer for ticket mutations and querying.

### Modified Capabilities
- `rag-evaluation`: Support live LLM-as-a-Judge evaluations using Ragas.

## Impact

- **Database**: Adds a `tickets` table to PostgreSQL (`POSTGRES_SYNC_URL`).
- **Services Affected**: `services/knowledge/`, `services/action/`, `scripts/evaluate_rag.py`, `scripts/seed_data.py`.
