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
};

export default function () {
  const path = Math.random() < 0.8 ? '/api/data' : '/health';

  const response = http.get(`${TARGET}${path}`, {
    timeout: '3s',
    tags: { scenario: 'organic' },
  });

  check(response, {
    'successful response': (r) => r.status === 200,
  });

  sleep(1 + Math.random());
}
