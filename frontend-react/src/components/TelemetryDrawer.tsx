import type { ChatMessage, UserRole } from '../types/agent';

interface TelemetryDrawerProps {
  message: ChatMessage | null;
  activeRole: UserRole;
  onClose: () => void;
}

export function TelemetryDrawer({ message, activeRole, onClose }: TelemetryDrawerProps) {
  const open = message !== null;
  const meta = message?.metadata;
  const telemetry = message?.telemetry;

  const traceId = meta?.trace_id || telemetry?.trace_id || 'N/A';
  const execMs = telemetry?.execution_ms ?? (meta?.execution_ms || (meta ? null : 'N/A'));
  const roleLabel = activeRole ? `${activeRole.label} (${activeRole.title})` : 'N/A';

  const chunks = meta?.retrieved_chunks || [];
  const chunkScores = telemetry?.chunk_scores || meta?.chunk_scores || chunks.map((c) => c.relevance_score || 0);
  const topScores = chunkScores.slice(0, 3);

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-black/70 backdrop-blur-md transition-opacity duration-300 ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
        onClick={onClose}
      />

      {/* Drawer Panel */}
      <div
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-neutral-800 bg-[#0d0d10] transition-transform duration-300 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {/* Drawer Header */}
        <div className="flex items-center justify-between border-b border-neutral-800 p-4">
          <div>
            <h3 className="text-sm font-black tracking-wide uppercase text-purple-400 font-mono flex items-center gap-2">
              🛡️ Security & Telemetry
            </h3>
            <p className="text-[10px] text-neutral-400">RBAC Clearance, Vector Scores & OpenTelemetry Tracing</p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close telemetry"
            className="rounded-xl border border-neutral-800 bg-neutral-900 px-3 py-1.5 text-xs font-semibold text-neutral-400 transition-all hover:bg-neutral-800 hover:text-white"
          >
            Close
          </button>
        </div>

        {/* Drawer Body */}
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5 text-xs">
          {/* Active Persona RBAC Clearance */}
          <section className="rounded-2xl border border-purple-500/20 bg-purple-950/20 p-4">
            <div className="text-[10px] font-black uppercase tracking-wider text-purple-400 font-mono mb-1">
              Active Persona Clearance
            </div>
            <div className="text-sm font-bold text-white">{roleLabel}</div>
            <div className="mt-1 text-[11px] text-neutral-400 font-mono">
              API Clearance Tier: <span className="text-purple-300">{activeRole.user_id}</span>
            </div>
          </section>

          {/* Execution Timing */}
          <section className="rounded-2xl border border-neutral-800 bg-black/60 p-4">
            <div className="text-[10px] font-black uppercase tracking-wider text-neutral-400 font-mono mb-1">
              Execution Duration
            </div>
            <div className="text-lg font-mono font-bold text-emerald-400">
              {execMs !== null && execMs !== undefined ? `${execMs} ms` : 'N/A'}
            </div>
          </section>

          {/* Chunk Relevance Scores */}
          <section className="rounded-2xl border border-neutral-800 bg-black/60 p-4">
            <div className="text-[10px] font-black uppercase tracking-wider text-neutral-400 font-mono mb-3">
              Top Vector Retrieval Scores (Qdrant)
            </div>
            {topScores.length === 0 ? (
              <div className="text-neutral-500 font-mono italic text-[11px]">N/A — No vector chunks retrieved</div>
            ) : (
              <div className="space-y-3">
                {topScores.map((score, i) => {
                  const pct = Math.min(100, Math.round(score * 100));
                  return (
                    <div key={i} className="space-y-1">
                      <div className="flex justify-between text-[11px] font-mono">
                        <span className="text-neutral-300">Chunk #{i + 1}</span>
                        <span className="text-purple-300 font-semibold">{score.toFixed(3)} ({pct}%)</span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-neutral-800 overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-purple-600 to-indigo-400 rounded-full transition-all duration-500"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* OpenTelemetry Trace ID */}
          <section className="rounded-2xl border border-neutral-800 bg-black/60 p-4">
            <div className="text-[10px] font-black uppercase tracking-wider text-neutral-400 font-mono mb-1">
              OpenTelemetry Trace ID
            </div>
            <p className="break-all font-mono text-[11px] text-purple-300 bg-neutral-900/80 rounded-lg p-2 border border-neutral-800">
              {traceId}
            </p>
          </section>
        </div>
      </div>
    </>
  );
}
