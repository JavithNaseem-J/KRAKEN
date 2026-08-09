import { AlertTriangle, Check, ChevronDown, ChevronRight, Clock, Code2, Copy, Loader2, Lock, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import Markdown from 'react-markdown';

import { fetchApprovalDetails, submitApprovalDecision } from '../services/api';
import type { ApprovalDetails, ApprovalState } from '../types/agent';

interface InlineApprovalCardProps {
  approvalId: string;
  state: ApprovalState;
  createdAt?: string;
  isExecuting?: boolean;
  onResolved: (approvalId: string, decision: 'approve' | 'reject') => void;
  onExpired?: (approvalId: string) => void;
}

function formatReasoning(text: string): string {
  if (!text) return '';
  return text
    .replace(/(?:###|\*\*|#)*\s*(RELEVANT INFORMATION|GAPS OR CONFLICTS|CONCLUSION):?\s*(?:\*\*|#)*/gi, '\n\n#### **$1**\n\n')
    .replace(/(?:^|\n)\s*[•\*]\s*/g, '\n- ')
    .replace(/([^\n])\s*•\s*/g, '$1\n- ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function formatCountdown(seconds: number): string {
  if (seconds <= 0) return '00:00';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

export function InlineApprovalCard({
  approvalId,
  state,
  createdAt,
  isExecuting,
  onResolved,
  onExpired,
}: InlineApprovalCardProps) {
  const [details, setDetails] = useState<ApprovalDetails | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<'approve' | 'reject' | null>(null);
  const [showPayload, setShowPayload] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState<number>(900); // 15 minutes default
  const [isExpired, setIsExpired] = useState<boolean>(state === 'expired');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (state !== 'pending') {
      if (state === 'expired') setIsExpired(true);
      return;
    }

    let cancelled = false;
    fetchApprovalDetails(approvalId)
      .then((d) => {
        if (!cancelled) setDetails(d);
      })
      .catch((e: Error) => {
        if (!cancelled) {
          const msg = e.message.toLowerCase();
          if (msg.includes('404') || msg.includes('not found')) {
            setIsExpired(true);
            onExpired?.(approvalId);
          } else {
            setError(e.message);
          }
        }
      });

    return () => {
      cancelled = true;
    };
  }, [approvalId, state, onExpired]);

  // Live 1-second countdown timer
  useEffect(() => {
    if (state !== 'pending' || isExpired) return;

    const baseTime = createdAt ? new Date(createdAt).getTime() : Date.now();
    const expiresAtMs = baseTime + 15 * 60 * 1000;

    const updateTimer = () => {
      const diffSec = Math.max(0, Math.floor((expiresAtMs - Date.now()) / 1000));
      setRemainingSeconds(diffSec);
      if (diffSec <= 0) {
        setIsExpired(true);
        onExpired?.(approvalId);
      }
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [state, createdAt, isExpired, approvalId, onExpired]);

  const decide = async (decision: 'approve' | 'reject') => {
    if (!details || submitting || isExpired) return;
    setSubmitting(decision);
    setError(null);
    try {
      await submitApprovalDecision(approvalId, decision, details.csrf_token);
      onResolved(approvalId, decision);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to submit decision.');
      setSubmitting(null);
    }
  };

  const copyId = () => {
    void navigator.clipboard.writeText(approvalId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const cardStateClass =
    isExpired || state === 'expired'
      ? 'border-neutral-800 border-l-4 border-l-neutral-600 bg-neutral-900/60'
      : state === 'approved'
      ? 'border-neutral-800 border-l-4 border-l-emerald-500 bg-neutral-900/95'
      : state === 'rejected'
      ? 'border-neutral-800 border-l-4 border-l-red-500 bg-neutral-900/95'
      : 'border-neutral-800 border-l-4 border-l-amber-500 bg-neutral-900/95';

  return (
    <div className={`w-full rounded-2xl border backdrop-blur-xl p-4 shadow-2xl transition-all ${cardStateClass}`}>
      {/* Minimal Clean Header */}
      <div className="flex items-center justify-between border-b border-white/5 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-white tracking-wide">
              Action Approval Gate
            </span>
          </div>
          <p className="text-[11px] text-neutral-400 mt-0.5">
            Security clearance required before proceeding
          </p>
        </div>

        {/* Remaining Time Countdown Badge */}
        {state === 'pending' && !isExpired && (
          <div className="flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 font-mono text-xs font-semibold text-amber-300">
            <Clock size={13} className="animate-pulse text-amber-400" />
            <span>Expires in {formatCountdown(remainingSeconds)}</span>
          </div>
        )}
      </div>

      {state === 'pending' && !details && !error && !isExpired && (
        <div className="flex items-center justify-center gap-2 py-6 text-xs text-neutral-400">
          <Loader2 size={15} className="animate-spin text-amber-400" />
          Loading request details…
        </div>
      )}

      {error && (
        <div className="mt-3 flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
          <AlertTriangle size={14} className="text-red-400" />
          <span>{error}</span>
        </div>
      )}

      {details && (
        <div className="mt-3 space-y-3">
          {/* Agent Reasoning */}
          <div className="rounded-xl border border-white/5 bg-black/50 p-3 text-xs text-neutral-300 leading-relaxed">
            <span className="text-[10px] font-bold text-neutral-400 uppercase tracking-wider block mb-1">
              Agent Justification & Context
            </span>
            <div className="text-xs text-neutral-300 leading-relaxed">
              <Markdown
                components={{
                  h4({ children }) {
                    return (
                      <h4 className="text-[11px] font-black uppercase tracking-widest text-purple-300 mt-2 mb-1 border-b border-purple-500/30 pb-0.5 font-mono">
                        {children}
                      </h4>
                    );
                  },
                  p({ children }) {
                    return (
                      <p className="text-justify leading-relaxed text-neutral-200 mb-1 font-sans">
                        {children}
                      </p>
                    );
                  },
                  strong({ children }) {
                    return <strong className="font-black text-white">{children}</strong>;
                  },
                  li({ children }) {
                    return (
                      <li className="text-justify leading-relaxed text-neutral-200 my-0.5 font-sans">
                        {children}
                      </li>
                    );
                  },
                }}
              >
                {formatReasoning(details.reasoning)}
              </Markdown>
            </div>
          </div>

          {/* Collapsible Payload Toggle */}
          <div className="rounded-xl border border-white/5 bg-black/50 overflow-hidden">
            <button
              onClick={() => setShowPayload((prev) => !prev)}
              className="w-full flex items-center justify-between p-2.5 text-xs text-neutral-400 hover:text-white transition-colors"
            >
              <span className="flex items-center gap-1.5 font-mono text-[11px]">
                <Code2 size={13} className="text-purple-400" />
                Inspect Action Payload ({Object.keys(details.payload || {}).length} fields)
              </span>
              {showPayload ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>

            {showPayload && (
              <pre className="border-t border-white/5 bg-black p-3 font-mono text-[11px] text-emerald-400 overflow-x-auto max-h-48">
                {JSON.stringify(details.payload, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}

      {/* Active Decision Buttons */}
      {state === 'pending' && !isExpired && (
        <div className="mt-4 flex items-center gap-2">
          <button
            disabled={!details || submitting !== null}
            onClick={() => void decide('approve')}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-500 transition-all active:scale-[0.98] disabled:opacity-40 shadow-lg shadow-emerald-950"
          >
            {submitting === 'approve' ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Check size={14} />
            )}
            Authorize Execution
          </button>
          <button
            disabled={!details || submitting !== null}
            onClick={() => void decide('reject')}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-neutral-700 bg-neutral-800 px-4 py-2 text-xs font-bold text-neutral-300 hover:bg-neutral-700 hover:text-white transition-all active:scale-[0.98] disabled:opacity-40"
          >
            {submitting === 'reject' ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <X size={14} />
            )}
            Deny Request
          </button>
        </div>
      )}

      {/* Completed / Expired Status Banner */}
      {(state !== 'pending' || isExpired) && (
        <div className="mt-3 flex items-center justify-between rounded-xl border border-white/5 bg-black/40 px-3 py-2 text-xs">
          <span className="text-neutral-400">Security Gate Status:</span>
          <span
            className={`font-bold font-mono inline-flex items-center gap-1.5 ${
              state === 'approved'
                ? 'text-emerald-400'
                : state === 'rejected'
                ? 'text-red-400'
                : 'text-neutral-400'
            }`}
          >
            {state === 'approved' ? (
              isExecuting ? (
                <>
                  <Loader2 size={13} className="animate-spin text-emerald-400" />
                  <span>APPROVED & EXECUTING…</span>
                </>
              ) : (
                <>
                  <Check size={13} />
                  <span>APPROVED & EXECUTED</span>
                </>
              )
            ) : state === 'rejected' ? (
              <>
                <X size={13} />
                <span>REJECTED</span>
              </>
            ) : (
              <>
                <Lock size={13} />
                <span>AUTHORIZATION EXPIRED</span>
              </>
            )}
          </span>
        </div>
      )}

      <div className="mt-2.5 flex items-center justify-between text-[10px] font-mono text-neutral-400 px-0.5">
        <button
          onClick={copyId}
          title="Click to copy full Approval ID"
          className="inline-flex items-center gap-1.5 hover:text-white transition-colors"
        >
          <span>Ref: #{approvalId.slice(0, 8)}</span>
          {copied ? <Check size={10} className="text-emerald-400" /> : <Copy size={10} />}
        </button>
      </div>
    </div>
  );
}
