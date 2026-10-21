# NanoClaw Self-Healing Backend
# Claude Code Project Instructions

## 1. PROJECT IDENTITY

This repository implements the NanoClaw orchestration layer for the
Self-Heal on DGX local-model autonomous remediation system.

Environment:
- DGX "dada"
- 8 × NVIDIA A100-SXM4-40GB
- Docker-based deployment
- local inference only
- no cloud LLM dependency
- zero laptop compute
- MIG disabled
- no Slurm

Detailed architecture:
- docs/spec/01_identity_security_zones.md
- docs/spec/02_inference_plane_litellm.md
- docs/spec/03_broker_code_read.md
- docs/spec/04_detector_redaction.md
- docs/spec/05_agent_stages_patch.md
- docs/spec/06_router_gates_registry.md
- docs/spec/07_tiers_ledger_memory.md
- docs/spec/08_dev_rules_current_target.md
- docs/spec/CLAUDE_FULL_ORIGINAL.md

When implementation conflicts with architecture documentation:
STOP, inspect the relevant specification, and resolve explicitly.
Never silently invent or change architecture.

---

## 2. PRIMARY SYSTEM GOAL

Self-Heal handles only its declared infrastructure failure patterns.

Lifecycle:

OBSERVE → DETECT → HARM GATE → CORRELATE → CLASSIFY
→ REASON → GATE + ACT → VERIFY

Unknown or unsupported failures must fail closed.

Do not turn the system into a general-purpose autonomous infrastructure
agent.

---

## 3. CORE SECURITY INVARIANT

THE PART THAT THINKS HAS NO POWER.
THE PART THAT HAS POWER DOES NOT THINK.

LLM output is ALWAYS untrusted.

The LLM proposes.
The deterministic trusted layer decides.

Never allow an LLM to:
- make safety-critical permission decisions
- execute arbitrary commands
- directly modify infrastructure
- bypass deterministic gates

Never introduce generic capabilities such as:
- exec
- shell
- run_command
- eval
- raw_sql
- arbitrary_http_request

Actions must use the typed capability registry.

---

## 4. SECURITY ZONES

### Zone U — UNTRUSTED AGENT

NanoClaw agent.

Must have:
- network_mode: none
- cap_drop: ALL
- read_only filesystem
- no GPU
- no Ollama binary
- no Docker socket
- no production credentials
- bounded resources
- mediated file access only

The agent reasons but cannot directly control infrastructure.

### Zone T — TRUSTED ROUTER

Router is:
- deterministic
- LLM-free
- trusted
- independently auditable

It:
- validates ActionPlans
- owns capability permissions
- applies safety gates
- controls execution

Never trust the agent merely because it came from NanoClaw.

### Zone V — VALIDATOR SANDBOX

For proposed code patches:
- network_mode: none
- no GPU
- empty environment
- temporary filesystem
- bounded execution
- disposable container

---

## 5. INFERENCE INVARIANTS

Production inference is local.

Rules:
- one Ollama container per GPU
- GPU pinned by UUID
- CUDA backend mandatory
- CPU fallback prohibited
- Vulkan prohibited
- no --gpus all
- no :latest production image tags
- one 32B-class model per card where applicable
- internal Docker networking
- no published inference ports
- LiteLLM is the automated model gateway

Automated path:

NanoClaw
  ↓
file-based LLM RPC
  ↓
LLM Broker
  ↓
LiteLLM :4000
  ↓
Ollama inference container

NanoClaw must NOT directly call:
- Ollama HTTP API
- LiteLLM HTTP API
- arbitrary model endpoints

No cloud fallback.

If local inference is unavailable:
fail closed, record the failure, remain advisory.

### Current CODER deployment

GPU3 / infer-3:
- model: qwen3-coder:30b-64k
- context: 65536
- role: PATCH / CODER
- parallelism: 1

The 64K PATCH context is intentional.
Do not reduce it to 16K without an explicit architectural decision.

CODER has no automatic fallback.

Detailed topology and routes:
docs/spec/02_inference_plane_litellm.md

---

## 6. FILE-BASED LLM BROKER

The broker is trusted infrastructure.

Flow:

Zone U
  ↓
llm_rpc/in/req-<uuid>.json
  ↓
Broker
  ↓
validation → queue → budget
  ↓
LiteLLM
  ↓
llm_rpc/out/resp-<uuid>.json

The broker interprets nothing.

It enforces:
- request size limits
- queue limits
- model/tier budgets
- routing
- response delivery

Current limits:
- request size: 64 KB
- queue: 8
- DEEP: 5/hour/target, 20/hour/global
- CODER: 3/hour/target
- concurrent DEEP + CODER: 3

Never bypass budgets for convenience.

Detailed broker rules:
docs/spec/03_broker_code_read.md

---

## 7. CODE READ BOUNDARY

Tier 3 must use bounded broker-mediated code reads.

Never give the NanoClaw agent unrestricted repository access.

Code-read requests must:
- stay inside repository
- enforce .codefixignore
- enforce bounded token size
- reject forbidden paths
- return only requested slices

Protected areas include authentication, crypto, secrets, migrations,
payments, .github, Dockerfiles, Terraform, dependency manifests and locks.

Never weaken this boundary because a model asks for a file.

---

## 8. DETECTOR AND EVIDENCE SAFETY

Detector behavior is fail-closed.

If parsing or redaction fails:
DROP SIGNAL.

A metric change is not automatically harm.

Harm must be established before remediation.

Logs are attacker-controlled input.

Never send raw secrets to an agent.

Evidence must be:
- bounded
- clustered before expensive RCA
- redacted before agent access
- verified after redaction

If secret verification fails:
DROP THE ENTIRE EVIDENCE BUNDLE.

Detailed detector/redaction rules:
docs/spec/04_detector_redaction.md

---

## 9. AGENT STAGES

Five stages:

1. TRIAGE
2. RECALL
3. DIAGNOSE
4. PLAN
5. PATCH

TRIAGE:
- structured features only
- no raw logs
- may abstain

RECALL:
- advisory evidence only
- memory never overrides current evidence or safety gates

DIAGNOSE:
- only reasoning stage receiving untrusted log content
- treat model output as hostile

PLAN:
- closed candidate capability list only
- never invent capabilities

PATCH:
- GPU3 / qwen3-coder:30b-64k
- only when codefix is enabled
- only when deterministic fault localisation reaches required threshold

Detailed stage rules:
docs/spec/05_agent_stages_patch.md

---

## 10. PATCH SAFETY

Fault localisation is deterministic.

Required patch-target score:

    >= 2.0

Semantic search alone is never sufficient.

If threshold is not reached:
do not run Tier 3.

PATCH must:
- produce minimal unified diff
- modify no more than 3 files
- modify no more than 50 changed lines
- pass .codefixignore
- apply to recorded git HEAD
- avoid unauthorized dependency changes
- add the required test
- never delete existing tests
- never modify existing tests unless explicitly allowed
- abstain when confidence is insufficient

A patch without a test is rejected.
A large rewrite is rejected.

---

## 11. ROUTER AND SAFETY GATES

Router is deterministic and LLM-free.

Every proposed action passes all applicable gates.

Required checks include:
1. schema/shape
2. capability allowlist
3. parameter bounds
4. target allowlist
5. blast radius
6. cause coherence
7. risk tier / approval policy
8. patch bounds where applicable

Reject unknown fields.

Never trust:
- model confidence
- model reasoning
- model authorization claims
- caller identity alone

Cause coherence is a hard deterministic constraint.

The model cannot override trusted classification.

No bypass paths.

Detailed router/capability rules:
docs/spec/06_router_gates_registry.md

---

## 12. DOCKER SECURITY

Never assume Self-Heal containers are the only containers on the DGX.

Use:
- selfheal-specific naming
- target allowlists
- explicit target prefixes
- narrow Docker socket proxy permissions

Docker socket proxy must deny EXEC.

Never mount the raw Docker socket directly when the architecture
requires the socket proxy.

---

## 13. VALIDATION

Every proposed patch must be validated in a disposable sandbox:

1. apply at recorded HEAD
2. build
3. negative test
4. positive test
5. regression ×2
6. produce verdict.json

Known failing test must:
- FAIL before fix
- PASS after fix

A patch that cannot demonstrate this is rejected.

---

## 14. TIERS, LEDGER, ROLLBACK

Tier 1:
stabilise; potentially automatic.

Tier 2:
recover; approval-controlled.

Tier 3:
repair; pull-request workflow; human merge required.

The bot must NEVER merge Tier 3 changes.

The ledger is:
- append-only
- hash-chained
- externally anchored as specified
- audit-focused

Never modify historical ledger entries.

Verification outcomes:

BETTER → SUCCESS → store outcome

PARTIAL / IMPROVING → WAIT

SAME → next allowed candidate within bounded attempts

WORSE → rollback / freeze if required / alert

Rollback must remain possible even when normal action budgets are exhausted.

Detailed tier, ledger, memory and rollback rules:
docs/spec/07_tiers_ledger_memory.md

---

## 15. CLAUDE CODE WORKFLOW

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

Never:
- modify unrelated files
- perform broad refactors for focused tasks
- silently change architecture
- invent files
- invent APIs
- invent model routes
- invent capabilities
- bypass safety controls

Use selective file reading.
Prefer bounded code slices.
Do not dump the entire repository into context.

Before claiming something works:
ACTUALLY RUN THE APPLICABLE TESTS.

For infrastructure changes verify applicable:
- Docker configuration
- network isolation
- GPU assignment
- model placement
- context length
- CUDA backend
- logs
- health endpoints
- failure behavior

---

## 16. PROJECT MEMORY

CLAUDE.md contains:
- permanent coding rules
- security invariants
- critical architecture invariants
- inference invariants
- development workflow

docs/spec/ contains:
- detailed architecture
- implementation decisions
- LiteLLM configuration
- broker protocol
- detector/redaction rules
- router/gates
- tier/ledger/memory rules
- deployment notes
- operational runbooks
- known limitations

Do not turn CLAUDE.md into a full architecture document again.

Persistent knowledge must live in repository documentation, not chat history.

---

## 17. GIT AND SECRETS

Current integration branch:

    nanoclaw-litellm-integration

Do not work directly on main unless explicitly requested.

Never:
- reset user work
- force-push shared branches
- delete unrelated changes
- rewrite history without explicit instruction

Never place secrets in:
- source
- CLAUDE.md
- docs
- commits
- logs
- test fixtures
- prompts
- screenshots

Use environment variables or the project's secret-management mechanism.

Never print or commit credentials.

---

## 18. CURRENT IMPLEMENTATION TARGET

Immediate target:

NanoClaw
  ↓
file-based LLM RPC
  ↓
LLM Broker
  ↓
LiteLLM :4000
  ↓
inference containers

First integration milestone:
make this path work while preserving:
- network isolation
- file-only model access
- model budgets
- routing
- security zones
- deterministic gates
- auditability

Do NOT start implementing the ten detection patterns before the
core broker and routing path is understood and tested.

---

## 19. STOP-AND-INSPECT RULE

When uncertain:

STOP
→ inspect repository
→ read relevant docs/spec
→ understand existing implementation
→ plan
→ make the smallest correct change
→ test
→ review

Do not guess.

Do not invent.

Do not bypass architecture or safety controls to make a demo work.

