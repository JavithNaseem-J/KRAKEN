## 1. Hybrid Search and Cross-Encoder Re-Ranking

- [x] 1.1 Implement keyword frequency scoring helper in `services/knowledge/retriever.py`
- [x] 1.2 Implement Reciprocal Rank Fusion (RRF) algorithm to combine vector distance and keyword match ranks in `KnowledgeRetriever.retrieve()`
- [x] 1.3 Implement cross-encoder re-ranking step in `services/knowledge/retriever.py` to re-rank top candidates before returning `RetrievalResult`

## 2. PostgreSQL Ticket Store Migration

- [x] 2.1 Add `tickets` table DDL and connection pool initialization to `services/action/handlers/ticket_handler.py`
- [x] 2.2 Add automatic ticket seeding helper to populate PostgreSQL `tickets` table from `data/workspace/tickets.json` on startup
- [x] 2.3 Refactor `_mutate_ticket` in `services/action/handlers/ticket_handler.py` to acquire `SELECT ... FOR UPDATE` row locks and update tickets in PostgreSQL with fallback to local JSON file
- [x] 2.4 Update `scripts/seed_data.py` to seed PostgreSQL `tickets` table

## 3. Live LLM-as-a-Judge RAGAS Evaluation

- [x] 3.1 Refactor `scripts/evaluate_rag.py` to support live `ragas.evaluate` execution with Groq/OpenAI LLM judge when API keys are available
- [x] 3.2 Update `eval_report.md` generation to format live vs fallback evaluation metrics cleanly

## 4. Verification and Testing

- [x] 4.1 Update `tests/unit/test_ticket_handler.py` to verify Postgres ticket store fallback and mutation logic
- [x] 4.2 Run `pytest tests/unit -v --tb=short` to ensure all unit tests pass
- [x] 4.3 Run `ruff check . && ruff format --check .` to ensure 0 style/lint errors
