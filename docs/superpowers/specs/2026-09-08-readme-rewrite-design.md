# KRAKEN README Rewrite Design

## Goal

Replace the current README with a concise, evidence-backed introduction that lets a new reader quickly understand what KRAKEN is, why it matters, and how to run it.

## Content and order

The README will contain:

1. Project title and one-line summary.
2. The configured Render deployment as the demo; no screenshot will be added.
3. One combined problem-and-features section.
4. One compact text architecture diagram derived from the gateway, in-process subsystem routing, and LangGraph node sequence.
5. A short technology stack.
6. Verified results from the current repository test runs and committed dataset manifest.
7. Setup, local run, and one basic API example in the README's only fenced code block.
8. The deployment link.
9. Repository-backed operational caveats.
10. Future work already identified by the project or evident from its current test and deployment configuration.

## Evidence rules

- Every numeric value and implementation claim must trace to repository code, configuration, committed data, or an executed test result.
- The README will distinguish the deterministic offline evaluation from live model-quality evaluation.
- The audit system will be described as SHA-256 hash-chained, not permanently append-only, because expired audit rows are deleted by the implementation.
- Optional PostgreSQL, Redis, and Qdrant integrations will not be presented as mandatory for degraded local startup.
- Unsupported superlatives and unmeasured performance claims will be removed.

## Verified values available

- Backend unit suite: 314 passed.
- Backend integration suite: 7 passed.
- Frontend unit suite: 6 passed across 4 files.
- Offline evaluator contract: 50 cases, 100.0% source recall, 100.0% required-fact coverage, 100.0% response-contract compliance, 0 prohibited-claim violations, and 0 request errors. This is fixture-based contract validation, not live model quality.
- Synthetic manifest: 500 tickets, 30 documents, 75 scenarios, and 4 SLA levels.
- Acceptance script: 8 named deployment checks.

## Validation

After editing, verify:

- Exactly one fenced code block is present.
- Exactly one architecture diagram is present.
- The demo uses the configured Render URL and no screenshot is referenced.
- All required sections exist and problem/features remain combined.
- Every number can be located in a source file, configuration, committed dataset, or the captured test output.
- Markdown links and local commands are syntactically valid.
