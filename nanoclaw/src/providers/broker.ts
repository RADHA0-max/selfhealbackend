import path from 'node:path';
import { registerProviderContainerConfig } from './provider-container-registry.js';

registerProviderContainerConfig('broker', () => ({
  mounts: [
    {
      hostPath: path.resolve(process.cwd(), '../llm_rpc/in'),
      containerPath: '/llm_rpc/in',
      readonly: false,
    },
    {
      hostPath: path.resolve(process.cwd(), '../llm_rpc/out'),
      containerPath: '/llm_rpc/out',
      readonly: true,
    },
  ],
}));
