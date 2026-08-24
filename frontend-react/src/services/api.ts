import axios from 'axios';

import type { PersonaRole } from '../context/PersonaContext';
import type {
  ApprovalDetails,
  PendingApproval,
  QueryResponse,
  RunResponse,
} from '../types/agent';

function getBaseUrl(envUrl: string | undefined): string {
  const configured = envUrl?.trim();
  if (!configured) return '';
  if (
    configured.startsWith('/') ||
    configured.startsWith('http://') ||
    configured.startsWith('https://')
  ) {
    return configured.replace(/\/$/, '');
  }
  return `https://${configured.replace(/\/$/, '')}`;
}

const API_URL = getBaseUrl(import.meta.env.VITE_API_URL);

export interface DemoSession {
  session_id: string;
  csrf_token: string;
  persona: PersonaRole;
  actor_id: string;
  expires_at: string;
  query_limit: number;
  write_limit: number;
  demo_mode: true;
}

let sessionPromise: Promise<DemoSession> | null = null;

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
  ) {
    super(message);
  }
}

export function bootstrapDemoSession(force = false): Promise<DemoSession> {
  if (!sessionPromise || force) {
    sessionPromise = axios
      .post<DemoSession>(`${API_URL}/v1/demo/session`, undefined, { withCredentials: true })
      .then(({ data }) => data)
      .catch((error) => {
        sessionPromise = null;
        throw error;
      });
  }
  return sessionPromise;
}

async function sessionHeaders(): Promise<Record<string, string>> {
  const session = await bootstrapDemoSession();
  return {
    'Content-Type': 'application/json',
    'X-CSRF-Token': session.csrf_token,
  };
}

export async function transitionPersona(persona: PersonaRole): Promise<DemoSession['persona']> {
  const session = await bootstrapDemoSession();
  const { data } = await axios.post<{ persona: DemoSession['persona'] }>(
    `${API_URL}/v1/demo/persona`,
    { persona, csrf_token: session.csrf_token },
    { withCredentials: true },
  );
  return data.persona;
}

export async function resetDemoSession(): Promise<DemoSession> {
  const current = await bootstrapDemoSession();
  const { data } = await axios.post<DemoSession>(
    `${API_URL}/v1/demo/session/reset`,
    { csrf_token: current.csrf_token },
    { withCredentials: true },
  );
  sessionPromise = Promise.resolve(data);
  return data;
}

export async function runAgentQuery(message: string, sessionId: string): Promise<RunResponse> {
  const { data } = await axios.post<RunResponse>(
    `${API_URL}/v1/run`,
    { message, session_id: sessionId },
    { headers: await sessionHeaders(), withCredentials: true, timeout: 120_000 },
  );
  return data;
}

export function pollSessionStatus(sessionId: string): Promise<RunResponse> {
  void sessionId;
  return axios
    .get<RunResponse>(`${API_URL}/v1/demo/status`, { withCredentials: true })
    .then(({ data }) => data);
}

export async function uploadKnowledgeDocument(
  file: File,
  allowedRoles = 'public',
): Promise<{ status: string; filename: string; chunks_ingested: number }> {
  const session = await bootstrapDemoSession();
  const formData = new FormData();
  formData.append('file', file);
  formData.append('allowed_roles', allowedRoles);
  const { data } = await axios.post<{
    status: string;
    filename: string;
    chunks_ingested: number;
  }>(`${API_URL}/v1/knowledge/upload`, formData, {
    withCredentials: true,
    headers: { 'X-CSRF-Token': session.csrf_token },
  });
  return data;
}

export async function fetchApprovalDetails(approvalId: string): Promise<ApprovalDetails> {
  const { data } = await axios.get<{
    approval_id: string;
    action_name: string;
    payload: Record<string, unknown>;
    reasoning: string;
    csrf_token: string;
  }>(`${API_URL}/approve/${approvalId}/details`, { withCredentials: true });
  return {
    approval_id: data.approval_id,
    action_name: data.action_name || 'Unknown action',
    risk_level: 'CRITICAL',
    reasoning: data.reasoning || 'No reasoning provided.',
    payload: data.payload || {},
    csrf_token: data.csrf_token,
  };
}

export async function submitApprovalDecision(
  approvalId: string,
  decision: 'approve' | 'reject',
  approvalCsrfToken: string,
): Promise<{ session_id: string; agent_response?: QueryResponse }> {
  const demo = await bootstrapDemoSession();
  const body = new URLSearchParams({
    decision,
    csrf_token: approvalCsrfToken,
    demo_csrf_token: demo.csrf_token,
  });
  const { data } = await axios.post<{
    session_id: string;
    agent_response?: QueryResponse;
  }>(`${API_URL}/approve/${approvalId}/decision`, body, {
    withCredentials: true,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return { session_id: data.session_id || '', agent_response: data.agent_response };
}

export interface AgentStreamEvent {
  node: string;
  status: 'start' | 'end' | 'error' | 'pending_approval' | 'cache_hit';
  elapsed_ms?: number;
  response?: RunResponse;
  message?: string;
}

export async function streamAgentQuery(
  message: string,
  sessionId: string,
  onEvent: (event: AgentStreamEvent) => void,
): Promise<RunResponse | undefined> {
  let response: Response | undefined;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    response = await fetch(`${API_URL}/v1/run/stream`, {
      method: 'POST',
      credentials: 'include',
      headers: await sessionHeaders(),
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    if (response.status === 401 && attempt === 0) {
      await bootstrapDemoSession(true);
      continue;
    }
    if (![502, 503, 504].includes(response.status) || attempt === 2) break;
    onEvent({
      node: 'backend_waking',
      status: 'start',
      message: 'The demo service is waking. Your query is preserved.',
    });
    await new Promise((resolve) => window.setTimeout(resolve, 1500 * (attempt + 1)));
  }
  if (!response) throw new ApiRequestError('Backend unavailable.', 503, 'backend_unavailable');
  if (!response.ok || !response.body) {
    let message = `Request failed with status ${response.status}.`;
    let code = 'request_failed';
    try {
      const body = await response.json();
      message = body.error || body.detail?.code || body.detail || message;
      code = body.code || body.detail?.code || code;
    } catch {
      // Keep the safe status-based message.
    }
    throw new ApiRequestError(message, response.status, code);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalResponse: RunResponse | undefined;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const event: AgentStreamEvent = JSON.parse(line.slice(6));
        onEvent(event);
        if (event.response) finalResponse = event.response;
      } catch {
        // A malformed provider event is skipped; the terminal event remains authoritative.
      }
    }
  }
  return finalResponse;
}

export async function exportSessionHTML(
  sessionId: string,
  messages: unknown[],
  persona: { label: string; title: string },
): Promise<Blob> {
  const response = await fetch(`${API_URL}/v1/report/export`, {
    method: 'POST',
    credentials: 'include',
    headers: await sessionHeaders(),
    body: JSON.stringify({ session_id: sessionId, messages, persona }),
  });
  if (!response.ok) throw new Error(`HTML export failed with status ${response.status}`);
  return response.blob();
}

export type { PendingApproval, QueryResponse, RunResponse };
