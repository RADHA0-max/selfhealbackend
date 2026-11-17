import http from 'k6/http';
import { check, sleep } from 'k6';
import { safeTarget } from './target_guard.js';

const TARGET = safeTarget(
  __ENV.TARGET_URL || 'http://testbed-envoy:10000'
);

export const options = {
  scenarios: {
    organic_60vu: {
      executor: 'constant-vus',
      vus: 60,
      duration: '30s',
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

  if (!jar.cookiesForURL(TARGET).nanoclaw_session) {
    jar.set(TARGET, 'nanoclaw_session', session);
  }

  const response = http.get(`${TARGET}${path}`, {
    headers: {
      'User-Agent': 'NanoClaw-Organic-P16/1.0',
      'X-Test-Session': session,
    },
    timeout: '3s',
    redirects: 0,
  });

  check(response, {
    'organic response is HTTP 200': (r) => r.status === 200,
  });

  // Deterministic per-VU timing variation.
  sleep(0.2 + ((vu * 7 + iteration * 3) % 9) * 0.05);
}
