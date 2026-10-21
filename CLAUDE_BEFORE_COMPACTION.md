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

# 10. FILE-BASED LLM BROKER

The broker is trusted infrastructure.

Expected flow:

    Zone U agent
        ↓
    llm_rpc/in/req-<uuid>.json
        ↓
    Broker
        ↓
    validation
        ↓
    queue
        ↓
    budget
        ↓
    LiteLLM
        ↓
    llm_rpc/out/resp-<uuid>.json
        ↓
    Zone U agent

The broker interprets NOTHING.

It forwards validated requests and enforces:

- request size limits
- queue limits
- model/tier budgets
- routing
- response delivery

Request size cap:

    64 KB

Queue:

    8

Expected model budgets:

    DEEP:
        5 per hour per target
        20 per hour globally

    CODER:
        3 per hour per target

Concurrent DEEP + CODER budget:

    3
    (2 DEEP lanes + 1 CODER lane)

Do not bypass these limits for convenience.

---

# 11. CODE READ RPC

Tier 3 needs source code, but the NanoClaw agent must not have unrestricted
repository access.

Use the broker for bounded code-read requests.

Example:

    {
      "kind": "code_read",
      "paths": ["src/db/pool.py"],
      "around_line": 247,
      "context_lines": 60
    }

The broker must:

- ensure paths remain inside the repository
- enforce .codefixignore
- enforce bounded token size
- reject forbidden paths
- return only requested slices

Minimum protected areas include:

    **/auth/**
    **/crypto/**
    **/*secret*
    **/migrations/**
    **/payment/**
    .github/**
    Dockerfile*
    **/*.tf
    **/requirements*.txt
    **/package.json
    **/*.lock

Never weaken this boundary merely because a model asks for a file.

---

# 12. DETECTOR PIPELINE

Detector tick:

    every 10 seconds

Pipeline:

    guards
      ↓
    feature vector
      ↓
    rolling buffer
      ↓
    detector plugin
      ↓
    backstop
      ↓
    harm gate
      ↓
    sustained anomaly
      ↓
    fingerprint
      ↓
    deduplication
      ↓
    cross-target correlation
      ↓
    deterministic classifier
      ↓
    fault localiser
      ↓
    log clustering
      ↓
    redaction
      ↓
    verification
      ↓
    Signal → inbound.db

Detector behaviour must fail closed.

If parsing or redaction fails:

    DROP SIGNAL

Do not emit potentially unsafe evidence.

---

# 13. DETECTOR RULES

Detector plugins include:

- isolation_forest
- trend_regression
- ewma_baseline
- distribution_shift
- rate_behaviour
- ab_statistical
- graph_propagation

IsolationForest must use a multivariate feature vector and appropriate
scaling.

Do not reduce it to a single-metric anomaly detector.

Learned detectors:

- use rolling windows
- refit periodically
- freeze fitting from signal emission until verification closes
- must have a deterministic backstop

The backstop is NOT a fallback.

It runs in parallel with the ML detector.

Report separately:

- model detection
- backstop detection
- combined detection

---

# 14. HARM GATE

A metric changing is NOT automatically an incident.

The system must distinguish:

    CHANGE

from:

    HARM

Examples:

- higher traffic can be healthy
- high CPU can be normal during batch work
- memory growth after startup can be normal
- deployment activity can temporarily change metrics

Only harmful changes should progress into remediation.

---

# 15. HOSTILE LOG HANDLING

Logs are attacker-controlled input.

Required limits:

    MAX_LINE_BYTES = 8192
    MAX_FIELD_BYTES = 512
    MAX_LINES = 300
    REGEX_TIMEOUT_MS = 100

Prefer safe/linear-time regex implementations.

If parsing, redaction or verification fails:

    drop signal
    alert meta-monitor
    do not cross the trust boundary

---

# 16. LOG CLUSTERING

Raw logs must be compressed before expensive RCA.

Process:

1. normalize timestamps
2. normalize numbers
3. normalize UUIDs
4. normalize hexadecimal values
5. normalize strings
6. normalize paths
7. group by template
8. rank by count and recency
9. preserve important ERROR messages
10. preserve rare templates

Target:

    approximately 14K tokens → approximately 600 tokens

Do not simply truncate logs.

Rare diagnostic evidence must survive clustering.

---

# 17. REDACTION

Redaction occurs BEFORE evidence reaches the agent.

Redact at minimum:

    email
    ip
    token
    authorization
    cookie
    session_id
    password
    bearer
    api_key
    credit_card
    phone
    jwt

Use:

1. pattern-based detection
2. entropy-based detection
3. verification pass

If verification finds remaining secrets:

    DROP THE ENTIRE EVIDENCE BUNDLE

The agent must never receive raw secrets.

---

# 18. NANOCLAW AGENT STAGES

Five reasoning stages:

    1. TRIAGE
    2. RECALL
    3. DIAGNOSE
    4. PLAN
    5. PATCH

### TRIAGE

GPU0 / FAST.

Features only.

No raw logs.

Answers:

- is this real?
- severity?
- confidence?
- abstain?

### RECALL

GPU4 / embeddings.

Performs semantic retrieval.

If:

    cosine similarity > 0.92
    AND identical fingerprint
    AND previous outcome == SUCCESS

the system may skip DIAGNOSE and PLAN according to the architecture's
memory policy.

Memory confidence remains capped as specified by the architecture.

### DIAGNOSE

GPU2/GPU5 / DEEP.

This is the only reasoning stage that receives untrusted log content.

Treat its output as hostile.

Skip where deterministic classification is sufficiently confident,
subject to pattern-specific exceptions.

### PLAN

GPU1 / FAST.

Chooses only from the manifest's closed candidate list.

Never invent capabilities.

### PATCH

GPU3 / CODER.

Uses qwen3-coder:30b-64k with 65,536 context.

Only runs when codefix is enabled and fault localisation meets the
required threshold.

---

# 19. FAULT LOCALISATION

Fault localisation is deterministic.

Inputs can include:

- stack frames
- OTel code attributes
- endpoint-to-handler mapping
- git blame
- semantic search

The required threshold is:

    score >= 2.0

Semantic search alone must never be sufficient to nominate a patch target.

If no candidate reaches the threshold:

    Tier 3 does not run.

The system should remain advisory rather than fabricate a patch target.

---

# 20. PATCH RULES

PATCH output must satisfy all deterministic checks before sandbox execution.

Required bounds:

    ≤ 3 files
    ≤ 50 changed lines

Required:

- paths pass .codefixignore
- patch applies cleanly to recorded git HEAD
- no unauthorized dependency changes
- no dependency manifest modifications
- no CI modification
- test is added
- existing tests are not deleted
- existing tests are not modified unless explicitly allowed by architecture

A patch without a test is rejected.

A large rewrite is rejected.

A patch that cannot confidently solve the issue must abstain.

---

# 21. ROUTER

The router is:

- deterministic
- trusted
- LLM-free
- small enough to audit
- incapable of dynamic model-generated execution

Every proposed action passes through all applicable gates.

Never create a bypass path.

Never trust:

- model confidence
- model reasoning
- model claims of authorization
- caller identity alone

---

# 22. SAFETY GATES

The architecture defines deterministic safety checks covering:

1. schema/shape
2. capability allowlist
3. parameter bounds
4. target allowlist
5. blast radius
5b. cause coherence
6. risk tier / approval policy
7. patch bounds

Every action must satisfy the applicable checks.

Use strict schemas.

Unknown fields must be rejected rather than silently discarded.

---

# 23. CAUSE COHERENCE

The action must be compatible with the trusted deterministic classification.

The agent cannot override the detector's cause.

Hard vetoes must remain independent of the model.

Examples include:

- do not scale into highly concentrated attack traffic
- do not restart the last service replica
- do not block traffic when evidence indicates real human sessions
- for cascade failures, act on the identified root rather than a follower

Never remove a cause-coherence rule merely because an LLM proposes a
different action.

---

# 24. CAPABILITY REGISTRY

Actions are typed records.

They are NOT arbitrary command strings.

Capabilities include infrastructure, proxy and data-plane operations as
defined in the architecture.

There must be no generic:

    exec
    shell
    run_command
    eval
    raw_sql
    arbitrary_http_request

capability.

Tier 3 code repair uses:

    propose_patch

with:

    backend = none

It does not execute code directly.

---

# 25. DOCKER SECURITY

The DGX Docker daemon may be shared.

Never assume selfheal containers are the only containers on the host.

Use:

- selfheal-specific naming
- target allowlists
- explicit target prefixes
- narrow Docker socket proxy permissions

Docker socket proxy must deny:

    EXEC

The router must never mount the raw Docker socket directly if the
architecture specifies the socket proxy.

---

# 26. VALIDATOR WORKFLOW

For a proposed patch:

    1. APPLY at recorded HEAD
    2. BUILD
    3. NEGATIVE TEST
    4. POSITIVE TEST
    5. REGRESSION ×2
    6. produce verdict.json

The negative test is critical.

The known failing test must:

    FAIL before the fix

and:

    PASS after the fix

A patch that cannot demonstrate this is rejected.

Validator containers are disposable.

---

# 27. TIER MODEL

Tier 1:

    stabilise
    seconds
    potentially automatic

Tier 2:

    recover
    minutes
    approval-controlled

Tier 3:

    repair
    pull-request workflow
    human merge required

The bot must never merge Tier 3 changes.

The bot may prepare a PR.

A human performs the final merge.

---

# 28. LEDGER

The ledger is:

- append-only
- hash-chained
- externally anchored as specified
- used for auditability

Record relevant events including:

- gate_reject
- executed
- verified
- rolled_back
- patch_validated
- patch_rejected
- pr_opened
- merged
- tier_used

Do not modify historical ledger entries.

---

# 29. VERIFICATION AND ROLLBACK

Verification occurs at the architecture-defined intervals.

Possible outcomes:

    BETTER
        → SUCCESS
        → store outcome in memory

    PARTIAL / IMPROVING
        → WAIT
        → do not immediately act again

    SAME
        → next allowed candidate
        → bounded attempts

    WORSE
        → rollback
        → freeze if required
        → alert

Rollback must remain possible even when ordinary action budgets are
exhausted.

A failed fix may re-enter as a NEW SIGNAL.

---

# 30. INCIDENT MEMORY

Successful incidents may be embedded and stored for future retrieval.

Memory is advisory evidence.

Memory must never override:

- deterministic gates
- current detector evidence
- current target state
- current safety policy

A memory hit can accelerate reasoning.

It cannot independently authorize an unsafe action.

---

# 31. LLM CONTEXT MANAGEMENT

The current PATCH/CODER model uses:

    qwen3-coder:30b-64k

with:

    65536 context tokens

Do not reduce this to 16K without an explicit architectural decision.

Do not increase context blindly either.

Large context consumes VRAM and can affect throughput.

When working with Claude Code:

- use selective file reading
- use repository documentation
- use /context when appropriate
- avoid dumping the entire repository into prompts
- prefer targeted code slices
- use broker code_read for bounded source access where applicable

Claude Code's own conversation compaction is allowed.

Compaction does NOT replace project memory.

Persistent architectural knowledge belongs in:

    CLAUDE.md
    docs/

Do not rely on chat history as the only source of project knowledge.

---

# 32. CLAUDE CODE DEVELOPMENT WORKFLOW

For every significant task:

    1. INSPECT
    2. PLAN
    3. IMPLEMENT
    4. TEST
    5. REVIEW
    6. RE-TEST
    7. COMMIT

Before editing:

    git status
    git diff

After editing:

    git diff
    git status

Never modify unrelated files.

Never perform broad refactors for a focused task unless explicitly
requested.

Never silently change architecture.

---

# 33. PROJECT MEMORY

Use:

    CLAUDE.md

for:

- permanent coding rules
- security boundaries
- architecture invariants
- inference topology
- model routing
- development workflow

Use:

    docs/

for:

- detailed architecture decisions
- implementation decisions
- LiteLLM configuration
- broker protocol
- security decisions
- test strategy
- deployment notes
- operational runbooks
- known limitations

Do not turn CLAUDE.md into a 5000-line architecture document.

The complete architecture document remains the detailed reference.

---

# 34. TESTING REQUIREMENTS

Before claiming a feature works, actually execute its tests.

Use applicable:

- unit tests
- integration tests
- type checks
- linting
- build checks
- security tests
- negative tests
- regression tests

Never claim a test passed without running it.

For infrastructure changes, also verify:

- Docker configuration
- network isolation
- GPU assignment
- model placement
- context length
- CUDA backend
- logs
- health endpoints
- failure behaviour

---

# 35. GIT RULES

Current development branch:

    nanoclaw-litellm-integration

Never work directly on main for this integration unless explicitly
requested.

Before significant work:

    git status

After changes:

    git diff

Create focused commits.

Never:

- reset user work
- force-push shared branches
- delete unrelated changes
- rewrite history without explicit instruction

Do not commit secrets.

---

# 36. DOCUMENTATION RULE

Whenever an architectural decision changes, document:

- what changed
- why it changed
- what alternatives existed
- security implications
- performance implications
- rollback procedure
- verification performed

The current 64K PATCH context is an example of such a documented
deployment-level change.

---

# 37. NO SECRET LEAKS

Never place secrets in:

- source files
- CLAUDE.md
- docs/
- Git commits
- logs
- test fixtures
- model prompts
- screenshots

Use environment variables or the project's secret-management mechanism.

Never print API keys.

Never commit credentials.

---

# 38. LOCAL-ONLY INFERENCE

The automated Self-Heal system is local-only.

Do not add cloud model fallbacks.

Do not silently route failed local inference to an external provider.

If the local inference plane is unavailable:

    fail closed
    record the failure
    remain advisory
    do not invent a successful response

---

# 39. INTERACTIVE CLAUDE CODE VS AUTOMATED NANOCLAW

These are two different workflows.

## Interactive development

Claude Code may be used by the developer to inspect and modify the
NanoClaw repository.

The developer may use the local coder model:

    qwen3-coder:30b-64k

through the appropriate inference gateway.

## Automated self-healing

The automated agent must use:

    NanoClaw
        ↓
    file RPC
        ↓
    LLM Broker
        ↓
    LiteLLM
        ↓
    Ollama

The automated agent must NOT directly call:

    Ollama HTTP API
    LiteLLM HTTP API
    arbitrary model endpoints

The direct infer-3 tests performed during setup are validation tests only.
They are NOT the final NanoClaw architecture.

---

# 40. CURRENT IMPLEMENTATION TARGET

The immediate development target is:

    NanoClaw
       ↓
    file-based LLM RPC
       ↓
    LLM Broker
       ↓
    LiteLLM :4000
       ↓
    inference containers

The first integration milestone is to make this path work without violating:

- network isolation
- file-only model access
- model budgets
- routing
- security zones
- deterministic gates
- auditability

Do not start implementing the ten detection patterns before the core
broker and routing path is understood and tested.

---

# 41. IMPORTANT DEVELOPMENT RULE

When uncertain:

    STOP
    INSPECT THE REPOSITORY
    READ THE RELEVANT ARCHITECTURE SECTION
    PLAN
    THEN CHANGE CODE

Do not guess.

Do not invent files.

Do not invent APIs.

Do not invent model routes.

Do not invent capabilities.

Do not bypass safety controls to make a demo work.

Prefer the smallest correct implementation.
