/**
 * TypeScript contracts mirroring the KRAKEN backend data models.
 *
 * - QueryResponse    ← shared/models/agent.py :: QueryResponse (orchestrator /run)
 * - PendingApproval  ← orchestrator /run HITL pause payload
 * - AgentMetadata    ← reasoning/trace metadata attached to assistant messages
 * - ChatMessage      ← UI-level chat stream entry
 */

export interface RetrievedChunk {
  chunk_id?: string;
  source: string;
  document_id?: string;
  content: string;
  relevance_score: number;
  metadata?: Record<string, unknown>;
}

/** Successful agent execution response from POST /v1/run. */
export interface QueryResponse {
  session_id: string;
  answer: string;
  reasoning: string;
  action_taken: string | null;
  action_result: unknown | null;
  sources: string[];
  retrieved_chunks?: RetrievedChunk[];
  confidence?: number | null;
  evidence?: string[];
  execution_time_sec?: number | null;
  timestamp: string;
  trace_id: string | null;
}

/** HITL pause payload returned by POST /v1/run while awaiting approval. */
export interface PendingApproval {
  status: 'pending_approval';
  approval_id: string;
  session_id: string;
  message: string;
}

/** Union of all possible POST /v1/run response shapes. */
export type RunResponse = QueryResponse | PendingApproval;

/** Type guard: does this /v1/run response represent a pending HITL approval? */
export function isPendingApproval(res: RunResponse): res is PendingApproval {
  return (res as PendingApproval).status === 'pending_approval';
}

/** Parsed details of a pending approval (fetched from the Approval Service). */
export interface ApprovalDetails {
  approval_id: string;
  action_name: string;
  risk_level: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  reasoning: string;
  payload: Record<string, unknown>;
  csrf_token: string;
}

/** Reasoning/trace metadata attached to a completed assistant message. */
export interface AgentMetadata {
  reasoning: string;
  action_taken: string | null;
  action_result: unknown | null;
  sources: string[];
  retrieved_chunks?: RetrievedChunk[];
  trace_id: string | null;
  timestamp: string;
}

export type ChatMessageRole = 'user' | 'assistant' | 'system';

export type ApprovalState = 'pending' | 'approved' | 'rejected' | 'expired';

/** A single entry in the chat stream. */
export interface ChatMessage {
  id: string;
  role: ChatMessageRole;
  content: string;
  timestamp: string;
  /** Present on completed assistant responses. */
  metadata?: AgentMetadata;
  /** Present when the message represents a HITL approval request. */
  approval_id?: string;
  approval_state?: ApprovalState;
  approval_details?: ApprovalDetails;
}

/** A persisted chat session/thread. */
export interface ChatSession {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

/** Selectable user roles for the multi-role user switcher. */
export interface UserRole {
  user_id: string;
  label: string;
  title: string;
  api_key: string;
}
