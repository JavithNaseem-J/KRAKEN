/**
 * TypeScript contracts mirroring the KRAKEN backend data models.
 *
 * - QueryResponse    ← shared/models/agent.py :: QueryResponse (orchestrator /run)
 * - PendingApproval  ← orchestrator /run HITL pause payload
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

export interface CacheMetadata {
  hit: boolean;
  scope: string;
  knowledge_version: string | null;
  embedding_model: string | null;
}

/** Successful agent execution response from POST /v1/run. */
export interface QueryResponse {
  session_id: string;
  answer: string;
  action_taken: string | null;
  action_result: unknown | null;
  sources: string[];
  retrieved_chunks?: RetrievedChunk[];
  chunk_scores?: number[];
  execution_ms?: number | null;
  confidence?: number | null;
  evidence?: string[];
  execution_time_sec?: number | null;
  timestamp: string;
  trace_id: string | null;
  cache: CacheMetadata;
}

/** HITL pause payload returned by POST /v1/run while awaiting approval. */
export interface PendingApproval {
  status: 'pending_approval';
  approval_id: string;
  session_id: string;
  message: string;
}

export interface RunningExecution {
  status: 'running';
  session_id: string;
}

/** Union of all possible POST /v1/run response shapes. */
export type RunResponse = QueryResponse | PendingApproval | RunningExecution;

/** Type guard: does this /v1/run response represent a pending HITL approval? */
export function isPendingApproval(res: RunResponse): res is PendingApproval {
  return (res as PendingApproval).status === 'pending_approval';
}

export function isRunningExecution(res: RunResponse): res is RunningExecution {
  return (res as RunningExecution).status === 'running';
}

/** Parsed details of a pending approval (fetched from the Approval Service). */
export interface ApprovalDetails {
  approval_id: string;
  action_name: string;
  risk_level: 'CRITICAL' | 'SAFE';
  approval_reason: string;
  payload: Record<string, unknown>;
  session_id: string;
  status: string;
  created_at?: string;
  initiator_id: string;
  initiator_role: string;
  csrf_token: string;
}

export type ChatMessageRole = 'user' | 'assistant' | 'system';

export type ApprovalState = 'pending' | 'approved' | 'rejected' | 'expired';

export interface ResponseMetadata {
  action_taken: string | null;
  action_result: unknown | null;
  sources: string[];
  retrieved_chunks?: RetrievedChunk[];
  chunk_scores?: number[];
  confidence?: number | null;
  evidence?: string[];
  execution_ms?: number | null;
  execution_time_sec?: number | null;
  trace_id: string | null;
  timestamp: string;
  cache: CacheMetadata;
}

/** A single entry in the chat stream. */
export interface ChatMessage {
  id: string;
  role: ChatMessageRole;
  content: string;
  timestamp: string;
  /** Safe response evidence and operational metadata. */
  metadata?: ResponseMetadata;
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
}
