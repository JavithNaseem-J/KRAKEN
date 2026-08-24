# KRAKEN Public Production Demo Design

Status: Approved
Date: 2026-08-24
Target: `https://kraken-pme9.onrender.com/`

## Purpose

KRAKEN will be deployed as a public portfolio demonstration of a production-oriented AI
operations system. The LLM, retrieval, embeddings, semantic cache, agent graph, policy
evaluation, HITL interruption, and SSE transport are real. Tickets and operational actions use
synthetic, visitor-isolated data and never affect external systems.

Local acceptance testing is the release gate for the same code and service contracts deployed
to Render. A degraded dependency may produce an honest error, but it cannot produce a passing
release result for a feature that depends on that service.

## Goals

- Demonstrate all eight advertised workflows end to end.
- Keep every visitor's synthetic data and uploads isolated.
- Use real Groq chat inference and Qdrant Cloud inference and retrieval.
- Remove browser-visible privileged credentials and role authority.
- Fit within free-tier service constraints and handle cold starts clearly.
- Deploy only after automated local and CI acceptance checks pass.
- Make health, readiness, cache use, and degraded dependencies observable.

## Non-Goals

- No real firewall, identity-provider, endpoint, filesystem, or ticketing-system mutation.
- No claim of production SLA, high availability, or durable customer data on free infrastructure.
- No public account registration, enterprise SSO, or real employee authorization.
- No fake LLM or RAG success when the configured provider is unavailable.

## Deployment Architecture

One Render web service serves both the compiled React application and the FastAPI API:

- `/` and frontend asset paths serve the React build.
- `/v1/*` serves agent, knowledge, report, and audit API routes.
- `/approve/*` serves HITL details and decisions.
- `/health` is a process liveness check.
- `/ready` reports capability-level readiness.

The Docker build uses a frontend build stage and copies the compiled assets into the Python
runtime image. FastAPI serves those assets after API routes are registered. This removes the
current static-site-to-backend rewrite, avoids cross-origin configuration, and uses one free web
service.

Managed dependencies remain separate:

- Groq provides chat completion and structured agent decisions.
- Qdrant Cloud stores knowledge, session-scoped uploaded chunks, and semantic-cache vectors.
- Qdrant Cloud Inference generates embeddings with a free supported model.
- Redis stores rate-limit counters and one-hour demo session state.
- Postgres stores LangGraph checkpoints and redacted audit metadata where required.

Render runs with `ENVIRONMENT=prod`. All service credentials are injected as server-side secrets.

## Demo Session Security

The browser obtains an anonymous, signed demo session from the backend. The session identifier is
unguessable, expires after one hour, and scopes all mutable demo resources. Privileged API keys
are not compiled into frontend JavaScript.

The four UI personas are simulations for demonstrating policy behavior:

- User: read-only FAQ, personal synthetic ticket lookup, and ticket creation.
- Alice: Tier 1 triage and staging of critical simulated actions.
- Bob: simulated incident commander and HITL approver.
- Admin: simulated administrative approver.

Changing a UI persona does not grant authority by itself. The backend validates the signed demo
session, permitted transition, initiating persona, and approving persona. A requester cannot
approve the same action identity. The UI labels the environment as `Demo Mode / Synthetic Data`.

## Isolation And Retention

Every mutable record carries a `demo_session_id`. Queries for tickets, approvals, uploads,
checkpoints, and cache entries include that scope when the data is visitor-owned.

- Chat state, tickets, approvals, and uploads expire after one hour.
- Uploaded vectors are deleted after one hour.
- Redacted audit metadata expires after seven days.
- Raw upload content is never written to application logs or audit records.
- Secrets and detected personal data are redacted before persisted audit storage.
- Cleanup is idempotent and runs opportunistically at startup and on a bounded schedule.

Seed FAQ, SLA, cybersecurity policy, and ticket fixtures remain shared and read-only. A visitor's
ticket changes overlay the seed data only within that visitor's session.

## RAG And Semantic Cache

Knowledge ingestion and query paths use Qdrant Cloud Inference rather than loading a transformer
model into the 512 MB Render process. The same embedding model and vector dimensions are used for
ingestion, retrieval, uploads, and semantic caching.

Retrieval behavior:

1. Validate and sanitize the query.
2. Search shared FAQ and SLA collections.
3. Include seed ticket data only for explicit ticket identifiers and permitted roles.
4. Include uploaded chunks only when their `demo_session_id` matches the caller.
5. Apply existing policy redaction and relevance thresholds.
6. Send grounded chunks to Groq for reasoning and response composition.

Semantic-cache behavior applies equally to `/v1/run` and `/v1/run/stream`. A cache hit is explicit
in API metadata and SSE events. Cache keys include the knowledge version, role, and any relevant
session scope so one visitor cannot receive another visitor's uploaded content. Upload or shared
knowledge ingestion invalidates affected cache entries.

## Actions And HITL

Action risk is aligned with realistic demo behavior:

- `get_ticket_status` and knowledge responses are read-only.
- `create_ticket` is safe and executes immediately in session-scoped synthetic storage.
- `close`, `escalate`, `unlock_account`, and `quarantine_ip` are critical and require simulated
  HITL approval.

A critical action is staged, written to the session-scoped approval queue, and interrupts the
LangGraph run. Approval details expose only a session-bound CSRF token. Bob or Admin may approve or
reject through the signed demo session. Approval resumes the original graph checkpoint. Approved
execution calls only a synthetic demo adapter; rejected execution performs no mutation.

## Upload Controls

Public demo uploads are supported with these limits:

- PDF, TXT, and Markdown only.
- Maximum 2 MB per file.
- Maximum three uploads per session.
- Parsed as data only; uploaded content is never executed.
- Prompt-like instructions in documents remain untrusted retrieval content.
- Chunks and vectors are tagged with the visitor's session and expire after one hour.

Invalid type, size, parse, or quota returns a clear client-safe error. Prompt-like document content
is labeled and handled as untrusted evidence rather than executable instruction. The backend does
not reveal paths, stack traces, provider keys, or uploaded contents in errors.

## Abuse Controls

- Twenty AI queries per IP per rolling hour.
- Five simulated write actions per demo session.
- Redis is the primary distributed limiter.
- A bounded in-process limiter protects a single instance if Redis is unavailable.
- Exhausted limits return HTTP 429 with `Retry-After` and a clear UI message.
- Request-size limits and prompt-injection checks run before LLM, embedding, or storage calls.

## Failure Handling And Observability

`/health` returns success when the FastAPI process can serve requests. `/ready` reports individual
states for Groq, Qdrant retrieval, Qdrant inference, Redis, Postgres, semantic cache, and HITL
checkpointing. Required capability failure makes readiness degraded.

The frontend distinguishes:

- Render cold start or backend waking.
- Rate-limit exhaustion.
- Prompt-injection rejection.
- AI provider unavailable or quota exhausted.
- Retrieval unavailable.
- HITL pending, approved, rejected, or expired.
- SSE transport interruption with a safe status-poll fallback.

Logs use trace and session-safe correlation identifiers. Secrets, raw document content, and full
personal prompts are excluded. Provider calls use bounded timeouts and retries; repeated provider
failures open a short circuit to avoid three sequential node timeouts.

## CI/CD Release Gate

GitHub Actions must complete before Render deployment:

1. Backend lint, unit tests, and type checks.
2. Frontend lint, unit tests, and production build.
3. Secret and dependency checks.
4. Integration tests against isolated local service substitutes.
5. The eight-workflow acceptance suite.
6. Docker image build and startup readiness check.

Render deployment is triggered only after the gate passes. A post-deploy smoke test checks the live
frontend, `/health`, `/ready`, one signed anonymous demo session, RAG retrieval, SSE completion, and
a non-mutating HITL interception. Provider credentials remain GitHub or Render secrets and are
never printed by tests.

## Acceptance Criteria

The release is acceptable only when all scenarios pass through public gateway contracts:

1. Knowledge RAG returns a grounded FAQ answer with trusted source metadata.
2. Ticket lookup returns isolated status and details for an explicit synthetic ticket ID.
3. Ticket creation executes immediately and is visible only in the originating session.
4. A critical action returns `pending_approval` and does not mutate state.
5. Approve and reject decisions resume the original graph and produce the correct isolated result.
6. Prompt injection is rejected before retrieval, inference, action selection, or storage.
7. A repeated eligible query produces an observable semantic-cache hit with lower execution time.
8. SSE emits start, node progress, terminal response, pending approval, and error events correctly.

Additional release assertions:

- Two concurrent demo sessions cannot read or mutate each other's tickets, uploads, or approvals.
- Browser bundles contain no API keys, service tokens, or provider credentials.
- Public uploads enforce type, size, count, isolation, and expiry.
- Readiness fails honestly when a required real provider is unavailable.
- The application can restart without relying on Render's ephemeral filesystem.

## Delivery Sequence

1. Unify frontend and backend deployment and remove browser credentials.
2. Add signed demo sessions, rate limits, and visitor-scoped synthetic storage.
3. Correct action risk and simulated HITL authorization.
4. Move embeddings and retrieval to Qdrant Cloud Inference.
5. Isolate and expire uploads, cache entries, and audit data.
6. Add SSE cache handling, capability readiness, and frontend degraded states.
7. Build the eight-workflow acceptance suite and CI deployment gate.
8. Run locally with real providers, push, deploy, and run live smoke tests.

## Known Free-Tier Constraints

Render may spin the service down after inactivity, so the first request can take about a minute.
Render's local filesystem is ephemeral. Qdrant, Redis, Postgres, and Groq free tiers may suspend,
expire, or enforce quotas. The UI and readiness endpoint disclose these conditions, and the project
does not claim an uptime SLA.
