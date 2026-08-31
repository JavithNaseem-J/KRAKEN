import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import type { ChatMessage as ChatMessageType } from '../types/agent';
import { ChatMessage } from './ChatMessage';

vi.mock('./CodeBlock', () => ({
  default: ({ code }: { code: string }) => <div data-testid="syntax-highlighter">{code}</div>,
}));

const baseMessage: ChatMessageType = {
  id: 'message-1',
  role: 'assistant',
  content: 'Use the corporate VPN portal.',
  timestamp: '2026-08-30T00:00:00.000Z',
};

const props = {
  onApprovalResolved: () => undefined,
};

test('renders ordinary markdown without loading syntax highlighting', () => {
  render(<ChatMessage message={baseMessage} {...props} />);

  expect(screen.getByText('Use the corporate VPN portal.')).toBeInTheDocument();
  expect(screen.queryByText('Reasoning')).not.toBeInTheDocument();
  expect(screen.queryByTestId('syntax-highlighter')).not.toBeInTheDocument();
});

test('loads syntax highlighting for a fenced code block', async () => {
  render(
    <ChatMessage
      message={{
        ...baseMessage,
        content: '```python\nprint("connected")\n```',
      }}
      {...props}
    />,
  );

  const highlighter = await screen.findByTestId('syntax-highlighter');
  expect(highlighter).toHaveTextContent('print("connected")');
});
