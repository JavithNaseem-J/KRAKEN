## Context

KRAKEN is a single-process AI Agent that orchestrates LLM-driven agents via LangGraph, retrieves knowledge from Qdrant, and uses Langfuse for observability. It runs on Groq for LLM inference.

Currently, the project includes:
- **Umbrella packages**: `langchain`, `langchain-community` (pulling hundreds of unused integrations)
- **Heavy eval stack**: `ragas`, `datasets`, `pyarrow`, `pandas`, `transformers` (~1.5GB)
- **Legacy PDF lib**: `reportlab` (C-extension PDF generator)
- **OpenTelemetry references** in UI (to be removed in future change)

These dependencies bloat Docker images, slow import times, and create security noise without adding value.

## Goals / Non-Goals

**Goals:**
- Remove `langchain` and `langchain-community` umbrella packages; retain `langchain-openai`, `langchain-core`, `langgraph`
- Replace `ragas` + `datasets` evaluation with a lightweight LLM-as-a-Judge harness using Groq/`ChatOpenAI`
- Remove `reportlab` and replace PDF generation with clean Jinja2 HTML or text output
- Standardize observability on Langfuse only (OpenTelemetry removal for future change)
- Cut container image size by ~1.5GB and reduce import times

**Non-Goals:**
- Not changing any API contracts (`/v1/run`, `/health`, `/ready`, `/report/export`)
- Not removing `langfuse` (essential observability layer)
- Not modifying agent architecture or LangGraph flow
- Not changing Groq as the primary LLM provider

## Decisions

### 1. Replace `langchain` & `langchain-community` with direct imports
**Why**: `langchain` umbrella pulls 500MB+ of unused vector stores, document loaders, and API wrappers. `langchain-community` adds further bloat.

**Decision**: Import only what's needed:
- `from langchain_openai import ChatOpenAI, OpenAIEmbeddings` (Groq driver)
- `from langchain_core.runnables import Runnable` (type hints)
- `from langgraph import StateGraph, END` (orchestration)

**Rationale**: LangChain's modular design supports this; the umbrella package exists only for convenience, not technical necessity.

### 2. Replace `ragas` + `datasets` with LLM-as-a-Judge
**Why**: `ragas` requires 1.5GB of HuggingFace dependencies and hardcodes OpenAI as the judge model. It doesn't work with Groq.

**Decision**: Build a custom evaluator using `ChatOpenAI` (Groq-compatible) + Pydantic `with_structured_output`. Define three metrics:
- **Faithfulness**: Does the answer stay within retrieved chunks?
- **Context Recall**: How many relevant chunks were retrieved?
- **Answer Relevance**: Is the answer helpful and on-topic?

**Rationale**: Zero extra dependencies, works with any OpenAI-compatible provider, runs in milliseconds on Groq, and gives full control over evaluation criteria.

### 3. Replace `reportlab` with Jinja2 HTML output
**Why**: `reportlab` is a legacy C-extension library with complex layout code. It adds binary build overhead and maintenance burden.

**Decision**: Replace `src/api/report.py` PDF generation with:
- Jinja2 HTML templates (clean, versionable, easy to test)
- OR simple text-based incident brief output
- Client-side PDF export via browser (if HTML → PDF is needed)

**Rationale**: HTML is more maintainable and portable. PDF generation can happen client-side where needed.

### 4. Keep `langchain-openai` (not `langchain`)
**Why**: `langchain-openai` provides `ChatOpenAI` and `OpenAIEmbeddings` which work with **any OpenAI-compatible API** (Groq, DeepSeek, Ollama, etc.). It's lightweight (~200MB) and actively maintained.

**Rationale**: This is the driver layer for Groq. The umbrella `langchain` package adds no value here.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Import paths break if LangChain modules are reorganized | Pin exact versions (`langchain-openai>=0.1.0`); run CI gate after change |
| LLM-as-a-Judge scores vary by LLM choice | Document that scores use Groq (`llama-3.3-70b`); add `temperature=0.0` for determinism |
| PDF export users expect `.pdf` files | Add client-side HTML → PDF export via `window.print()` or browser API |
| `ragas` was used in evals pipeline | Replace with custom evaluator; add validation tests |

## Migration Plan

1. **Update `pyproject.toml`**: Remove `langchain`, `langchain-community`, `ragas`, `datasets`, `reportlab` from dependencies and extras
2. **Regenerate `requirements.txt`**: `uv export --no-dev > requirements.txt`
3. **Regenerate `requirements-dev.txt`**: Update to `-e .[dev,eval]`
4. **Code changes**:
   - `src/api/report.py`: Replace PDF generation with Jinja2/HTML output
   - `tests/evals/eval_harness.py`: Rewrite using `ChatOpenAI` + Pydantic structured output
   - `tests/evals/test_rag_evals.py`: Update imports and assert on new output format
5. **Frontend cleanup**: Remove OpenTelemetry references from `TelemetryDrawer.tsx` and `ReasoningInspectorDrawer.tsx` (already done in previous change)
6. **CI**: Add `pytest tests/evals` to CI pipeline
7. **Smoke test**: `uv sync && python main.py && curl localhost:8000/health`

## Open Questions

None — decisions are clear and based on concrete observations of current codebase bloat.
