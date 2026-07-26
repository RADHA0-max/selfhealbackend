import time
import json
import logging
import subprocess
import requests
import redis
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Config
REDIS_HOST = "redis"
LITELLM_URL = "http://host.docker.internal:4000/v1/messages" # Or whatever IP your proxy uses
GEMINI_MODEL = "gemini/gemma-4-31b-it"

# The hardcoded approval policy
APPROVAL_POLICY = {
    "scale_up": {"auto_execute": True},
    "scale_down": {"auto_execute": True},
    "rate_limit": {"auto_execute": True},
    "block_ip": {"auto_execute": False},
    "rollback": {"auto_execute": False},
    "alert_human": {"auto_execute": True}, # just logs/notifies
}

# The cooldown actions (from v3.1 fix)
COOLDOWN_ACTIONS = {"scale_up", "scale_down", "rate_limit"}

r = redis.Redis(host=REDIS_HOST, decode_responses=True)

def get_system_prompt():
    try:
        with open("/app/analyzer/system-prompt.md", "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("system-prompt.md not found. Ensure paths are correct.")
        return ""

def call_gemma(payload):
    """Call Gemma via LiteLLM proxy with a 10s timeout."""
    prompt = get_system_prompt()
    user_msg = f"ANOMALY DETECTED:\n{json.dumps(payload, indent=2)}"
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": "dummy",
        "anthropic-version": "2023-06-01"
    }
    
    data = {
        "model": GEMINI_MODEL,
        "max_tokens": 500,
        "system": prompt,
        "messages": [{"role": "user", "content": user_msg}]
    }
    
    try:
        resp = requests.post(LITELLM_URL, json=data, headers=headers, timeout=10)
        resp.raise_for_status()
        
        # Anthropic format response from LiteLLM
        content = resp.json()["content"][0]["text"]
        
        # Clean up any potential markdown wrapping from the LLM
        if content.startswith("```json"):
            content = content.replace("```json", "", 1)
        if content.endswith("```"):
            content = content[:-3]
            
        return json.loads(content.strip())
    except Exception as e:
        logger.error(f"Analyzer (Gemma) failure: {e}")
        return None

def write_audit_log(action_plan, trigger_type, result, approved, auto_executed):
    """Writes audit event to JSONL file."""
    event = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "action": action_plan.get("action"),
        "params": action_plan.get("action_params", {}),
        "trigger": trigger_type,
        "severity": action_plan.get("severity", "UNKNOWN"),
        "confidence": action_plan.get("confidence", 0.0),
        "approved": approved,
        "auto_executed": auto_executed,
        "result": result
    }
    
    try:
        with open("/app/logs/executor-audit.jsonl", "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")

def run_action(action, params):
    """Execute the actual mitigation."""
    logger.info(f"Executing action: {action} with params: {params}")
    
    if action == "scale_up" or action == "scale_down":
        target = params.get("target_replicas", 3)
        # Shell out to docker compose. 
        # Note: running this requires the host's Docker socket to be mounted into the Executor container.
        cmd = ["docker", "compose", "up", "-d", "--scale", f"mock-server={target}", "--no-recreate"]
        try:
            res = subprocess.run(cmd, check=True, capture_output=True, text=True, cwd="..")
            return {"status": "success", "message": f"Scaled to {target}", "output": res.stdout}
        except subprocess.CalledProcessError as e:
            return {"status": "failed", "message": "Docker scale failed", "error": e.stderr}
            
    elif action == "rate_limit":
        # Call our mock-server admin endpoint
        try:
            resp = requests.post("http://mock-server:8080/admin/rate-limit", json={"enabled": True}, timeout=5)
            return {"status": "success", "message": resp.json().get("status")}
        except Exception as e:
            return {"status": "failed", "error": str(e)}
            
    elif action == "alert_human":
        logger.warning(f"HUMAN ALERT: Paging on-call for {params}")
        return {"status": "success", "message": "On-call paged"}
        
    return {"status": "failed", "error": "Unknown action"}

def await_onecli_approval(action_plan):
    """Mock approval hold. In reality, this talks to OneCLI dashboard."""
    logger.info(f"Action {action_plan['action']} requires approval. Blocking...")
    # For demo purposes, we automatically reject high-risk actions to show the failure path
    time.sleep(2)
    return {"status": "rejected", "message": "Approval denied in demo mode"}

def process_payload(payload_str):
    """Full Analyzer -> Executor pipeline."""
    payload = json.loads(payload_str)
    trigger_type = payload.get("type", "unknown")
    logger.info(f"Processing anomaly trigger: {trigger_type}")
    
    # 1. Call Analyzer (Gemma)
    action_plan = call_gemma(payload)
    
    if not action_plan:
        logger.error("Analyzer failed to return a valid plan. Pipeline aborting.")
        # We don't delete the inflight lock here. 
        # The safety net is that the TTL (120s/300s) expires naturally, preventing retry storms.
        return

    # Validate action is allowed
    action = action_plan.get("action")
    if action not in APPROVAL_POLICY:
        logger.error(f"Analyzer returned invalid action: {action}")
        return
        
    auto = APPROVAL_POLICY[action]["auto_execute"]
    
    # 2. Execute
    try:
        if auto:
            result = run_action(action, action_plan.get("action_params", {}))
        else:
            result = await_onecli_approval(action_plan)

        # 3. State Handoff (Cooldown)
        # Apply the fix from v3.1: scale_up, scale_down, and rate_limit all get cooldowns
        if action in COOLDOWN_ACTIONS and result.get("status") == "success":
            r.set("cooldown:traffic_spike", json.dumps({
                "action": action,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "params": action_plan.get("action_params"),
            }), ex=90)
            logger.info(f"Set 90s cooldown for {action}")

        # Write audit log (Fix from v3.1: approved = not auto)
        write_audit_log(action_plan, trigger_type, result, approved=(not auto), auto_executed=auto)

    except Exception as e:
        logger.error(f"Execution failed: {e}")
        write_audit_log(action_plan, trigger_type, {"error": str(e)}, approved=False, auto_executed=auto)

    finally:
        # Executor ALWAYS clears inflight on success OR failure if it reached this far
        r.delete(f"inflight:{trigger_type}")
        logger.info(f"Cleared inflight lock for {trigger_type}")

# Minimum seconds between LLM calls (prevents burst requests to Gemma)
MIN_LLM_INTERVAL = 5
last_llm_call = 0

def main():
    global last_llm_call
    logger.info("Executor Agent starting... waiting for anomalies on Redis queue.")
    
    while True:
        try:
            # BLPOP blocks until an item appears on the queue (timeout=5s)
            # This is atomic — no race condition, no duplicate processing
            result = r.blpop("analysis_queue", timeout=5)
            
            if result is None:
                # Timeout — no anomalies in queue, loop back and wait again
                continue
            
            _, payload_str = result  # result is (key_name, value)
            
            # Rate limiter: enforce minimum gap between LLM calls
            elapsed = time.time() - last_llm_call
            if elapsed < MIN_LLM_INTERVAL:
                wait_time = MIN_LLM_INTERVAL - elapsed
                logger.info(f"Rate limiter: waiting {wait_time:.1f}s before next LLM call")
                time.sleep(wait_time)
            
            last_llm_call = time.time()
            process_payload(payload_str)
            
        except Exception as e:
            logger.error(f"Executor loop error: {e}")
            time.sleep(2)  # back off on errors

if __name__ == "__main__":
    main()