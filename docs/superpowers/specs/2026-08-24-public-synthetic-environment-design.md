# KRAKEN Public Synthetic Environment Design

## Purpose

KRAKEN is a public synthetic enterprise environment for evaluating retrieval, agent composition, policy enforcement, safe tool use, human approval, caching, streaming, and operational recovery. Every enterprise record and every downstream action is synthetic. Public access does not weaken authentication, isolation, quotas, prompt defense, approval policy, or audit controls.

## Runtime Boundary

The production image serves the React application and a consolidated FastAPI process. The gateway owns public authentication and routes requests in-process to the orchestrator, knowledge, action, approval, memory, and audit applications. PostgreSQL stores canonical tickets, runtime generation metadata, checkpoints, and audit events. Redis stores generation-scoped temporary sessions, limits, approvals, overlays, and exact cache entries. Qdrant stores generation-scoped knowledge, semantic cache entries, private uploads, and episodic memories.

The active generation is `SYNTHETIC_DATASET_GENERATION`. Readiness remains false unless the committed manifest, PostgreSQL metadata and ticket count, and Qdrant payloads all agree with that generation and PostgreSQL marks its state `active`.

## Dataset Contract

The canonical corpus is deterministic and contains:

- 75 curated capability scenarios with stable expected outcomes
- 500 tickets spanning P1-P4 priorities and realistic 90-day lifecycles
- 30 FAQ, policy, IAM, cloud, incident, compliance, and operations documents
- complete P1-P4 SLA and action-risk mappings

The corpus includes near matches, missing-information cases, superseded guidance, role restrictions, no-answer cases, prompt-injection content, safe actions, critical approval paths, semantic-cache paraphrases, and dependency-failure scenarios. Fictional names, `.example` domains, and documentation IP ranges prevent accidental real-world identifiers from entering the dataset.

## Public Sessions

`POST /v1/session` issues a signed, HttpOnly, expiring anonymous session tied to the active dataset generation. Persona changes require CSRF proof and can select only server-registered operational personas. The backend owns actor identity and role; browser headers and payload fields cannot increase privilege.

Mutable tickets, uploads, approvals, short-term memory, and checkpoints are isolated to the signed session. A generation change invalidates the cookie and causes the frontend to discard incompatible persisted conversations and persona state.

## Retrieval And Agent Execution

Healthy requests traverse standard components:

1. The gateway validates identity, rate limits, payload size, CSRF, and prompt safety.
2. The reasoner and retriever build a generation-scoped evidence context.
3. The decider selects only registered actions and derives risk from the registry.
4. Safe reads and writes use the action service and session-scoped synthetic repositories.
5. Critical actions pause at the approval queue and resume the original checkpoint only after an authorized decision.
6. The responder produces a grounded final answer with sources, timing, trace identity, cache metadata, and truthful synthetic action evidence.

Internal model deliberation is ephemeral. It is not returned, logged, persisted, cached, audited, or displayed. Provider-failure fallbacks activate only after a measured failure, remain grounded and uncached, and cannot create or claim a mutation.

## Synthetic Action Safety

Action results include `synthetic: true`, `dataset_generation`, and a synthetic target or receipt. Ticket creation and updates affect only KRAKEN session state. Containment and account operations do not call a real firewall, identity provider, endpoint manager, cloud account, or external ticket platform.

Critical actions require registry policy and human approval even though their targets are synthetic. This preserves the operational control evidence the system is designed to demonstrate.

## Controlled Reset

`scripts/reset_synthetic_environment.py` is preview-only by default. Its targets are hardcoded to KRAKEN-owned generation rows, Redis prefixes, Qdrant collections, and generated paths. It never flushes a shared Redis database, drops a PostgreSQL schema, accepts an arbitrary table or path, or deletes unrelated Qdrant collections.

Execution requires all of the following:

- `ALLOW_SYNTHETIC_DATA_RESET=true`
- the expected current generation
- the configured target generation
- the exact phrase `RESET KRAKEN TO <target-generation>`

The checkpointed phases are preflight, invalidate, clear PostgreSQL, clear Redis, clear Qdrant, clear generated files, generate, validate, seed PostgreSQL, ingest Qdrant, capability smoke, activate, and verify. A failed run leaves readiness false and can be rerun idempotently for the same target generation. Reports contain counts, phase outcomes, durations, generation IDs, and checksums, with secrets and records excluded.

## Acceptance Contract

A release is accepted only when backend tests, frontend tests and build, corpus validation, repository contract scans, and reset safety tests pass. The production acceptance command must report all eight flows:

1. Knowledge RAG and FAQ retrieval
2. Semantic cache acceleration
3. Ticket status lookup
4. Synthetic ticket creation
5. HITL interception
6. HITL resumption
7. Prompt-injection defense
8. SSE lifecycle completion

The browser smoke additionally verifies the synthetic disclosure, current ticket identifiers, grounded answer formatting, truthful action metadata, and absence of public model reasoning.
