import axios from 'axios';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { ErrorBoundary } from './components/ErrorBoundary';
import { ReasoningInspectorDrawer } from './components/ReasoningInspectorDrawer';
import { SessionSidebar } from './components/SessionSidebar';
import RuixenMoonChat from './components/ui/ruixen-moon-chat';
import { useApprovalPoller } from './hooks/useApprovalPoller';
import { runAgentQuery, streamAgentQuery, type AgentStreamEvent } from './services/api';
import { usePersona } from './context/PersonaContext';
import {
  isPendingApproval,
  type ChatMessage as ChatMessageType,
  type ChatSession,
  type QueryResponse,
  type UserRole,
} from './types/agent';

const SESSIONS_STORAGE_KEY = 'akea.chat.sessions.v1';

const USER_ROLES: UserRole[] = [
  {
    user_id: 'alice',
    label: 'Alice',
    title: 'Tier 1 Analyst',
    api_key: import.meta.env.VITE_API_KEY_ANALYST ?? import.meta.env.VITE_API_KEY_ALICE ?? 'dev-key-analyst-default',
  },
  {
    user_id: 'bob',
    label: 'Bob',
    title: 'Security Lead',
    api_key: import.meta.env.VITE_API_KEY_ADMIN ?? import.meta.env.VITE_API_KEY_BOB ?? 'dev-key-admin-default',
  },
  {
    user_id: 'admin',
    label: 'Admin',
    title: 'Approver',
    api_key:
      import.meta.env.VITE_API_KEY_ADMIN ??
      'dev-key-admin-default',
  },
];

function newSession(): ChatSession {
  const now = new Date().toISOString();
  return {
    session_id: crypto.randomUUID(),
    title: '',
    created_at: now,
    updated_at: now,
    messages: [],
  };
}

function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(SESSIONS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ChatSession[];
    if (!Array.isArray(parsed)) return [];

    const nowMs = Date.now();
    return parsed.map((s) => ({
      ...s,
      messages: s.messages.map((m) => {
        if (m.approval_state === 'pending') {
          const ageMs = nowMs - new Date(m.timestamp).getTime();
          if (ageMs > 15 * 60 * 1000) {
            return { ...m, approval_state: 'expired' as const };
          }
        }
        return m;
      }),
    }));
  } catch {
    return [];
  }
}

function queryResponseToMessage(res: QueryResponse): ChatMessageType {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    content: res.answer,
    timestamp: res.timestamp ?? new Date().toISOString(),
    metadata: {
      reasoning: res.reasoning,
      action_taken: res.action_taken,
      action_result: res.action_result,
      sources: res.sources,
      retrieved_chunks: res.retrieved_chunks,
      trace_id: res.trace_id,
      timestamp: res.timestamp,
    },
  };
}

export default function App() {
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    const loaded = loadSessions();
    return loaded.length > 0 ? loaded : [newSession()];
  });
  const [activeSessionId, setActiveSessionId] = useState<string>(
    () => sessions[0]?.session_id ?? '',
  );
  const { activePersona } = usePersona();
  const [busy, setBusy] = useState(false);
  const [pendingSessionId, setPendingSessionId] = useState<string | null>(null);
  const [inspectedMessage, setInspectedMessage] = useState<ChatMessageType | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const activeSession = sessions.find((s) => s.session_id === activeSessionId) ?? null;

  // Local storage persistence with LRU eviction (keep 20 most recent sessions)
  useEffect(() => {
    let toSave = sessions;
    if (sessions.length > 20) {
      toSave = [...sessions]
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
        .slice(0, 20);
    }
    localStorage.setItem(SESSIONS_STORAGE_KEY, JSON.stringify(toSave));
  }, [sessions]);

  const updateSession = useCallback(
    (sessionId: string, updater: (s: ChatSession) => ChatSession) => {
      setSessions((prev) =>
        prev.map((s) =>
          s.session_id === sessionId
            ? { ...updater(s), updated_at: new Date().toISOString() }
            : s,
        ),
      );
    },
    [],
  );

  const appendMessage = useCallback(
    (sessionId: string, message: ChatMessageType) => {
      updateSession(sessionId, (s) => ({
        ...s,
        title: s.title || (message.role === 'user'
          ? (message.content.length > 50 ? message.content.slice(0, 50) + '…' : message.content)
          : s.title),
        messages: [...s.messages, message],
      }));
    },
    [updateSession],
  );

  const handleCompletedResponse = useCallback(
    (sessionId: string, res: QueryResponse) => {
      updateSession(sessionId, (s) => ({
        ...s,
        messages: s.messages.map((m) =>
          m.approval_state === 'pending'
            ? { ...m, approval_state: 'approved' as const }
            : m,
        ),
      }));
      appendMessage(sessionId, queryResponseToMessage(res));
      setPendingSessionId((cur) => (cur === sessionId ? null : cur));
    },
    [appendMessage, updateSession],
  );

  // Background polling while pending approval
  useApprovalPoller({
    pendingSessionId,
    apiKey: activePersona.apiKey,
    onUpdate: (res) => {
      if (!isPendingApproval(res)) {
        handleCompletedResponse(res.session_id, res);
      }
    },
    onTimeout: (reason?: string) => {
      if (!pendingSessionId) return;
      updateSession(pendingSessionId, (s) => ({
        ...s,
        messages: s.messages.map((m) =>
          m.approval_state === 'pending'
            ? { ...m, approval_state: 'expired' as const }
            : m,
        ),
      }));
      appendMessage(pendingSessionId, {
        id: crypto.randomUUID(),
        role: 'system',
        content: reason || 'Security authorization request timed out after 15 minutes.',
        timestamp: new Date().toISOString(),
      });
      setPendingSessionId(null);
    },
  });

  const [streamingSteps, setStreamingSteps] = useState<AgentStreamEvent[]>([]);

  const sendMessage = async (text: string) => {
    if (!activeSession || busy) return;
    const sessionId = activeSession.session_id;

    appendMessage(sessionId, {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    });
    setBusy(true);
    setStreamingSteps([]);

    try {
      const finalRes = await streamAgentQuery(
        text,
        sessionId,
        activePersona.apiKey,
        (event) => setStreamingSteps((prev) => [...prev, event]),
        activePersona.role,
        activePersona.id,
      );
      setStreamingSteps([]);

      if (finalRes) {
        if (isPendingApproval(finalRes)) {
          appendMessage(sessionId, {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: (finalRes as any).message,
            timestamp: new Date().toISOString(),
            approval_id: (finalRes as any).approval_id,
            approval_state: 'pending',
          });
          setPendingSessionId(sessionId);
        } else {
          appendMessage(sessionId, queryResponseToMessage(finalRes));
        }
      } else {
        // SSE ended without a response payload — fall back to poll
        const res = await runAgentQuery(
          '',
          sessionId,
          activePersona.apiKey,
          activePersona.role,
          activePersona.id,
        );
        if (isPendingApproval(res)) {
          appendMessage(sessionId, {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: res.message || 'A CRITICAL triage action requires human approval. Check the approval service.',
            timestamp: new Date().toISOString(),
            approval_id: res.approval_id || undefined,
            approval_state: 'pending',
          });
          if (res.approval_id) setPendingSessionId(sessionId);
        } else if (res && res.answer) {
          appendMessage(sessionId, queryResponseToMessage(res));
        } else {
          appendMessage(sessionId, {
            id: crypto.randomUUID(),
            role: 'system',
            content: 'The agent completed the analysis but produced no response. Please try your request again.',
            timestamp: new Date().toISOString(),
          });
        }
      }
    } catch (e: unknown) {
      setStreamingSteps([]);
      let errorMsg = 'The agent encountered an error processing your request. Please try again.';
      if (axios.isAxiosError(e)) {
        const status = e.response?.status;
        const data = e.response?.data as { error?: string; detail?: string } | undefined;
        const serverError = data?.error || data?.detail;
        if (status === 403) {
          errorMsg = serverError || 'Access denied. This operation requires operator-level clearance.';
        } else if (status === 400) {
          errorMsg = serverError || 'Security violation: request blocked by gateway.';
        } else if (status && status >= 500) {
          const incidentId = Math.random().toString(36).substring(2, 10).toUpperCase();
          errorMsg = `The agent encountered an error processing your request. Incident ID: #${incidentId}`;
        } else {
          errorMsg = serverError || 'The agent encountered an error. Please try again.';
        }
      }
      appendMessage(sessionId, {
        id: crypto.randomUUID(),
        role: 'system',
        content: errorMsg,
        timestamp: new Date().toISOString(),
      });
    } finally {
      setBusy(false);
    }

  };

  const handleApprovalResolved = useCallback(
    (approvalId: string, decision: 'approve' | 'reject') => {
      const sessionId = pendingSessionId ?? activeSessionId;
      updateSession(sessionId, (s) => ({
        ...s,
        messages: s.messages.map((m) =>
          m.approval_id === approvalId
            ? { ...m, approval_state: decision === 'approve' ? 'approved' : 'rejected' }
            : m,
        ),
      }));
      setPendingSessionId(null);
      if (decision === 'reject') {
        appendMessage(sessionId, {
          id: crypto.randomUUID(),
          role: 'system',
          content: 'Action rejected. The agent will not execute the requested operation.',
          timestamp: new Date().toISOString(),
        });
      }
    },
    [pendingSessionId, activeSessionId, updateSession, appendMessage],
  );

  const handleApprovalExpired = useCallback(
    (approvalId: string) => {
      const sessionId = pendingSessionId ?? activeSessionId;
      updateSession(sessionId, (s) => ({
        ...s,
        messages: s.messages.map((m) =>
          m.approval_id === approvalId && m.approval_state === 'pending'
            ? { ...m, approval_state: 'expired' as const }
            : m,
        ),
      }));
      if (pendingSessionId === sessionId) setPendingSessionId(null);
    },
    [pendingSessionId, activeSessionId, updateSession],
  );

  const createSession = () => {
    const s = newSession();
    setSessions((prev) => [s, ...prev]);
    setActiveSessionId(s.session_id);
    setPendingSessionId(null);
  };

  const deleteSession = (sessionId: string) => {
    setSessions((prev) => {
      const next = prev.filter((s) => s.session_id !== sessionId);
      if (next.length === 0) {
        const fresh = newSession();
        setActiveSessionId(fresh.session_id);
        return [fresh];
      }
      if (sessionId === activeSessionId) {
        setActiveSessionId(next[0].session_id);
      }
      return next;
    });
    if (sessionId === pendingSessionId) setPendingSessionId(null);
  };

  const messages = useMemo(() => activeSession?.messages ?? [], [activeSession]);

  const activeRole: UserRole = useMemo(
    () => ({
      user_id: activePersona.id,
      label: activePersona.label,
      title: activePersona.title,
      api_key: activePersona.apiKey,
    }),
    [activePersona],
  );

  return (
    <div className="flex h-full w-full bg-black overflow-hidden">
      {/* Session Sidebar */}
      <SessionSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        roles={USER_ROLES}
        activeRole={activeRole}
        isOpen={sidebarOpen}
        onToggleOpen={() => setSidebarOpen((prev) => !prev)}
        onSelectSession={(id) => setActiveSessionId(id)}
        onNewSession={createSession}
        onDeleteSession={deleteSession}
        onSelectRole={() => {}}
      />

      {/* Main Ruixen Moon Chat Component */}
      <main className="flex-1 h-full min-w-0">
        <RuixenMoonChat
          disabled={busy}
          onSend={(text) => void sendMessage(text)}
          messages={messages}
          activeRole={activeRole}
          pendingSessionId={pendingSessionId}
          activeSessionId={activeSessionId}
          sessionTitle={activeSession?.title}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(true)}
          onApprovalResolved={handleApprovalResolved}
          onApprovalExpired={handleApprovalExpired}
          onInspectReasoning={setInspectedMessage}
          streamingSteps={streamingSteps}
        />
      </main>

      {/* Slide-Over Reasoning Inspector */}
      <ErrorBoundary>
        <ReasoningInspectorDrawer
          message={inspectedMessage}
          onClose={() => setInspectedMessage(null)}
        />
      </ErrorBoundary>
    </div>
  );
}
