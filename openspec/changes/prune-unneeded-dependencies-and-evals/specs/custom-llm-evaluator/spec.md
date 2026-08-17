## ADDED Requirements

### Requirement: LLM-as-a-Judge evaluator replaces Ragas-based evaluation
The repository SHALL provide a lightweight, zero-dependency LLM-as-a-Judge RAG evaluator that uses `ChatOpenAI` (any OpenAI-compatible provider, default: Groq) with Pydantic `with_structured_output` to score retrieval and answer quality, replacing the `ragas` and `datasets` dependencies entirely.

#### Scenario: Evaluator scores faithfulness
- WHEN the evaluator receives a user query, retrieved chunks, and a generated answer
- THEN it SHALL return a structured `EvaluationResult` with a `faithfulness` score between 0.0 and 1.0

#### Scenario: Evaluator scores context recall
- WHEN the evaluator receives a user query and a list of retrieved chunks
- THEN it SHALL return a `context_recall` score between 0.0 and 1.0 measuring how many relevant facts were retrieved

#### Scenario: Evaluator scores answer relevance
- WHEN the evaluator receives a user query and a generated answer
- THEN it SHALL return an `answer_relevance` score between 0.0 and 1.0 measuring how well the answer addresses the query

#### Scenario: Evaluator uses deterministic inference
- WHEN the evaluator calls the LLM for scoring
- THEN it SHALL use `temperature=0.0` to produce deterministic, reproducible scores

### Requirement: Eval harness runs against the consolidated application
The eval harness SHALL send requests to `http://localhost:8000` (the consolidated gateway) and score responses using the LLM-as-a-Judge evaluator, storing results in a JSON report file.

#### Scenario: Eval harness produces a scoring report
- WHEN the eval harness is executed via `python tests/evals/eval_harness.py`
- THEN it SHALL produce a JSON file containing per-sample faithfulness, context_recall, and answer_relevance scores
- AND the report SHALL include an aggregate mean for each metric

#### Scenario: Eval tests validate scoring accuracy
- WHEN `pytest tests/evals/` is executed
- THEN all eval tests SHALL pass, confirming the evaluator produces valid scores in the [0.0, 1.0] range for each metric

### Requirement: No HuggingFace or Ragas dependencies required for evaluation
The `[project.optional-dependencies.eval]` section SHALL NOT include `ragas`, `datasets`, `pyarrow`, or `transformers`. The eval stack SHALL depend only on the core application dependencies plus the standard dev dependencies.

#### Scenario: Eval extras install cleanly
- WHEN `uv sync --extra eval` is executed
- THEN it SHALL complete without installing any HuggingFace `datasets`, `transformers`, or `ragas` packages
- AND `pip list | grep -E "ragas|datasets|transformers"` SHALL return empty
