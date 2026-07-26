import http from 'http';
import { log } from '../log.js';
import type { ChannelAdapter, ChannelDefaults, ChannelSetup, InboundEvent } from './adapter.js';
import { registerChannelAdapter } from './channel-registry.js';

const PLATFORM_ID = 'alertmanager';

const DEFAULTS: ChannelDefaults = {
  dm: { engageMode: 'pattern', engagePattern: '.', threads: false, unknownSenderPolicy: 'public' },
  group: { engageMode: 'pattern', engagePattern: '.', threads: false, unknownSenderPolicy: 'public' },
  mentions: 'never',
};

function createAdapter(): ChannelAdapter {
  let server: http.Server | null = null;

  return {
    name: 'alertmanager',
    channelType: 'alertmanager',
    supportsThreads: false,
    defaults: DEFAULTS,

    async setup(config: ChannelSetup): Promise<void> {
      server = http.createServer((req, res) => {
        if (req.method === 'POST' && req.url === '/alerts') {
          let body = '';
          req.on('data', chunk => { body += chunk.toString(); });
          req.on('end', async () => {
            try {
              const payload = JSON.parse(body);
              if (payload.alerts && payload.alerts.length > 0) {
                for (const alert of payload.alerts) {
                  const alertMsg = `ANOMALY DETECTED: ${alert.labels.alertname} - ${alert.annotations.summary}\n${alert.annotations.description}\nStatus: ${alert.status}`;
                  await config.onInbound(PLATFORM_ID, null, {
                    id: `alert-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                    kind: 'chat',
                    timestamp: new Date().toISOString(),
                    content: {
                      text: alertMsg,
                      sender: 'alertmanager',
                      senderId: `alertmanager:${PLATFORM_ID}`,
                    },
                  });
                }
              }
              res.writeHead(200);
              res.end('OK');
            } catch (err) {
              log.error('Alertmanager webhook error', { err });
              res.writeHead(400);
              res.end('Bad Request');
            }
          });
        } else {
          res.writeHead(404);
          res.end('Not Found');
        }
      });

      return new Promise<void>((resolve, reject) => {
        server!.once('error', reject);
        server!.listen(8081, '0.0.0.0', () => {
          log.info('Alertmanager channel listening on port 8081');
          resolve();
        });
      });
    },

    async teardown(): Promise<void> {
      if (server) {
        await new Promise<void>((resolve) => {
          server!.close(() => resolve());
        });
        server = null;
      }
    },

    isConnected(): boolean {
      return server !== null;
    },

    async deliver(platformId, _threadId, message): Promise<string | undefined> {
      // Alerts are one-way in this adapter. Outbound messages (like system_action)
      // are intercepted by delivery.ts.
      return undefined;
    },
  };
}

registerChannelAdapter('alertmanager', { factory: createAdapter, defaults: DEFAULTS });
