# NanoClaw Self-Healing Backend
# Claude Code Project Instructions

## 1. PROJECT IDENTITY

This repository implements the NanoClaw-based orchestration layer for the
Self-Heal on DGX local-model autonomous remediation system.

Substrate:

- NanoClaw v2
- DGX "dada"
- 8 × NVIDIA A100-SXM4-40GB
- 1 TB RAM
- approximately 1.2 TB free storage
- MIG disabled
- no Slurm
- Docker-based deployment
- all components run on the same DGX host
- inference is local
- no cloud LLM dependency
- zero laptop compute

The architecture is defined in:

    Nanoclaw_new_docs(1).txt

That architecture document is the primary architectural reference.

When implementation details conflict with the architecture document,
do not silently choose one. Inspect the relevant section and resolve the
difference explicitly.

---

# 2. PRIMARY SYSTEM GOAL

The system automatically handles ten named infrastructure failure patterns.

The overall lifecycle is:

    OBSERVE
       ↓
    DETECT
       ↓
    HARM GATE
       ↓
    CORRELATE
       ↓
    CLASSIFY
       ↓
    REASON
       ↓
    GATE + ACT
       ↓
    VERIFY

The system:

1. observes metrics, logs and traces
2. detects anomalous behaviour
3. determines whether the anomaly is actually harmful
4. correlates related failures
5. performs deterministic classification where possible
6. uses the sandboxed LLM agent for reasoning
7. passes proposed actions through deterministic gates
8. executes only approved typed capabilities
9. verifies the result
10. rolls back when the result is worse

The system intentionally handles only its declared failure patterns.

Do NOT attempt to turn it into a general-purpose autonomous infrastructure
agent.

Unknown or unsupported failures should fail closed.

---

# 3. CORE SECURITY PRINCIPLE

The most important architectural principle is:

    THE PART THAT THINKS HAS NO POWER.
    THE PART THAT HAS POWER DOES NOT THINK.

LLM output is ALWAYS untrusted.

The LLM proposes.

The deterministic trusted layer decides.

Never make an LLM responsible for a safety-critical permission decision.

Never allow the model to directly execute arbitrary commands.

Never introduce:

    exec
    shell
    run_command
    eval
    raw_sql
    arbitrary_http_request

as general-purpose capabilities.

If a proposed action is not explicitly represented by the typed capability
registry, it must not execute.

---

# 4. THREE SECURITY ZONES

## Zone U — UNTRUSTED AGENT

NanoClaw agent.

Required properties:

- network_mode: none
- cap_drop: ALL
- read_only filesystem
- no GPU
- no Ollama binary
- no Docker socket
- no production credentials
- bounded resources
- only mediated file access

The agent can reason but cannot directly control infrastructure.

## Zone T — TRUSTED ROUTER

The router:

- contains no LLM
- contains no dynamic model-generated code
- uses deterministic checks
- validates every ActionPlan
- owns the real execution permissions
- owns the capability registry
- owns the safety gates

The router must never trust the agent merely because the request
came from NanoClaw.

Every request is independently validated.

## Zone V — VALIDATOR SANDBOX

Used for LLM-generated code patches.

Required properties:

- network_mode: none
- no GPU
- empty environment
- temporary filesystem
- bounded execution time
- destroyed after every validation run

The validator executes proposed code only after deterministic patch checks.

---

# 5. NANOCLAW RESPONSIBILITY

NanoClaw provides:

- sandboxed agent runtime
- agent lifecycle
- mediated two-file channel

This project provides:

- network isolation
- capability restrictions
- file-RPC LLM broker
- deterministic routing
- seven/eight safety gates as defined by the architecture
- capability registry
- backends
- budgets
- ledger
- verification
- rollback
- detector runtime
- classifiers
- harm gates
- incident memory
- chaos harness
- observability
- model routing

Do not assume NanoClaw's default security hardening is sufficient.

Verify the actual runtime configuration.

---

