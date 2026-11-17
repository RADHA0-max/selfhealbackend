import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const scenarioDir = path.resolve(here, '../k6');

const scenarios = [
  'baseline',
  'organic',
  'burst',
  'cache',
  'parallel',
  'ddos',
  'headless_botnet',
  'scraper',
  'nat_control',
  'ambiguous',
];

function runScenario(name, vu = 1, iteration = 0, target = 'http://127.0.0.1:10000') {
  assert.match(name, /^[a-z_]+$/);

  const filename = path.join(scenarioDir, `${name}.js`);
  let source = fs.readFileSync(filename, 'utf8');

  // Resolve the local testbed target guard without network access.
  const guardPath = path.join(scenarioDir, 'target_guard.js');
  const guardSource = fs.readFileSync(guardPath, 'utf8')
    .replace('export function safeTarget', 'function safeTarget');

  source = source.replace(
    /^import \{ safeTarget \} from '\.\/target_guard\.js';$/gm,
    ''
  );

  source = guardSource + '\n' + source;

  // Only the known k6 import forms are supported.
  source = source.replace(
    /^import http from 'k6\/http';$/gm,
    'const http = __mockHttp;'
  );

  source = source.replace(
    /^import \{ check, sleep \} from 'k6';$/gm,
    'const { check, sleep } = __mockK6;'
  );

  source = source.replace(
    /^export const options =/gm,
    'const options ='
  );

  source = source.replace(
    /^export default function \(\)/gm,
    'function defaultScenario()'
  );

  const calls = [];
  const sleeps = [];
  const checks = [];

  function record(method, url, params = {}) {
    assert.equal(method, 'GET');
    assert.equal(typeof url, 'string');
    assert.match(url, /^http:\/\/127\.0\.0\.1:10000\//);

    assert.equal(params.timeout, '3s');

    calls.push({
      method,
      url,
      headers: params.headers ?? {},
      tags: params.tags ?? {},
    });

    return { status: 200 };
  }

  const mockHttp = {
    get(url, params) {
      return record('GET', url, params);
    },
    batch(requests) {
      assert.ok(Array.isArray(requests));
      return requests.map(([method, url, body, params]) => {
        assert.equal(body, null);
        return record(method, url, params);
      });
    },
  };

  const mockK6 = {
    check(response, predicates) {
      for (const predicate of Object.values(predicates)) {
        checks.push(predicate(response));
      }
      return true;
    },
    sleep(seconds) {
      assert.ok(Number.isFinite(seconds));
      assert.ok(seconds >= 0 && seconds <= 10);
      sleeps.push(seconds);
    },
  };

  const context = vm.createContext({
    __mockHttp: mockHttp,
    __mockK6: mockK6,
    __ENV: { TARGET_URL: target },
    __VU: vu,
    __ITER: iteration,
    Math,
  });

  const script = new vm.Script(
    `${source}\n;globalThis.__result = { options, defaultScenario };`,
    { filename, timeout: 1000 }
  );

  script.runInContext(context, { timeout: 1000 });

  assert.equal(typeof context.__result.defaultScenario, 'function');

  context.__result.defaultScenario();

  assert.ok(calls.length >= 1);
  assert.ok(calls.length <= 10);
  assert.ok(checks.length >= 1);
  assert.ok(checks.every(Boolean));

  return {
    name,
    calls,
    sleeps,
    options: context.__result.options,
  };
}

let assertions = 0;

for (const name of scenarios) {
  const first = runScenario(name, 1, 0);
  const second = runScenario(name, 2, 1);

  assert.ok(first.calls.length > 0);
  assert.ok(second.calls.length > 0);

  for (const run of [first, second]) {
    const options = run.options;
    const scenario = Object.values(options.scenarios ?? {})[0];

    const stages = options.stages ?? scenario?.stages;

    if (stages) {
      assert.ok(Array.isArray(stages));
      assert.ok(stages.length >= 1 && stages.length <= 10);

      let totalSeconds = 0;

      for (const stage of stages) {
        assert.match(stage.duration, /^\d+s$/);
        assert.ok(Number.isInteger(stage.target));
        assert.ok(stage.target >= 0 && stage.target <= 10);

        totalSeconds += parseInt(stage.duration, 10);
      }

      assert.ok(totalSeconds > 0 && totalSeconds <= 30);
    } else {
      const duration = options.duration ?? scenario?.duration;

      assert.match(duration, /^\d+s$/);
      assert.ok(parseInt(duration, 10) > 0);
      assert.ok(parseInt(duration, 10) <= 30);
    }

    assertions++;
  }

  // Reject unsafe environment overrides before any HTTP request.
  for (const unsafe of [
    'https://example.com',
    'http://127.0.0.1:8080',
    'http://127.0.0.1:10000.evil.com',
  ]) {
    assert.throws(() => runScenario(name, 1, 0, unsafe));
  }

  // Ensure every workload has an explicit, conservative VU ceiling.
  const opts = first.options;
  if (opts.vus !== undefined) {
    assert.ok(Number.isInteger(opts.vus));
    assert.ok(opts.vus >= 1 && opts.vus <= 10);
  }

  for (const scenario of Object.values(opts.scenarios ?? {})) {
    if (scenario.vus !== undefined) {
      assert.ok(Number.isInteger(scenario.vus));
      assert.ok(scenario.vus >= 1 && scenario.vus <= 10);
    }
  }

  if (name === 'organic' || name === 'parallel') {
    assert.ok(first.calls.length >= 2);
  }

  if (name === 'nat_control') {
    assert.notEqual(
      first.calls[0].headers['X-Test-Session'],
      second.calls[0].headers['X-Test-Session']
    );
  }

  if (name === 'ambiguous') {
    assert.notEqual(
      first.calls[0].url,
      second.calls[0].url
    );
  }

  console.log(`PASS ${name}`);
}

console.log(
  `P14 offline k6 execution: ${scenarios.length} scenarios, ` +
  `${assertions} bounded-run checks passed`
);
