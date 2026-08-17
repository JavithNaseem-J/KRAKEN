## ADDED Requirements

### Requirement: No umbrella langchain packages in production dependencies
The project SHALL NOT list `langchain` or `langchain-community` as top-level dependencies in `pyproject.toml` or `requirements.txt`. Only direct model driver packages (`langchain-openai`, `langchain-core`, `langgraph`, `langgraph-checkpoint-postgres`) SHALL be present as LangChain-related dependencies.

#### Scenario: Container image excludes umbrella packages
- **WHEN** the Docker image is built from the Dockerfile using `requirements.txt`
- **THEN** `pip list | grep -E "^langchain |^langchain-community"` SHALL return empty

#### Scenario: Import resolution succeeds without umbrella packages
- **WHEN** the application boots via `python main.py` or tests run via `pytest`
- **THEN** all LangChain imports (`ChatOpenAI`, `OpenAIEmbeddings`, `StateGraph`, `Runnable`) resolve correctly from `langchain-openai`, `langchain-core`, and `langgraph` packages

### Requirement: No ReportLab dependency in production dependencies
The project SHALL NOT list `reportlab` as a dependency in `pyproject.toml` or `requirements.txt`. Incident report / briefing generation SHALL use Jinja2 HTML templates or plain-text output instead.

#### Scenario: Report generation uses HTML or text format
- **WHEN** `POST /v1/report/export` is called with `session_id`
- **THEN** the response SHALL be an HTML document or plain-text brief (not a binary PDF)
- **AND** the `reportlab` package SHALL NOT be importable in the production container

### Requirement: Eval stack uses zero HuggingFace dependencies
The `[project.optional-dependencies.eval]` section SHALL NOT include `ragas`, `datasets`, `pyarrow`, or `transformers`. Evaluation SHALL use only core application dependencies plus the LLM-as-a-Judge evaluator.

#### Scenario: Eval extras install without HuggingFace packages
- **WHEN** `uv sync --extra eval` is executed
- **THEN** no packages from `ragas`, `datasets`, `pyarrow`, or `transformers` SHALL be installed
- **AND** `pip list | grep -E "ragas|datasets|pyarrow|transformers"` SHALL return empty

### Requirement: OpenTelemetry removed from production code
All OpenTelemetry imports, instrumentors, and tracer providers SHALL be removed from `src/api/orchestrator.py` and all other production modules. Langfuse SHALL be the only observability integration.

#### Scenario: No OpenTelemetry imports in production
- **WHEN** a static scan runs for `opentelemetry` or `otel` across all tracked `.py` files under `src/`
- **THEN** zero matches are found in import statements or instrumentation setup code

#### Scenario: OpenTelemetry text removed from frontend
- **WHEN** the frontend components `TelemetryDrawer.tsx` and `ReasoningInspectorDrawer.tsx` are inspected
- **THEN** no references to "OpenTelemetry" SHALL exist; labels SHALL use "Execution Trace ID" instead
