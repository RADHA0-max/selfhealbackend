import {
  readFileSync,
  writeFileSync,
} from 'node:fs';

const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$/;

export function validateRunId(value) {
  if (typeof value !== 'string' || !ID_PATTERN.test(value)) {
    throw new Error('Invalid experiment run ID');
  }

  return value;
}

export function validateParallelArms(arms) {
  if (!Array.isArray(arms) || arms.length < 2) {
    throw new Error('At least two experiment arms required');
  }

  const seen = new Set();

  for (const arm of arms) {
    if (!arm || typeof arm !== 'object') {
      throw new Error('Invalid experiment arm');
    }

    const runId = validateRunId(arm.run_id);

    if (seen.has(runId)) {
      throw new Error(`Duplicate run ID: ${runId}`);
    }

    seen.add(runId);
  }

  return true;
}

export function validateRequestIsolation(events) {
  if (!Array.isArray(events)) {
    throw new Error('Events must be an array');
  }

  const ownership = new Map();

  for (const event of events) {
    const runId = validateRunId(event.run_id);
    const requestId = event.request_id;

    if (typeof requestId !== 'string' || !requestId) {
      throw new Error('Missing request ID');
    }

    const existing = ownership.get(requestId);

    if (existing !== undefined && existing !== runId) {
      throw new Error(
        `Cross-arm request collision: ${requestId}`
      );
    }

    ownership.set(requestId, runId);
  }

  return {
    events: events.length,
    unique_requests: ownership.size,
    cross_arm_collisions: 0,
  };
}

function main() {
  const inputPath = process.argv[2];

  if (!inputPath) {
    console.error(
      'Usage: node parallel_isolation.mjs <evidence.json>'
    );
    process.exitCode = 2;
    return;
  }

  const input = JSON.parse(readFileSync(inputPath, 'utf8'));

  validateParallelArms(input.arms);

  const result = validateRequestIsolation(input.events);

  console.log(JSON.stringify({
    status: 'PASS',
    ...result,
  }, null, 2));
}

if (
  process.argv[1] &&
  import.meta.url === new URL(
    `file://${process.argv[1]}`
  ).href
) {
  main();
}
