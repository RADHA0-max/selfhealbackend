import urllib.request
import json
import threading
import time

print('1. Injecting Chaos State...')
try:
    data = json.dumps({'rps': 500, 'duration_sec': 60, 'pattern': 'sudden'}).encode()
    req = urllib.request.Request('http://localhost:8080/chaos/spike', data=data, headers={'Content-Type': 'application/json'}, method='POST')
    print(urllib.request.urlopen(req).read().decode())
except Exception as e:
    print(f"Failed to inject chaos: {e}")

print('2. Bombarding server with requests to trigger the AI...')
def spam():
    for _ in range(500):
        try:
            urllib.request.urlopen('http://localhost:8080/api/process', timeout=2)
        except:
            pass

for _ in range(50):
    threading.Thread(target=spam, daemon=True).start()

print("Traffic started! Let it run for 30 seconds...")
time.sleep(30)
print('Done!')
