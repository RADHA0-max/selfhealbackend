import http from 'k6/http';
import { check, sleep } from 'k6';

const TARGET = __ENV.TARGET_URL || 'http://127.0.0.1:10000';

export const options = {
  scenarios: {
    controlled_burst: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '5s', target: 1 },
        { duration: '5s', target: 3 },
        { duration: '5s', target: 1 },
      ],
      gracefulRampDown: '2s',
    },
  },
};

export default function () {
  const response = http.get(`${TARGET}/api/data`, {
    timeout: '3s',
    tags: { scenario: 'controlled_burst' },
  });

  check(response, {
    'successful response': (r) => r.status === 200,
  });

  sleep(1);
}
