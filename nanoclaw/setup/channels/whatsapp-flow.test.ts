import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  brightSelect: vi.fn(),
  note: vi.fn(),
  userInput: vi.fn(),
}));

vi.mock('../lib/bright-select.js', () => ({
  brightSelect: mocks.brightSelect,
}));

vi.mock('../lib/theme.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/theme.js')>()),
  note: mocks.note,
}));

vi.mock('../logs.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../logs.js')>()),
  userInput: mocks.userInput,
}));

import { BACK_TO_CHANNEL_SELECTION } from '../lib/back-nav.js';
import { runWhatsAppChannel } from './whatsapp.js';

describe('WhatsApp shared-number risk gate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the warning and requires explicit acknowledgement for a shared number', async () => {
    mocks.brightSelect.mockResolvedValueOnce('shared').mockResolvedValueOnce('continue').mockResolvedValueOnce('back');

    const result = await runWhatsAppChannel('Daniel');

    expect(result).toBe(BACK_TO_CHANNEL_SELECTION);
    expect(mocks.note).toHaveBeenCalledWith(
      expect.stringContaining('temporarily suspend or permanently ban that number'),
      'Risk to your WhatsApp account',
    );
    expect(mocks.userInput).toHaveBeenCalledWith('whatsapp_shared_risk_acknowledged', 'true');
  });

  it('does not show the warning for a dedicated number', async () => {
    mocks.brightSelect.mockResolvedValueOnce('dedicated').mockResolvedValueOnce('back');

    const result = await runWhatsAppChannel('Daniel');

    expect(result).toBe(BACK_TO_CHANNEL_SELECTION);
    expect(mocks.note).not.toHaveBeenCalled();
    expect(mocks.userInput).not.toHaveBeenCalledWith('whatsapp_shared_risk_acknowledged', expect.anything());
  });

  it('switches to dedicated mode when the user declines the shared-number risk', async () => {
    mocks.brightSelect.mockResolvedValueOnce('shared').mockResolvedValueOnce('dedicated').mockResolvedValueOnce('back');

    const result = await runWhatsAppChannel('Daniel');

    expect(result).toBe(BACK_TO_CHANNEL_SELECTION);
    expect(mocks.note).toHaveBeenCalledOnce();
    expect(mocks.userInput).not.toHaveBeenCalledWith('whatsapp_shared_risk_acknowledged', expect.anything());
  });
});
