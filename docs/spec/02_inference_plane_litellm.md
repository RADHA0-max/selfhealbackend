
# 6. INFERENCE PLANE

The inference plane uses one Ollama container per GPU.

Rules:

- GPU is pinned by UUID
- OLLAMA_KEEP_ALIVE=-1
- OLLAMA_MAX_LOADED_MODELS=1
- no --gpus all
- no :latest production image tags
- no SCHED_SPREAD
- one 32B-class model per card
- internal Docker network
- no published inference ports
- LiteLLM is the inference gateway
- CUDA backend is mandatory
- Vulkan is not acceptable
- CPU fallback is not acceptable for production inference

Every inference container must be validated with:

- correct GPU
- correct model
- correct context
- 100% GPU placement where expected
- CUDA backend
- expected VRAM usage

Default generation parameters:

    temperature = 0
    top_p = 0.1
    repeat_penalty = 1.0

Where structured output is required:

    format = JSON Schema

Malformed structured output should be prevented through constrained
decoding rather than repaired downstream.

Every model schema must contain an explicit abstain path where applicable.

---

# 7. CURRENT DGX INFERENCE TOPOLOGY

## GPU0 — TRIAGE

Container:

    infer-0

Role:

    FAST / TRIAGE

Model:

    qwen2.5:7b-q8_0

Context:

    4096

Parallel:

    2

Purpose:

    Determine whether a detected incident is real and estimate severity.

Input should contain clean structured features.

Do NOT send raw log text to TRIAGE.

---

## GPU1 — PLAN

Container:

    infer-1

Role:

    PLAN

Model:

    qwen2.5:7b-q8_0

Context:

    8192

Parallel:

    2

Purpose:

    Select an allowed capability from a closed candidate list and populate
    its typed parameters.

PLAN must never invent arbitrary actions.

---

## GPU2 — DEEP RCA LANE A

Container:

    infer-2

Role:

    DEEP / DIAGNOSE

Model:

    qwen3-coder:30b

Context:

    16384

Parallel:

    1

Purpose:

    Root-cause analysis.

This is one of the DEEP lanes.

It is allowed to process the sanitized and clustered evidence that may contain
attacker-controlled log content.

Treat all model output as hostile.

---

## GPU5 — DEEP RCA LANE B

Container:

    infer-2b

Role:

    DEEP / DIAGNOSE replica

Model:

    qwen2.5:32b-q4_K_M

Context:

    16384

Parallel:

    1

Purpose:

    Second DEEP lane for concurrent incident diagnosis.

This lane balances infer-2.

Two DEEP lanes may process independent incidents concurrently.

---

## GPU3 — PATCH / CODER

Container:

    infer-3

Role:

    PATCH / CODER

CURRENT MODEL:

    qwen3-coder:30b-64k

CURRENT CONTEXT:

    65536

Parallel:

    1

This is an intentional deployment update from the original architecture's
16K PATCH context.

The 64K context has been explicitly validated on infer-3.

The model must remain pinned to GPU3.

Purpose:

    Produce minimal code patches for Tier 3 remediation.

PATCH must:

- produce a minimal unified diff
- change as few lines as possible
- avoid reformatting
- add no unnecessary dependencies
- never delete tests
- include exactly the required regression test
- support abstention when confidence is insufficient

PATCH is only permitted when:

    codefix.enabled == true

AND:

    fault_localiser_score >= 2.0

PATCH output is a proposal.

PATCH never directly modifies the repository.

---

## GPU4 — RECALL / EMBEDDINGS

Container:

    infer-4

Role:

    RECALL / EMBEDDINGS

Model:

    nomic-embed-text

Parallel:

    4

Purpose:

    Semantic retrieval of previous incidents, RCA information,
    remediation history and related technical knowledge.

Embedding inference is not reasoning.

It must not be used as a substitute for RCA or deterministic safety checks.

---

## GPU6 / GPU7

Reserved for:

- headroom
- temporary validation
- additional FAST/PLAN capacity
- development assistant workloads

Do not consume these GPUs for production roles without explicitly
documenting the change.

---

# 8. INFERENCE ROUTING

The logical LiteLLM routes are:

    fast
    plan
    deep
    coder
    embed

Expected mapping:

    fast  → infer-0
    plan  → infer-1
    deep  → infer-2 / infer-2b
    coder → infer-3
    embed → infer-4

DEEP has two balanced lanes.

CODER has NO automatic fallback.

If the CODER route is unavailable, Tier 3 should skip rather than silently
fall back to a different model.

Expected fallbacks:

    deep → plan
    fast → plan

Do not introduce cloud fallbacks.

---

# 9. LITELLM

LiteLLM is the inference gateway.

Expected architecture:

    NanoClaw
        ↓
    file-based LLM Broker
        ↓
    LiteLLM :4000
        ↓
    Ollama inference container

LiteLLM must be the sole model gateway for the automated system.

NanoClaw must NOT directly connect to Ollama.

Do not add direct HTTP inference calls to NanoClaw.

The agent's model-call path is FILE-ONLY.

LiteLLM configuration must remain local-only.

Do not add Anthropic, OpenAI, Gemini or other cloud providers to the
automated inference configuration unless explicitly requested and
architecturally approved.

---

