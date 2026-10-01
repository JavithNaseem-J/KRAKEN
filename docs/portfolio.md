# KRAKEN portfolio guide

KRAKEN is a portfolio demonstration of an AI assisted IT and security workflow. It has no real users or measured business impact. The business idea is reducing time spent finding support policy, handling routine tickets, and reviewing risky requests. This project demonstrates controls for that idea over synthetic Northstar data; it does not establish savings in a deployed organization.

## Interview walkthrough

Run the stack as described in the [README](../README.md), open the browser UI, and use these three flows. Public personas are test roles in one demo application. Switching personas demonstrates authorization logic; it does not prove that two independent people reviewed a request. Every action mutates synthetic state.

1. **Grounded policy answer:** Ask, “How do I connect to the corporate VPN?” Show the cited knowledge source, then ask again to show a cache hit. A missing or conflicting source should produce a limited answer.
2. **Routine ticket:** Ask for a medium priority VPN ticket for Morgan Reed, then look up the returned synthetic ticket ID. Creation is a safe action and its receipt must not claim human approval.
3. **Critical request:** As Alice, request quarantine of a synthetic IP. Show the pending approval and policy. Switch to Bob and deny it; the mutation must not run. Start a fresh request, approve it as Bob, and inspect the execution receipt and audit history. The action service requires a matching, server owned approval record before dispatch.

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

On this change, Ruff lint and format checks and Mypy passed; Python unit/evaluation tests passed **340**, integration tests passed **7**, and frontend tests passed **9**. Frontend typecheck and build passed, and the browser bundle contained none of the CI credential markers. Local Playwright critical workflows passed **5 desktop** tests with one mobile-only skip and **6 mobile** tests using a Vite server and the suite's API fixture. The offline evaluator ran **50** cases with 100% source recall, required fact coverage, and response contract compliance, zero prohibited claims, and zero request errors. A fresh corpus generated under ignored `reports/disposable-corpus/` matched the committed SLA rules and manifest. In-memory Qdrant tests verified that updated SLA risk knowledge is retrieved while `v2` knowledge and cache entries are excluded. Docker was not installed here, so the CI container smoke and security scan were not run locally. That fixture based evaluation verifies evaluator and response contracts; it does not measure live model quality, operational uptime, or business value.

For live quality evidence, ingest knowledge collection version `v3` into a disposable or staging environment without resetting unrelated tickets. Run the target revision with valid role identities and a known commit SHA, then use:

```powershell
$stagingUrl = "https://your-staging-host"
$deployedSha = "your-40-character-commit-sha"
.venv\Scripts\python.exe tests/evals/eval_harness.py --mode live --base-url $stagingUrl --expected-sha $deployedSha --json-report reports/ai-evaluation-live.json --junit-report reports/ai-evaluation-live.xml
.venv\Scripts\python.exe tests/evals/eval_harness.py --mode stream --base-url $stagingUrl --expected-sha $deployedSha --case HOLDOUT-001 --samples 20 --json-report reports/ai-stream-answer.json
```

The harness checks the target's `/version` SHA and creates a separate public session for each live case. It selects and verifies the effective persona through session APIs. Reports record per-case results, target revision, dataset generation, observed cache origin when available, and unknown provider/model provenance when the target does not expose it. Stream mode records time to first visible delta, terminal time, errors, and optional disconnect behavior by response category. Use `--disconnect-after-delta` for a separate cancellation run. No valid staging quality or latency run was available during this change, so no live score, median, or p95 is claimed. The existing `reduce-chat-latency` staging measurement task remains open.

## Cleanup record

Baseline revision: `b77c88edebf53018225010ba2905239400707bed`; the tracked tree was clean before implementation. It had 244 tracked files. Runtime counting includes tracked `.py`, `.ts`, `.tsx`, and `.css` files under `src/` and `frontend-react/src/`, excluding `.test.*` and `frontend-react/src/test/`. The baseline was **100 files / 15,992 physical lines**. The result is **98 files / 15,613 physical lines**, a net reduction of **2 runtime files / 379 runtime lines**. Test, documentation, generated data, and dependency changes are excluded from this runtime count. The security fix adds some code; removal of unused feature paths accounts for the net reduction.

| Candidate | Consumers and entry points reviewed | Decision, replacement, and check |
|---|---|---|
| `write_json_file`, `src/tools/write_tool.py` | Registry, dispatcher, policy phrases, decider prompt, generated SLA risk map, tests; absent from public action allowlist | Removed action and module. Kept `atomic_write_json` for ticket storage. Unsupported action and ticket persistence checks pass. |
| Episodic memory | Internal memory endpoints, agent reader/writer, Qdrant startup, models, tests; public sessions bypassed episodic paths | Removed episodic paths and exclusive modules. Redis session history, LangGraph checkpoints, and Qdrant knowledge/cache remain. Memory and resume tests pass. Legacy collection name remains only in reset ownership metadata. |
| Memory service PostgreSQL pool | Memory startup/shutdown; no other consumer of its `app.state.db_pool` | Removed that pool. Ticket, audit, and checkpoint database use remains. Memory health reflects the Redis session store. |
| Conflicting SLA risk map | Synthetic generator and knowledge loader used names that disagreed with runtime registry | Generate the map from canonical registry policy. Regenerated SLA, manifest checksums, and evaluation references; risk consistency tests pass. Knowledge version moved from `v2` to `v3`. |
| Approval success mandate | Responder appended success language when approval or any action success appeared | Replaced with receipts from each structured result. Tests cover approved failure, safe success, missing transaction ID, and mixed results. |
| Critical action authorization | Service token and graph resume could reach dispatch without retained decision | Redis evidence now binds action, payload, session, generation, expiry, and approver. Execution is claimed once; identical completed retries reuse the result. Direct call, mismatch, replay, outage, and concurrency tests pass. |
| Repeated HTTP transport selection | Internal HTTP helper and gateway JSON/stream proxy | Shared client selection with caller-specific status and streaming behavior. Gateway and orchestration tests pass. |
| Repeated background task supervision | Orchestrator cache write and memory writer | Shared task retention, completion logging, and bounded shutdown. Persistence tests pass. |
| Fabricated metrics counter | `metrics_text()` always emitted one request | Removed fixed counter; retained truthful service liveness. Metrics contract test passes. |
| Old README design note | `docs/superpowers/specs/2026-09-08-readme-rewrite-design.md`; its result is in README | Removed after reference review. Current README and this guide hold the project explanation. |
| Frontend, API boundaries, tests, config, dependencies, CI, deployment files | Imports, routes, dynamic registries, scripts, lockfiles, browser workflows | Retained where a current workflow or verification gate uses them. No exclusive dependency remained after feature removals: Qdrant and PostgreSQL still have live consumers. Distinct security and outage tests remain separate. |

Approval records expire after the configured approval timeout. Resolved decision, claim, and result keys are retained for the timeout plus one hour, while stored expiry still prevents late authorization. A crash after mutation and before result storage leaves an uncertain claimed execution; the service returns conflict instead of repeating the action. Recovery requires checking synthetic target state and making a fresh approval. Approvals created under the old record schema cannot authorize the new action boundary and should be allowed to expire or invalidated during rollout. Deployment, remote knowledge ingestion, and remote reset are separate operations.
