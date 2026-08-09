## 1. Dependencies and Environment Settings

- [x] 1.1 Add `langfuse>=2.30.0`, `ragas>=0.1.0`, and `datasets>=2.18.0` to `requirements.txt`
- [x] 1.2 Add `langfuse_public_key`, `langfuse_secret_key`, `langfuse_host`, and `semantic_cache_enabled` settings to `shared/config.py`
- [x] 1.3 Update `.env.example` with Langfuse and Caching configuration keys

## 2. Langfuse Observability Integration

- [x] 2.1 Create `services/orchestrator/observability.py` helper to instantiate `CallbackHandler` from `langfuse` with graceful fallback when keys are absent
- [x] 2.2 Update `services/orchestrator/main.py` to pass the Langfuse callback handler into `agent_graph.ainvoke` config

## 3. Multi-Tier Caching System

- [x] 3.1 Create `shared/cache.py` implementing `SemanticCache` using Qdrant collection `akea_semantic_cache` (similarity $\ge 0.92$)
- [x] 3.2 Implement Redis retrieval lookup caching and invalidation helper `invalidate_retrieval_cache()` in `shared/cache.py`
- [x] 3.3 Hook `invalidate_retrieval_cache()` into `services/knowledge/main.py` `POST /ingest` endpoint
- [x] 3.4 Wire `SemanticCache` into `services/orchestrator/main.py` `/run` endpoint to intercept query execution on cache hits

## 4. Ragas RAG Evaluation Pipeline

- [x] 4.1 Create benchmark evaluation dataset `data/workspace/eval_dataset.json` containing 10+ ground truth test cases
- [x] 4.2 Create `scripts/evaluate_rag.py` running Ragas evaluation metrics (Faithfulness, Answer Relevance, Context Precision, Context Recall) and printing/exporting `eval_report.md`

## 5. Verification and Testing

- [x] 5.1 Add unit tests in `tests/unit/test_caching.py` testing semantic cache hit/miss logic and Redis cache invalidation
- [x] 5.2 Add unit tests in `tests/unit/test_observability.py` testing Langfuse callback fallback
- [x] 5.3 Run `pytest tests/unit -v --tb=short` to ensure all unit tests pass
- [x] 5.4 Run `ruff check . && ruff format --check .` to ensure 0 style/lint errors
