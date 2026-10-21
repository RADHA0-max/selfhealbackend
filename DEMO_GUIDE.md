# Safe demonstration guide

Run from `/home/ollama/nanoclaw-dev`. These steps use existing dependencies and temporary/local files. They do not require a Docker deployment or new inference. Do not run root manual integration scripts or Compose commands as shortcuts.

## 1. Automated verification

```bash
python3 -m unittest discover -s selfhealbench/tests -v
python3 -m unittest discover -s integration -v
python3 -m pytest tests -q
npm --prefix router test -- --reporter=dot
```

The integration suite binds a temporary Unix socket and may require permission outside a restricted sandbox. Its LiteLLM HTTP boundary is mocked. See TEST_RESULTS.md for the fresh results already collected; rerunning is optional for presentation.

## 2. Real diagnosis plumbing with a simulated model

```bash
python3 -m unittest integration.test_nanoclaw_diagnostic_transport.DiagnosticTests.test_actual_provider_broker_client_with_mocked_http -v
```

This traverses the real NanoClaw provider, file RPC, broker and HTTP client with a fake HTTP response. Input includes a failed db probe and a synthetic secret; the test verifies redaction and no scenario-label leakage. The structured fixture output is:

```json
{"root_cause":"db","action":"clear_fault","target":"db","reason":"HTTP failure"}
```

Call it a **mocked model response through the real transport**, not a new AI diagnosis. The user's historical real AI round trip was not repeated during this audit.

## 3. Trusted Router authorization, mock action and durable audit

```bash
npm --prefix router test -- tests/docker_e2e.test.ts tests/trusted_router.test.ts tests/audit_ledger.test.ts person2-tests/backend_contract.test.ts
```

These tests exercise the actual Router against an in-memory Docker adapter. Supported scale_service actions require valid trusted synthetic evidence; unsafe targets, root mismatches and duplicate actions reject. SQLite action state and the hash-chain audit are verified in temporary directories. The backend-contract test shows benchmark diagnosis/restart payloads cannot become trusted execution.

**Boundary:** clear_fault and start_container are not executable capabilities of this Router. They must remain rejected. There is no approved mapping from a db outage to scaling, and the demo does not invent one.

## 4. Ten-case synthetic recovery and verification report

Inspect the saved `docs/verification/mock-demo.json`, or generate a fresh report at a previously unused path:

```bash
python3 -m selfhealbench.bench.demo --out /tmp/selfhealbench-demo-review.json
```

Existing outputs are never overwritten. This demonstration uses generated probes, scripted diagnoses, an in-memory recovery backend, the production plan validator, campaign orchestration, three-observation verifier and scorer. It records mock execution/cleanup events. The synthetic clock avoids waiting for real services.

Show `mode`, `limitations`, `records`, `results`, `audit`, `simulated_recovery_success`, `live_recovery_success` and `pending_live_scenarios`. Expected live score is null; all ten live scenarios remain pending. This is a separate mock harness, not an authorization bypass or a live benchmark. Its audit is not the Router's tamper-evident ledger.

## 5. Infrastructure review

Read NETWORK_SAFETY_REPORT.md and `docs/verification/network-inventory.json`. To refresh only read-only discovery into a new local path when appropriate:

```bash
python3 -m selfhealbench.bench.audit_network --out /tmp/selfhealbench-network-review.json
```

Current result: shared default daemon, no alternate context observed, no authoritative campus/VPN allocation confirmation. **NETWORK_PREFLIGHT_BLOCKED**. No subnet is approved. Passing CIDR review would only establish eligibility for human review.

## Future live-test plan — not executed, currently blocked

Before considering execution, complete the P0 rows in REMAINING_WORK.md. An operator must provide an explicitly approved isolated environment, independently verify its daemon/socket against the shared daemon, verify exact ownership/readiness, approve the exact scenario/operation and review cleanup/rollback. Resolve and test the trusted Router capability contract first; changing booleans in approval JSON cannot bypass the code block.

Use a fresh approval document, not the historical template as evidence. Populate independently observed shared_daemon_id and distinct daemon_id, canonical endpoint/context, refreshed authoritative network inventory, named operator, exact scenario list and all independent approvals. Predeploy resources through a separately reviewed operator procedure; this task supplies no network-create or Compose-up command. Keep the benchmark token in the environment without printing it. Do not infer GPU or inference access from benchmark approval.

After the missing Router code and isolated environment have been reviewed and explicitly authorized, the existing runner's exact **single-case command shape** is:

```bash
python3 -m selfhealbench.bench.run \
  --mode live --agent nanoclaw --only SHB-001 \
  --approvals /approved/selfhealbench/approval.json \
  --nanoclaw-root /home/ollama/nanoclaw-dev/nanoclaw \
  --rpc-in /approved/selfhealbench/rpc/in \
  --rpc-out /approved/selfhealbench/rpc/out \
  --model fast --approved-inference --inject --execute \
  --out /approved/selfhealbench/results/SHB-001.json
```

Paths above are explicit placeholders for reviewed resources, not existing authorized paths. The current code intentionally rejects this campaign before injection. Model selection must also resolve the fast/log mismatch noted in the audit; this syntax example does not approve that alias for live diagnosis.

First approve a healthy SHB-010 control using `--only SHB-010`, then approve each fault case separately. Never launch the ten-case campaign implicitly. Retain correlated diagnosis, trusted authorization/audit, observed fault, baseline/recovery histories, telemetry completeness and cleanup evidence for each case. Stop on cleanup failure, identity/ownership drift or uncertain execution; use reviewed manual reconciliation rather than repeated recovery. No live results are claimed until those artifacts exist.
