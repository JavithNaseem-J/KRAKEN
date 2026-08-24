import axios from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { pollSessionStatus } from './api';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('pollSessionStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('reads signed-session status without submitting another query', async () => {
    vi.mocked(axios.get).mockResolvedValue({
      data: { status: 'running', session_id: 'server-session' },
    });

    await expect(pollSessionStatus('browser-session')).resolves.toEqual({
      status: 'running',
      session_id: 'server-session',
    });
    expect(axios.get).toHaveBeenCalledWith('/v1/demo/status', { withCredentials: true });
    expect(axios.post).not.toHaveBeenCalled();
  });
});
