import http from 'k6/http';
import { check, sleep } from 'k6';

const TARGET = __ENV.TARGET_URL || 'http://127.0.0.1:10000';

export const options = {
  vus: 1,
  duration: '10s',
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<1000'],
  },
};

export default function () {
  const response = http.get(`${TARGET}/api/data`, {
    timeout: '3s',
    tags: { scenario: 'person_c_baseline' },
  });

  check(response, {
    'HTTP 200': (r) => r.status === 200,
  });

  sleep(1);
}
