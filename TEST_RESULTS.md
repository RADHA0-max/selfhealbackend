# Test results

## Latest verification — 22 October 2026

| Suite | Passed | Failed |
|---|---:|---:|
| SelfHealBench | 56 | 0 |
| NanoClaw Integration | 19 | 0 |
| Broker / RPC / Budget | 75 | 0 |
| Router / Security Gates | 132 | 0 |
| **Total** | **282** | **0** |

All four suites passed in the latest terminal verification.
The Broker suite returned exit code 0.

These results cover automated offline and mocked tests,
not live Docker recovery or GPU inference.

---


Audit date: 21 October 2026 (Asia/Kolkata client date). All reported test results were obtained during this audit. No real Docker faults, Docker mutations, GPU calls or live recovery were performed.

## Latest offline continuation — final applicable runs

| Command | Discovered | Passed | Failed | Errors | Skipped | Framework runtime |
|---|---:|---:|---:|---:|---:|---:|
| `python3 -m unittest discover -s selfhealbench/tests -v` | 55 | 55 | 0 | 0 | 0 | 0.033s |
| `python3 -m unittest discover -s integration -v` | 19 | 19 | 0 | 0 | 0 | 2.633s |
| `python3 -m pytest tests -q` | 75 | 75 | 0 | 0 | 0 | 0.55s |
| `npm --prefix router test -- --reporter=dot` | 132 (26 files) | 132 | 0 | 0 | 0 | 10.33s |

**281 passed** across all four freshly run suites. Integration used permitted temporary Unix-socket access, with HTTP mocked and no Docker or live inference. Router was rerun after final review tightened exact cleanup-parent binding; Python/integration code was unchanged after their final runs. New tests: 31 mock-contract, 21 broker durability, 10 telemetry. Existing tests were preserved and stronger evidence fixtures replaced the previous flag-only fixtures.

The new mock module also passed:

```bash
cd router
./node_modules/.bin/tsc --noEmit --target ES2022 --module NodeNext --moduleResolution NodeNext --types node --strict --skipLibCheck offline/benchmark-recovery.ts
```

The first ad-hoc type-check command omitted `--types node` and failed to resolve installed Node declarations; the corrected command above passed without installing dependencies or changing source to silence errors. Existing pytest-asyncio fixture-scope warning remains.

New regression coverage includes exact authority/parent binding, ownership/freshness/healthy control rejection, unchanged production registry rejection, durable mock IDs and budgets, cleanup limits, uncertain actions, reconciliation outbox replay and audit tampering. Broker tests use temporary files and fake model functions, including two child processes and a child deliberately exiting after a fake model call. They verify no repeated inference, safe republishing, cancellation/crash uncertainty, corrupted journal rejection, symlink/hardlink/FIFO/directory rejection, symlink-at-open race and bounded batch size. Telemetry tests reject malformed/stale/duplicate/unowned metrics/traces, incomplete collections, forged history flags, missing observations, invalid spacing, late probes, malformed records and invalid rate windows.

`docs/verification/mock-demo-offline-v2.json` was freshly generated: ten synthetic cases completed, live score null, ten live cases pending. The older mock-demo.json remains historical and does not satisfy the stronger telemetry/history contract. No synthetic artifact is a live result. Git diff whitespace check passed.

The sections below retain the prior audit's results for traceability; **219 is the prior total, not the current total**.

## Baseline before changes

| Command | Discovered | Passed | Failed | Errors | Skipped | Framework runtime |
|---|---:|---:|---:|---:|---:|---:|
| `python3 -m unittest discover -s selfhealbench/tests -v` | 38 | 38 | 0 | 0 | 0 | 0.019s |
| `python3 -m unittest discover -s integration -v` (sandbox) | 19 | 18 | 0 | 1 | 0 | 1.777s |
| Same integration command, permitted Unix-socket access | 19 | 19 | 0 | 0 | 0 | 2.534s |
| `python3 -m pytest tests -q` | 41 | 41 | 0 | 0 | 0 | 0.26s |
| `npm test -- --reporter=dot` in `router/` | 101 (25 files) | 101 | 0 | 0 | 0 | 10.31s |

The sandbox integration error was `PermissionError: Operation not permitted` for the temporary Unix-domain socket fixture, not a broker or live-inference failure. The permitted rerun passed. Router Docker-named tests use in-memory adapters; child-process ledger tests use temporary files/SQLite.

## Final applicable suites

| Suite / command | Discovered | Passed | Failed | Errors | Skipped | Framework runtime |
|---|---:|---:|---:|---:|---:|---:|
| SelfHealBench unittest discovery | 45 | 45 | 0 | 0 | 0 | 0.026s |
| Integration unittest discovery, permitted socket fixture | 19 | 19 | 0 | 0 | 0 | 2.573s |
| Broker/RPC/budget `python3 -m pytest tests -q` | 54 | 54 | 0 | 0 | 0 | 0.29s |
| Router (unchanged; baseline remains applicable) | 101 | 101 | 0 | 0 | 0 | 10.31s |

**219 tests passed across four distinct suites.** Counts are not live scenario counts. An intermediate new regression initially errored because Python Mock reserves `assert_*` names; explicitly defining the fake `assert_ready` corrected the test fixture, and the suite then passed. No production safety check was weakened.

## What was exercised

- Real Python diagnosis adapter → real NanoClaw TS BrokerProvider → temporary file RPC → real Python broker/client → **mocked HTTP**; one correlated structured diagnosis, no tools and no hidden label/secret forwarding.
- Malformed/oversized/duplicate JSON and wrong response correlation; diagnosis timeout.
- Bounded HTTP stream, no redirects, 30s HTTP deadline, sanitized errors, timeout classification, malformed content/embedding handling in code (embedding-specific regression remains a follow-up).
- Broker path-unsafe IDs, duplicate request keys, existing-response duplicate inference prevention; existing size, budget and concurrency tests.
- Shared context/socket, canonical socket alias, matching/missing shared daemon identity, unrelated-container rejection, missing approvals, unsafe targets, overlap/missing routes/campus confirmation.
- Missing Router integration blocks campaign and direct injection/execution/cleanup before Docker/HTTP calls.
- Hostile healthy-control plan never reaches executor; missing cleanup/telemetry/history or failed rollback cannot score successful recovery; consecutive observations/deadline checked.
- Router startup, exact target/action schemas, safety budgets, root coherence, idempotency, ledger tampering, crash recovery and reconciliation.

## Demonstration and limits

`python3 -m selfhealbench.bench.demo --out docs/verification/mock-demo.json` completed. Ten synthetic cases completed with simulated recovery success 1.0, no healthy-control intervention, and a mock audit trail. `live_recovery_success` is null and all ten live scenario IDs remain pending. The demo is scripted, not AI-generated; it neither imports the production Docker executor for use nor contacts a daemon. Its regression test prohibits subprocess and urllib calls.

Python runtime observed: 3.8.10; pytest 8.3.5; pytest-asyncio 0.24.0; Router Vitest 5.0.3. Existing pytest warns that `asyncio_default_fixture_loop_scope` is unset. Dependencies were already installed; none installed by this task. `pyproject.toml` is test configuration, not an installation manifest. General NanoClaw tests, manual root scripts, and nonmatching `tests/broker/*_test.py` were not run. No production readiness claim follows from these tests.
