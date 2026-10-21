# Fresh test results

Audit date: 21 October 2026 (Asia/Kolkata client date). All reported test results were obtained during this audit. No real Docker faults, Docker mutations, GPU calls or live recovery were performed.

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
