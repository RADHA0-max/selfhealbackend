/**
 * `drivers/index.ts` wiring tests — focused on `dockerNetworkArgs`, the
 * function that turns `spec.network` into the actual `docker create`
 * network flags. A network-isolated agent (`spec.network === 'none'`)
 * must short-circuit before any egress-lockdown or host-gateway logic runs.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('../log.js', () => ({
  log: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn(), fatal: vi.fn() },
}));

import { dockerNetworkArgs } from './index.js';
import { fixtureSpec } from './spec-fixture.js';

describe('dockerNetworkArgs', () => {
  it('returns --network none for a network-isolated spec, before any egress/host-gateway logic', () => {
    const spec = fixtureSpec({ network: 'none' });
    expect(dockerNetworkArgs(spec)).toEqual(['--network', 'none']);
  });

  it('does not short-circuit a shared-private spec', () => {
    const spec = fixtureSpec({ network: 'shared-private' });
    expect(dockerNetworkArgs(spec)).not.toEqual(['--network', 'none']);
  });
});
