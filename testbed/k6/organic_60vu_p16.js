import http from 'k6/http';
import { check, sleep } from 'k6';
import { safeTarget } from './target_guard.js';
import { Counter } from 'k6/metrics';

const executedRequests = new Counter('nanoclaw_request_manifest');

const TARGET = safeTarget(
  __ENV.TARGET_URL || 'http://testbed-envoy:10000'
);

export const options = {
  scenarios: {
    organic_60vu: {
      executor: 'per-vu-iterations',
      vus: 60,
      iterations: 20,
      maxDuration: '30s',
      gracefulStop: '0s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.10'],
  },
};

const PATHS = [
  '/health',
  '/ready',
  '/api/data',
];

export default function () {
  const vu = __VU;
  const iteration = __ITER;

  const path = PATHS[(vu + iteration) % PATHS.length];

  // k6 maintains an independent default cookie jar for each VU.
  // The testbed does not currently issue cookies, so this is a
  // workload-side session marker, not server-authenticated identity.
  const jar = http.cookieJar();
  const session = `organic-vu-${vu}`;

  // Unique per VU/iteration. This identifies a workload request,
  // not an authenticated client or independently verified source IP.
  const runId = __ENV.NANOCLAW_RUN_ID;
  if (!runId || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$/.test(runId)) {
    throw new Error('Valid NANOCLAW_RUN_ID is required');
  }
  const requestId = `${runId}-organic-vu-${vu}-iter-${iteration}`;

  if (!jar.cookiesForURL(TARGET).nanoclaw_session) {
    jar.set(TARGET, 'nanoclaw_session', session);
  }

  const response = http.get(`${TARGET}${path}`, {
    headers: {
      'User-Agent': 'NanoClaw-Organic-P16/1.0',
      'X-Test-Session': session,
      'X-Request-ID': requestId,
    },
    timeout: '3s',
    redirects: 0,
  });

  executedRequests.add(1, {
    request_id: requestId,
    workload: 'organic_60vu',
  });

  check(response, {
    'organic response is HTTP 200': (r) => r.status === 200,
  });

  // Deterministic per-VU timing variation.
  sleep(0.2 + ((vu * 7 + iteration * 3) % 9) * 0.05);
}
