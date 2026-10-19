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

  constructor(options: ProviderOptions = {}) {
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

    const model = this.model;

    const processPrompt = async function* (
      prompt: string,
    ): AsyncGenerator<ProviderEvent> {
      const requestId = `req-${randomUUID()}`;

      const requestPayload = {
        request_id: requestId,
        model,
        messages: [
          ...(input.systemContext?.instructions
            ? [
                {
                  role: 'system',
                  content: input.systemContext.instructions,
                },
              ]
            : []),
          {
            role: 'user',
            content: prompt,
          },
        ],
      };

      const tempPath = path.join(RPC_IN_DIR, `.${requestId}.tmp`);
      const requestPath = path.join(RPC_IN_DIR, `${requestId}.json`);
      const responsePath = path.join(
        RPC_OUT_DIR,
        `resp-${requestId}.json`,
      );

      fs.writeFileSync(
        tempPath,
        JSON.stringify(requestPayload),
        'utf8',
      );

      fs.renameSync(tempPath, requestPath);

      const startTime = Date.now();

      while (!aborted && Date.now() - startTime < TIMEOUT_MS) {
        if (fs.existsSync(responsePath)) {
          const raw = fs.readFileSync(responsePath, 'utf8');
          const response = JSON.parse(raw) as BrokerResponse;

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
        `Broker RPC timed out after ${TIMEOUT_MS}ms ` +
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
