import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const guard = fs.readFileSync(
  path.resolve(here, '../k6/target_guard.js'),
  'utf8'
).replace('export function safeTarget', 'function safeTarget');

const context = vm.createContext({});
new vm.Script(`${guard}\nglobalThis.safeTarget = safeTarget;`)
  .runInContext(context);

const allowed = [
  'http://127.0.0.1:10000',
  'http://localhost:10000',
  'http://testbed-envoy:10000',
];

const rejected = [
  'https://example.com',
  'http://example.com:10000',
  'http://127.0.0.1:8080',
  'http://127.0.0.1:10000/',
  'http://127.0.0.1:10000?x=1',
  'http://user:pass@127.0.0.1:10000',
  'http://127.0.0.1:10000.evil.com',
  'http://169.254.169.254',
  '',
  null,
  undefined,
  10000,
];

for (const target of allowed) {
  assert.equal(context.safeTarget(target), target);
}

for (const target of rejected) {
  assert.throws(() => context.safeTarget(target));
}

console.log(
  `P14 target guard: ${allowed.length} allowed, ` +
  `${rejected.length} rejected — PASS`
);
