# Benchmark recovery capability contract — proposal v1

Status: **PROPOSED, NOT APPROVED FOR LIVE EXECUTION**. Prepared and reviewed against `TrustedRouter`, `ActionStore`, `ReconciliationService`, the audit ledger, `live.py`, and the current benchmark schemas. This is an engineering self-review, not independent security review or operator approval. No registry entries or live executor permissions are added by this proposal.

## Authority and boundaries

The LLM supplies only the existing strict four-field diagnosis. A trusted orchestrator constructs an action envelope; an authenticated operator authority approves that exact envelope. Neither model fields, scenario labels, approval booleans, a mock grant nor successful network preflight confer authority. The production Router continues to reject both capabilities until the user explicitly approves this contract and a subsequent executable implementation is reviewed.

Proposed live envelope: version 1, actionId, campaignId, capability (`clear_fault` or `start_container`), target (exactly api/db/worker/auth), purpose (`recovery` or `cleanup`), and parentActionId only for cleanup. All fields are required except that conditional parent; unknown fields, duplicate JSON keys, nonstrings and invalid IDs reject. No command, URL, path, socket, image, delay or generic parameters may come from the model. The offline prototype uses `mode: mock` instead of a live version and accepts parsed objects only; any future JSON boundary must reject duplicate keys before parsing.

An authority grant binds operatorId, actionId, campaignId, capability, target, purpose, immutable container ID, daemon ID, issuance and expiry (maximum five minutes). Live authority must resolve authenticated identity, revocation and grant provenance outside the payload, store a grant digest, and recheck immediately before dispatch. Permission to inject is separate from permission to recover; recovery permission never authorizes cleanup of unrelated resources. Prototype grants are plainly labeled fixtures and cannot enter the production Router.

## Exact target ownership

Resolve the service through a trusted campaign manifest. Require a 64-hex immutable container ID, dedicated project `selfhealbench-pilot`, scope label `isolated-pilot`, and exact Compose service label. Require the approved canonical socket/context and daemon ID distinct from the independently observed shared daemon ID. Validate the entire isolated daemon workload inventory, target labels, network membership, approved ports, no privilege/escalation/host mounts and resource restrictions. Recheck identity before dispatch; replacements are new targets requiring new approval. Prefix matching and name-only identity are prohibited.

The prototype owns four in-memory fixture resources with exact IDs and project/scope. It accepts no external backend, HTTP callback, Docker adapter or dynamic dispatch. Production deployment attestation remains an explicit unimplemented live prerequisite.

## Evidence and semantics

Trusted collection supplies a complete, baseline-verified snapshot no older than 30 seconds, no future timestamps, matching target/container/daemon and observed state. The target must be unhealthy; missing telemetry is not evidence of a fault. Hidden scenario labels are never used to authorize recovery. Correlate proposal root with the trusted target before constructing the envelope.

| Capability | Required state | Only permitted effect | Verification |
|---|---|---|---|
| clear_fault | Target running; authenticated benchmark control observation says error or latency; unhealthy probes support the target | Set benchmark fault mode to none and delay to zero at a fixed trusted endpoint | Control readback plus complete service probes and fresh telemetry |
| start_container | Exact owned container observed stopped; independent probe unavailable; not running/restarting/unknown | Start that existing immutable container once | Same ID observed running plus complete service probes and fresh telemetry |

No restart, stop, create, remove, scale, shell, arbitrary HTTP or image operations are implied. A healthy target/control rejects mutation. Success of dispatch is not recovery: three consecutive complete healthy observations at least two seconds apart within 20 seconds, with matching service identities and latency ≤2000ms, are required. Required logs/traces/metrics must be present and fresh; error-rate windows, when collected, must show nonworsening recovery. Unavailable evidence yields UNVERIFIED, never synthetic certainty.

## Idempotency, budgets and durable ordering

A trusted actionId is single-use across restarts; retries with the same or different body do not execute again. Bind immutable metadata before dispatch, then use the existing durable action store and audit mechanisms. Per-target mutex, three reservations per 15 minutes, eight globally per 15 minutes and 90-second target cooldown remain unchanged. Cleanup shares these budgets; there is no emergency bypass. Budget exhaustion before a campaign means do not inject. Reserve room for a separately authorized cleanup plan during future campaign planning; the prototype does not implement injection or reservation of a whole campaign.

Order: validate authority/evidence/ownership → verify ledger → bind metadata/claim → reserve budget → fsynced intent audit → mark EXECUTING → dispatch once → verify independently → fsynced result audit → complete → release mutex. Failure before dispatch may mark FAILED; attempts remain charged. Failure after dispatch begins, timeout, cancellation or crash preserves EXECUTING/NEEDS_RECONCILIATION and the mutex. No timeout lease may authorize repeating the operation. Action and evidence digests belong in trusted storage; audit entries contain IDs, capability and reason codes, never prompts, credentials or raw diagnostic logs.

Cross-file audit/SQLite commits are not atomic. Existing fail-closed pending states and reconciliation outbox must cover every gap. The prototype binds its metadata in the same local mock DB before the action claim; an orphan binding is denied, not resumed. It reuses production budget/ledger code, but does not claim to provide authenticated live authority or a production distributed transaction.

## Cleanup and uncertain execution

Cleanup is a new exact action with its own grant, budget, audit and parentActionId. Parent must be a completed action on the same campaign and immutable resource; no wildcard/all-services reset. A still-uncertain parent locks the target. Cleanup is never automatic on a healthy control. If already healthy, record a read-only verified/no-change outcome rather than dispatching another mutation. Cleanup failure stops the campaign; no recursive cleanup retry. A blanket start-all/clear-all loop is excluded from this proposed contract.

Starting a container has no automatically authorized inverse stop; clearing a fault has no authorized inverse re-injection. If recovery worsens health or is uncertain, stop and preserve state/evidence. A separately authenticated reconciliation operator must inspect the exact resource, establish a safe state, and authorize resolution of the exact action ID. Persist reconciliation intent and completion through the existing outbox; release the lock only after durable completion audit. Reconciliation records disposition, not a claim that original recovery succeeded. It never dispatches recovery or resets the consumed ID. Crash recovery may publish already-approved pending audit completions, never infer approval or rerun actions.

## Review findings and decisions

| Review question | Decision |
|---|---|
| Does scale_service authorize these actions? | No. No translation or registry expansion. |
| Can a fixture grant authorize live execution? | No. Separate offline module with internal in-memory resources only; production Router unchanged. |
| Can healthy, stale, incomplete or mismatched evidence pass? | Reject deterministically before mock dispatch. |
| Can a crash or timeout repeat an action? | No automatic retry; persistent unresolved ID and target lock. |
| Can cleanup exceed ownership or budgets? | No; exact parent-linked action and independent grant under the same limits. |
| Can successful verification repair missing authority/audit? | No; each boundary is independent. |
| Can a rejected or uncertain action score live recovery? | No. Prototype results always have mock status and no live score. |
| What needs explicit approval? | This capability contract, authority mechanism, exact deployment scope and later executable live implementation. None is approved by this document. |

## Offline implementation and acceptance plan

1. Add a separate mock-only prototype under `router/offline/`, strict schemas and internal fixture adapter; preserve registry and live blockers. Test both actions, rejection paths, durable duplicate/uncertain states, budget/cleanup rules, audit integrity, restart and reconciliation. The existing synthetic ten-case demo remains clearly separate.
2. Broker: descriptor-based bounded regular-file reads; broker-private durable SQLite request claims and tombstones; exclusive process ownership; atomic/fsynced publication; fail-closed uncertain claims after crashes; completed responses may be republished without inference. No live queue migration/run in this task. Keep existing wire protocol compatible. Expiry/cancellation/admission and retention require a separately specified producer contract.
3. Telemetry: pure strict freshness/shape validators, bounded sanitized raw probe observations in histories, recomputed health rather than trusted booleans, malformed record handling, fresh complete Prometheus/trace evidence and optional error-rate comparison. Connect read-only collection validation without calling it against shared infrastructure.
4. Run all four suites with mocks/temporary fixtures; update reports with exact scope and limitations. Stop before any live capability work and request explicit approval of this document.
