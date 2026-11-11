import http from 'k6/http';
import { check, sleep } from 'k6';

const TARGET = __ENV.TARGET_URL || 'http://127.0.0.1:10000';

export const options = {
  vus: 1,
  duration: '10s',
};

export default function () {
  const params = {
    headers: {
      'X-Test-Arm': 'person-c-parallel-control',
      'X-Test-Session': `parallel-user-${__VU}`,
    },
    timeout: '3s',
    tags: { scenario: 'parallel_control' },
  };

  const responses = http.batch([
    ['GET', `${TARGET}/health`, null, params],
    ['GET', `${TARGET}/api/data`, null, params],
  ]);

  for (const response of responses) {
    check(response, {
      'successful response': (r) => r.status === 200,
    });
  }

  sleep(1);
}
