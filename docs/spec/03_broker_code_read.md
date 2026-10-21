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

