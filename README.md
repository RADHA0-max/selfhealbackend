# Self-Heal on DGX — Local-Model Autonomous Remediation

**Host:** DGX `dada` · `172.16.40.56`  
**OS:** Ubuntu (kernel 5.4) · **RAM:** 1 TB · **Disk free:** ~1.2 TB  
**GPUs:** 8 × A100-SXM4-40GB · Driver 535 · CUDA 12.2 · MIG off  
**Orchestration:** Docker only (no Slurm, no host CUDA toolkit, no sudo for runtime)

This system detects, diagnoses, and remediates faults in target services using **only local models**. No cloud LLM calls. Every model invocation is budgeted, audited, and gated.

---

## Design Principles

| Principle | Enforcement |
|-----------|-------------|
| One container per GPU | Hard UUID pin, `MAX_LOADED_MODELS=1`, `KEEP_ALIVE=-1` |
| No published inference ports | Internal Docker network only; LiteLLM is the sole gateway |
| File-based model calls | NanoClaw never opens sockets; broker is the only path |
| Closed candidate lists | PLAN stage chooses only from an allow-list |
| Negative test gate | A proposed patch must make a known-failing test fail |
| Human merge for Tier 3 | Bot can open PRs; only humans merge |
| Append-only ledger | Hash-chained, external hash sink |
| Meta-monitor heals nothing | Separate process, separate alert path |

★ marks items that are novel or were changed specifically for this DGX / driver 535 setup.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  INFERENCE PLANE  (one container per GPU)                                   │
│  Pinned Ollama (cuda_v12) or llama.cpp (CUDA 12.2)                          │
│  Internal network · no published ports · only LiteLLM joins                 │
│                                                                             │
│  infer-0  GPU0  triage     qwen2.5:7b-q8_0        ctx 4k   par 2            │
│  infer-1  GPU1  plan       qwen2.5:7b-q8_0        ctx 8k   par 2            │
│  infer-2  GPU2  rca        qwen2.5:32b-q4_K_M     ctx 16k  par 1            │
│  infer-2b GPU5  rca        (replica, 2nd DEEP lane) ★ ctx 16k par 1         │
│  infer-3  GPU3  patch      qwen3-coder:30b        ctx 16k  par 1            │
│  infer-4  GPU4  embed      nomic-embed-text       par 4                     │
│  GPU6–7          free / headroom / extra FAST-PLAN / dev assistant          │
│                                                                             │
│  All: temperature 0 · top_p 0.1 · repeat_penalty 1.0                        │
│       format=<JSON Schema> ⇒ malformed JSON structurally impossible         │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │ container network (same host)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  LiteLLM :4000                                                              │
│  Routes: fast │ plan │ deep (×2 balanced) │ coder │ embed                   │
│  five api_bases · num_retries 1 · NO cloud                                  │
│  fallbacks: deep→plan, fast→plan · coder has NONE (Tier 3 skips)            │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   ▲
┌──────────────────────────────────┴──────────────────────────────────────────┐
│  LLM BROKER  (trusted, ~120 lines, interprets NOTHING)                      │
│  poll llm_rpc/in/ → 64 KB cap → queue 8 → GPU budget → LiteLLM → out/      │
│  Budget: DEEP 5/h/target, 20/h global · CODER 3/h/target                    │
│          concurrent DEEP+CODER = 3 (2 DEEP lanes + 1 CODER) ★               │
│  ██ This is NanoClaw’s replaced model-call path ★ ██                        │
│  Default HTTP client is REMOVED. Files only.                                │
└──────────────────────────────────▲──────────────────┬───────────────────────┘
                        req-<uuid>.json      resp-<uuid>.json
                                   │                  ▼
┌══════════════════════════════════╪══════════════════════════════════════════┐
║  DOCKER STACK   docker compose -p selfheal   (same host)                    ║
║  Chaos arms = extra target stacks (-p selfheal-a1/a2/a3), NOT GPUs ★        ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

---

## Target Services

| Service | Prefix boundary |
|---------|-----------------|
| `selfheal-svc-api` | Real isolation boundary on shared DGX |
| `selfheal-svc-db` | Others may deploy under different prefixes |
| `selfheal-svc-worker` | |
| `selfheal-svc-auth` | |

Observability: Prometheus (10 s), Loki, OpenTelemetry traces + service graph, Envoy access log (IP, UA, cookie, timing), git mirror (read-only).

---

## Detection Pipeline (Zone T′ — semi-trusted)

`net:none` · no credentials

| Stage | Function |
|-------|----------|
| A | Anomalous? 7 plugins ∥ dumb backstop — both every tick |
| B | Harmful? Harm gate — a change is not an incident |
| C | Duplicate? Dedup 30 s + `incident_group` via topology |
| D | Why? Deterministic classifier — **no LLM** |
| E | Where? Fault localiser: stack ∩ blame ∩ OTel, score ≥ 2.0 |
| F | Compress? Log clustering ★ 14 k tok → ~600 |
| G | Redact → verify → write **one** Signal row |

Output lands in `inbound.db` (read-only for the agent).

---

## NanoClaw Agent (Zone U)

`net:none` · `cap_drop:ALL` · `read_only` · no GPU · no ollama binary  
⚠ Verify isolation with `docker inspect`.

| Stage | GPU / Model | Notes |
|-------|-------------|-------|
| 1 TRIAGE | infer-0 (GPU0) | Features only — **no log text** |
| 2 RECALL | infer-4 (GPU4) | k-NN; sim > 0.92 ⇒ skip 3 & 4, tier = NONE ★ |
| 3 DIAGNOSE | infer-2 / infer-2b (GPU2\|5) | **Only** stage that reads untrusted bytes; 2 DEEP lanes in parallel ★ |
| 4 PLAN | infer-1 (GPU1) | Choose from a **closed** candidate list |
| 5 PATCH | infer-3 (GPU3) | Minimal diff + one FAILING test ★; gated by `codefix.enabled` **and** localiser ≥ 2.0 |

Every call: write file → broker → LiteLLM → container. **No sockets.**

---

## Decision & Execution Paths

```
outbound.db  { action? patch? both? }
        │
        ├──────────────────────────────┐
        ▼                              ▼
┌───────────────────────┐   ┌──────────────────────────────────────┐
│ ZONE T — ROUTER       │   │ ZONE V — VALIDATOR SANDBOX           │
│ (NO LLM)              │   │ Executes LLM-written code            │
│                       │   │ net:none · env:{} · tmpfs · 120 s    │
│ G1 shape              │   │ NO GPU · destroyed after EVERY run   │
│ G2 allowlist          │   │                                      │
│ G3 bounds             │   │ 1 APPLY     at recorded HEAD         │
│ G4 target ★           │   │ 2 BUILD                              │
│ G5 blast              │   │ 3 NEGATIVE ★ stash fix, run test —   │
│ G5b cause match       │   │     it MUST FAIL, else REJECT        │
│ G6 risk               │   │ 4 POSITIVE  suite + new test         │
│ G7 patch bounds       │   │ 5 REGRESS   ×2, deterministic?       │
│                       │   └────────────────┬─────────────────────┘
│ dockerproxy EXEC:0 ★  │                    │ verdict.json
│ narrow allowlist onto │                    ▼
│ a SHARED daemon       │         ┌────────────────────────────┐
│                       │         │ PR OPENER (router only)    │
│ EXECUTOR              │         │ scoped token · NO workflows│
│ Docker│Envoy│Data     │         │ selfheal/* → main, NEVER   │
│ TIER 1 stabilise ~sec │         │ push                       │
│ TIER 2 recover   ~min │         │ branch protection: bot     │
└───────────┬───────────┘         │ cannot approve / merge     │
            │                     └──────────────┬─────────────┘
            │                                    ▼
            │                     ┌────────────────────────────┐
            │                     │ ██ HUMAN MERGES ██  TIER 3 │
            │                     └──────────────┬─────────────┘
            ▼                                    │
┌──────────────────────────────────────────┐     │
│ VERIFIER  +60 s / +300 s (+1800 s P02)   │     │
│   better  → SUCCESS → embed → memory.db  │     │
│   partial → improving: WAIT, do not act ★│     │
│   same    → next candidate (max 2)       │     │
│   worse   → inverse() → freeze → page    │     │
│   a failed fix re-enters as a NEW SIGNAL ★│    │
└───────────────────────┬──────────────────┘     │
                        ▼                        │
┌────────────────────────────────────────────────┴─────────────────┐
│ LEDGER — append-only · hash-chained · external hash sink         │
│   gate_reject · executed · verified · rolled_back                │
│   patch_validated · patch_rejected · pr_opened · merged          │
│   + tier_used ⇒ "how many incidents needed the 32B at all?" ★    │
└──────────────────────────────────────────────────────────────────┘
```

---

## Meta-Monitor

Separate process, separate alert path. Observes:

- Per-container VRAM
- Queue depth
- Tier mix
- PR merge rate
- Ledger chain integrity
- Rollback rate
- Runtime check (CUDA, not Vulkan) ★

**Heals nothing, on purpose.**

---

## Inference Configuration (hard constraints)

```
temperature     = 0
top_p           = 0.1
repeat_penalty  = 1.0
format          = <JSON Schema>   # malformed JSON is structurally impossible
```

⚠ Under a real 12–16 k prompt keep VRAM < ~39 GB per card.  
⚠ Confirm logs show `library=cuda variant=v12 compute=8.0` (not Vulkan/CPU).

---

## Model Roles Summary

| Alias | Container | GPU | Model | Context | Parallel |
|-------|-----------|-----|-------|---------|----------|
| triage / fast | infer-0 | 0 | qwen2.5:7b-q8_0 | 4 k | 2 |
| plan | infer-1 | 1 | qwen2.5:7b-q8_0 | 8 k | 2 |
| deep / rca | infer-2 | 2 | qwen2.5:32b-q4_K_M | 16 k | 1 |
| deep / rca (replica) | infer-2b | 5 | same | 16 k | 1 |
| coder / patch | infer-3 | 3 | **qwen3-coder:30b** | 16 k | 1 |
| embed | infer-4 | 4 | nomic-embed-text | — | 4 |
| free | — | 6–7 | headroom / dev | — | — |

---

## Working with the Local Coder Model (`qwen3-coder:30b`)

The patch model lives in **infer-3** (GPU3). It is reachable only through LiteLLM (`:4000`) or the file-based LLM Broker.

### Interactive coding agent (Claude Code CLI)

Claude Code can be pointed at LiteLLM and used as a human coding agent on the DGX host (outside Zone U):

```bash
export ANTHROPIC_BASE_URL="http://localhost:4000"
export ANTHROPIC_AUTH_TOKEN="sk-local"
export ANTHROPIC_API_KEY=""
export ANTHROPIC_MODEL="coder"          # or the exact LiteLLM model name

claude
```

This is for interactive development and exploration. It does **not** participate in the automated NanoClaw loop (which remains file-only and budgeted).

### Automated path (NanoClaw)

```
write req-<uuid>.json → llm_rpc/in/
         ↓
LLM Broker (budget + queue + GPU accounting)
         ↓
LiteLLM → infer-3
         ↓
resp-<uuid>.json ← llm_rpc/out/
```

---

## Safety & Isolation Quick Reference

| Zone | Network | Caps | Writable | GPU | Credentials |
|------|---------|------|----------|-----|-------------|
| T′ Detector | none | — | limited | no | none |
| U NanoClaw | none | ALL dropped | read_only | no | none |
| V Validator | none | — | tmpfs only | no | env:{} |
| T Router | controlled | dockerproxy EXEC:0 | — | no | scoped |
| Inference | internal only | — | — | yes (pinned) | none exposed |

---

## Operational Commands (host)

```bash
# Inference health
docker ps --filter name=infer-
docker logs infer-3 2>&1 | grep -E 'library=cuda|qwen3-coder|VRAM'

# GPU / VRAM
nvidia-smi -i 3
watch -n 2 'nvidia-smi -i 3 --query-gpu=memory.used,memory.total,utilization.gpu --format=csv'

# LiteLLM
curl -s http://localhost:4000/v1/models | jq .

# Stack
docker compose -p selfheal ps
docker compose -p selfheal logs -f
```

---

## Tier Summary

| Tier | Latency | Typical action | Model involvement |
|------|---------|----------------|-------------------|
| 1 | ~seconds | Stabilise (Docker / Envoy / data) | none or fast |
| 2 | ~minutes | Recover | plan / deep |
| 3 | human | Merge PR | coder (patch) + human |

A failed fix re-enters the system as a **new Signal**.

---

## License & Status

Internal research / production self-healing stack.  
All inference is local. No external model providers are contacted at runtime.
