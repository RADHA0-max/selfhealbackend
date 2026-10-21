/** Single-turn inference using the actual NanoClaw provider, with no tools or delivery.
 * Does NOT start index.ts, poll-loop, CLI, MCP, Docker, or host action dispatch.
 * RPC directories are explicit: invoking this against live queues requires approval.
 */
import fs from 'node:fs';
import { BrokerProvider } from './providers/broker.js';

class DiagnosticTimeout extends Error {}

async function main() {
  const [inDir, outDir, model, timeout] = process.argv.slice(2);
  if (!inDir || !outDir || !model || !timeout) throw new Error('Explicit RPC directories, model and timeout required');
  if (!fs.statSync(inDir).isDirectory() || !fs.statSync(outDir).isDirectory()) throw new Error('RPC directory missing');
  const input = Buffer.alloc(60 * 1024 + 1);
  let length = 0;
  while (length < input.length) {
    const n = fs.readSync(0, input, length, input.length - length, null);
    if (!n) break;
    length += n;
  }
  if (length > 60 * 1024) throw new Error('Diagnostic input too large');
  const request = JSON.parse(input.subarray(0, length).toString('utf8'));
  if (Object.keys(request).sort().join(',') !== 'prompt,request_id' ||
      !/^diag-[a-f0-9]{32}$/.test(request.request_id) ||
      typeof request.prompt !== 'string' || !request.prompt.trim()) throw new Error('Invalid diagnostic input');
  let rpcRequestId = '';
  const provider = new BrokerProvider({ model }, {
    inDir, outDir, timeoutMs: Number(timeout), onRequest: id => { rpcRequestId = id; },
  });
  const query = provider.query({ prompt: request.prompt, cwd: process.cwd() });
  query.end();
  try {
    for await (const event of query.events) {
      if (event.type === 'error') {
        if (event.classification === 'broker_timeout') throw new DiagnosticTimeout();
        throw new Error('Broker inference failed');
      }
      if (event.type !== 'result') continue;
      if (event.isError || typeof event.text !== 'string') throw new Error('No diagnostic result');
      // Unwrap exactly one inert delivery wrapper. Never interpret or dispatch tags.
      const match = /^<message to="local-cli">([\s\S]*)<\/message>$/.exec(event.text.trim());
      if (!match || match[1].includes('<message') || match[1].includes('</message>')) throw new Error('Invalid diagnostic wrapper');
      // Preserve raw JSON so the Python boundary can reject duplicate keys.
      // JSON.parse here would silently discard duplicate-field evidence.
      const diagnosis = match[1];
      process.stdout.write(JSON.stringify({request_id: request.request_id, rpc_request_id: rpcRequestId, diagnosis}));
      return;
    }
    throw new Error('Missing result');
  } finally {
    query.abort();
  }
}
main().catch((error) => {
  // No model output, evidence, credentials or internal exceptions on stderr.
  process.stderr.write('Diagnostic inference failed\n');
  process.exitCode = error instanceof DiagnosticTimeout ? 124 : 1;
});
