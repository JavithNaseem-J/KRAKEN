import axios from 'axios';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { SessionSidebar } from './components/SessionSidebar';
import RuixenMoonChat from './components/ui/ruixen-moon-chat';
import { useApprovalPoller } from './hooks/useApprovalPoller';
import {
  ApiRequestError,
  pollSessionStatus,
  streamAgentQuery,
  type AgentStreamEvent,
} from './services/api';
import { usePersona } from './context/PersonaContext';
import {
  isPendingApproval,
  isRunningExecution,
  type ChatMessage as ChatMessageType,
  type ChatSession,
  type QueryResponse,
  type RunResponse,
  type UserRole,
} from './types/agent';

const SESSIONS_STORAGE_KEY = 'akea.chat.sessions.v1';

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

export function sanitizeStoredSessions(value: unknown, nowMs = Date.now()): ChatSession[] {
  try {
    const parsed = value as ChatSession[];
    if (!Array.isArray(parsed)) return [];

    return parsed.map((s) => ({
      ...s,
      messages: (Array.isArray(s.messages) ? s.messages : []).map((m) => {
        const legacyMessage = stripReasoningFields(m) as ChatMessageType & {
          approval_details?: unknown;
        };
        const { approval_details: _legacyApprovalDetails, ...safeMessage } = legacyMessage;
        if (safeMessage.approval_state === 'pending') {
          const ageMs = nowMs - new Date(safeMessage.timestamp).getTime();
          if (ageMs > 15 * 60 * 1000) {
            return { ...safeMessage, approval_state: 'expired' as const };
          }
        }
        return safeMessage;
      }),
    }));
  } catch {
    return [];
  }
}

export function stripReasoningFields(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stripReasoningFields);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => key.toLowerCase() !== 'reasoning')
        .map(([key, item]) => [key, stripReasoningFields(item)]),
    );
  }
  return value;
}

function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(SESSIONS_STORAGE_KEY);
    if (!raw) return [];
    return sanitizeStoredSessions(JSON.parse(raw));
  } catch {
    return [];
  }
}

function queryResponseToMessage(res: QueryResponse): ChatMessageType {
  let content = res.answer;
  if (!content || !content.trim()) {
    content = 'The agent completed the request but did not produce a user-facing response.';
  }

  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    content,
    timestamp: res.timestamp ?? new Date().toISOString(),
    metadata: stripReasoningFields({
      action_taken: res.action_taken,
      action_result: res.action_result,
      sources: res.sources,
      retrieved_chunks: res.retrieved_chunks,
      chunk_scores: res.chunk_scores,
      confidence: res.confidence,
      evidence: res.evidence,
      execution_ms: res.execution_ms,
      execution_time_sec: res.execution_time_sec,
      trace_id: res.trace_id,
      timestamp: res.timestamp,
      cache: res.cache,
    }) as ChatMessageType['metadata'],
  };
}

export default function App() {
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    const loaded = loadSessions();
    if (loaded.length > 0 && loaded[0].messages.length === 0) {
      return loaded;
    }
    const fresh = newSession();
    return [fresh, ...loaded];
  });
  const [activeSessionId, setActiveSessionId] = useState<string>(
    () => sessions[0]?.session_id ?? '',
  );
  const { activePersona } = usePersona();
  const [busy, setBusy] = useState(false);
  const [pendingSessionId, setPendingSessionId] = useState<string | null>(null);
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
    onUpdate: (res) => {
      if (!isPendingApproval(res) && !isRunningExecution(res)) {
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
        (event) => setStreamingSteps((prev) => [...prev, event]),
      );
      setStreamingSteps([]);

      if (finalRes && !isRunningExecution(finalRes)) {
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
        // SSE ended without a terminal payload. Poll state without re-running actions.
        let res: RunResponse = await pollSessionStatus(sessionId);
        for (let attempt = 0; attempt < 4 && isRunningExecution(res); attempt += 1) {
          await new Promise((resolve) => window.setTimeout(resolve, 1_000));
          res = await pollSessionStatus(sessionId);
        }
        if (isRunningExecution(res)) {
          throw new ApiRequestError(
            'The response stream was interrupted. Your query is preserved; please retry.',
            503,
            'stream_interrupted',
          );
        }
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
        } else if (res && (res.answer || res.action_result || res.action_taken)) {
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
      if (e instanceof ApiRequestError) {
        if (e.status === 429) {
          errorMsg = 'Demo query limit reached. Please retry after the rate-limit window resets.';
        } else if (e.status === 400) {
          errorMsg = 'The security gateway rejected this prompt. Rephrase it as a legitimate support request.';
        } else if (e.status === 403) {
          errorMsg = 'This simulated persona does not have permission for that operation.';
        } else if (e.status === 503 || e.status === 504) {
          errorMsg = 'The AI or retrieval provider is temporarily unavailable. Your query remains in this chat.';
        } else {
          errorMsg = e.message;
        }
      } else if (axios.isAxiosError(e)) {
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
    (approvalId: string, decision: 'approve' | 'reject', agentResponse?: QueryResponse) => {
      const sessionId = pendingSessionId ?? activeSessionId;
      updateSession(sessionId, (s) => {
        const updatedMessages = s.messages.map((m) =>
          m.approval_id === approvalId
            ? { ...m, approval_state: decision === 'approve' ? ('approved' as const) : ('rejected' as const) }
            : m,
        );
        if (decision === 'reject') {
          return {
            ...s,
            messages: [
              ...updatedMessages,
              {
                id: crypto.randomUUID(),
                role: 'system' as const,
                content: 'Action rejected. The agent will not execute the requested operation.',
                timestamp: new Date().toISOString(),
              },
            ],
          };
        } else if (agentResponse) {
          return {
            ...s,
            messages: [...updatedMessages, queryResponseToMessage(agentResponse)],
          };
        }
        return {
          ...s,
          messages: updatedMessages,
        };
      });
      setPendingSessionId(null);
    },
    [pendingSessionId, activeSessionId, updateSession],
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
    }),
    [activePersona],
  );

  return (
    <div className="flex h-full w-full bg-black overflow-hidden">
      {/* Session Sidebar */}
      <SessionSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        isOpen={sidebarOpen}
        onToggleOpen={() => setSidebarOpen((prev) => !prev)}
        onSelectSession={(id) => setActiveSessionId(id)}
        onNewSession={createSession}
        onDeleteSession={deleteSession}
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
          streamingSteps={streamingSteps}
        />
      </main>
    </div>
  );
}
