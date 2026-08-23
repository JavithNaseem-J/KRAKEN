/**
 * API client for the KRAKEN backend services.
 *
 * - Gateway  POST /v1/run                          (chat / status polling)
 * - Approval GET  /approve/{approval_id}           (details + CSRF token)
 * - Approval POST /approve/{approval_id}/decision  (inline HITL decision)
 */
import axios, { AxiosInstance } from 'axios';

import type {
  ApprovalDetails,
  PendingApproval,
  QueryResponse,
  RunResponse,
} from '../types/agent';

function getBaseUrl(envUrl: string | undefined, defaultLocal: string): string {
  const configured = envUrl?.trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  return defaultLocal.replace(/\/$/, '');
}

const GATEWAY_URL = getBaseUrl(
  import.meta.env.VITE_GATEWAY_URL || import.meta.env.VITE_API_URL,
  'http://localhost:8000',
);
const APPROVAL_URL = getBaseUrl(
  import.meta.env.VITE_APPROVAL_URL || import.meta.env.VITE_API_URL,
  GATEWAY_URL,
);

function gatewayClient(apiKey: string, operatorRole?: string, userId?: string): AxiosInstance {
  const headers: Record<string, string> = {
    'X-API-Key': apiKey,
    'Content-Type': 'application/json',
  };
  if (operatorRole) headers['X-Operator-Role'] = operatorRole;
  if (userId) headers['X-User-Id'] = userId;

  return axios.create({
    baseURL: GATEWAY_URL,
    timeout: 120_000,
    headers,
  });
}

const approvalClient: AxiosInstance = axios.create({
  baseURL: APPROVAL_URL,
  timeout: 30_000,
});

/**
 * Submit a query (or empty-message status poll) to the Gateway.
 * Returns either a completed QueryResponse or a PendingApproval payload.
 */
export async function runAgentQuery(
  message: string,
  sessionId: string,
  apiKey: string,
  operatorRole?: string,
  userId?: string,
): Promise<RunResponse> {
  const { data } = await gatewayClient(apiKey, operatorRole, userId).post<RunResponse>('/v1/run', {
    message,
    session_id: sessionId,
  });
  return data;
}

/** Convenience wrapper: poll current execution status of a session. */
export async function pollSessionStatus(
  sessionId: string,
  apiKey: string,
  operatorRole?: string,
  userId?: string,
): Promise<RunResponse> {
  return runAgentQuery('', sessionId, apiKey, operatorRole, userId);
}

/** Upload a document file dynamically into the knowledge vector store. */
export async function uploadKnowledgeDocument(
  file: File,
  apiKey: string,
  allowedRoles: string = 'public',
): Promise<{ status: string; filename: string; chunks_ingested: number }> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('allowed_roles', allowedRoles);

  const { data } = await axios.post<{ status: string; filename: string; chunks_ingested: number }>(
    `${GATEWAY_URL}/v1/knowledge/upload`,
    formData,
    {
      headers: {
        'X-API-Key': apiKey,
        'Content-Type': 'multipart/form-data',
      },
    },
  );
  return data;
}

/**
 * Fetch pending approval details (action name, reasoning, payload) and the
 * CSRF token required to submit a decision. Parsed from the Approval Service
 * HTML page, which is the canonical source of this data.
 */
export async function fetchApprovalDetails(approvalId: string): Promise<ApprovalDetails> {
  const { data } = await approvalClient.get<{
    approval_id: string;
    action_name: string;
    payload: Record<string, unknown>;
    reasoning: string;
    session_id: string;
    status: string;
    created_at?: string;
    csrf_token: string;
  }>(`/approve/${approvalId}/details`);

  return {
    approval_id: data.approval_id,
    action_name: data.action_name || 'Unknown action',
    risk_level: 'CRITICAL',
    reasoning: data.reasoning || 'No reasoning provided.',
    payload: data.payload || {},
    csrf_token: data.csrf_token,
  };
}

/**
 * Submit an approve/reject decision for a pending approval.
 * Returns the session_id associated with the resolved approval.
 */
export async function submitApprovalDecision(
  approvalId: string,
  decision: 'approve' | 'reject',
  csrfToken: string,
  approverRole?: string,
  approverId?: string,
): Promise<{ session_id: string }> {
  const params: Record<string, string> = { decision, csrf_token: csrfToken };
  if (approverRole) params['approver_role'] = approverRole;
  if (approverId) params['approver_id'] = approverId;

  const body = new URLSearchParams(params);
  const { data: html } = await approvalClient.post<string>(
    `/approve/${approvalId}/decision`,
    body,
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, responseType: 'text' },
  );

  const sessionMatch = html.match(/session[_-]id["'\s:>=]+([0-9a-fA-F-]{36})/);
  return { session_id: sessionMatch ? sessionMatch[1] : '' };
}

/** Shape of each SSE event streamed from /v1/run/stream */
export interface AgentStreamEvent {
  node: string;
  status: 'start' | 'end' | 'error' | 'pending_approval';
  elapsed_ms?: number;
  response?: RunResponse;
  message?: string;
}

/**
 * Stream agent query via SSE. Calls onEvent for each node step.
 * Returns the final RunResponse (from the done or pending_approval event payload, or undefined).
 */
export async function streamAgentQuery(
  message: string,
  sessionId: string,
  apiKey: string,
  onEvent: (event: AgentStreamEvent) => void,
  operatorRole?: string,
  userId?: string,
): Promise<RunResponse | undefined> {
  const reqHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-API-Key': apiKey,
  };
  if (operatorRole) reqHeaders['X-Operator-Role'] = operatorRole;
  if (userId) reqHeaders['X-User-Id'] = userId;

  const response = await fetch(`${GATEWAY_URL}/v1/run/stream`, {
    method: 'POST',
    headers: reqHeaders,
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`Stream request failed: ${response.status}`);
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
      if (line.startsWith('data: ')) {
        try {
          const event: AgentStreamEvent = JSON.parse(line.slice(6));
          onEvent(event);
          if (event.response) finalResponse = event.response;
        } catch {
          // ignore malformed SSE lines
        }
      }
    }
  }

  if (buffer.trim().startsWith('data: ')) {
    try {
      const event: AgentStreamEvent = JSON.parse(buffer.trim().slice(6));
      onEvent(event);
      if (event.response) finalResponse = event.response;
    } catch {
      // ignore malformed trailing line
    }
  }

  return finalResponse;
}

/** Export a session as a downloadable incident briefing PDF report. */
export async function exportSessionPDF(
  sessionId: string,
  messages: unknown[],
  persona: { label: string; title: string },
  apiKey: string,
): Promise<Blob> {
  const response = await fetch(`${GATEWAY_URL}/v1/report/export`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
    },
    body: JSON.stringify({ session_id: sessionId, messages, persona }),
  });

  if (!response.ok) {
    throw new Error(`PDF export failed with status ${response.status}`);
  }

  return await response.blob();
}

export type { PendingApproval, QueryResponse, RunResponse };
