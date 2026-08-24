import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { SessionSidebar } from './SessionSidebar';
import { PERSONAS, PersonaProvider, usePersona } from '../context/PersonaContext';
import type { ChatSession } from '../types/agent';

const sessions: ChatSession[] = [
  {
    session_id: 'session-1',
    title: 'Suspicious sign-in',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    messages: [],
  },
];

function ActivePersonaProbe() {
  const { activePersona } = usePersona();
  return <output aria-label="active persona">{activePersona.role}</output>;
}

function renderSidebar() {
  return render(
    <PersonaProvider>
      <SessionSidebar
        sessions={sessions}
        activeSessionId="session-1"
        isOpen={true}
        onToggleOpen={() => undefined}
        onSelectSession={() => undefined}
        onNewSession={() => undefined}
        onDeleteSession={() => undefined}
      />
      <ActivePersonaProbe />
    </PersonaProvider>,
  );
}

describe('SessionSidebar persona contract', () => {
  it('renders persona controls from the shared persona metadata', () => {
    renderSidebar();

    for (const persona of PERSONAS) {
      expect(screen.getByRole('button', { name: new RegExp(persona.label, 'i') })).toBeInTheDocument();
      expect(screen.getByText(persona.title)).toBeInTheDocument();
    }
  });

  it('updates active persona through shared context', async () => {
    const user = userEvent.setup();
    renderSidebar();

    await user.click(screen.getByRole('button', { name: /admin/i }));

    expect(screen.getByLabelText('active persona')).toHaveTextContent('admin');
  });
});
