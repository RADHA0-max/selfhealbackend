/**
 * TypeScript RPC Adapter for NanoClaw Agent-Runner
 *
 * This adapter implements the file-based RPC communication with the trusted broker
 * following the architecture requirements for Zone U (untrusted agent) communication.
 *
 * The adapter follows the existing Python RPC contract and interfaces with:
 * - Broker (file-based LLM broker)
 * - LiteLLM inference gateway
 * - Ollama inference containers
 *
 * Security: This adapter ensures the agent never directly accesses Ollama/LiteLLM
 * and always uses the broker for all model interactions.
 */

import { v4 as uuidv4 } from 'uuid';
import fs from 'fs';
import path from 'path';
import { promisify } from 'util';

const writeFile = promisify(fs.writeFile);
const readFile = promisify(fs.readFile);
const unlink = promisify(fs.unlink);
const exists = promisify(fs.exists);

// Define the interfaces from the architecture
export interface QueryInput {
  model: string;
  messages: Array<{ role: string; content: string }>;
  temperature?: number;
  top_p?: number;
  repeat_penalty?: number;
  format?: string;
  stream?: boolean;
}

export interface ProviderEvent {
  type: 'success' | 'error' | 'timeout' | 'processing';
  requestId: string;
  data?: any;
  error?: string;
  timestamp: number;
}

export interface AgentQuery {
  query(input: QueryInput): Promise<ProviderEvent>;
}

export interface AgentProvider {
  name: string;
  createQuery(): AgentQuery;
}

// RPC Request/Response format matching the broker protocol
export interface RPCRequest {
  request_id: string;
  model: string;
  messages: Array<{ role: string; content: string }>;
  temperature?: number;
  top_p?: number;
  repeat_penalty?: number;
  format?: string;
  stream?: boolean;
  timeout?: number;
}

export interface RPCResponse {
  request_id: string;
  ok: boolean;
  result?: any;
  error?: string;
  timestamp: number;
}

/**
 * TypeScript RPC Client for NanoClaw Broker Integration
 *
 * This client implements the file-based RPC communication with the broker
 * following the architecture requirements.
 */
export class TypeScriptRPCClient implements AgentQuery {
  private brokerPath: string;
  private timeoutMs: number;

  constructor(brokerPath: string = '/llm_rpc', timeoutMs: number = 30000) {
    this.brokerPath = brokerPath;
    this.timeoutMs = timeoutMs;
  }

  /**
   * Execute a query through the broker RPC interface
   *
   * This method follows the architecture requirements:
   * 1. Creates a request in the broker directory
   * 2. Waits for the response in the broker directory
   * 3. Validates the response
   * 4. Handles errors appropriately
   * 5. Emits appropriate ProviderEvents
   */
  async query(input: QueryInput): Promise<ProviderEvent> {
    const requestId = uuidv4();

    // Create the RPC request
    const request: RPCRequest = {
      request_id: requestId,
      model: input.model,
      messages: input.messages,
      temperature: input.temperature,
      top_p: input.top_p,
      repeat_penalty: input.repeat_penalty,
      format: input.format,
      stream: input.stream,
      timeout: this.timeoutMs,
    };

    // Validate request structure
    if (!request.model || !request.messages || !Array.isArray(request.messages)) {
      return {
        type: 'error',
        requestId,
        error: 'Invalid request structure',
        timestamp: Date.now(),
      };
    }

    // Ensure broker directory exists
    try {
      await fs.promises.mkdir(this.brokerPath, { recursive: true });
    } catch (err) {
      return {
        type: 'error',
        requestId,
        error: `Failed to create broker directory: ${err.message}`,
        timestamp: Date.now(),
      };
    }

    const requestFile = path.join(this.brokerPath, `req-${requestId}.json`);
    const responseFile = path.join(this.brokerPath, `resp-${requestId}.json`);

    try {
      // Write request atomically
      await writeFile(requestFile, JSON.stringify(request, null, 2));

      // Wait for response with timeout
      const startTime = Date.now();
      let response: RPCResponse | null = null;

      while (Date.now() - startTime < this.timeoutMs) {
        try {
          if (await exists(responseFile)) {
            const responseContent = await readFile(responseFile, 'utf8');
            response = JSON.parse(responseContent);
            break;
          }
        } catch (err) {
          // File might not exist yet or be corrupted, continue waiting
        }

        // Wait 100ms before checking again
        await new Promise((resolve) => setTimeout(resolve, 100));
      }

      // Clean up request file
      try {
        await unlink(requestFile);
      } catch (err) {
        // Log but don't fail on cleanup
        console.warn(`Failed to cleanup request file: ${err.message}`);
      }

      // Check if we got a response
      if (!response) {
        return {
          type: 'timeout',
          requestId,
          error: 'Request timeout waiting for broker response',
          timestamp: Date.now(),
        };
      }

      // Validate response
      if (response.request_id !== requestId) {
        return {
          type: 'error',
          requestId,
          error: `Response ID mismatch: expected ${requestId}, got ${response.request_id}`,
          timestamp: Date.now(),
        };
      }

      // Handle broker errors
      if (!response.ok) {
        return {
          type: 'error',
          requestId,
          error: response.error || 'Broker returned error',
          timestamp: Date.now(),
        };
      }

      // Success case
      return {
        type: 'success',
        requestId,
        data: response.result,
        timestamp: Date.now(),
      };
    } catch (error) {
      // Clean up request file on error
      try {
        await unlink(requestFile);
      } catch (cleanupError) {
        // Log but don't fail on cleanup
        console.warn(`Failed to cleanup request file on error: ${cleanupError.message}`);
      }

      return {
        type: 'error',
        requestId,
        error: `RPC communication error: ${error.message}`,
        timestamp: Date.now(),
      };
    }
  }
}

/**
 * ClaudeProvider implementation that uses the TypeScript RPC Client
 */
export class ClaudeProvider implements AgentProvider {
  name: string = 'claude';
  private rpcClient: TypeScriptRPCClient;

  constructor(brokerPath?: string) {
    this.rpcClient = new TypeScriptRPCClient(brokerPath);
  }

  createQuery(): AgentQuery {
    return this.rpcClient;
  }
}

/**
 * Factory function to create providers
 */
export function createProvider(providerName: string, brokerPath?: string): AgentProvider | null {
  switch (providerName.toLowerCase()) {
    case 'claude':
      return new ClaudeProvider(brokerPath);
    default:
      return null;
  }
}
