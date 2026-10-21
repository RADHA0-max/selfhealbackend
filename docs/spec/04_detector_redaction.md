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

