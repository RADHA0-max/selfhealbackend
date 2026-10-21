import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { BrokerProvider } from './broker.js';

test('broker preserves original prompt and assistant response across retry', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'nanoclaw-p2-'));
  const inDir = path.join(root, 'in');
  const outDir = path.join(root, 'out');
  fs.mkdirSync(inDir);
  fs.mkdirSync(outDir);

  try {
    const provider = new BrokerProvider(
      { model: 'fast' },
      { inDir, outDir },
    );

    const query = provider.query({
      prompt: 'Reply with exactly P2-MARKER',
      cwd: root,
      systemContext: {
        instructions: 'Wrap responses in <message to="local-cli">...</message>',
      },
    });

    const observed: Array<{
      messages: Array<{ role: string; content: string }>;
    }> = [];

    const simulateBroker = async () => {
      const seen = new Set<string>();
      const deadline = Date.now() + 5000;

      while (observed.length < 2 && Date.now() < deadline) {
        for (const filename of fs.readdirSync(inDir)) {
          if (!filename.endsWith('.json') || seen.has(filename)) continue;

          seen.add(filename);
          const request = JSON.parse(
            fs.readFileSync(path.join(inDir, filename), 'utf8'),
          );

          observed.push(request);

          const content = observed.length === 1
            ? 'P2-MARKER'
            : '<message to="local-cli">P2-MARKER</message>';

          fs.writeFileSync(
            path.join(outDir, `resp-${request.request_id}.json`),
            JSON.stringify({
              request_id: request.request_id,
              ok: true,
              content,
            }),
          );
        }

        await new Promise((resolve) => setTimeout(resolve, 10));
      }

      assert.equal(observed.length, 2, 'Expected two broker requests');
    };

    const consume = async () => {
      let results = 0;

      for await (const event of query.events) {
        if (event.type !== 'result') continue;

        results++;

        if (results === 1) {
          assert.equal(event.text, 'P2-MARKER');
          query.push(
            'Your response was not delivered. Please resend it using the required XML wrapper.',
          );
        } else {
          assert.equal(
            event.text,
            '<message to="local-cli">P2-MARKER</message>',
          );
          query.end();
          break;
        }
      }
    };

    await Promise.all([simulateBroker(), consume()]);

    assert.deepEqual(
      observed[1].messages.map((message) => message.role),
      ['system', 'user', 'assistant', 'user'],
    );
    assert.equal(observed[1].messages[1].content, 'Reply with exactly P2-MARKER');
    assert.equal(observed[1].messages[2].content, 'P2-MARKER');
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('oversized broker request is rejected before entering the queue', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'nanoclaw-p2-size-'));
  const inDir = path.join(root, 'in');
  const outDir = path.join(root, 'out');
  fs.mkdirSync(inDir);
  fs.mkdirSync(outDir);

  try {
    const provider = new BrokerProvider({}, { inDir, outDir });
    const query = provider.query({
      prompt: 'X'.repeat(70 * 1024),
      cwd: root,
    });

    await assert.rejects(async () => {
      for await (const _event of query.events) {
        // Consume until the provider rejects the oversized request.
      }
    }, /exceeds 64 KiB/);

    assert.deepEqual(fs.readdirSync(inDir), []);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('mismatched broker response ID is rejected', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'nanoclaw-p2-id-'));
  const inDir = path.join(root, 'in');
  const outDir = path.join(root, 'out');
  fs.mkdirSync(inDir);
  fs.mkdirSync(outDir);

  try {
    const provider = new BrokerProvider({}, { inDir, outDir });
    const query = provider.query({
      prompt: 'Check request ID',
      cwd: root,
    });

    const respond = async () => {
      const deadline = Date.now() + 5000;

      while (Date.now() < deadline) {
        const requestFile = fs.readdirSync(inDir).find((name) => name.endsWith('.json'));

        if (requestFile) {
          const request = JSON.parse(
            fs.readFileSync(path.join(inDir, requestFile), 'utf8'),
          );

          fs.writeFileSync(
            path.join(outDir, `resp-${request.request_id}.json`),
            JSON.stringify({
              request_id: 'wrong-request-id',
              ok: true,
              content: 'This must not be accepted',
            }),
          );
          return;
        }

        await new Promise((resolve) => setTimeout(resolve, 10));
      }

      throw new Error('Timed out waiting for test request');
    };

    await Promise.all([
      respond(),
      assert.rejects(async () => {
        for await (const _event of query.events) {
          // Consume until response-ID validation rejects the response.
        }
      }, /Broker response ID mismatch/),
    ]);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

for (const [name, response] of [
  ['oversized response', 'x'.repeat(65537)],
  ['non-boolean success', JSON.stringify({ok: 'true', content: 'x'})],
  ['non-string content', JSON.stringify({ok: true, content: {command: 'ignored'}})],
  ['malformed JSON', '{broken'],
] as const) {
  test(`broker rejects ${name}`, async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'nanoclaw-invalid-'));
    const inDir = path.join(root, 'in');
    const outDir = path.join(root, 'out');
    fs.mkdirSync(inDir); fs.mkdirSync(outDir);
    const provider = new BrokerProvider({}, {inDir, outDir, timeoutMs: 500});
    const query = provider.query({prompt: 'diagnose', cwd: root});
    query.end();
    const timer = setInterval(() => {
      for (const file of fs.readdirSync(inDir).filter(n => n.endsWith('.json'))) {
        const req = JSON.parse(fs.readFileSync(path.join(inDir, file), 'utf8'));
        fs.writeFileSync(path.join(outDir, `resp-${req.request_id}.json`), response);
      }
    }, 10);
    try {
      await assert.rejects(async () => {
        for await (const _event of query.events) { /* must reject */ }
      });
    } finally {
      query.abort(); clearInterval(timer);
      fs.rmSync(root, {recursive: true, force: true});
    }
  });
}

test('broker timeout yields an error without a result', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'nanoclaw-timeout-'));
  const inDir = path.join(root, 'in'); const outDir = path.join(root, 'out');
  fs.mkdirSync(inDir); fs.mkdirSync(outDir);
  const provider = new BrokerProvider({}, {inDir, outDir, timeoutMs: 20});
  const query = provider.query({prompt: 'diagnose', cwd: root});
  query.end();
  try {
    const events = [];
    for await (const event of query.events) events.push(event);
    assert.ok(events.some(e => e.type === 'error' && e.classification === 'broker_timeout'));
    assert.ok(events.some(e => e.type === 'result' && e.isError === true));
    assert.ok(!events.some(e => e.type === 'result' && !e.isError));
  } finally {
    query.abort(); fs.rmSync(root, {recursive: true, force: true});
  }
});
