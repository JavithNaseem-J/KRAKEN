# KRAKEN README Rewrite Design

## Goal

Replace the current README with a concise, evidence-backed introduction that lets a new reader quickly understand what KRAKEN is, why it matters, and how to run it.

## Content and order

The README will contain:

1. Project title and one-line summary.
2. The configured Render deployment as the demo; no screenshot will be added.
3. One combined problem-and-features section.
4. Two Mermaid diagrams: a full system architecture and a recruiter-focused request/HITL sequence.
5. A short technology stack.
6. Verified results from the current repository test runs and committed dataset manifest.
7. Setup, local run, and one basic API example in one shell code block. Together with the two Mermaid blocks, the README will contain three fenced blocks.
8. The deployment link.
9. A compact REST API table listing the public gateway's HTTP method, path, and purpose. It will cover operational probes, public sessions, agent execution and SSE streaming, HITL approvals, private knowledge uploads, report export, and audit history.
10. Repository-backed operational caveats.
11. Future work already identified by the project or evident from its current test and deployment configuration.

## Evidence rules

- Every numeric value and implementation claim must trace to repository code, configuration, committed data, or an executed test result.
- The README will distinguish the deterministic offline evaluation from live model-quality evaluation.
- The audit system will be described as SHA-256 hash-chained, not permanently append-only, because expired audit rows are deleted by the implementation.
- Optional PostgreSQL, Redis, and Qdrant integrations will not be presented as mandatory for degraded local startup.
- Unsupported superlatives and unmeasured performance claims will be removed.

## Verified values available

- Automated tests: 327 passed in total, comprising 314 backend unit, 7 backend integration, and 6 frontend tests.
- Offline evaluator contract: 50 cases, 100.0% source recall, 100.0% required-fact coverage, 100.0% response-contract compliance, 0 prohibited-claim violations, and 0 request errors. This is fixture-based contract validation, not live model quality.
- Synthetic corpus scale: 500 tickets, 30 documents, and 75 capability scenarios.

The README will omit secondary counts such as SLA levels, test-file counts, and the number of acceptance-script checks.

## Validation

After editing, verify:

- Exactly two Mermaid diagrams are present: one full system flowchart and one request/HITL sequence diagram.
- Exactly three fenced blocks are present: two Mermaid diagrams and one setup/run/example shell block.
- The sequence diagram shows both the safe response path and the critical-action approval, resume, execution, audit, and response path.
- The demo uses the configured Render URL and no screenshot is referenced.
- The REST API table matches the routes declared by `src/api/gateway.py`; internal subsystem-only routes are excluded.
- All required sections exist and problem/features remain combined.
- Every number can be located in a source file, configuration, committed dataset, or the captured test output.
- Markdown links and local commands are syntactically valid.
