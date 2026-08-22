"""
Robust load generator using ThreadPoolExecutor.
Avoids crashing the process when the server slows down and connections pile up.
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.request

TARGET = "http://mock-server:8080/api/process"
RPS = int(sys.argv[1]) if len(sys.argv) > 1 else 50
DURATION = int(sys.argv[2]) if len(sys.argv) > 2 else 120

sent = 0
errors = 0

def fire():
    global sent, errors
    try:
        req = urllib.request.Request(TARGET, headers={'Connection': 'close'})
        with urllib.request.urlopen(req, timeout=5) as r:
            r.read()
    except Exception:
        errors += 1
    finally:
        sent += 1

print(f"Load generator: {RPS} RPS for {DURATION}s -> {TARGET}")
start = time.time()
interval = 1.0 / RPS

# Cap threads to avoid OS limits. 400 threads is well within limits.
pool = ThreadPoolExecutor(max_workers=400)

try:
    while time.time() - start < DURATION:
        pool.submit(fire)
        time.sleep(interval)
except Exception as e:
    print("Main loop error:", e)

pool.shutdown(wait=False)
elapsed = time.time() - start
print(f"Done. Sent {sent} requests in {elapsed:.1f}s ({sent/elapsed:.1f} actual RPS), {errors} errors")
