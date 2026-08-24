import { AlertTriangle, Check, ChevronDown, ChevronRight, Clock, Code2, Copy, Loader2, Lock, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import Markdown from 'react-markdown';

import { fetchApprovalDetails, submitApprovalDecision } from '../services/api';
import type { ApprovalDetails, ApprovalState, QueryResponse } from '../types/agent';
import { usePersona } from '../context/PersonaContext';
import { formatReasoning } from '../lib/formatReasoning';

interface InlineApprovalCardProps {
  approvalId: string;
  state: ApprovalState;
  createdAt?: string;
  isExecuting?: boolean;
  onResolved: (approvalId: string, decision: 'approve' | 'reject', response?: QueryResponse) => void;
  onExpired?: (approvalId: string) => void;
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
  const { activePersona } = usePersona();
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
    let attempts = 0;

    const load = async () => {
      while (attempts < 3 && !cancelled) {
        try {
          attempts++;
          const d = await fetchApprovalDetails(approvalId);
          if (!cancelled) {
            setDetails(d);
            setError(null);
            return;
          }
        } catch (e: unknown) {
          if (cancelled) return;
          const msg = e instanceof Error ? e.message.toLowerCase() : '';
          if (attempts >= 3) {
            if (msg.includes('404') || msg.includes('not found')) {
              setIsExpired(true);
              onExpired?.(approvalId);
            } else {
              setError(e instanceof Error ? e.message : 'Error fetching approval details');
            }
          } else {
            await new Promise((r) => setTimeout(r, 1000));
          }
        }
      }
    };

    void load();

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
    if (decision === 'approve' && !activePersona.canApprove) {
      setError(`Access Denied: ${activePersona.label} cannot authorize operational execution.`);
      return;
    }
    setSubmitting(decision);
    setError(null);
    try {
      const res = await submitApprovalDecision(
        approvalId,
        decision,
        details.csrf_token,
        activePersona.role,
        activePersona.id,
      );
      onResolved(approvalId, decision, res.agent_response);
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

  const [ticketUser, setTicketUser] = useState('');
  const [ticketCategory, setTicketCategory] = useState('');
  const [ticketPriority, setTicketPriority] = useState('medium');
  const [ticketDescription, setTicketDescription] = useState('');

  useEffect(() => {
    if (details?.payload) {
      const p = details.payload as Record<string, string>;
      setTicketUser(p.user_name || p.user || 'Alice');
      setTicketCategory(p.category || 'Hardware');
      setTicketPriority((p.priority || 'medium').toLowerCase());
      setTicketDescription(p.description || '');
    }
  }, [details]);

  const isTicketAction = details?.action_name === 'create_ticket' || details?.action_name?.includes('ticket');

  return (
    <div className={`w-full rounded-2xl border backdrop-blur-xl p-4 shadow-2xl transition-all ${cardStateClass}`}>
      {/* Minimal Clean Header */}
      <div className="flex items-center justify-between border-b border-white/5 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-white tracking-wide">
              Action Approval Gate — {details?.action_name || 'Verification'}
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
          {/* Editable Ticket Creation Form (if create_ticket action) */}
          {isTicketAction && state === 'pending' && !isExpired && (
            <div className="rounded-xl border border-purple-500/30 bg-purple-950/20 p-3.5 space-y-2.5">
              <div className="flex items-center justify-between border-b border-purple-500/20 pb-1.5">
                <span className="text-[11px] font-black uppercase tracking-wider text-purple-300 font-mono">
                  🎫 Pre-Filled IT Ticket Details (Editable)
                </span>
                <span className="text-[10px] text-neutral-400">Extracted from prompt</span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <label className="block text-[10px] font-mono text-neutral-400 mb-1">Affected User</label>
                  <input
                    type="text"
                    value={ticketUser}
                    onChange={(e) => setTicketUser(e.target.value)}
                    className="w-full rounded-lg border border-neutral-700 bg-black/80 px-2.5 py-1 text-xs text-white focus:border-purple-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-mono text-neutral-400 mb-1">Category</label>
                  <input
                    type="text"
                    value={ticketCategory}
                    onChange={(e) => setTicketCategory(e.target.value)}
                    className="w-full rounded-lg border border-neutral-700 bg-black/80 px-2.5 py-1 text-xs text-white focus:border-purple-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <label className="block text-[10px] font-mono text-neutral-400 mb-1">Priority Level</label>
                  <select
                    value={ticketPriority}
                    onChange={(e) => setTicketPriority(e.target.value)}
                    className="w-full rounded-lg border border-neutral-700 bg-black/80 px-2.5 py-1 text-xs text-white focus:border-purple-500 focus:outline-none"
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] font-mono text-neutral-400 mb-1">Description</label>
                  <input
                    type="text"
                    value={ticketDescription}
                    onChange={(e) => setTicketDescription(e.target.value)}
                    className="w-full rounded-lg border border-neutral-700 bg-black/80 px-2.5 py-1 text-xs text-white focus:border-purple-500 focus:outline-none"
                  />
                </div>
              </div>
            </div>
          )}

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
        <div className="mt-4 flex flex-col gap-2.5">
          {!activePersona.canApprove && (
            <div className="flex items-center gap-2 p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-[11px] text-amber-300">
              <Lock size={14} className="shrink-0 text-amber-400" />
              <span>
                <strong>Clearance Required:</strong> Current persona (<em>{activePersona.label}</em>)
                cannot authorize operational execution. Switch to{' '}
                <strong>Incident Commander</strong> or <strong>Admin</strong> in the header to approve.
              </span>
            </div>
          )}

          <div className="flex items-center gap-2">
            <button
              disabled={!details || submitting !== null || !activePersona.canApprove}
              onClick={() => void decide('approve')}
              className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition-all shadow-lg ${
                activePersona.canApprove
                  ? 'bg-emerald-600 text-white hover:bg-emerald-500 active:scale-[0.98] shadow-emerald-950 cursor-pointer'
                  : 'bg-neutral-800 text-neutral-500 border border-neutral-700/50 cursor-not-allowed opacity-50'
              }`}
              title={
                activePersona.canApprove
                  ? 'Authorize execution of staged operational change'
                  : 'Insufficient clearance to authorize execution'
              }
            >
              {submitting === 'approve' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : activePersona.canApprove ? (
                <Check size={14} />
              ) : (
                <Lock size={14} />
              )}
              {activePersona.canApprove ? 'Authorize Execution' : 'Authorization Locked'}
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
