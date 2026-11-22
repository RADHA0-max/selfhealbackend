import http from 'k6/http';
import { check } from 'k6';
import { safeTarget } from './target_guard.js';

const TARGET = safeTarget(__ENV.TARGET_URL);

export const options = {
  scenarios: {
    bounded: {
      executor: 'per-vu-iterations',
      vus: 1,
      iterations: 1,
      maxDuration: '15s',
      gracefulStop: '0s',
    },
  },

  thresholds: {
    http_req_failed: ['rate==0'],
  },
};

export default function () {
  for (const path of ['/health', '/ready', '/api/data']) {
    const response = http.get(`${TARGET}${path}`, {
      redirects: 0,
      timeout: '3s',
      headers: {
        'X-Request-ID': 'p01_smoke_001-smoke',
      },
    });

    check(response, {
      [`${path} returns 200`]: (r) => r.status === 200,
    });
  }
}
