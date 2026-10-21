import { afterEach, expect, test } from 'vitest';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { appendAuditEvent, verifyAuditLedger } from '../src/audit-ledger';

let tempDir = '';

afterEach(async () => {
  if (tempDir) {
    await rm(tempDir, { recursive: true, force: true });
    tempDir = '';
  }
});

async function makeLedgerPath() {
  tempDir = await mkdtemp(join(tmpdir(), 'selfheal-ledger-test-'));
  return join(tempDir, 'audit.jsonl');
}

test('ledger appends events and verifies the hash chain', async () => {
  const path = await makeLedgerPath();

  await appendAuditEvent(path, {
    eventType: 'gate_reject',
    actionId: 'action-1',
    capability: 'scale_service',
    gate: 'GATE_5',
    reasonCode: 'trusted_evidence_missing',
  });

  await appendAuditEvent(path, {
    eventType: 'verified',
    actionId: 'action-1',
    reasonCode: 'verification_passed',
  });

  const result = await verifyAuditLedger(path);

  expect(result.ok).toBe(true);
  expect(result.entries).toBe(2);
  expect(result.headHash).toMatch(/^[a-f0-9]{64}$/);
});

test('ledger detects modification of a historical entry', async () => {
  const path = await makeLedgerPath();

  await appendAuditEvent(path, {
    eventType: 'gate_reject',
    actionId: 'action-2',
    gate: 'GATE_5',
    reasonCode: 'trusted_evidence_missing',
  });

  const contents = await readFile(path, 'utf8');
  await writeFile(
    path,
    contents.replace('action-2', 'action-X'),
    'utf8',
  );

  const result = await verifyAuditLedger(path);
  expect(result.ok).toBe(false);
});

test('ledger rejects arbitrary fields that could contain prompts or secrets', async () => {
  const path = await makeLedgerPath();

  await expect(
    appendAuditEvent(path, {
      eventType: 'gate_reject',
      actionId: 'action-3',
      prompt: 'private prompt content',
    } as never),
  ).rejects.toThrow(/Unsupported audit field/);
});

test('ledger refuses to append after historical tampering', async () => {
  const path = await makeLedgerPath();

  await appendAuditEvent(path, {
    eventType: 'gate_reject',
    actionId: 'action-4',
    gate: 'GATE_5',
    reasonCode: 'trusted_evidence_missing',
  });

  const contents = await readFile(path, 'utf8');
  await writeFile(path, contents.replace('action-4', 'action-X'), 'utf8');

  await expect(
    appendAuditEvent(path, {
      eventType: 'verified',
      actionId: 'action-4',
      reasonCode: 'verification_passed',
    }),
  ).rejects.toThrow(/invalid audit ledger/i);
});

test('concurrent appends preserve ledger integrity', async () => {
  const path = await makeLedgerPath();

  const results = await Promise.all(
    Array.from({ length: 10 }, (_, index) =>
      appendAuditEvent(path, {
        eventType: 'gate_reject',
        actionId: `concurrent-${index}`,
        gate: 'GATE_5',
        reasonCode: 'trusted_evidence_missing',
      }),
    ),
  );

  expect(results).toHaveLength(10);

  const verification = await verifyAuditLedger(path);
  expect(verification, JSON.stringify(verification, null, 2)).toMatchObject({
  ok: true,
  entries: 10,
});
  expect(verification.entries).toBe(10);
});

test('ledger rejects an incomplete final record', async () => {
  const path = await makeLedgerPath();

  await appendAuditEvent(path, {
    eventType: 'gate_reject',
    actionId: 'action-incomplete',
    gate: 'GATE_5',
    reasonCode: 'trusted_evidence_missing',
  });

  const contents = await readFile(path, 'utf8');
  await writeFile(path, contents.trimEnd(), 'utf8');

  const result = await verifyAuditLedger(path);

  expect(result.ok).toBe(false);
  expect(result.error).toContain('incomplete record');
});

test('ledger rejects malformed JSON records', async () => {
  const path = await makeLedgerPath();

  await writeFile(path, '{not-valid-json}\n', 'utf8');

  const result = await verifyAuditLedger(path);

  expect(result.ok).toBe(false);
  expect(result.error).toContain('Invalid record 1');
});

test('missing or empty ledger verifies as an empty chain', async () => {
  const path = await makeLedgerPath();

  const missing = await verifyAuditLedger(path);
  expect(missing).toMatchObject({
    ok: true,
    entries: 0,
    headHash: '0'.repeat(64),
  });

  await writeFile(path, '', 'utf8');

  const empty = await verifyAuditLedger(path);
  expect(empty).toMatchObject({
    ok: true,
    entries: 0,
    headHash: '0'.repeat(64),
  });
});
