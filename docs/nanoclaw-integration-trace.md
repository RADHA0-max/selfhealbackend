# NanoClaw Integration Trace — Person 2

Date: 2026-10-20
Scope: NanoClaw agent-to-broker inference integration.
Owner: Person 2 (Integration Engineer).

## Verified inference path

1. `nanoclaw/scripts/chat.ts` sends a message through the CLI Unix socket.
2. `nanoclaw/src/channels/cli.ts` accepts the inbound message.
3. NanoClaw routes it to the configured agent group.
4. `nanoclaw/container/agent-runner/src/index.ts` starts the configured provider.
5. `nanoclaw/container/agent-runner/src/providers/broker.ts` writes an atomic
   `req-<uuid>.json` request to `/llm_rpc/in`.
6. The host broker reads the corresponding mounted `llm_rpc/in` directory.
7. `broker/main.py` processes the request through `broker/litellm_client.py`.
8. LiteLLM routes the `fast` alias to the configured local Qwen inference backend.
9. The broker writes `resp-<request_id>.json` into `llm_rpc/out`.
10. The agent-side broker provider reads the response, validates its request ID,
    and yields the result to NanoClaw.
11. NanoClaw delivers the formatted message to the CLI.

## Real agent-initiated round trip

CLI request marker: `P2-LIVE-20261020-B`

Broker request ID:
`req-84d0ae52-4092-413b-8259-b418fa79102e`

Broker log:
`Processing request req-84d0ae52-4092-413b-8259-b418fa79102e for model fast`

LiteLLM response:
`<message to="local-cli">P2-LIVE-20261020-B</message>`

Observed CLI output:
`P2-LIVE-20261020-B`

Result: PASS. The request originated from NanoClaw, traversed the broker,
and the response was delivered back to the CLI.

## Integration defect and fix

Observed defect: when NanoClaw requested a formatting correction, the broker
provider sent only the correction prompt and discarded the original prompt
and previous model response.

Fix: maintain conversation history across `AgentQuery.push()` calls within
the active provider query. Preserve the original task and prior assistant
response when issuing a corrective retry. Bound serialized broker requests
to 64 KiB. Allow optional RPC directories for isolated tests without changing
production directory defaults.

Modified provider:
`nanoclaw/container/agent-runner/src/providers/broker.ts`

## Automated regression tests

Test file:
`nanoclaw/container/agent-runner/src/providers/broker.p2.test.ts`

Executed with Node.js 22 and `tsx`:

- Conversation history retained across corrective retries: PASS
- Oversized requests rejected before entering the queue: PASS
- Mismatched response IDs rejected: PASS
- TypeScript compilation (`pnpm exec tsc --noEmit`): PASS

These tests use temporary RPC directories, not the live broker queue.

## Limitations and outstanding work

- The live marker test succeeded on its first response. It does not prove
  that the running Bun process loaded the updated retry-handling module.
- The current regression suite does not yet cover broker unavailability,
  timeouts, concurrency, or budget exhaustion.
- The SelfHealBench Python package is not present in the inspected checkout.
  `NanoClawBenchAdapter.diagnose(evidence)` remains unimplemented.
- CLI routed messages avoid superseding interactive chat clients, but a
  correlated, isolated reply path has not yet been verified.
- The adapter must invoke the real NanoClaw agent, never bypass the agent
  with a direct Python broker request.
- No remediation, fault injection, router, safety, or scoring functionality
  belongs to Person 2's implementation.

## Ownership boundary

Person 2 owns the agent integration, adapter, integration tests, and this
trace document. Person 1 owns evidence collection. Person 3 owns routing,
safety, remediation authorization, evaluation, and scoring.
