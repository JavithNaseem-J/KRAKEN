## Context

While unit tests (`173 passed`) verify individual functions, an enterprise agentic RAG platform requires holistic pre-production validation covering vector search precision, latency under concurrent load, security vulnerabilities, and end-to-end multi-service state transitions.

## Goals / Non-Goals

**Goals:**
- Implement an automated RAG Evaluation suite asserting grounding faithfulness (>0.90) and retrieval precision across sample queries.
- Implement an async concurrent load generator (`scripts/test_load_concurrency.py`) measuring P95/P99 latency under 20-50 concurrent workers.
- Implement a security audit runner (`scripts/run_security_audit.py`) checking hardcoded secrets, unsafe functions, and dependency vulnerabilities.
- Provide a unified CLI gate runner (`scripts/run_preprod_qa_gate.py`) returning exit code 0 on PASS and exit code 1 on FAIL.

**Non-Goals:**
- Requiring third-party paid SaaS testing subscriptions (all scripts run natively using Python async HTTP client & Pytest).

## Decisions

### Decision 1: Pure Async Python Load Generator over Heavy External Tools
- **Choice**: Write `scripts/test_load_concurrency.py` using `asyncio` and `httpx` to simulate concurrent user threads against Gateway port 8000.
- **Rationale**: Keeps the project zero-dependency and zero-cost while accurately capturing P95/P99 latency metrics and HTTP 200/429/500 status distribution.

### Decision 2: Grounded Faithfulness Score Calculation
- **Choice**: Compare LLM final answer strings against retrieved vector chunk content to compute a n-gram keyword overlap & grounding precision score (`[0.0, 1.0]`).
- **Rationale**: Ensures answers stay 100% grounded in source documents without relying on external API eval keys.

## Risks / Trade-offs

- **[Risk] Groq API rate limits (HTTP 429) during heavy load testing** → **Mitigation**: Handle 429 status gracefully in load generator and measure rate-limit resilience.
