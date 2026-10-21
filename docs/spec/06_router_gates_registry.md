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

