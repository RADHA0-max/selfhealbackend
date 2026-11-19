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
  guardSource.replace('export function safeTarget', 'function safeTarget') +
  '\nglobalThis.safeTarget = safeTarget;',
  guardContext,
);

const safeTarget = guardContext.safeTarget;

function createVU(vu, target = 'http://testbed-envoy:10000') {
  const cookies = new Map();
  const requests = [];
  const sleeps = [];
  const checks = [];

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

  const transformed = source
    .replace(/^import .*;$/gm, '')
    .replace('export const options =', 'const options =')
    .replace('export default function ()', 'function workload()');

  const context = {
    __ENV: { TARGET_URL: target , NANOCLAW_RUN_ID: 'offline' },
    __VU: vu,
    __ITER: 0,
    safeTarget,
    Counter: class {
      constructor(name) {
        this.name = name;
      }
      add() {}
    },
    http: {
      cookieJar() {
        return jar;
      },
      get(url, params) {
        requests.push({
          url,
          params,
          cookie: cookies.get(target),
        });
        return { status: 200 };
      },
    },
    check(response, predicates) {
      const results = Object.values(predicates)
        .map(predicate => predicate(response));
      checks.push(...results);
      return results.every(Boolean);
    },
    sleep(seconds) {
      sleeps.push(seconds);
    },
  };

  vm.runInNewContext(
    transformed + '\nglobalThis.__test = { options, workload };',
    context,
    { timeout: 1000 },
  );

  return {
    options: context.__test.options,
    run(iteration) {
      context.__ITER = iteration;
      context.__test.workload();
    },
    requests,
    sleeps,
    checks,
    cookies,
  };
}

const vus = Array.from(
  { length: 60 },
  (_, index) => createVU(index + 1),
);

assert.equal(vus[0].options.scenarios.organic_60vu.vus, 60);
assert.equal(vus[0].options.scenarios.organic_60vu.executor, 'per-vu-iterations');
assert.equal(vus[0].options.scenarios.organic_60vu.vus, 60);
assert.equal(vus[0].options.scenarios.organic_60vu.iterations, 20);
assert.equal(vus[0].options.scenarios.organic_60vu.maxDuration, '30s');
assert.equal(vus[0].options.scenarios.organic_60vu.gracefulStop, '0s');

for (const vu of vus) {
  for (let iteration = 0; iteration < 3; iteration++) {
    vu.run(iteration);
  }

  assert.equal(vu.requests.length, 3);
  assert.equal(vu.sleeps.length, 3);
  assert.deepEqual(vu.checks, [true, true, true]);

  for (const request of vu.requests) {
    assert.equal(request.params.timeout, '3s');
    assert.equal(request.params.redirects, 0);
    assert.equal(
      request.cookie,
      request.params.headers['X-Test-Session'],
    );
  }
}

const allRequests = vus.flatMap(vu => vu.requests);
const sessions = new Set(
  allRequests.map(request => request.cookie)
);
const paths = new Set(
  allRequests.map(request => new URL(request.url).pathname)
);

assert.equal(allRequests.length, 180);
assert.equal(sessions.size, 60);
assert.deepEqual(
  [...paths].sort(),
  ['/api/data', '/health', '/ready'],
);

for (const unsafe of [
  'https://example.com',
  'http://127.0.0.1:8080',
  'http://testbed-envoy:10000@external.example',
]) {
  assert.throws(() => createVU(1, unsafe));
}

console.log(
  'P16: 60 isolated VU cookie jars, 180 mocked requests, ' +
  '3 paths, real target guard — PASS'
);
