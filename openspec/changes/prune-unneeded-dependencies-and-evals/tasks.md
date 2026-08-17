## 1. Dependency Pruning

- [x] 1.1 Remove `langchain` and `langchain-community` from `pyproject.toml` dependencies; keep `langchain-openai`, `langchain-core`, `langgraph`, `langgraph-checkpoint-postgres`
- [x] 1.2 Remove `ragas`, `datasets` from `[project.optional-dependencies.eval]` in `pyproject.toml`
- [x] 1.3 Remove `reportlab` from `pyproject.toml` dependencies
- [x] 1.4 Regenerate `uv.lock` to reflect dependency changes
- [x] 1.5 Regenerate `requirements.txt` via `uv export --no-dev > requirements.txt`
- [x] 1.6 Regenerate `requirements-dev.txt` to reference `.[dev]`

## 2. Report Generation Refactor

- [x] 2.1 Rewrite `src/api/report.py` to generate incident reports as HTML (using Jinja2 templates) or plain-text output instead of binary PDF
- [x] 2.2 Remove all `import reportlab` references from `src/`
- [x] 2.3 Update any tests in `tests/unit/` that assert PDF-specific output to assert HTML or text format

## 3. Custom LLM-as-a-Judge Evaluator

- [x] 3.1 Create `tests/evals/llm_judge.py`: a lightweight evaluator module using `ChatOpenAI` (Groq-compatible) + Pydantic `with_structured_output` to score Faithfulness, Context Recall, and Answer Relevance (all 0.0–1.0)
- [x] 3.2 Define `EvaluationResult` Pydantic model with fields: `faithfulness: float`, `context_recall: float`, `answer_relevance: float`
- [x] 3.3 Rewrite `tests/evals/eval_harness.py` to send requests to `http://localhost:8000` (consolidated gateway) and score using `llm_judge.py`
- [x] 3.4 Rewrite `tests/evals/test_rag_evals.py` to import from `llm_judge.py`, assert scores are valid floats in [0.0, 1.0] for each metric
- [x] 3.5 Add `pytest tests/evals` to `.github/workflows/ci.yml` (eval gate)

## 4. Frontend Cleanup (OpenTelemetry references)

- [x] 4.1 Remove all "OpenTelemetry" text from `frontend-react/src/components/TelemetryDrawer.tsx` and `frontend-react/src/components/ReasoningInspectorDrawer.tsx` — use "Execution Trace ID" instead
- [x] 4.2 Verify `npm run build` succeeds after frontend cleanup

## 5. Verification

- [x] 5.1 Run `ruff check .` — must pass clean
- [x] 5.2 Run `mypy src/` — must pass clean
- [x] 5.3 Run `pytest tests/unit` — all existing unit tests must pass
- [x] 5.4 Run `pytest tests/integration -m integration` — all integration tests must pass
- [x] 5.5 Confirm no banned packages in `uv.lock` or `requirements.txt` (lock file: 139 packages, no langchain/langchain-community/ragas/datasets/pyarrow/reportlab)
- [ ] 5.6 Build Docker image (`docker build -t kraken-test .`) — must succeed with no umbrella packages

## 6. Commit

- [ ] 6.1 Stage all changes and commit as a single changeset with message: `refactor: prune unneeded dependencies and replace eval stack with LLM-as-a-Judge`
