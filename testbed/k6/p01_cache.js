import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { safeTarget } from './target_guard.js';

const TARGET = safeTarget(__ENV.TARGET_URL || 'http://testbed-envoy:10000');
const RUN_ID = __ENV.NANOCLAW_RUN_ID;

if (!RUN_ID || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$/.test(RUN_ID)) {
  throw new Error('Valid NANOCLAW_RUN_ID is required');
}

const requests = new Counter('nanoclaw_request_manifest');

export const options = {

  scenarios: {
    p01_cache: {
      executor: 'per-vu-iterations',
      vus: 5,
      iterations: 10,
      maxDuration: '60s',
      gracefulStop: '0s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.20'],
  },
  discardResponseBodies: true,
};

export default function () {
  const vu = __VU;
  const iteration = __ITER;
  const requestId = `${RUN_ID}-cache-vu-${vu}-iter-${iteration}`;

  // Cache-busting query models unique-object demand.
  // Actual cache misses require a configured cache and cache telemetry.
  const key = `${RUN_ID}-${vu}-${iteration}`;
  const url = `${TARGET}/api/data?cache_key=${encodeURIComponent(key)}`;

  const response = http.get(url, {
    headers: {
      'User-Agent': 'NanoClaw-Cache-P01/1.0',
      'X-Request-ID': requestId,
      'X-Test-Workload': 'p01_cache',
    },
    timeout: '3s',
    redirects: 0,
  });

  requests.add(1, {
    workload: 'p01_cache',
    request_id: requestId,
  });

  check(response, {
    'cache workload HTTP 200': (r) => r.status === 200,
  });

  sleep(0.25);
}
