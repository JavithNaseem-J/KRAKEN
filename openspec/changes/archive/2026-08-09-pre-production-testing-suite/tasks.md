## 1. Automated RAG Evaluation Suite

- [x] 1.1 Create `tests/evals/test_rag_evals.py` with golden IT support queries, calculating Precision@k, Recall@k, and Faithfulness grounding scores.
- [x] 1.2 Add assertion thresholds requiring >0.80 Precision and >0.85 Faithfulness on vector retrieval.

## 2. Load & Concurrency Benchmark Generator

- [x] 2.1 Create `scripts/test_load_concurrency.py` simulating 20-50 concurrent async workers hitting `http://localhost:8000/api/query`.
- [x] 2.2 Calculate and display latency metrics (Average, P50, P90, P95, P99) and HTTP status code distribution (200, 429, 500).

## 3. Automated Security & SAST Audit Runner

- [x] 3.1 Create `scripts/run_security_audit.py` scanning for hardcoded secrets, pattern matching prompt injection defenses, and validating path traversal bounds.

## 4. Master Pre-Production QA Gate Runner

- [x] 4.1 Create `scripts/run_preprod_qa_gate.py` combining Unit Tests, RAG Evals, Security Audit, and Load Benchmark into a single pipeline with pass/fail exit code.
- [x] 4.2 Run `python scripts/run_preprod_qa_gate.py` to verify full enterprise QA gate pass.
