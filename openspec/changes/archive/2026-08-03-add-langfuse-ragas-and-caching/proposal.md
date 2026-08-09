## Why

While AKEA provides robust microservice orchestrations, it currently lacks production LLM observability, automated RAG quality evaluations, and query/response caching. Adding **Langfuse** provides full visibility into LLM costs, generation traces, and node latencies; **Ragas** delivers automated evaluation of RAG faithfulness, answer relevance, context precision, and recall; and a **Multi-Tier Caching System** (Semantic, Prompt, and Retrieval) drastically reduces LLM API costs while delivering sub-30ms response times for recurring queries.

## What Changes

- **Langfuse LLM Observability**: Integrate `langfuse` python SDK into `services/orchestrator/`, passing `CallbackHandler` to LangGraph execution calls to capture token counts, node execution traces, and generation latency trees.
- **Ragas RAG Evaluation Framework**: Add `ragas` & `datasets` to dependencies, create ground truth test dataset `data/workspace/eval_dataset.json`, and build `scripts/evaluate_rag.py` to calculate Faithfulness, Answer Relevance, Context Precision, and Context Recall.
- **Semantic LLM Response Cache**: Intercept queries using Qdrant vector similarity (`akea_semantic_cache` collection). If query Cosine similarity is $\ge 0.92$, return cached answer instantly without hitting LLM endpoints.
- **Prompt & Retrieval Cache**: SHA-256 hash caching for prompt strings and Redis key-value caching for exact vector retrieval lookups, automatically invalidated when `POST /ingest` runs.

## Capabilities

### New Capabilities
- `llm-observability`: Tracing, token counting, and cost monitoring via Langfuse.
- `rag-evaluation`: Automated evaluation pipeline computing Faithfulness, Answer Relevance, Context Precision, and Context Recall via Ragas.
- `multi-tier-caching`: Semantic response cache, prompt hash cache, and Redis vector retrieval cache with ingestion invalidation hooks.

### Modified Capabilities
- *(None — existing public REST API contracts remain unchanged)*

## Impact

- **Dependencies**: Add `langfuse>=2.30.0`, `ragas>=0.1.0`, and `datasets>=2.18.0` to `requirements.txt`.
- **Configuration**: Add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, and `SEMANTIC_CACHE_ENABLED` settings in `shared/config.py` and `.env.example`.
- **Services Affected**: `services/orchestrator/`, `services/knowledge/`, `scripts/evaluate_rag.py`, `shared/config.py`.
