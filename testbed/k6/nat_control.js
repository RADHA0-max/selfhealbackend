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
  // Multiple logical users may share a network address.
  // This header is a synthetic session label, not an IP address.
  const session = `nat-user-${__VU}`;
  const response = http.get(`${TARGET}/api/data`, {
    headers: {
      'User-Agent': 'NanoClaw-NAT-Control/1.0',
      'X-Test-Session': session,
    },
    timeout: '3s',
    tags: { scenario: 'nat_negative_control' },
  });

  check(response, {
    'HTTP 200': (r) => r.status === 200,
  });

  sleep(1);
}
