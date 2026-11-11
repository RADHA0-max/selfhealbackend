import http from 'k6/http';
import { check, sleep } from 'k6';

const TARGET = __ENV.TARGET_URL || 'http://127.0.0.1:10000';

export const options = {
  vus: 1,
  duration: '15s',
  thresholds: {
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  // Mixed request pattern; classification remains unverified.
  const path = __ITER % 3 === 0 ? '/ready' : '/api/data';

  const response = http.get(`${TARGET}${path}`, {
    headers: {
      'User-Agent': 'NanoClaw-Ambiguous/1.0',
      'X-Test-Session': `ambiguous-user-${__VU}`,
    },
    timeout: '3s',
    tags: { scenario: 'synthetic_ambiguous' },
  });

  check(response, {
    'HTTP 200': (r) => r.status === 200,
  });

  sleep(1);
}
