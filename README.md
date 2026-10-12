# KRAKEN

**A stateful AI support agent that retrieves authorized knowledge, operates synthetic tickets, and pauses critical actions for human approval verified at the execution boundary.**

**Live**: [Click Here](https://kraken-bdtw.onrender.com)

Python 3.12 · FastAPI · LangGraph · Groq · Qdrant · Redis · PostgreSQL · React · TypeScript · Docker

Support workflows need more than an answer: they need relevant policy, current ticket information, and a clear boundary between advice and operational changes. KRAKEN connects these steps in a finite workflow with structured action results and checkpointed approval pauses.

The application uses synthetic Northstar policies, SLA rules, and tickets. Ticket operations update application-owned records. Firewall quarantine and account unlock produce synthetic receipts; external security systems are not called.



## Evidence

| Evidence | What it establishes |
|---|---|
| [Agent graph](src/agent/agent.py), [action registry](src/utils/registry.py), [execution boundary](src/api/action.py) | Six workflow stages, eight registered actions, and stored approval verification before critical dispatch |
| Locally documented main evaluation | 78 cases: 64 passed, 11 failed, 3 unverified; the complete quality gate remains unfinished |
| Local tests and browser artifacts | Contract and graph-outcome coverage exists; retained live browser failures show empty answers |

The evaluation row is a recorded local summary, not a fresh measurement of the hosted revision. References are source-derived and lack independent human review. Later focused repairs have not established a complete rerun. Most tests, corpus files, scripts, and evaluation records are excluded from the current public Git checkout.

## Architecture

```mermaid
flowchart LR
    UI["React chat"] --> Gateway["FastAPI gateway"]
    Gateway --> Agent["LangGraph workflow"]
    Agent --> Knowledge["Knowledge retrieval"]
    Knowledge --> Qdrant[("Qdrant: knowledge and response cache")]
    Agent -. "eligible cache" .-> Qdrant
    Agent -. "when needed" .-> LLM["Configured Groq models"]
    Agent --> Actions["Action service"]
    Agent -- "pause" --> Approval["Approval service"]
    Gateway -- "human decision" --> Approval
    Approval --> Redis[("Redis: sessions and decisions")]
    Approval -- "resume callback" --> Agent
    Actions -- "verify and claim; public overlays" --> Redis
    Agent -- "checkpoints" --> Postgres[("PostgreSQL")]
    Actions -- "non-public tickets" --> Postgres
    Agent --> Memory["Session history"]
    Memory --> Redis
    Actions -. "best-effort delivery" .-> Audit["Audit service"]
    Audit --> Postgres
```

- **One runtime:** the gateway initializes subsystem FastAPI apps and routes internal calls through ASGI transports. The same Docker image serves the React bundle.
- **Retrieval:** Qdrant dense candidates are expanded for ticket IDs, documents, and SLA severities, then ranked with token-frequency fusion and heuristics. Role, session, expiry, knowledge version, and dataset generation constrain eligibility.
- **Workflow:** retrieval → reasoning → decision → execution → response → memory. Explicit operations and ticket lookups have deterministic routes; structured model output handles other decisions. Responses may return authorized evidence directly.
- **Approval:** critical actions interrupt the graph. A decision callback resumes its checkpoint; execution verifies the stored authorization again.
- **State:** Redis holds sessions, decisions, and public ticket overlays. PostgreSQL holds configured checkpoints, audit records, and non-public tickets.

| Path | Responsibility |
|---|---|
| [src/agent](src/agent/) | Graph, state, and workflow nodes |
| [src/api](src/api/) | Gateway, orchestration, retrieval, actions, approvals, memory, audit |
| [src/utils](src/utils/) | Store clients, schemas, sessions, caching, logging |
| [frontend-react/src](frontend-react/src/) | Chat, persona controls, uploads, approval UI |
| [Dockerfile](Dockerfile), [render.yaml](render.yaml) | Container and hosted configuration |

### Engineering decisions and trade-offs

**Policy owns risk.** The registry determines action risk rather than accepting a model-provided label. The action service binds approval to the action, payload, session, initiator, generation, expiry, and eligible approver. Redis claims suppress duplicate critical dispatch, but mutation and receipt persistence are separate operations.

**Evidence before model composition.** Deterministic ticket routes, direct retrieved-text answers, and structured action receipts reduce unnecessary model steps. Corpus-specific heuristics limit generalization; retrieval uses neither a separate BM25 index nor a learned cross-encoder.

**Scoped response caching.** Eligible grounded read responses carry role, scope, model, knowledge-version, and generation context. Operational requests bypass shared caching. Qdrant semantic lookup has an exact-query Redis fallback; failed invalidation remains a reliability concern.

**Best-effort background persistence.** Memory and cache writes avoid delaying completion. Trace IDs and redacted structured logs support diagnosis, while audit delivery can degrade to stdout.

## Run locally

Use Python 3.12, Node.js 22, npm, and uv. Create a root `.env`; a fresh clone does not include the local environment example.

```dotenv
ENVIRONMENT=dev
HITL_SERVICE_TOKEN=<unique-random-secret-at-least-32-characters>
PUBLIC_SESSION_SECRET=<unique-random-secret>
LLM_API_KEY=<groq-api-key>
POSTGRES_URL=postgresql+asyncpg://<user>:<password>@<host>:5432/<database>
POSTGRES_SYNC_URL=postgresql://<user>:<password>@<host>:5432/<database>
REDIS_URL=rediss://<user>:<password>@<host>:<port>
QDRANT_URL=https://<qdrant-host>
QDRANT_API_KEY=<qdrant-api-key>
```

Full workflows require working backing services and a populated Qdrant index matching the [settings](src/utils/config.py): `v4`, `northstar-v1`, and the configured embedding model/dimensions. Source corpus and ingestion tools are local-only, so a fresh clone cannot rebuild that index unaided. Unconfigured services can boot degraded.

```bash
uv sync --frozen
npm --prefix frontend-react ci
npm --prefix frontend-react run build
uv run uvicorn src.api.gateway:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`. `/health` reports liveness; `/version` identifies the build and effective model/corpus configuration. `/ready` checks configured capabilities but does not fully exercise embedding inference.

## Verification

The [tracked deployment workflow](.github/workflows/deploy.yml) builds an image, checks container health, triggers Render, and verifies hosted readiness and the exact commit SHA. The broader local CI suite is excluded from Git and does not gate this workflow.

In the full local development checkout, these commands cover backend contracts, graph integration outcomes, and frontend checks:

```bash
uv sync --frozen --extra dev
uv run python -m pytest tests/unit tests/evals/test_rag_evals.py tests/evals/test_isolated_launcher.py
uv run python -m pytest tests/integration -m integration
npm --prefix frontend-react run typecheck
npm --prefix frontend-react test
```

Unit/integration tests use controlled stores and scripted model responses. Critical browser tests mock API responses. The deterministic offline evaluator constructs expected-value answers and validates its scorer; isolated agent evaluation uses external inference. These evidence levels establish different things. Commands were inspected, not executed during this review.

## Limits

- Public personas are selectable synthetic actors; human identities are unverified.
- Secondary audit/report routes need stronger ownership checks; same-name uploads can overwrite another session's indexed points.
- Local fallbacks lose durability/coherence, audit writes are best effort, and critical execution has no atomic exactly-once guarantee.
- SSE is implemented, but progressive browser delivery, concurrency behavior, and current hosted quality require further verification.

## FutureWork

- Publish reproducible test and evaluation assets.
- Complete the full benchmark with independently reviewed references and hosted stream evidence.
- Strengthen ownership checks and upload identities.

## Licensed

MIT License.

<details>
<summary>License text</summary>

```text
MIT License

Copyright (c) 2026 Naseem

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

</details>
