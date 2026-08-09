## ADDED Requirements

### Requirement: Automated RAG Faithfulness & Relevance Benchmarking
The test suite SHALL provide an automated RAG evaluation framework in `tests/evals/test_rag_evals.py` that verifies retrieval precision and grounding faithfulness across golden IT queries.

#### Scenario: Golden query precision benchmarking
- **WHEN** the RAG eval test suite executes against the Knowledge service
- **THEN** top-5 chunk retrieval precision exceeds 0.80 and answer grounding faithfulness exceeds 0.85

### Requirement: Concurrent Load & Latency Benchmarking
The test suite SHALL provide a load generator in `scripts/test_load_concurrency.py` that simulates 20+ concurrent user sessions against the Gateway and outputs P95 and P99 latency distribution.

#### Scenario: High concurrency load test
- **WHEN** 20 concurrent workers send requests to `http://localhost:8000/api/query`
- **THEN** the load generator reports P95 latency and HTTP 200 success rate without server crashes

### Requirement: Unified Pre-Production QA Gate
The system SHALL provide `scripts/run_preprod_qa_gate.py` that executes unit tests, RAG evals, security audits, and load benchmarks in sequence, returning exit code 0 on complete pass.

#### Scenario: Pre-production QA gate execution
- **WHEN** `python scripts/run_preprod_qa_gate.py` is invoked
- **THEN** all 4 testing gates execute sequentially and output a summary report
