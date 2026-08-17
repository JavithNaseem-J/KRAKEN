## Why

KRAKEN contains unnecessary dependency bloat (`langchain` & `langchain-community` umbrella packages, `ragas` & HuggingFace `datasets` evaluation stack, and `reportlab` PDF generation) that increases container build times, bloats Docker image size by 1.5GB+, and introduces continuous security warning noise. 

Standardizing strictly on direct model drivers (`langchain-openai` for Groq/OpenAI-compatible APIs, `langgraph` for orchestration, `langfuse` for observability) and introducing a built-in zero-dependency LLM-as-a-Judge RAG evaluator gives KRAKEN a lean, fast, and 100% production-grade footprint.

## What Changes

- **Dependency Pruning**: Remove top-level `langchain` and `langchain-community` umbrella packages from `pyproject.toml` and `requirements.txt`. Retain direct imports from `langchain-openai`, `langchain-core`, and `langgraph`.
- **RAG Evaluation Refactor**: Remove `ragas` and `datasets` from `[project.optional-dependencies.eval]`. Replace `tests/evals/eval_harness.py` and `tests/evals/test_rag_evals.py` with a lightweight, built-in **LLM-as-a-Judge evaluator** powered by Groq (`ChatOpenAI` + Pydantic structured output) that measures Faithfulness, Context Recall, and Answer Relevance.
- **PDF Export Refactor**: Remove `reportlab` dependency from `pyproject.toml` and replace PDF briefing generation in `src/api/report.py` with a clean Jinja2 HTML/CSS incident report renderer or standard text brief output.
- **Clean Observability**: Confirm 100% removal of legacy OpenTelemetry text and packages from backend and frontend UI components.

## Capabilities

### New Capabilities
- `custom-llm-evaluator`: Lightweight, zero-dependency LLM-as-a-Judge evaluation harness powered by Groq (`ChatOpenAI`) that scores Faithfulness, Context Recall, and Answer Relevance without heavy HuggingFace/Ragas packages.

### Modified Capabilities
- `lean-agent-runtime`: Prune umbrella packages (`langchain`, `langchain-community`), evaluation dependencies (`ragas`, `datasets`), and PDF libraries (`reportlab`), standardizing strictly on direct model drivers (`langchain-openai`), `langgraph`, and `langfuse`.

## Impact

- **Codebase**: `pyproject.toml`, `requirements.txt`, `uv.lock`, `src/api/report.py`, `tests/evals/eval_harness.py`, `tests/evals/test_rag_evals.py`.
- **Dependencies**: Smaller container footprint (~1.5GB savings), faster cold-start import times, zero heavy HuggingFace datasets/transformers dependencies.
- **APIs & Backend**: All API contracts (`/v1/run`, `/v1/report/export`, `/health`, `/ready`) remain intact.
