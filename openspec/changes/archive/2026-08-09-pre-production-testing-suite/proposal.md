## Why

Establish an enterprise Fortune 500 pre-production QA & security test automation suite for KRAKEN. This suite provides continuous validation across four key testing gates: (1) RAG grounding faithfulness & answer relevance benchmarking, (2) concurrent load & P95/P99 latency stress testing, (3) automated security vulnerability & SAST code scanning, and (4) end-to-end multi-service integration assertions. Adding this suite guarantees 99.99% operational stability and zero regression prior to cloud production release.

## What Changes

- **RAG Faithfulness & Relevance Eval Suite**: Create `tests/evals/test_rag_evals.py` to calculate precision, recall, and grounding faithfulness across golden IT support queries.
- **Concurrent Load & Latency Benchmark Script**: Create `scripts/test_load_concurrency.py` simulating 20-50 concurrent user requests to measure P95/P99 latency, HTTP status codes, and throughput.
- **Automated Security & SAST Audit Script**: Create `scripts/run_security_audit.py` automating static analysis (`bandit`), secret detection (`gitleaks`), and package vulnerability audits.
- **Master QA Pre-Production Gate Script**: Create `scripts/run_preprod_qa_gate.py` to execute all test rounds in sequence and output a unified pass/fail enterprise QA report.

## Capabilities

### New Capabilities
- `pre-production-qa`: Adds automated RAG evaluation, load stress benchmarking, SAST security scanning, and master QA gate reporting to KRAKEN.

### Modified Capabilities
- None.

## Impact

- **Affected Code**: `tests/evals/`, `scripts/test_load_concurrency.py`, `scripts/run_security_audit.py`, `scripts/run_preprod_qa_gate.py`.
- **APIs**: Unchanged endpoints; calls existing API Gateway (`:8000`), Knowledge (`:8002`), and Audit (`:8006`) endpoints.
- **Dependencies**: Uses `httpx`, `asyncio`, `pytest`, `structlog`, and standard Python libraries.
