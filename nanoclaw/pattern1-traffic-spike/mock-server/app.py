"""
Mock Microservice — simulates a production API server that degrades under load.
Exposes Prometheus metrics and chaos injection endpoints for self-healing demos.
"""

import time
import random
import threading
import psutil
from flask import Flask, request, jsonify
from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
REQUEST_COUNT = Counter(
    "request_count", "Total requests", ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "request_latency_seconds", "Request latency in seconds",
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)
CPU_UTILIZATION = Gauge("cpu_utilization", "CPU utilization percentage")
MEMORY_UTILIZATION = Gauge("memory_utilization", "Memory utilization percentage")
ACTIVE_CONNECTIONS = Gauge("active_connections", "Currently active connections")
HTTP_503_COUNT = Counter("http_503_count", "Total 503 responses")
HTTP_200_COUNT = Counter("http_200_count", "Total 200 responses")
REQUEST_ARRIVALS = Counter("request_arrivals", "Requests received (counted on arrival, before processing)")

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------
chaos_state = {
    "active": False,
    "rps": 0,
    "pattern": "sudden",
    "simulated_load": 0.0,       # 0.0 – 1.0, drives latency + errors
    "start_time": 0,
    "duration_sec": 0,
}
rate_limit_state = {
    "enabled": False,
    "max_rps": 100,              # requests per second when rate-limiting
    "window_count": 0,
    "window_start": time.time(),
}
active_conns = 0

# Locks for thread safety since gunicorn uses --threads 4
active_conns_lock = threading.Lock()
rate_limit_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def update_system_metrics():
    """Refresh CPU/memory gauges from the real process."""
    CPU_UTILIZATION.set(psutil.cpu_percent(interval=None))
    MEMORY_UTILIZATION.set(psutil.virtual_memory().percent)


def get_simulated_load() -> float:
    """Return a value 0.0–1.0 representing current artificial load.
    Decays to 0 once the chaos window expires."""
    if not chaos_state["active"]:
        return 0.0

    elapsed = time.time() - chaos_state["start_time"]
    duration = chaos_state["duration_sec"]

    if elapsed > duration:
        chaos_state["active"] = False
        chaos_state["simulated_load"] = 0.0
        return 0.0

    pattern = chaos_state["pattern"]
    progress = elapsed / duration  # 0→1 over the window

    if pattern == "sudden":
        # Instant jump to full load
        load = 1.0
    elif pattern == "gradual":
        # Linear ramp: 0 → 1 over the duration
        load = progress
    elif pattern == "ddos":
        # Erratic spikes — random bursts
        load = min(1.0, 0.6 + random.random() * 0.4)
    else:
        load = 0.5

    chaos_state["simulated_load"] = load
    return load


def check_rate_limit() -> bool:
    """Return True if the request should be rejected (429)."""
    if not rate_limit_state["enabled"]:
        return False
    
    with rate_limit_lock:
        now = time.time()
        # Reset window every second
        if now - rate_limit_state["window_start"] >= 1.0:
            rate_limit_state["window_count"] = 0
            rate_limit_state["window_start"] = now
        rate_limit_state["window_count"] += 1
        return rate_limit_state["window_count"] > rate_limit_state["max_rps"]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/api/process", methods=["GET"])
def api_process():
    """Main API endpoint. Latency and error rate scale with simulated load."""
    global active_conns

    # Count arrival BEFORE any processing or sleep
    REQUEST_ARRIVALS.inc()

    # Rate-limit check
    if check_rate_limit():
        REQUEST_COUNT.labels("GET", "/api/process", "429").inc()
        return jsonify({"error": "rate limited"}), 429

    with active_conns_lock:
        active_conns += 1
    ACTIVE_CONNECTIONS.set(active_conns)

    try:
        load = get_simulated_load()
        update_system_metrics()

        # Simulate latency scaling with load
        base_latency = 0.01  # 10ms baseline
        max_latency = 5.0    # 5s under full load
        latency = base_latency + (max_latency - base_latency) * (load ** 2)
        latency *= (0.8 + random.random() * 0.4)  # ±20% jitter
        time.sleep(latency)

        REQUEST_LATENCY.observe(latency)

        # Simulate 503 errors under heavy load
        error_probability = max(0, load - 0.5) * 1.5  # starts at load=0.5, maxes at 0.75
        if random.random() < error_probability:
            HTTP_503_COUNT.inc()
            REQUEST_COUNT.labels("GET", "/api/process", "503").inc()
            return jsonify({
                "error": "service overloaded",
                "load": round(load, 3),
                "latency_ms": round(latency * 1000, 1),
            }), 503

        HTTP_200_COUNT.inc()
        REQUEST_COUNT.labels("GET", "/api/process", "200").inc()
        return jsonify({
            "status": "ok",
            "data": f"processed-{random.randint(1000, 9999)}",
            "load": round(load, 3),
            "latency_ms": round(latency * 1000, 1),
        })

    finally:
        with active_conns_lock:
            active_conns -= 1
        ACTIVE_CONNECTIONS.set(active_conns)


@app.route("/health", methods=["GET"])
def health():
    """
    Liveness check — always returns 200 unless the process is truly dead.
    Note: This does NOT reflect service load degradation, just process uptime.
    """
    return jsonify({"status": "healthy", "timestamp": time.time()})


@app.route("/metrics", methods=["GET"])
def metrics():
    """Prometheus scrape endpoint — exposition format."""
    update_system_metrics()
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/chaos/spike", methods=["POST"])
def chaos_spike():
    """Inject a traffic spike simulation.
    Body: {"rps": 500, "duration_sec": 60, "pattern": "sudden"|"gradual"|"ddos"}
    """
    data = request.get_json(force=True)
    rps = data.get("rps", 500)
    duration_sec = data.get("duration_sec", 60)
    pattern = data.get("pattern", "sudden")

    if pattern not in ("sudden", "gradual", "ddos"):
        return jsonify({"error": f"unknown pattern: {pattern}"}), 400

    chaos_state["active"] = True
    chaos_state["rps"] = rps
    chaos_state["pattern"] = pattern
    chaos_state["duration_sec"] = duration_sec
    chaos_state["start_time"] = time.time()
    chaos_state["simulated_load"] = 1.0 if pattern == "sudden" else 0.0

    return jsonify({
        "status": "chaos injected",
        "rps": rps,
        "duration_sec": duration_sec,
        "pattern": pattern,
    })


@app.route("/admin/rate-limit", methods=["POST"])
def admin_rate_limit():
    """Toggle rate limiting on/off.
    Body: {"enabled": true|false, "max_rps": 100}
    """
    data = request.get_json(force=True)
    
    with rate_limit_lock:
        rate_limit_state["enabled"] = data.get("enabled", False)
        if "max_rps" in data:
            rate_limit_state["max_rps"] = data["max_rps"]
        rate_limit_state["window_count"] = 0
        rate_limit_state["window_start"] = time.time()

    return jsonify({
        "status": "rate limiting " + ("enabled" if rate_limit_state["enabled"] else "disabled"),
        "max_rps": rate_limit_state["max_rps"],
    })


# ---------------------------------------------------------------------------
# Dev server fallback (gunicorn is used in production via Dockerfile CMD)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Debug=False for safety, even in this fallback path
    app.run(host="0.0.0.0", port=8080, debug=False)