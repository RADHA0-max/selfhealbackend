import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { safeTarget } from './target_guard.js';

const TARGET = safeTarget(
  __ENV.TARGET_URL || 'http://testbed-envoy:10000'
);

const requests = new Counter('nanoclaw_request_manifest');

const RUN_ID = __ENV.NANOCLAW_RUN_ID;

if (!RUN_ID || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$/.test(RUN_ID)) {
  throw new Error('Valid NANOCLAW_RUN_ID is required');
}

export const options = {

  scenarios: {
    p01_scraper: {
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

const PATHS = [
  '/api/data',
  '/health',
  '/ready',
];

export default function () {
  const vu = __VU;
  const iteration = __ITER;

  const path = PATHS[(vu + iteration) % PATHS.length];

  const requestId =
    `${RUN_ID}-scraper-vu-${vu}-iter-${iteration}`;

  const response = http.get(`${TARGET}${path}`, {
    headers: {
      'User-Agent': 'NanoClaw-Synthetic-Scraper-P01/1.0',
      'X-Request-ID': requestId,
      'X-Test-Workload': 'p01_scraper',
      'Accept': 'application/json,text/html',
    },
    timeout: '3s',
    redirects: 0,
  });

  requests.add(1, {
    workload: 'p01_scraper',
    request_id: requestId,
  });

  check(response, {
    'scraper request received HTTP 200': (r) =>
      r.status === 200,
  });

  // Sequential traversal with bounded pacing.
  sleep(0.5);
}
