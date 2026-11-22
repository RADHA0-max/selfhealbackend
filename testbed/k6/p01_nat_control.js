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
    p01_nat_control: {
      executor: 'per-vu-iterations',
      vus: 10,
      iterations: 5,
      maxDuration: '60s',
      gracefulStop: '0s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.10'],
  },
  discardResponseBodies: true,
};

const PATHS = ['/health', '/ready', '/api/data'];

export default function () {
  const vu = __VU;
  const iteration = __ITER;
  const session = `nat-client-${vu}`;
  const jar = http.cookieJar();

  if (!jar.cookiesForURL(TARGET).nanoclaw_session) {
    jar.set(TARGET, 'nanoclaw_session', session);
  }

  const requestId = `${RUN_ID}-nat-vu-${vu}-iter-${iteration}`;
  const path = PATHS[(vu + iteration) % PATHS.length];

  const response = http.get(`${TARGET}${path}`, {
    headers: {
      'User-Agent': 'NanoClaw-NAT-Control-P01/1.0',
      'X-Test-Session': session,
      'X-Request-ID': requestId,
      'X-Test-Workload': 'p01_nat_control',
    },
    timeout: '3s',
    redirects: 0,
  });

  requests.add(1, {
    workload: 'p01_nat_control',
    request_id: requestId,
  });

  check(response, {
    'NAT control HTTP 200': (r) => r.status === 200,
  });

  sleep(0.3 + ((vu + iteration) % 5) * 0.1);
}
