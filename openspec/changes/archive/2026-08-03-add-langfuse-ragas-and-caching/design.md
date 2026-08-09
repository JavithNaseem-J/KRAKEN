## Context

AKEA operates a multi-service AI architecture with LangGraph orchestration, Qdrant vector retrieval, and FastAPI services. As traffic grows, the system needs:
1. Production LLM observability to track prompt cost, latency trees, and node executions.
2. An automated RAG evaluation framework to quantitatively score retrieval precision and LLM hallucination rates.
3. Multi-tier caching (Semantic, Prompt, and Retrieval) to lower LLM API consumption and improve response latency.

## Goals / Non-Goals

**Goals:**
- **Langfuse Tracing**: Attach `CallbackHandler` from `langfuse` to LangGraph graph invocations without breaking offline dev setups.
- **Ragas RAG Evaluation**: Build `scripts/evaluate_rag.py` evaluating 4 key metrics (`faithfulness`, `answer_relevance`, `context_precision`, `context_recall`) using a curated ground truth dataset (`data/workspace/eval_dataset.json`).
- **Semantic LLM Response Cache**: Intercept queries using Qdrant vector similarity (`akea_semantic_cache` collection). Queries with similarity $\ge 0.92$ return cached responses in <30ms.
- **Retrieval & Prompt Cache**: Redis caching for exact vector search results with invalidation hooks on `POST /ingest`.

**Non-Goals:**
- Replacing LangGraph or Qdrant Cloud.
- Modifying PostgreSQL checkpoint schemas.

## Decisions

### 1. Langfuse Optional Callback Integration
- **Decision**: Initialize `CallbackHandler` from `langfuse.callback` inside `services/orchestrator/main.py`. If `LANGFUSE_PUBLIC_KEY` is not provided, gracefully pass `callbacks=[]`.
- **Rationale**: Prevents crashes in local development or test suites when Langfuse credentials are not present.

### 2. Ground Truth Dataset & Ragas Script
- **Decision**: Store evaluation benchmark dataset in `data/workspace/eval_dataset.json`. Implement `scripts/evaluate_rag.py` using `ragas.evaluate` with metrics: `faithfulness`, `answer_relevance`, `context_precision`, `context_recall`.
- **Rationale**: Standardizes continuous evaluation for RAG quality assurance across prompt or embedding updates.

### 3. Qdrant-Based Semantic Caching
- **Decision**: Store past query-response pairs in a dedicated Qdrant collection `akea_semantic_cache` (vector = embedding of user prompt; payload = response dict).
- **Threshold**: Similarity $\ge 0.92$ (Cosine distance $\le 0.08$).
- **Rationale**: Sub-30ms response for duplicate or paraphrased user questions, cutting Groq/OpenAI token costs significantly.

### 4. Redis Retrieval Cache Invalidation
- **Decision**: Cache `KnowledgeRetriever.retrieve()` results in Redis with key `retrieval:{sha256(query_and_sources)}`. Clear all `retrieval:*` keys when `POST /ingest` runs.
- **Rationale**: Guarantees zero stale retrieval results when new knowledge docs are ingested.

## Risks / Trade-offs

- **[Risk] Semantic Cache False Positives**: Paraphrased queries with distinct subtle intents (e.g. "Cancel ticket 1" vs "Cancel ticket 2") matching high vector similarity.
  - *Mitigation*: Include target ticket/entity IDs in the cache key or restrict semantic caching to general FAQ/informational queries.
- **[Risk] Langfuse API Failures**: External Langfuse server downtime causing graph invocation delays.
  - *Mitigation*: Configure Langfuse flush mode as non-blocking background task.

## Migration Plan

1. Add dependencies `langfuse`, `ragas`, `datasets` to `requirements.txt`.
2. Add settings to `shared/config.py` and `.env.example`.
3. Create `services/orchestrator/observability.py` for Langfuse callback setup.
4. Implement `shared/cache.py` (Semantic & Redis retrieval cache).
5. Build `scripts/evaluate_rag.py` and `data/workspace/eval_dataset.json`.
6. Run verification unit tests.
