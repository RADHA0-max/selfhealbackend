import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const scenarios = [
  ['p01_ddos', 10, 10],
  ['p01_scraper', 5, 10],
];

for (const [name, vus, iterations] of scenarios) {
  test(`${name}: isolated target and bounded workload`, () => {
    const source = readFileSync(
      new URL(`../k6/${name}.js`, import.meta.url),
      'utf8'
    );

    assert.match(source, /safeTarget/);
    assert.match(source, /target_guard\.js/);

    assert.match(
      source,
      new RegExp(`vus:\\s*${vus}`)
    );

    assert.match(
      source,
      new RegExp(`iterations:\\s*${iterations}`)
    );

    assert.match(source, /per-vu-iterations/);
    assert.match(source, /maxDuration/);
    assert.match(source, /NANOCLAW_RUN_ID/);
    assert.match(source, /X-Request-ID/);
    assert.match(source, /timeout: '3s'/);
    assert.match(source, /redirects: 0/);
  });
}

test('synthetic DDoS and scraper have distinct behavior', () => {
  const ddos = readFileSync(
    new URL('../k6/p01_ddos.js', import.meta.url),
    'utf8'
  );

  const scraper = readFileSync(
    new URL('../k6/p01_scraper.js', import.meta.url),
    'utf8'
  );

  assert.match(ddos, /sleep\(0\.1\)/);
  assert.match(scraper, /sleep\(0\.5\)/);

  assert.match(ddos, /Synthetic-DDoS/);
  assert.match(scraper, /Synthetic-Scraper/);

  assert.notEqual(ddos, scraper);
});
