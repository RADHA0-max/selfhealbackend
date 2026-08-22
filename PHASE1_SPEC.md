# Phase 1 — Schemas and the Manifest Loader

**Goal:** the typed spine. Nothing in this phase calls an LLM, touches Docker, or executes anything.

**Exit criterion:** a hand-written `Signal` JSON round-trips `inbound.db` → loader → `ActionPlan` → `outbound.db`, verified by one test command. No other service running.

---

## Scope

### Build

1. `patterns/p01_traffic_spike.yaml` — port the existing observer's thresholds into the manifest shape (see below)
2. `schema/` — `Signal`, `ActionPlan`, `Manifest` types with runtime validation (Pydantic if Python, Zod if TS — pick one language for the router and stay in it)
3. `schema/db.sql` — three SQLite schemas: `inbound`, `outbound`, `ledger`
4. `loader/` — reads `patterns/*.yaml`, validates each against the `Manifest` schema, fails loudly on any invalid file at startup

### Do NOT build

- Any LLM call
- Any Docker call
- The router gates (Phase 2)
- The detector runtime (Phase 3)
- Do not modify anything under `pattern1-traffic-spike/` — it stays untouched and running until Phase 3 replaces it

---

## Type definitions

**Signal** — what a detector emits, what the agent reads:

```
signal_id        uuid
pattern_id       string, must match a loaded manifest id
fingerprint      string  (hash of pattern_id + target + bucketed severity; for dedup)
detected_at      iso8601
target           string, must be in ALLOWED_SERVICES
severity         enum: info | warning | critical
detector         string (which plugin fired)
metrics          map<string, float>
evidence         { logs: string[], metrics_window: object, redacted: bool }
```

**ActionPlan** — what the agent writes, what the router validates:

```
plan_id          uuid
signal_id        uuid, FK to the signal
proposed_at      iso8601
action           string (Phase 2 checks this against the registry; Phase 1 just types it)
params           object (opaque here — Phase 2's Gate 1 gives it a per-action schema)
confidence       float, 0.0–1.0 inclusive
reasoning        string
requires_cloud   bool
```

Reject unknown fields on both. Not just wrong types — unknown fields. That is Gate 1's foundation and it must be built in from the start.

---

## SQLite schemas

`inbound.db` — detector writes, agent reads (read-only mount)
- `signals` table, plus a `status` column: `new | claimed | processed`
- verification outcomes get written back here as new signals (a failed fix is just another signal — no special case)

`outbound.db` — agent writes, router reads. The agent's SOLE output channel.
- `plans` table, plus `verdict` (`pending | approved | rejected`) and `rejected_by_gate` (nullable int 1–6)

`ledger.db` — router writes only. Append-only, hash-chained.
- every row carries `prev_hash` and `row_hash`
- **every** proposal AND every rejection is recorded, with the gate that rejected it
- no UPDATE or DELETE statement may exist anywhere in the codebase against this table

---

## The P01 manifest

Port from `pattern1-traffic-spike/observer/observer.py`. Follow the structure in `ARCHITECTURE_v3.md` §6. Two guards are mandatory and inherited by every pattern:

```yaml
guards:
  - "variance(metric) > 0"      # the zero-variance IsolationForest bug
  - "container_uptime > 5m"
detect:
  min_samples: 20               # the insufficient-baseline freeze
```

Both bugs cost a full session on P1. They are declarative now — fixed once, structurally, for all ten patterns.

Remediation candidates for P01: `scale_service` (risk low, `delta: +1`, `max: 6`). Nothing else yet.

---

## Verification

Write `test_phase1.py` (or `.ts`) asserting:

1. `p01_traffic_spike.yaml` loads and validates
2. A malformed manifest (missing `detect.type`) fails loudly at load, not at first use
3. A hand-written Signal inserts into `inbound.db` and reads back identical
4. A Signal with `pattern_id` not matching any manifest is rejected
5. A Signal with an extra unknown field is rejected
6. An ActionPlan with `confidence: 1.5` is rejected
7. An ActionPlan inserts into `outbound.db` and reads back identical
8. Ledger hash chain: insert 3 rows, verify each `prev_hash` matches the previous `row_hash`

All eight pass ⇒ Phase 1 done. Show me the diff and the test output.