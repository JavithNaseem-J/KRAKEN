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

const GATEWAY_URL = (
  import.meta.env.VITE_GATEWAY_URL ??
  import.meta.env.VITE_API_URL ??
  'http://localhost:8000'
).replace(/\/$/, '');
const APPROVAL_URL = (
  import.meta.env.VITE_APPROVAL_URL ??
  import.meta.env.VITE_API_URL ??
  'http://localhost:8004'
).replace(/\/$/, '');

function gatewayClient(apiKey: string): AxiosInstance {
  return axios.create({
    baseURL: GATEWAY_URL,
    timeout: 120_000,
    headers: {
      'X-API-Key': apiKey,
      'Content-Type': 'application/json',
    },
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
): Promise<RunResponse> {
  const { data } = await gatewayClient(apiKey).post<RunResponse>('/v1/run', {
    message,
    session_id: sessionId,
  });
  return data;
}

/** Convenience wrapper: poll current execution status of a session. */
export async function pollSessionStatus(
  sessionId: string,
  apiKey: string,
): Promise<RunResponse> {
  return runAgentQuery('', sessionId, apiKey);
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
): Promise<{ session_id: string }> {
  const body = new URLSearchParams({ decision, csrf_token: csrfToken });
  const { data: html } = await approvalClient.post<string>(
    `/approve/${approvalId}/decision`,
    body,
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, responseType: 'text' },
  );

  const sessionMatch = html.match(/session[_-]id["'\s:>=]+([0-9a-fA-F-]{36})/);
  return { session_id: sessionMatch ? sessionMatch[1] : '' };
}

export type { PendingApproval, QueryResponse, RunResponse };
