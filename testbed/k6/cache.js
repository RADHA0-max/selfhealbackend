import http from 'k6/http';
import { check, sleep } from 'k6';

const TARGET = __ENV.TARGET_URL || 'http://127.0.0.1:10000';

export const options = {
  vus: 1,
  duration: '15s',
};

export default function () {
  const response = http.get(`${TARGET}/api/data`, {
    headers: {
      'Cache-Control': 'no-cache',
    },
    timeout: '3s',
    tags: { scenario: 'cache_probe' },
  });

  check(response, {
    'successful response': (r) => r.status === 200,
  });

  sleep(1);
}
