# KRAKEN portfolio guide

KRAKEN is a production-grade portfolio project for an AI-assisted IT and security workflow. The business idea is reducing time spent finding support policy, handling routine tickets, and reviewing risky requests. It demonstrates the application and its controls using a self-contained Northstar demo dataset; it has no measured organizational savings or external users.

## Interview walkthrough

Run the stack as described in the [README](../README.md), open the browser UI, and use these three flows. Public personas are demo roles in one application. Switching personas demonstrates authorization logic; it does not prove that two independent people reviewed a request. Actions update application-owned demo records.

1. **Grounded policy answer:** Ask, “How do I connect to the corporate VPN?” Show the cited knowledge source, then ask again to show a cache hit. A missing or conflicting source should produce a limited answer.
2. **Routine ticket:** Ask for a medium priority VPN ticket for Morgan Reed, then look up the returned ticket ID. Creation is a safe action and its receipt must not claim human approval.
3. **Critical request:** As Alice, request quarantine of an IP address in the demo dataset. Show the pending approval and policy. Switch to Bob and deny it; the mutation must not run. Start a fresh request, approve it as Bob, and inspect the execution receipt and audit history. The action service requires a matching, server owned approval record before dispatch.

The design keeps LangGraph checkpoints for pause and resume, Redis for sessions and approval state, Qdrant for knowledge retrieval and semantic caching, PostgreSQL for tickets, checkpoints, and hash chained audit entries, and a FastAPI gateway for the React UI and API. These parts serve the walkthrough, but operating them has a meaningful deployment cost. Audit delivery is best effort; the hash chain detects changes to stored entries but does not guarantee that every attempted event was stored.

## Verification and evidence

Run these commands from the repository root unless a directory change is shown:

```powershell
.venv\Scripts\ruff.exe check src tests scripts
.venv\Scripts\mypy.exe src scripts
.venv\Scripts\python.exe -m pytest tests/unit tests/evals -q
.venv\Scripts\python.exe -m pytest tests/integration -m integration -q
.venv\Scripts\python.exe tests/evals/eval_harness.py --mode offline --json-report reports/ai-evaluation-offline.json --junit-report reports/ai-evaluation-offline.xml
cd frontend-react
npm run typecheck
npm run test
npm run build
```

For the local browser contract, start `npm run dev -- --host 127.0.0.1 --port 5174` in `frontend-react`, then run `$env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:5174"; npm run test:e2e:critical` in another PowerShell session.

On this change, Ruff lint and format checks and Mypy passed; Python unit/evaluation tests passed **351**, integration tests passed **7**, and frontend tests passed **11**. Frontend typecheck and build passed, and the browser bundle contained none of the CI credential markers. Local Playwright critical workflows passed **5 desktop** tests with one mobile-only skip and **6 mobile** tests using a Vite server and the suite's API fixture. The offline evaluator ran **50** cases with 100% source recall, required fact coverage, and response contract compliance, zero prohibited claims, and zero request errors. A fresh corpus generated under ignored `reports/disposable-corpus/` matched the committed SLA rules and manifest. In-memory Qdrant tests verified that updated SLA risk knowledge is retrieved while older knowledge and cache entries are excluded. Docker was not installed here, so the CI container smoke and security scan were not run locally. That fixture based evaluation verifies evaluator and response contracts; it does not measure live model quality, operational uptime, or business value.

For repeatable live quality evidence, deploy the intended revision to a dedicated test target with the matching Northstar corpus, ingested knowledge collection version `v4`, and enough query capacity for the full suite and streaming samples. The evaluator creates and verifies a public demo persona for each case; no separate role credentials are needed. Do not reset unrelated tickets. Then use:

```powershell
$stagingUrl = "https://your-staging-host"
$deployedSha = "your-40-character-commit-sha"
.venv\Scripts\python.exe tests/evals/eval_harness.py --mode live --base-url $stagingUrl --expected-sha $deployedSha --json-report reports/ai-evaluation-live.json --junit-report reports/ai-evaluation-live.xml
.venv\Scripts\python.exe tests/evals/eval_harness.py --mode stream --base-url $stagingUrl --expected-sha $deployedSha --case HOLDOUT-001 --samples 20 --json-report reports/ai-stream-answer.json
```

RAGAS is an optional evaluation dependency. Install it with `uv sync --frozen --extra dev --extra eval`, then add `--ragas` to a live evaluation command. For a small first run, use `--case HOLDOUT-001`. This scores the observed answer against the returned retrieval chunks with RAGAS faithfulness; cases with required reference facts also get RAGAS context recall. The report records scores and how many cases could actually be scored. `--ragas` fails the run if an eligible case has no usable chunks or the judge is unavailable. Ticket lookup, no-answer, and provider fallback cases are evaluated by their outcome checks instead. RAGAS scores are diagnostic until a reviewed threshold is calibrated against labeled examples; the deterministic case checks remain the pass gate. The judge sends the query, answer, retrieved chunk text, and reference facts to the configured LLM provider, so use a test target and data approved for that provider.

The harness checks the target's `/version` SHA and creates a separate public session for each live case. It selects and verifies the effective persona through session APIs. Reports record per-case results, target revision, dataset generation, observed cache origin when available, and unknown provider/model provenance when the target does not expose it. Stream mode records time to first visible delta, terminal time, errors, and optional disconnect behavior by response category. Use `--disconnect-after-delta` for a separate cancellation run.

On 2026-10-02, the public site's 20-query-per-IP-per-hour limit stopped an earlier run after 16 answers. A dedicated **local staging** target was then started from commit `5cd5d0611e2aae4f5b65175a046090f852b74235` with the matching `northstar-v1` corpus in its own Qdrant collection, live Qdrant cloud inference, and the configured Groq primary/fallback models. Its Redis behavior used a local in-memory emulator and fallback rate limiter; PostgreSQL and semantic caching were disabled. This isolates writes and provides real model/retrieval observations, but its latency is not representative of the hosted stack. Per-request model provenance was not exposed, so the evaluation report leaves provider/model and non-cache response origin unknown.

The full local live suite received **50/50** application responses: **48 passed**, source recall **100%**, required-fact coverage **77.8%** against an **80%** threshold, response-contract compliance **100%**, **0** prohibited claims, and **0** request errors. `SCN-057` and `HOLDOUT-001` omitted required facts in that run; both passed immediate isolated replays with the expected sources and facts. This is evidence of answer variability, not a passing quality gate. The per-case report is retained locally at `reports/ai-evaluation-live-v4-local.json` (ignored by Git).

That historical run used the earlier scorer. The current scorer verifies retrieved source fields, ticket lookup results, and expected outcomes, so its scores must be measured again before comparing revisions.

Repeated SSE observations on the same target were:

| Run | Samples | First visible deltas | Terminal events | Terminal median / p95 | Stream errors | Actual disconnects |
|---|---:|---:|---:|---:|---:|---:|
| Substantive answer | 10 | 0 | 10 | 9,127.7 / 60,689.0 ms | 0 | 0 |
| Disconnect after first delta | 5 | 0 | 5 | 15,284.5 / 21,938.8 ms | 0 | 0 |
| Greeting | 10 | 0 (expected) | 10 | 2,055.9 / 2,066.9 ms | 0 | 0 |

Of the 10 substantive responses, **2 were explicit provider fallbacks** and **8 were terminal-only with origin unknown**. The attempted disconnect run had one fallback and four other terminal-only responses. No cache-hit sample was available because the isolated target disabled the shared semantic cache. The substantive `auto_respond` path returns its prepared action result before the responder's model stream, so it currently emits no visible answer deltas. First-visible-answer latency and cancellation after a delta therefore remain **unmeasured** for that flow. `reduce-chat-latency` task 4.5 remains open. Redacted local reports are `reports/ai-stream-generated-v4-local.json`, `reports/ai-stream-disconnect-v4-local.json`, and `reports/ai-stream-greeting-v4-local.json`.

Hosted Chromium checks passed for service health, the public page, live ticket lookup, and a VPN knowledge answer (**3 smoke tests**). Two further browser checks passed the full approval workflow: Alice staged separate demo containment requests, and Bob denied one and approved the other. The browser showed **REJECTED** without execution and **APPROVED & EXECUTED** with an agent response, respectively. These checks do not replace the full live quality gate above.

## Cleanup record

Baseline revision: `b77c88edebf53018225010ba2905239400707bed`; the tracked tree was clean before implementation. It had 244 tracked files. Runtime counting includes tracked `.py`, `.ts`, `.tsx`, and `.css` files under `src/` and `frontend-react/src/`, excluding `.test.*` and `frontend-react/src/test/`. The baseline was **100 files / 15,992 physical lines**. The current result is **98 files / 15,626 physical lines**, a net reduction of **2 runtime files / 366 runtime lines**. Test, documentation, generated data, and dependency changes are excluded from this runtime count. The security and live-evaluation fixes added code; removal of unused feature paths accounts for the net reduction.

A second reduction pass inventoried all **241 tracked files** present at its start: 106 runtime and frontend source files (including frontend tests), 55 separate test files, 35 data files, 27 project/configuration/documentation files, and 18 generated agent-tooling files. It read each tracked file, checked exact duplicates and Python function bodies, scanned named exports and imports, and compared repeated eight-line blocks across runtime and test files. Candidates were reviewed against their callers before editing. The 18 `.agent` files had no repository consumers and were already ignored; they remain available locally but are no longer tracked. The resulting repository has **223 tracked files**. Large corpus definitions, lockfiles, distinct security tests, and deployment files remain because they serve current behavior or reproducibility.

| Candidate | Consumers and entry points reviewed | Decision, replacement, and check |
|---|---|---|
| `write_json_file`, `src/tools/write_tool.py` | Registry, dispatcher, policy phrases, decider prompt, generated SLA risk map, tests; absent from public action allowlist | Removed action and module. Kept `atomic_write_json` for ticket storage. Unsupported action and ticket persistence checks pass. |
| Episodic memory | Internal memory endpoints, agent reader/writer, Qdrant startup, models, tests; public sessions bypassed episodic paths | Removed episodic paths and exclusive modules. Redis session history, LangGraph checkpoints, and Qdrant knowledge/cache remain. Memory and resume tests pass. Legacy collection name remains only in reset ownership metadata. |
| Memory service PostgreSQL pool | Memory startup/shutdown; no other consumer of its `app.state.db_pool` | Removed that pool. Ticket, audit, and checkpoint database use remains. Memory health reflects the Redis session store. |
| Conflicting SLA risk map | Dataset generator and knowledge loader used names that disagreed with runtime registry | Generate the map from canonical registry policy. Regenerated SLA, manifest checksums, and evaluation references; risk consistency tests pass. Knowledge version later moved to `v4` for corrected ticket ownership content. |
| Live-evaluation corpus and retrieval gaps | Ticket loader, P2 SLA ranking, and old/current certificate references | Indexed ticket ownership, ranked exact SLA severity evidence, and corrected certificate policy references. The full live suite still failed on variable required-fact answers; the remaining limitation is recorded above. |
| Approval success mandate | Responder appended success language when approval or any action success appeared | Replaced with receipts from each structured result. Tests cover approved failure, safe success, missing transaction ID, and mixed results. |
| Browser approval callback result | API returned HTTP 200 with `status: error` if graph resume failed; browser could still label approval executed | Browser now requires callback success and an execution response before claiming approval completion. Focused API tests cover callback error and missing response. |
| Critical action authorization | Service token and graph resume could reach dispatch without retained decision | Redis evidence now binds action, payload, session, generation, expiry, and approver. Execution is claimed once; identical completed retries reuse the result. Direct call, mismatch, replay, outage, and concurrency tests pass. |
| Repeated HTTP transport selection | Internal HTTP helper and gateway JSON/stream proxy | Shared client selection with caller-specific status and streaming behavior. Gateway and orchestration tests pass. |
| Repeated model chunk parsing | Responder and orchestrator used the same structured text extraction | Shared visible-text extraction in the LLM utility; responder and streaming tests pass. |
| Repeated upstream HTTP errors and knowledge filters | Three gateway proxy handlers repeated error serialization; four knowledge queries repeated active version/generation conditions | Shared each rule at its existing boundary, preserving status, request ID, and filtered corpus behavior. Gateway and knowledge tests pass. |
| Unused runtime symbols | Role lookup/map and frontend HTML-export wrapper had no callers; the report endpoint remains available | Removed the dead symbols. Auth, frontend, and report contracts remain covered. |
| Generated `.agent` integration files | No application, test, CI, or documentation references; directory already listed in `.gitignore` | Removed 18 files from Git tracking without deleting local copies. |
| Repeated background task supervision | Orchestrator cache write and memory writer | Shared task retention, completion logging, and bounded shutdown. Persistence tests pass. |
| Fabricated metrics counter | `metrics_text()` always emitted one request | Removed fixed counter; retained truthful service liveness. Metrics contract test passes. |
| Old README design note | `docs/superpowers/specs/2026-09-08-readme-rewrite-design.md`; its result is in README | Removed after reference review. Current README and this guide hold the project explanation. |
| Frontend, API boundaries, tests, config, dependencies, CI, deployment files | Imports, routes, dynamic registries, scripts, lockfiles, browser workflows | Retained where a current workflow or verification gate uses them. No exclusive dependency remained after feature removals: Qdrant and PostgreSQL still have live consumers. Distinct security and outage tests remain separate. |

Approval records expire after the configured approval timeout. Resolved decision, claim, and result keys are retained for the timeout plus one hour, while stored expiry still prevents late authorization. A crash after mutation and before result storage leaves an uncertain claimed execution; the service returns conflict instead of repeating the action. Recovery requires checking the application-owned target state and making a fresh approval. Approvals created under the old record schema cannot authorize the new action boundary and should be allowed to expire or invalidated during rollout. Deployment, remote knowledge ingestion, and remote reset are separate operations.
