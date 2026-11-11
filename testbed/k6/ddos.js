import http from 'k6/http';
import { check, sleep } from 'k6';

const TARGET = __ENV.TARGET_URL || 'http://127.0.0.1:10000';

export const options = {
  vus: 3,
  duration: '15s',
  thresholds: {
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  // Synthetic high-concurrency pattern with conservative limits.
  // Run only against the isolated NanoClaw testbed.
  const response = http.get(`${TARGET}/api/data`, {
    headers: {
      'User-Agent': 'NanoClaw-Synthetic-DDoS/1.0',
    },
    timeout: '3s',
    tags: { scenario: 'synthetic_ddos' },
  });

  check(response, {
    'HTTP 200': (r) => r.status === 200,
  });

  sleep(1);
}
