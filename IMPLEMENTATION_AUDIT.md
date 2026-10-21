# Implementation audit

Audit date: 21 October 2026 (Asia/Kolkata client date). Source inspection plus fresh safe tests; historical claims are not current live evidence. No Docker mutation, fault injection, GPU allocation change, or live inference was performed. See TEST_RESULTS.md for actual runs.

## Offline continuation — current findings

The continuation implements the proposed contract only in `router/offline/benchmark-recovery.ts`, with 31 new mock tests. `docs/design/benchmark-recovery-contract.md` was delivered before implementation and self-reviewed; it remains unapproved for live use. Production `TrustedRouter`, capability registry, action store and ledger code were not modified. Both live benchmark actions still reject at the production boundary.

Broker durability now has a private SQLite journal, exclusive queue-owner lock, descriptor-based bounded regular-file reads, durable single-use claims and cached-response publication. Twenty-one new tests cover process competition, actual fixture-process death, cancellation, response loss/publication failure, changed-payload reuse, corruption and unsafe files. See `docs/design/broker-durability-notes.md` for rollout prerequisites and unresolved storage/expiry/budget limits.

Telemetry scoring now validates fresh exact service metrics and owned trace shape, saves bounded sanitized probe observations, recomputes health, enforces two-second spacing and rejects malformed evidence. Optional error-rate windows must be measured and show zero recovered errors; no error-rate collector was added. The fresh synthetic demo is `docs/verification/mock-demo-offline-v2.json`; the original mock-demo.json is historical and lacks the stronger evidence schema.

Fresh continuation suite totals: **55 benchmark + 19 integration + 75 broker/RPC + 132 Router = 281 passed**, zero failures/errors/skips in final runs. Strict TypeScript checking for the new mock module and its imported source passed. No Docker discovery, Docker execution, network mutation, fault injection, live inference or live RPC access occurred in this continuation. Earlier network observations were not refreshed. Existing unrelated working-tree changes were preserved; no commit or staging operation was performed.

## Actual structure and working-tree constraints

- `broker/`: Python file-RPC daemon, protocol, LiteLLM HTTP client, budgets, Dockerfile.
- `litellm/config.yaml`: local aliases and upstream mappings.
- `llm_rpc/`: runtime queues; queue contents were not read or modified.
- `integration/`: legacy CLI/mailbox transport, no-tool provider transport, diagnosis adapter and tests.
- `nanoclaw/`: existing nested checkout with TypeScript BrokerProvider and diagnostic entry point; its implementation was read, not changed.
- `router/`: TypeScript schemas, trusted Router, Docker adapter interface, SQLite action store, hash-chain audit and reconciliation; 25 test files.
- `selfhealbench/`: four-service app, telemetry configs, ten pilot scenarios, offline/live runners, network review, deployment review artifacts, fixtures and tests.
- `docs/spec/`: intended architecture; deployment descriptions are not proof of runtime conformance.
- Root: proxy-only `docker-compose.yml`, pytest-only `pyproject.toml`, old audit documents, manual/debug scripts and reference artifacts.

Most project files were already staged as additions; `nanoclaw/` and several debug files were already untracked. Those changes were preserved. This agent performed no commit, reset, clean or staging operation. During the task another actor advanced HEAD to `eaae9719` (fix: strengthen broker and self-healing safety regressions), incorporating the safety edits; that state was preserved. No AGENTS.md was found by the repository file search.

## Component assessment

DONE means verified within the stated offline scope, not production certification.

| Component | Status | Source/evidence | Gap and next action |
|---|---|---|---|
| File-RPC protocol | PARTIAL | `broker/protocol.py`, `broker/main.py`; protocol and regression tests | Bounded input, duplicate-key rejection, safe IDs, filename correlation and existing-response replay rejection now tested. Durable claims, process exclusion, cached response replay and safe inode reads are now fixture-tested. Cancellation outcomes remain uncertain without retry; producer expiry/admission, journal retention and operator orphan reconciliation remain incomplete. |
| Broker HTTP boundary | DONE | `broker/litellm_client.py`; mocked streaming/error/timeout tests | 30s deadline, 64KiB streamed cap, no redirects, shape checks, safe error classes and no response-body logging. GPU execution remains unverified. |
| Model budgets | PARTIAL | `broker/budget.py`, `broker/config.py`, 11 budget tests | Every request is charged to `default`; config-instance budget fields are not wired into tracker; counters reset on restart. Sequential processing bounds concurrency but queue batch size is not admission control. Need trusted target attribution and durable accounting. |
| LiteLLM aliases | PARTIAL | `litellm/config.yaml` | fast/plan: qwen2.5:7b-q8_0 on infer-0/1; deep: qwen3-coder:30b on infer-2 and qwen2.5:32b-q4_K_M on infer-2b; coder: ollama_chat/qwen3-coder:30b-64k on infer-3; embed: nomic-embed-text:latest on infer-4. Local-only; spec fallback routes are not configured. No changes made. |
| GPU deployment | BLOCKED | `docs/spec/02_inference_plane_litellm.md`; root Compose contains no inference deployment | UUID pinning, CUDA, contexts, VRAM and runtime model placement not freshly verified. Requires scoped deployment inventory; do not change allocations. |
| NanoClaw diagnostic path | DONE | `integration/test_nanoclaw_diagnostic_transport.py`, `nanoclaw/container/agent-runner/src/diagnostic.ts` | Real Python adapter → real TS provider → temporary file RPC → real broker → mocked HTTP verified. This proves plumbing, not live GPU inference. |
| Live inference | BLOCKED | Historical result in user request only | No new live request submitted. Need approved queue/model scope and backend readiness. |
| Evidence preparation | PARTIAL | `selfhealbench/bench/pilot.py` | Top-level allowlist, recursive key redaction, literal secret redaction, nesting/byte limits tested. Free-form logs may contain unrecognized secrets or labels; no complete hostile-log parser/clustering pipeline. |
| Diagnosis schema | DONE | `pilot.validate`, integration adapter/transport tests | Strict four-field benchmark plans, actions, matching roots/targets, duplicate model fields, sizes and correlation tested. Legacy adapter alone has a looser generic contract. |
| Trusted Router | DONE | `router/src/trusted-router.ts`, 132 Router tests including 31 separate mock-prototype tests | Supported scale_service path validates trusted evidence, exact targets, bounds, freshness, budget, idempotency, ledger and reconciliation. Only this narrow capability is executable. |
| Benchmark → trusted recovery | BLOCKED | `live.py` vs `router/src/trusted-router.ts` | Benchmark proposes clear_fault/start_container; trusted Router executes scale_service. Previous direct execution bypassed Router. Live entry and direct benchmark mutation methods now fail closed. A reviewed proposal and isolated mock prototype now exist. Live integration still requires explicit capability/policy approval, not a name conversion or inferred permission. |
| Docker adapter | PARTIAL | `router/src/backends/docker-backend.ts` | Exact target/replica checks and before/after verification tested with mocks. Interface does not independently prove daemon isolation or project ownership; no approved production adapter found here. |
| Network checker | DONE | `network_safety.py`, 12 tests | CIDR alignment, overlap, gateway, /26 sizing, missing inventory and campus confirmation rejected/blocked; successful review never authorizes provisioning. Existing 10/8-only /26 restriction is a proposal policy, not a discovered free subnet. |
| Live isolation | BLOCKED | `live.py`, `NETWORK_SAFETY_REPORT.md` | Current context is shared default; no isolated context observed. Added canonical shared-socket and independent shared-daemon-ID checks. Configuration attestations still need independent operational verification and freshness. |
| Verification/scoring | PARTIAL | `pilot.verify`, `scoring.py`, benchmark tests | Three consecutive healthy observations within 20s; missing/failed cases stay in denominator. Scoring now recomputes health from sanitized probe observations, checks spacing and strict telemetry freshness/completeness, cleanup and rollback. Optional measured error-rate windows are validated; their collection and long-term recurrence remain unimplemented. |
| Audit/reconciliation | DONE | `router/src/audit-ledger.ts`, `storage/action-store.ts`, `recovery/reconciliation.ts` | Crash, tampering, pending completion, lock and budget tests pass. Benchmark executor does not use this ledger; mock audit is explicitly a simulation. |
| Ten pilot scenarios | BLOCKED | `selfhealbench/scenarios/pilot.json`, `SCENARIO_READINESS.md` | All defined and fixture-tested; none freshly executed live. Pilot HTTP/latency/stop cases are not the full architecture's ten production failure detectors. |
| Production detector, harm gate, recall, code-read and validator | MISSING | Specs 03–07 versus inspected broker/benchmark/router source | No complete implementation of these specified pipelines in the integration. Keep outside this focused safety patch; design separately. |
| Deployment/reproducibility | PARTIAL | root Compose, `broker/Dockerfile`, `pyproject.toml`, deployment review JSON | Root Compose only deploys socket proxy, with mutable image tag, broad POST/container/service access and shared socket. Read-only socket mount does not restrict API methods. Python project file has no install/dependency metadata; test tools happen to be installed. |

## Architectural and security findings

1. **Critical, contained:** benchmark execution bypassed trusted Router, and benign controls could receive mutations. Live mutation is now disabled at the missing integration boundary; hostile healthy plans are rejected before mock/backend execution.
2. **High, addressed:** LiteLLM client buffered unbounded JSON and exposed backend/model text through logs/errors. Now bounded streaming, deadline, no redirects and sanitized errors; regression coverage included.
3. **High, addressed in offline scope:** unsafe RPC IDs, duplicate fields and already-published response replays. IDs are path-safe and responses prevent repeated inference while present. Continuation adds persistent replay protection, process exclusion and descriptor-based inode checks. Trusted parent-directory ownership, producer admission/expiry and operator orphan reconciliation remain prerequisites/limits.
4. **High, addressed:** flag-only recovery success could omit cleanup/telemetry/history. These are now mandatory. Reports still depend on trusted collection; they are not cryptographic proof of physical recovery.
5. **High, unresolved deployment:** socket proxy POST access to shared daemon is too broad for benchmark isolation. No deployment edits or daemon changes made. A project prefix or bridge does not solve this.
6. **Important design gap:** `DirectLLMAgent` is an explicitly named comparison baseline; it bypasses NanoClaw and must never serve as its fallback. Legacy CLI transport may wake the normal agent runtime; use the no-tool diagnostic entry point for approved diagnostics.
7. **Telemetry gap:** continuation validates Prometheus/Tempo HTTP status, response shape, service identity and freshness. Readiness alone still does not establish complete trace coverage or error-rate windows. Loki readiness is checked but logs come from Docker, with no Loki ingestion pipeline. `DeterministicAgent` only checks HTTP status and misses latency. Demo uses a separately labeled scripted fixture.
8. **Spec divergence:** diagnostic default fast route accepts sanitized log text, while TRIAGE spec excludes raw logs; constrained decoding and expected fallback policy are not configured. Resolve before production use; no alias/GPU changes made here.

## Duplicate/unused code and coverage

`pilot.evaluate`/its CLI overlap `run.replay`/`scoring.summarize`; their error and accounting contracts differ. `.pre-recovery`/`.pre-migration-fix` action-store snapshots, `selfhealbench/reference/*.txt`, root debugging/manual integration scripts and old reports are not current production implementations. Preserved for review rather than deleted. `tests/broker/unit_test.py` and `integration_test.py` are outside pytest's configured `test_*.py` discovery; no claim they ran. General NanoClaw test suite was not run. Existing Router docker_e2e tests use in-memory adapters, despite the filename.

## Patch ledger

| Files modified/added | Reason | Test evidence | Limitation |
|---|---|---|---|
| `broker/protocol.py`, `broker/main.py` | Reject ambiguous/path-unsafe requests, correlate filenames, prevent known duplicate inference, return budget failure | `tests/broker/test_safety_regressions.py`, existing protocol/main tests | Single-process/in-memory budget and filesystem races remain |
| `broker/litellm_client.py` | Bound backend read/time, reject malformed output, remove sensitive logging/errors | HTTP regressions plus real-provider mocked-HTTP integration | No fresh real model/backend call |
| `tests/broker/test_litellm_client.py`, `integration/test_nanoclaw_diagnostic_transport.py` | Make HTTP fakes stream bytes; assert new safe error contract | Both suites pass as recorded | Fakes are not real network tests |
| `selfhealbench/bench/live.py` | Disable unsupported Router bypass; reject socket/daemon aliases and healthy-control recovery | `test_safety_regressions.py`, runner tests | Live campaign intentionally blocked |
| `selfhealbench/bench/scoring.py`, `selfhealbench/tests/test_runner.py` | Require histories/cleanup/telemetry for positive recovery score | Recovery regressions and existing denominator tests | Historical flag-only records now score unverified/false |
| `selfhealbench/bench/demo.py`, `selfhealbench/tests/test_demo.py` | Reproducible ten-case synthetic demonstration | No-network/no-subprocess test, saved mock report | No claim of AI or live recovery |
| Six root reports and `docs/verification/` | Evidence, safety blockers, runbook and prioritized handoff | Commands and results in TEST_RESULTS.md | Operational approval remains external |

No new dependencies, cloud routes, GPU/model assignments, or action permissions. Revert code changes only through review; do not re-enable the old direct execution path as a demonstration workaround.

## Continuation patch ledger

| Files changed/added | Reason | Evidence | Known limitations |
|---|---|---|---|
| `router/offline/benchmark-recovery.ts`, `router/tests/benchmark_recovery_mock.test.ts` | Strict inert diagnosis proposal, exact mock grants/ownership, existing durable budgets/audit, parent-bound cleanup and uncertainty/reconciliation model | 31 new mock tests; full 132-test Router suite; strict type check | No authenticated live authority, backend integration or production registry permission |
| `broker/durability.py`, `broker/main.py`, `broker/config.py`, `tests/broker/test_durability.py` | Persist claims/responses, prevent inference replay after crashes, bounded inode reads and atomic output | 21 new durability tests; 75-test full Python suite; real-provider mocked-HTTP integration | Protected persistent state required; retention, expiry, quotas, orphan tooling and durable budgets remain open |
| `selfhealbench/bench/telemetry.py`, `pilot.py`, `scoring.py`, `live.py`, `tests/test_telemetry.py` | Reject stale/malformed telemetry and flag-only histories; retain sanitized observations and measured-rate validation | 10 new telemetry tests including subcases; 55-test benchmark suite | Read-only live collection code changed but never exercised against infrastructure; no complete tracing/log ingestion or hard reader cancellation |
| `selfhealbench/bench/demo.py`, runner/safety test fixtures, new synthetic report | Upgrade synthetic evidence to the stricter schema without weakening assertions | Synthetic ten-case demo and benchmark suite | The Python demonstration remains separate from the TypeScript mock capability lifecycle; neither proves live recovery |
| Design notes and root reports | Concrete design review, rollout constraints, completed/blocked items and current results | Review against final source and tests | Design remains proposed; explicit approval required before live capability implementation |
