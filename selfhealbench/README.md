# NanoClaw × SelfHealBench pilot

The real NanoClaw diagnostic provider completed one approved live inference-only request. Its correlated report is in `reports/live-diagnostic.json`. No live recovery scenarios or deployments have run. See `reports/evaluation.md` for verification scope and `reports/network-safety-review.md` for the blocked deployment approval gate.

## Safe offline use

From `/home/ollama/nanoclaw-dev`:

```bash
python3 -m unittest discover -s selfhealbench/tests -v
python3 -m unittest discover -s integration -v
node --import ./nanoclaw/node_modules/tsx/dist/loader.mjs nanoclaw/container/agent-runner/src/providers/broker.p2.test.ts
./nanoclaw/node_modules/.bin/tsc --noEmit -p nanoclaw/container/agent-runner/tsconfig.json
```

The legacy transport test binds a temporary Unix socket and may require one-time sandbox permission. All other inference in these tests uses temporary queues and a mocked HTTP response.

```bash
python3 -m selfhealbench.bench.run --agent deterministic \
  --records selfhealbench/fixtures/empty-records.json --out /tmp/selfhealbench-new-replay.json
```

The default is replay: it does not inject faults or contact Docker. `--agent recorded` evaluates existing `before` + `plan` entries keyed by scenario ID. `--agent nanoclaw` requires explicit root/queue/model parameters and a fresh inference approval. `--agent llm` is a distinct compatibility mode requiring an explicit approved local LiteLLM URL. It is never a NanoClaw fallback. Output files must be new. Empty input reports ten missing cases, not observed zero model accuracy.

## Network review

```bash
python3 -m selfhealbench.bench.network_safety \
  --candidate 10.250.30.0/26 --gateway 10.250.30.1 \
  --inventory selfhealbench/reports/network-inventory.json
```

Expected current exit code: 2 (blocked, campus allocation confirmation missing). The pure checker cannot create or attach a network. /26 has 64 total and 62 conventional usable addresses. 10/8 is not assumed free. The candidate is a review-only proposal. The read-only audit utility is available for a newly authorized context audit; the declined follow-up audit command has not been rerun.

## Deployment and live campaign

`deploy/compose.review.json` uses an external network and preloaded images only. Schema inspection is safe with a placeholder token:

```bash
BENCH_TOKEN=offline-schema-placeholder docker compose -f selfhealbench/deploy/compose.review.json config --quiet
```

No deployment or network-creation command is authorized. Exact proposed commands, ports and context requirements are in the network review. The reference app and observability configs are prepared from the professor's ZIP; no image build, package installation or pull has occurred. The original runner is preserved as inert `reference/bench-run.py.txt`, because it injects faults even without `--execute`.

`deploy/approval.template.json` is intentionally invalid for execution: all approvals are false and context/daemon/operator are unset. The prepared live backend rejects the default/shared daemon and requires a distinct approved local Unix-socket daemon, exact network/ports, labels, separate approvals and scenario scope. It cannot provision the stack. A remote isolated VM needs a separately reviewed runner location/transport.

Only after all independent approvals and deployment verification, the command shape is:

```bash
python3 -m selfhealbench.bench.run --mode live --agent nanoclaw \
  --approvals /path/to/operator-approved.json --inject --execute \
  --approved-inference --only SHB-010 \
  --nanoclaw-root /home/ollama/nanoclaw-dev/nanoclaw \
  --rpc-in /home/ollama/nanoclaw-dev/llm_rpc/in \
  --rpc-out /home/ollama/nanoclaw-dev/llm_rpc/out --model fast \
  --out /path/to/new-healthy-smoke-report.json
```

This is **not approved to run**. First authorize only the healthy scenario, then a single fault, then a separate ten-case campaign. BENCH_TOKEN must match the dedicated service token and must not be written into reports. If cleanup cannot restore baseline, the campaign stops. A timeout fails closed locally but does not cancel inference already consumed by the broker. No automatic retry occurs.

Evidence removes top-level and nested scenario/control labels, redacts supplied secrets and common credential fields/patterns, and is bounded. Unknown secrets embedded in arbitrary free text still require an evidence audit. Recovery checks require every service, correct body identity/status, finite latency, and repeated successes. Replay cannot certify recovery. All requested cases remain in scoring denominators; successful recovery latency means report sample counts alongside means.
