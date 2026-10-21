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

