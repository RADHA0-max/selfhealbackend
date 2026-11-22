import test from 'node:test';
import assert from 'node:assert/strict';

import {
  validateParallelArms,
  validateRequestIsolation,
} from '../experiments/parallel_isolation.mjs';

test('distinct parallel arms accepted', () => {
  assert.equal(
    validateParallelArms([
      { run_id: 'organic-arm-1' },
      { run_id: 'ddos-arm-2' },
    ]),
    true
  );
});

test('duplicate arm rejected', () => {
  assert.throws(
    () => validateParallelArms([
      { run_id: 'same' },
      { run_id: 'same' },
    ]),
    /Duplicate run ID/
  );
});

test('invalid run ID rejected', () => {
  assert.throws(
    () => validateParallelArms([
      { run_id: '../escape' },
      { run_id: 'safe' },
    ]),
    /Invalid experiment run ID/
  );
});

test('isolated request ownership passes', () => {
  const result = validateRequestIsolation([
    { run_id: 'arm-a', request_id: 'arm-a-1' },
    { run_id: 'arm-b', request_id: 'arm-b-1' },
  ]);

  assert.equal(result.cross_arm_collisions, 0);
  assert.equal(result.unique_requests, 2);
});

test('cross-arm request collision rejected', () => {
  assert.throws(
    () => validateRequestIsolation([
      { run_id: 'arm-a', request_id: 'shared-1' },
      { run_id: 'arm-b', request_id: 'shared-1' },
    ]),
    /Cross-arm request collision/
  );
});
