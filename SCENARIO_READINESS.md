# Scenario readiness

Source: `selfhealbench/scenarios/pilot.json`, `app/service.py`, `bench/live.py`, `bench/pilot.py`. Audit date: 21 October 2026. No live faults injected. All ten scenarios are **BLOCKED**, never PASSED. Synthetic demonstration results in `docs/verification/mock-demo.json` are not execution evidence for these rows.

Primary status is BLOCKED_BY_INFRASTRUCTURE for all cases: only the shared default daemon is observed. Every case also has BLOCKED_BY_APPROVAL; SHB-001–009 additionally NEEDS_IMPLEMENTATION for the trusted recovery adapter. The code now refuses live campaigns before injection, including SHB-010, until that boundary is resolved.

| ID | Fault / target | Expected observable symptoms | Evidence available in implementation | Diagnosis category | Proposed recovery (not Router-authorized) | Cleanup | Current status |
|---|---|---|---|---|---|---|---|
| SHB-001 | HTTP error / db | db /work 503; worker and API dependency failure | Four probes, bounded Docker logs, Prometheus up; Tempo search recorded separately | db | clear_fault(db) | Reset fault, restore full healthy baseline | BLOCKED_BY_INFRASTRUCTURE |
| SHB-002 | HTTP error / auth | auth 503; API dependency failure | Same collectors; auth/API symptoms | auth | clear_fault(auth) | Reset fault, verify all services | BLOCKED_BY_INFRASTRUCTURE |
| SHB-003 | HTTP error / worker | worker 503; API dependency failure | Same collectors; worker/API symptoms | worker | clear_fault(worker) | Reset fault, verify all services | BLOCKED_BY_INFRASTRUCTURE |
| SHB-004 | HTTP error / api | API 503; dependencies may remain healthy | Same collectors; API probe | api | clear_fault(api) | Reset fault, verify all services | BLOCKED_BY_INFRASTRUCTURE |
| SHB-005 | 2600ms latency / db | db response exceeds 2000ms health bound; upstream 2s dependency timeout | Probe latency and dependency errors, logs, metrics | db | clear_fault(db) | Clear delay, verify latency and status | BLOCKED_BY_INFRASTRUCTURE |
| SHB-006 | 2600ms latency / auth | auth slow; API dependency timeout | Probe latency, API errors, logs, metrics | auth | clear_fault(auth) | Clear delay, verify latency and status | BLOCKED_BY_INFRASTRUCTURE |
| SHB-007 | 2600ms latency / worker | worker slow; API dependency timeout | Probe latency, API errors, logs, metrics | worker | clear_fault(worker) | Clear delay, verify latency and status | BLOCKED_BY_INFRASTRUCTURE |
| SHB-008 | Container stopped / db | db connection unavailable (status 0); worker/API fail | Probe connection result, bounded logs, Prometheus up | db | start_container(db) | Start exact owned container, clear residual fault, verify | BLOCKED_BY_INFRASTRUCTURE |
| SHB-009 | Container stopped / auth | auth connection unavailable; API fails | Probe connection result, logs, Prometheus up | auth | start_container(auth) | Start exact owned container, clear residual fault, verify | BLOCKED_BY_INFRASTRUCTURE |
| SHB-010 | None / none | All four /work endpoints healthy, acceptable latency | Full probes, logs, metrics; no hidden control labels | none | no_op only; no recovery mutation | No mutation or cleanup on healthy control | BLOCKED_BY_INFRASTRUCTURE |

## Criteria applying to every row

**Authorization:** exact approved isolated context, canonical socket, daemon identity distinct from independently observed shared daemon; target ownership, entire daemon workload inventory, matching network/IPAM and ports; named operator with campus allocation, network, ports, isolated context, deployment, fault-injection and recovery approvals; exact scenario list; separate approved inference scope. Approval JSON is an attestation, not an authentication system. A context name or prefix is insufficient. Current approvals are absent. Benchmark actions are schema-valid proposals only; no silent translation to scale/restart is allowed.

**Readiness:** telemetry endpoints ready and baseline verified before fault injection. Record UTC onset and monotonic recovery durations. Fault must actually be observed for SHB-001–009. Hidden expected labels stay inside the harness.

**Success:** all four services return HTTP 200, matching service identity, body status `ok`, finite latency 0–2000ms for three consecutive observations, sampled at 2s intervals within 20s. Require complete pre-action evidence, baseline and recovery histories, successful injection/fault observation where applicable, verified cleanup, and no failed/required rollback. SHB-010 additionally requires no_op. No missing/failed case leaves the denominator. These are current pilot criteria, not proof of long-term symptom absence.

**Timeout:** verification deadline 20s; HTTP probe default 3s, Prometheus/Tempo reads 4s; Docker command limit 45s. Diagnostic transport defaults to 30s (bounded ≤120s), subprocess allows 5s shutdown grace; broker HTTP total limit is now 30s. No approved live campaign timeout budget has been established. Blocking readers can overrun wall-clock verification budget, but late results cannot establish success.

**Cleanup/rollback:** current implementation starts all four approved benchmark containers and clears faults, then verifies baseline. Cleanup failure stops campaign and invalidates recovery score. This broad cleanup requires exact approval and a future trusted adapter; it is currently disabled. There is no automatic evidence-based inverse action for a worsening recovery. Manual reconciliation and a reviewed rollback plan are prerequisites for live authorization.

**Evidence limitations:** current Prometheus query is only `up`; it does not establish error-rate improvement. Tempo response freshness/completeness and Loki ingestion are not verified. The no-fault control and malicious-plan rejection are covered by mocked tests, not live runs. All scenarios are READY_FOR_SAFE_TEST only in the synthetic fixture sense demonstrated by tests; this does not change their live status.
