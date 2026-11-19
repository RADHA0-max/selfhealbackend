import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(
  'testbed/k6/organic_60vu_p16.js', 'utf8'
);

const guardSource = fs.readFileSync(
  'testbed/k6/target_guard.js', 'utf8'
);

const guardContext = {};

vm.runInNewContext(
  guardSource.replace(
    'export function safeTarget',
    'function safeTarget'
  ) + '\nglobalThis.safeTarget = safeTarget;',
  guardContext,
);

const transformed = source
  .replace(/^import .*;$/gm, '')
  .replace('export const options =', 'const options =')
  .replace('export default function ()', 'function workload()');

const observed = [];

for (let vu = 1; vu <= 60; vu++) {
  const cookies = new Map();

  const jar = {
    cookiesForURL(url) {
      const value = cookies.get(url);
      return value ? { nanoclaw_session: [value] } : {};
    },
    set(url, name, value) {
      assert.equal(name, 'nanoclaw_session');
      cookies.set(url, value);
    },
  };

  const context = {
    __ENV: { TARGET_URL: 'http://testbed-envoy:10000', NANOCLAW_RUN_ID: 'offline' },
    __VU: vu,
    __ITER: 0,
    safeTarget: guardContext.safeTarget,
    Counter: class {
      constructor(name) {
        this.name = name;
      }
      add() {}
    },
    http: {
      cookieJar: () => jar,
      get(url, params) {
        observed.push({
          vu,
          iteration: context.__ITER,
          url,
          requestId: params.headers['X-Request-ID'],
          session: params.headers['X-Test-Session'],
        });
        return { status: 200 };
      },
    },
    check: () => true,
    sleep: () => {},
  };

  vm.runInNewContext(
    transformed + '\nglobalThis.workload = workload;',
    context,
    { timeout: 1000 },
  );

  for (let iteration = 0; iteration < 3; iteration++) {
    context.__ITER = iteration;
    context.workload();
  }
}

assert.equal(observed.length, 180);

const ids = observed.map(row => row.requestId);
assert.equal(new Set(ids).size, 180);

for (const row of observed) {
  assert.equal(
    row.requestId,
    `offline-organic-vu-${row.vu}-iter-${row.iteration}`
  );
  assert.equal(row.session, `organic-vu-${row.vu}`);
  assert.match(
    new URL(row.url).pathname,
    /^\/(health|ready|api\/data)$/
  );
}

console.log(
  'PASS: 180 unique deterministic X-Request-ID headers ' +
  'across 60 mocked VUs'
);
