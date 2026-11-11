import http from 'k6/http';
import { check, sleep } from 'k6';

const TARGET = __ENV.TARGET_URL || 'http://127.0.0.1:10000';

export const options = {
  vus: 2,
  duration: '15s',
  thresholds: {
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  // Synthetic automation pattern, not a real headless browser.
  const response = http.get(`${TARGET}/api/data`, {
    headers: {
      'User-Agent': 'NanoClaw-Synthetic-Headless/1.0',
      'X-Test-Session': `headless-user-${__VU}`,
    },
    timeout: '3s',
    tags: { scenario: 'synthetic_headless_botnet' },
  });

  check(response, {
    'HTTP 200': (r) => r.status === 200,
  });

  sleep(1);
}
