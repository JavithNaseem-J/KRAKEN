import { expect, test } from 'vitest';

import { sanitizeStoredSessions } from './App';

test('removes retired public metadata from stored chat sessions', () => {
  const sessions = sanitizeStoredSessions([
    {
      session_id: 'session-1',
      title: 'VPN help',
      created_at: '2026-08-30T00:00:00.000Z',
      updated_at: '2026-08-30T00:00:00.000Z',
      messages: [
        {
          id: 'message-1',
          role: 'assistant',
          content: 'Use the corporate VPN portal.',
          timestamp: '2026-08-30T00:00:00.000Z',
          metadata: {
            reasoning: 'private model analysis',
            trace_id: 'trace-1',
            sources: ['faq'],
            action_result: { status: 'safe', nested: { reasoning: 'private nested analysis' } },
          },
          approval_details: { reasoning: 'private approval analysis' },
        },
      ],
    },
  ]);

  expect(JSON.stringify(sessions)).not.toContain('reasoning');
  expect(sessions[0].messages[0].content).toBe('Use the corporate VPN portal.');
  expect(sessions[0].messages[0].metadata).toEqual({
    trace_id: 'trace-1',
    sources: ['faq'],
    action_result: { status: 'safe', nested: {} },
  });
});
