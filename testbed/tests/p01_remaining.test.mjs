import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const scenarios = {
  p01_headless_botnet: [8, 8],
  p01_ambiguous: [6, 8],
  p01_analytics: [4, 10],
};

for (const [name, [vus, iterations]] of Object.entries(scenarios)) {
  test(`${name}: bounded isolated scenario`, () => {
    const source = readFileSync(
      new URL(`../k6/${name}.js`, import.meta.url),
      'utf8'
    );

    assert.match(source, /safeTarget/);
    assert.match(source, /target_guard\.js/);
    assert.match(source, /per-vu-iterations/);
    assert.match(source, new RegExp(`vus:\\s*${vus}`));
    assert.match(source, new RegExp(`iterations:\\s*${iterations}`));
    assert.match(source, /maxDuration: '60s'/);
    assert.match(source, /NANOCLAW_RUN_ID/);
    assert.match(source, /X-Request-ID/);
    assert.match(source, /redirects: 0/);
    assert.match(source, /timeout: '3s'/);
  });
}
