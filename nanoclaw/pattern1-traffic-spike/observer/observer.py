import time
import json
import logging
import requests
import numpy as np
import redis
from collections import deque
from sklearn.ensemble import IsolationForest
from statsmodels.tsa.holtwinters import ExponentialSmoothing

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Config
PROMETHEUS_URL = "http://prometheus:9090"
REDIS_HOST = "redis"
POLL_INTERVAL = 10  # seconds
HISTORY_SIZE = 180  # 30 mins at 10s intervals
CAPACITY_THRESHOLD = 800  # Assume 1000 RPS is max capacity, alert at 80%
BASELINE_REPLICAS = 2

# Scale-down thresholds
SCALEDOWN_RATE_THRESHOLD = 50
SCALEDOWN_CPU_THRESHOLD = 30.0
SUSTAINED_LOW_TRAFFIC_WINDOW = 300  # 5 minutes

# Recovery thresholds
RECOVERY_LATENCY_THRESHOLD = 1.0
RECOVERY_ERROR_THRESHOLD = 0.05
RECOVERY_CPU_THRESHOLD = 70.0

r = redis.Redis(host=REDIS_HOST, decode_responses=True)

class MetricsPoller:
    def __init__(self):
        self.history = {
            "request_rate": deque(maxlen=HISTORY_SIZE),
            "cpu_util": deque(maxlen=HISTORY_SIZE),
            "latency": deque(maxlen=HISTORY_SIZE),
            "error_rate": deque(maxlen=HISTORY_SIZE)
        }
        self.iso_forest = IsolationForest(contamination=0.05, random_state=42)
        self.is_trained = False
        self.last_train_time = 0
        self.realtime_anomaly_count = 0

    def get_latest_metrics(self):
        try:
            # Query rate over last 10s
            rate_resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={
                "query": 'sum(rate(request_count_total[10s]))'
            }).json()
            rate = float(rate_resp['data']['result'][0]['value'][1]) if rate_resp['data']['result'] else 0.0

            # Query CPU
            cpu_resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={
                "query": 'cpu_utilization'
            }).json()
            cpu = float(cpu_resp['data']['result'][0]['value'][1]) if cpu_resp['data']['result'] else 0.0

            # Query latency (approximate avg over 10s using histogram sum/count)
            lat_sum = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={
                "query": 'rate(request_latency_seconds_sum[10s])'
            }).json()
            lat_count = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={
                "query": 'rate(request_latency_seconds_count[10s])'
            }).json()
            
            lat_s = 0.0
            l_sum = float(lat_sum['data']['result'][0]['value'][1]) if lat_sum['data']['result'] else 0.0
            l_cnt = float(lat_count['data']['result'][0]['value'][1]) if lat_count['data']['result'] else 0.0
            if l_cnt > 0:
                lat_s = l_sum / l_cnt

            # Query 503 error rate
            err_resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={
                "query": 'sum(rate(http_503_count_total[10s]))'
            }).json()
            err_rate = float(err_resp['data']['result'][0]['value'][1]) if err_resp['data']['result'] else 0.0
            
            # Query replica count
            # In Docker compose, we can estimate replicas by counting distinct instances of mock-server in metrics
            rep_resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={
                "query": 'count(up{job="mock-server"})'
            }).json()
            replicas = int(rep_resp['data']['result'][0]['value'][1]) if rep_resp['data']['result'] else BASELINE_REPLICAS

            metrics = {
                "request_rate": rate,
                "cpu_utilization": cpu,
                "request_latency_seconds": lat_s,
                "http_503_count_rate": err_rate,
                "current_replicas": replicas
            }
            
            self.history["request_rate"].append(rate)
            self.history["cpu_util"].append(cpu)
            self.history["latency"].append(lat_s)
            self.history["error_rate"].append(err_rate)
            
            return metrics
        except Exception as e:
            logger.error(f"Error fetching metrics: {e}")
            return None

    def run_detectors(self, current_metrics):
        if len(self.history["request_rate"]) < 3:
            return None # Not enough data yet
            
        now = time.time()
        
        # 1. Train/Retrain Isolation Forest every 5 mins
        if not self.is_trained or (now - self.last_train_time) > 300:
            X = np.column_stack((
                self.history["request_rate"],
                self.history["cpu_util"],
                self.history["latency"],
                self.history["error_rate"]
            ))
            self.iso_forest.fit(X)
            self.is_trained = True
            self.last_train_time = now
            logger.info("Retrained Isolation Forest baseline.")

        # 2. Real-time Detection (Isolation Forest)
        current_pt = np.array([[
            current_metrics["request_rate"],
            current_metrics["cpu_utilization"],
            current_metrics["request_latency_seconds"],
            current_metrics["http_503_count_rate"]
        ]])
        
        anomaly_score = self.iso_forest.decision_function(current_pt)[0]
        
        if anomaly_score < -0.1:
            self.realtime_anomaly_count += 1
        else:
            self.realtime_anomaly_count = 0
            
        # Require 3 consecutive windows to flag realtime
        if self.realtime_anomaly_count >= 3:
            return "realtime_spike"
            
        # 3. Predictive Detection (Holt-Winters)
        # Only run predictive if we have enough data and no realtime spike
        if len(self.history["request_rate"]) >= 90:
            try:
                # Use last 15 mins (90 points) to forecast next 5 mins (30 points)
                series = np.array(self.history["request_rate"])
                # Simple exponential smoothing for demo (trend=None since spikes can be sudden)
                model = ExponentialSmoothing(series, trend='add', seasonal=None, initialization_method="estimated")
                fit = model.fit()
                forecast = fit.forecast(30)
                
                max_forecast = max(forecast)
                if max_forecast > CAPACITY_THRESHOLD:
                    logger.info(f"Predictive threshold crossed! Forecasted max RPS: {max_forecast:.1f}")
                    return "predictive_spike"
            except Exception as e:
                logger.debug(f"Holt-Winters failed this cycle: {e}")

        return None


class AlertManager:
    def should_alert(self, alert_type: str, payload: dict) -> bool:
        # Cooldown gate: an action was already taken, still settling
        if r.get("cooldown:traffic_spike"):
            logger.info("Alert suppressed: cooldown active")
            return False

        if alert_type == "realtime_spike":
            # Real-time always preempts a predictive alert in flight
            r.delete("inflight:predictive_spike")
            # Atomic SET NX EX
            acquired = r.set("inflight:realtime_spike", json.dumps(payload), nx=True, ex=120)
            if not acquired:
                logger.info("Alert suppressed: realtime alert already in-flight")
                return False
            return True

        if alert_type == "predictive_spike":
            if r.get("inflight:realtime_spike"):
                logger.info("Alert suppressed: realtime already handling this")
                return False
            acquired = r.set("inflight:predictive_spike", json.dumps(payload), nx=True, ex=300)
            if not acquired:
                logger.info("Alert suppressed: predictive alert already in-flight")
                return False
            return True

        return False


def check_recovery(metrics):
    """Clears cooldown early if metrics confirm recovery."""
    if not r.get("cooldown:traffic_spike"):
        return
        
    healthy = (
        metrics["request_latency_seconds"] < RECOVERY_LATENCY_THRESHOLD
        and metrics["http_503_count_rate"] < RECOVERY_ERROR_THRESHOLD
        and metrics["cpu_utilization"] < RECOVERY_CPU_THRESHOLD
    )
    if healthy:
        r.delete("cooldown:traffic_spike")
        logger.info("Cooldown cleared early: metrics confirm recovery")


def check_scaledown(metrics):
    """Checks if we've sustained low traffic long enough to scale down."""
    if r.get("cooldown:traffic_spike") or r.get("inflight:realtime_spike") or r.get("inflight:predictive_spike"):
        return None  # never scale down while anything is active

    current_replicas = metrics["current_replicas"]
    is_low = (metrics["request_rate"] < SCALEDOWN_RATE_THRESHOLD
              and metrics["cpu_utilization"] < SCALEDOWN_CPU_THRESHOLD)

    if not is_low:
        r.delete("scaledown:eligible_since")
        return None

    since = r.get("scaledown:eligible_since")
    if since is None:
        r.set("scaledown:eligible_since", time.time())
        logger.info("Traffic low. Starting scale-down clock.")
        return None

    elapsed = time.time() - float(since)
    if elapsed >= SUSTAINED_LOW_TRAFFIC_WINDOW and current_replicas > BASELINE_REPLICAS:
        r.delete("scaledown:eligible_since")
        return {
            "type": "scaledown_eligible",
            "current_replicas": current_replicas,
            "target_replicas": BASELINE_REPLICAS
        }
    elif elapsed % 60 < POLL_INTERVAL: # Log once a minute
        logger.info(f"Sustained low traffic for {int(elapsed)}s... waiting for {SUSTAINED_LOW_TRAFFIC_WINDOW}s")
        
    return None



def emit_anomaly(payload):
    """Push anomaly onto a Redis queue. Executor uses BLPOP to consume one at a time."""
    logger.warning(f"EMITTING ANOMALY: {json.dumps(payload)}")
    # RPUSH adds to the tail of the list — FIFO order preserved
    # We also cap the queue at 10 to prevent unbounded growth
    r.rpush("analysis_queue", json.dumps(payload))
    r.ltrim("analysis_queue", -10, -1)  # keep only the 10 most recent

def main():
    logger.info("Observer Agent starting...")
    # Wait for Prometheus to boot and gather some initial data
    time.sleep(15) 
    
    poller = MetricsPoller()
    alert_manager = AlertManager()
    
    while True:
        try:
            metrics = poller.get_latest_metrics()
            if not metrics:
                time.sleep(POLL_INTERVAL)
                continue
                
            logger.info(f"Metrics: RPS={metrics['request_rate']:.1f}, CPU={metrics['cpu_utilization']:.1f}%, Latency={metrics['request_latency_seconds']:.3f}s, Replicas={metrics['current_replicas']}")
                
            # 1. Independent State Checks
            check_recovery(metrics)
            
            # 2. Detectors
            spike_type = poller.run_detectors(metrics)
            
            if spike_type:
                payload = {
                    "type": spike_type,
                    "metrics": metrics,
                    "timestamp": time.time()
                }
                if alert_manager.should_alert(spike_type, payload):
                    emit_anomaly(payload)
            else:
                # 3. Check Scaledown (only if no spikes detected)
                scaledown_payload = check_scaledown(metrics)
                if scaledown_payload:
                    # Treat scaledown as a special type of anomaly for the Analyzer
                    if alert_manager.should_alert("realtime_spike", scaledown_payload): # reuse realtime lock
                        emit_anomaly(scaledown_payload)
            
        except Exception as e:
            logger.error(f"Observer loop error: {e}")
            
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()