import { expect, test } from 'vitest';

import {
  applyStreamDelta,
  finalizeStreamedMessage,
  markStreamInterrupted,
  sanitizeStoredSessions,
} from './App';
import type { QueryResponse } from './types/agent';

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

test('finalizes one streamed assistant message without duplication', () => {
  const messageId = 'streamed-message';
  const streamed = applyStreamDelta([], messageId, 'Hello', '2026-01-01T00:00:00.000Z');
  const accumulated = applyStreamDelta(streamed, messageId, ' world', '2026-01-01T00:00:01.000Z');
  const response = { answer: 'Hello world' } as QueryResponse;

  const finalized = finalizeStreamedMessage(accumulated, messageId, response);

  expect(finalized).toHaveLength(1);
  expect(finalized[0]).toMatchObject({ id: messageId, role: 'assistant', content: 'Hello world' });
});

test('marks a partial streamed message as incomplete after a disconnect', () => {
  const messages = applyStreamDelta([], 'streamed-message', 'Partial answer', '2026-01-01T00:00:00.000Z');

  const interrupted = markStreamInterrupted(messages, 'streamed-message');

  expect(interrupted[0].content).toContain('Streaming interrupted. Please retry.');
});
