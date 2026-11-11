import http from 'k6/http';
import { check, sleep } from 'k6';

const TARGET = __ENV.TARGET_URL || 'http://127.0.0.1:10000';

export const options = {
  scenarios: {
    organic: {
      executor: 'constant-vus',
      vus: 1,
      duration: '15s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  const session = `organic-user-${__VU}`;

  const params = {
    headers: {
      'User-Agent': 'NanoClaw-Organic/1.0',
      'X-Test-Session': session,
    },
    timeout: '3s',
    tags: { scenario: 'organic' },
  };

  // Simulate a user checking service health and reading API data.
  const responses = http.batch([
    ['GET', `${TARGET}/health`, null, params],
    ['GET', `${TARGET}/api/data`, null, params],
  ]);

  for (const response of responses) {
    check(response, {
      'HTTP 200': (r) => r.status === 200,
    });
  }

  sleep(1 + Math.random());
}
