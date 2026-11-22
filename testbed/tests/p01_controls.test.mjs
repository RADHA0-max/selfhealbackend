import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

for (const name of ['p01_nat_control', 'p01_cache']) {
  test(`${name}: bounded and isolated`, () => {
    const source = readFileSync(
      new URL(`../k6/${name}.js`, import.meta.url),
      'utf8'
    );

    assert.match(source, /safeTarget/);
    assert.match(source, /target_guard\.js/);
    assert.match(source, /per-vu-iterations/);
    assert.match(source, /maxDuration/);
    assert.match(source, /NANOCLAW_RUN_ID/);
    assert.match(source, /X-Request-ID/);
    assert.match(source, /redirects: 0/);
  });
}

test('NAT control models distinct sessions', () => {
  const source = readFileSync(
    new URL('../k6/p01_nat_control.js', import.meta.url),
    'utf8'
  );

  assert.match(source, /http\.cookieJar\(\)/);
  assert.match(source, /nat-client-/);
  assert.match(source, /X-Test-Session/);
});

test('cache workload uses distinct cache keys', () => {
  const source = readFileSync(
    new URL('../k6/p01_cache.js', import.meta.url),
    'utf8'
  );

  assert.match(source, /cache_key=/);
  assert.match(source, /encodeURIComponent/);
});
