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

