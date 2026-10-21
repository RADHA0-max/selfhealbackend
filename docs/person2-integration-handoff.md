# Person 2 — NanoClaw / SelfHealBench Integration Handoff

## Status

Real NanoClaw agent-initiated diagnosis: VERIFIED.

Automated checks:
- Python integration tests: 12 passed
- TypeScript broker-provider tests: 3 passed
- TypeScript typecheck: passed

Live broker request:
`req-b20d588d-9db4-47f3-a71d-f19415f4a023`

The agent returned:
{"root_cause":"database connection issue","action":"monitor","target":"database","reason":"connection refused by database service"}

This was synthetic evidence. No remediation was executed.

## Person 2 implementation

- `integration/nanoclaw_adapter.py`
  - `NanoClawBenchAdapter(transport).diagnose(evidence: dict) -> dict`
  - Accepts `probes`, `docker_logs`, and `prometheus`
  - Truncates Docker logs to 8,000 characters
  - Limits the diagnosis prompt to 60 KiB
  - Requests JSON inside NanoClaw's required delivery wrapper
  - Strictly validates four string fields:
    `root_cause`, `action`, `target`, `reason`
  - Does not execute proposed actions

- `integration/nanoclaw_transport.py`
  - `NanoClawTransport(root, agent_group_id, session_id, timeout=120)`
  - Sends requests through the actual NanoClaw CLI socket
  - Uses unique request markers and correlated SQLite mailboxes
  - Does not bypass the agent by calling the broker directly

- `integration/test_nanoclaw_adapter.py`
- `integration/test_nanoclaw_transport.py`
- `nanoclaw/container/agent-runner/src/providers/broker.p2.test.ts`
- `docs/nanoclaw-integration-trace.md`

## Current verified runtime

Agent group: `ag-1791920154294-km8ujs`
Session: `sess-1791920358602-f23brc`
Provider: `broker`
Model alias observed: `fast`

These IDs are environment-specific; do not hardcode them in benchmark code.

## Person 3 integration contract

Call `NanoClawBenchAdapter.diagnose(evidence)` with evidence collected
by Person 1. The return value is a proposed diagnosis, not permission
to execute remediation.

Person 3 owns:
- Benchmark runner dispatch and adapter selection
- Safety validation and action allowlisting
- Remediation execution and evaluation
- Benchmark-specific configuration

## Known limitations

1. SelfHealBench `bench/run.py` is not present in this checkout.
   Final placement under `selfhealbench/bench/agents/` is pending.
2. The current running agent predates the latest broker-provider source
   changes; those changes passed isolated tests but were not verified
   in a freshly started live agent.
3. Outbound completion uses a 0.5-second quiet-period heuristic rather
   than an explicit end-of-turn signal.
4. Model output can propose unsupported actions, such as `monitor`.
   Person 3 must validate proposals before any execution.
5. The prompt treats diagnostic logs as untrusted data, but prompt text
   alone is not a security boundary.
6. The transport currently assumes local access to the CLI socket and
   session mailbox databases.
