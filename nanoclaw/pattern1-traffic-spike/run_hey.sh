cd ~/nanoclaw/pattern1-traffic-spike
docker compose exec -T --index 1 mock-server python -c "import urllib.request, json; urllib.request.urlopen(urllib.request.Request('http://localhost:8080/chaos/spike', data=json.dumps({'rps': 500, 'duration_sec': 60, 'pattern': 'sudden'}).encode(), headers={'Content-Type': 'application/json'}, method='POST'))"
docker run --rm --network pattern1-traffic-spike_default williamyeh/hey -z 30s -c 100 http://mock-server:8080/api/process
