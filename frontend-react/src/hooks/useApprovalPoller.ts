import { useEffect, useRef } from 'react';

import { pollSessionStatus } from '../services/api';
import { isPendingApproval, type RunResponse } from '../types/agent';

const POLL_INTERVAL_MS = 3_000;
/** Match the HITL approval token TTL (15 minutes). */
const MAX_POLL_DURATION_MS = 15 * 60_000;
/** Maximum consecutive network/server errors before halting (15 seconds of errors). */
const MAX_CONSECUTIVE_ERRORS = 5;

interface UseApprovalPollerOptions {
  /** Session currently in `pending_approval` state, or null when idle. */
  pendingSessionId: string | null;
  apiKey: string;
  onUpdate: (response: RunResponse) => void;
  onTimeout: (reason?: string) => void;
}

/**
 * Automatically polls POST /v1/run every 3 seconds while a session is in
 * `pending_approval` state, pushing status updates to the chat as soon as the
 * graph resumes — no manual refresh required. Stops after 15 minutes or 5 consecutive errors.
 */
export function useApprovalPoller({
  pendingSessionId,
  apiKey,
  onUpdate,
  onTimeout,
}: UseApprovalPollerOptions): void {
  // Keep callbacks in refs so interval restarts only on session change.
  const onUpdateRef = useRef(onUpdate);
  const onTimeoutRef = useRef(onTimeout);
  onUpdateRef.current = onUpdate;
  onTimeoutRef.current = onTimeout;

  useEffect(() => {
    if (!pendingSessionId) return;

    let consecutiveErrors = 0;
    const startedAt = Date.now();
    const timer = setInterval(() => {
      if (Date.now() - startedAt > MAX_POLL_DURATION_MS) {
        clearInterval(timer);
        onTimeoutRef.current('Security authorization request timed out after 15 minutes.');
        return;
      }
      pollSessionStatus(pendingSessionId, apiKey)
        .then((res) => {
          consecutiveErrors = 0;
          if (!isPendingApproval(res)) {
            clearInterval(timer);
            onUpdateRef.current(res);
          }
        })
        .catch((e: Error) => {
          consecutiveErrors++;
          if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
            clearInterval(timer);
            onTimeoutRef.current(
              e?.message || 'Execution status polling disconnected due to backend errors.'
            );
          }
        });
    }, POLL_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [pendingSessionId, apiKey]);
}
