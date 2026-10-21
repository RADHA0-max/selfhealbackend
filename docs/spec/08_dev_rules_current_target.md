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
