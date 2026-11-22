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
const PATHS = ['/api/data', '/health', '/api/data'];

export const options = {

  scenarios: {
    p01_headless_botnet: {
      executor: 'per-vu-iterations',
      vus: 8,
      iterations: 8,
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
  const requestId = `${RUN_ID}-p01_headless_botnet-vu-${vu}-iter-${iteration}`;
  const path = PATHS[(vu + iteration) % PATHS.length];

  const response = http.get(`${TARGET}${path}`, {
    headers: {
      'User-Agent': 'NanoClaw-Headless-Synthetic-P01/1.0',
      'X-Request-ID': requestId,
      'X-Test-Workload': 'p01_headless_botnet',
    },
    timeout: '3s',
    redirects: 0,
  });

  requests.add(1, {
    workload: 'p01_headless_botnet',
    request_id: requestId,
  });

  check(response, {
    'expected testbed response': (r) =>
      r.status === 200 || r.status === 429,
  });

  sleep(0.15);
}
