import * as fs from 'fs';
import * as path from 'path';
import { randomUUID } from 'crypto';

import { registerProvider } from './provider-registry.js';
import type { MemorySessionHookRegistration } from '../memory/session-hook.js';
import type {
  AgentProvider,
  AgentQuery,
  ProviderEvent,
  ProviderOptions,
  QueryInput,
} from './types.js';

const RPC_IN_DIR = '/llm_rpc/in';
const RPC_OUT_DIR = '/llm_rpc/out';

const DEFAULT_MODEL = 'fast';
const POLL_INTERVAL_MS = 100;
const TIMEOUT_MS = 120_000;

const ALLOWED_MODELS = new Set([
  'fast',
  'plan',
  'deep',
  'coder',
]);

interface BrokerResponse {
  request_id: string;
  ok: boolean;
  content?: string | null;
  error?: string | null;
}

export class BrokerProvider implements AgentProvider {
  private readonly model: string;
  private readonly rpcInDir: string;
  private readonly rpcOutDir: string;
  private readonly timeoutMs: number;
  private readonly onRequest?: (id: string) => void;

  constructor(
    options: ProviderOptions = {},
    rpcDirs: { inDir: string; outDir: string; timeoutMs?: number; onRequest?: (id: string) => void } = {
      inDir: RPC_IN_DIR,
      outDir: RPC_OUT_DIR,
    },
  ) {
    this.timeoutMs = rpcDirs.timeoutMs ?? TIMEOUT_MS;
    if (!Number.isFinite(this.timeoutMs) || this.timeoutMs <= 0 || this.timeoutMs > TIMEOUT_MS) {
      throw new Error('Invalid broker timeout');
    }
    this.onRequest = rpcDirs.onRequest;
    this.rpcInDir = rpcDirs.inDir;
    this.rpcOutDir = rpcDirs.outDir;
    const configuredModel = options.model || DEFAULT_MODEL;

    if (!ALLOWED_MODELS.has(configuredModel)) {
      throw new Error(
        `Unsupported broker model "${configuredModel}". ` +
          `Allowed models: ${[...ALLOWED_MODELS].join(', ')}`,
      );
    }

    this.model = configuredModel;
  }

  registerMemorySessionHook(
    _hook: MemorySessionHookRegistration,
    _memory?: unknown,
  ): void {}

  isSessionInvalid(_err: unknown): boolean {
    return false;
  }

  query(input: QueryInput): AgentQuery {
    const pending: string[] = [];
    let waiting: (() => void) | null = null;
    let ended = false;
    let aborted = false;

    const timeoutMs = this.timeoutMs;
    const onRequest = this.onRequest;
    const model = this.model;
    const rpcInDir = this.rpcInDir;
    const rpcOutDir = this.rpcOutDir;
    const history: Array<{ role: 'user' | 'assistant'; content: string }> = [];
    const formattingInstructions = [
      'BROKER OUTPUT FORMAT:',
      'For a user-visible reply, output exactly <message to="DESTINATION">TEXT</message>.',
      'Use an actual destination name from the instructions above.',
      'Never use <send_message>, <send_message to="...">, or other XML tags as substitutes.',
      'The send_message tool name is NOT a valid final-response XML tag.',
      'Do not merely acknowledge formatting corrections; resend the original answer.',
      'Do not output explanatory text outside the required message blocks.',
    ].join('\n');
    const systemMessages = [{
      role: 'system' as const,
      content: [input.systemContext?.instructions, formattingInstructions]
        .filter(Boolean)
        .join('\n\n'),
    }];

    const processPrompt = async function* (
      prompt: string,
    ): AsyncGenerator<ProviderEvent> {
      const requestId = `req-${randomUUID()}`;
      const nextHistory = [...history, { role: 'user' as const, content: prompt }];

      // Keep the latest request intact; discard older exchanges if needed.
      while (
        nextHistory.length > 1 &&
        Buffer.byteLength(JSON.stringify({
          request_id: requestId,
          model,
          messages: [...systemMessages, ...nextHistory],
        }), 'utf8') > 64 * 1024
      ) {
        nextHistory.shift();
      }

      const requestPayload = {
        request_id: requestId,
        model,
        messages: [...systemMessages, ...nextHistory],
      };

      if (Buffer.byteLength(JSON.stringify(requestPayload), 'utf8') > 64 * 1024) {
        throw new Error('Broker request exceeds 64 KiB limit');
      }

      const tempPath = path.join(rpcInDir, `.${requestId}.tmp`);
      const requestPath = path.join(rpcInDir, `${requestId}.json`);
      const responsePath = path.join(
        rpcOutDir,
        `resp-${requestId}.json`,
      );

      fs.writeFileSync(
        tempPath,
        JSON.stringify(requestPayload),
        { encoding: 'utf8', flag: 'wx', mode: 0o600 },
      );

      fs.renameSync(tempPath, requestPath);

      onRequest?.(requestId);
      const startTime = Date.now();

      while (!aborted && Date.now() - startTime < timeoutMs) {
        if (fs.existsSync(responsePath)) {
          const fd = fs.openSync(responsePath, 'r');
          const buffer = Buffer.alloc(64 * 1024 + 1);
          let count: number;
          try {
            count = fs.readSync(fd, buffer, 0, buffer.length, 0);
          } finally {
            fs.closeSync(fd);
          }
          if (count > 64 * 1024) throw new Error('Broker response exceeds 64 KiB limit');
          const raw = buffer.subarray(0, count).toString('utf8');
          const response = JSON.parse(raw) as BrokerResponse;

          if (!response || typeof response !== 'object' || typeof response.ok !== 'boolean') {
            throw new Error('Invalid broker response schema');
          }
          if (response.ok && (typeof response.content !== 'string' || !response.content.trim())) {
            throw new Error('Invalid broker response content');
          }
          if (response.request_id !== requestId) {
            throw new Error(
              `Broker response ID mismatch: expected ${requestId}, got ${response.request_id}`,
            );
          }

          if (!response.ok) {
            const message = response.error || 'Broker request failed';

            yield {
              type: 'error',
              message,
              retryable: true,
              classification: 'broker_error',
            };

            yield {
              type: 'result',
              text: null,
              isError: true,
              error: message,
            };

            return;
          }

          const content = response.content ?? '';

          history.splice(0, history.length, ...nextHistory);
          history.push({ role: 'assistant', content });

          if (content) {
            yield {
              type: 'text',
              text: content,
            };
          }

          yield {
            type: 'result',
            text: content,
          };

          return;
        }

        await new Promise((resolve) =>
          setTimeout(resolve, POLL_INTERVAL_MS),
        );
      }

      if (aborted) {
        return;
      }

      const message =
        `Broker RPC timed out after ${timeoutMs}ms ` +
        `waiting for ${requestId}`;

      yield {
        type: 'error',
        message,
        retryable: true,
        classification: 'broker_timeout',
      };

      yield {
        type: 'result',
        text: null,
        isError: true,
        error: message,
      };
    }.bind(this);

    const events: AsyncIterable<ProviderEvent> = {
      async *[Symbol.asyncIterator]() {
        yield { type: 'activity' };

        yield {
          type: 'init',
          continuation: `broker-session-${Date.now()}`,
        };

        yield { type: 'activity' };

        yield* processPrompt(input.prompt);

        while (!ended && !aborted) {
          if (pending.length > 0) {
            const prompt = pending.shift()!;
            yield { type: 'activity' };
            yield* processPrompt(prompt);
            continue;
          }

          await new Promise<void>((resolve) => {
            waiting = resolve;
          });

          waiting = null;
        }

        while (!aborted && pending.length > 0) {
          const prompt = pending.shift()!;
          yield { type: 'activity' };
          yield* processPrompt(prompt);
        }
      },
    };

    return {
      push(message: string) {
        if (ended || aborted) {
          return;
        }

        pending.push(message);
        waiting?.();
      },

      end() {
        ended = true;
        waiting?.();
      },

      events,

      abort() {
        aborted = true;
        waiting?.();
      },
    };
  }
}

registerProvider('broker', (options) => new BrokerProvider(options));
