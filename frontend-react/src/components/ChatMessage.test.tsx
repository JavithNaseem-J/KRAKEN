import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';

import type { ChatMessage as ChatMessageType } from '../types/agent';
import { ChatMessage } from './ChatMessage';

const baseMessage: ChatMessageType = {
  id: 'message-1',
  role: 'assistant',
  content: 'Use the corporate VPN portal.',
  timestamp: '2026-08-30T00:00:00.000Z',
};

const props = {
  onApprovalResolved: () => undefined,
  onInspectReasoning: () => undefined,
};

test('renders ordinary markdown without loading syntax highlighting', () => {
  render(<ChatMessage message={baseMessage} {...props} />);

  expect(screen.getByText('Use the corporate VPN portal.')).toBeInTheDocument();
  expect(screen.queryByTestId('syntax-highlighter')).not.toBeInTheDocument();
});

test(
  'loads syntax highlighting for a fenced code block',
  async () => {
    render(
      <ChatMessage
        message={{
          ...baseMessage,
          content: '```python\nprint("connected")\n```',
        }}
        {...props}
      />,
    );

    const highlighter = await screen.findByTestId('syntax-highlighter', {}, { timeout: 10_000 });
    expect(highlighter).toHaveTextContent('print("connected")');
  },
  15_000,
);
