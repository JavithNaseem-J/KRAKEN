import axios from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { pollSessionStatus, streamAgentQuery } from './api';

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
    expect(axios.get).toHaveBeenCalledWith('/v1/session/status', { withCredentials: true });
    expect(axios.post).not.toHaveBeenCalled();
  });
});

describe('streamAgentQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it('forwards ordered responder deltas before the authoritative terminal response', async () => {
    vi.mocked(axios.post).mockResolvedValue({
      data: { csrf_token: 'csrf-token', session_id: 'session-1' },
    });
    const payload = [
      'data: {"node":"responder","status":"delta","content":"Hello"}\n\n',
      'data: {"node":"responder","status":"delta","content":" world"}\n\n',
      'data: {"node":"done","status":"end","response":{"answer":"Hello world"}}\n\n',
    ].join('');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(payload));
            controller.close();
          },
        }),
      }),
    );
    const events: Array<{ status: string; content?: string }> = [];

    const response = await streamAgentQuery('hello', 'session-1', (event) => events.push(event));

    expect(events.filter((event) => event.status === 'delta').map((event) => event.content)).toEqual([
      'Hello',
      ' world',
    ]);
    expect(response).toMatchObject({ answer: 'Hello world' });
  });
});
