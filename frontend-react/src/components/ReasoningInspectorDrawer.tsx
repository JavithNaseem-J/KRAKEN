import Markdown from 'react-markdown';
import type { ChatMessage } from '../types/agent';

interface ReasoningInspectorDrawerProps {
  message: ChatMessage | null;
  onClose: () => void;
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

export function ReasoningInspectorDrawer({ message, onClose }: ReasoningInspectorDrawerProps) {
  const open = message !== null;
  const meta = message?.metadata;

  const chunks = meta?.retrieved_chunks || [];
  const actionTaken = meta?.action_taken;
  const isAutoRespond = !actionTaken || actionTaken === 'auto_respond';

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
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col border-l border-neutral-800 bg-[#111113] transition-transform duration-300 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {/* Drawer Header */}
        <div className="flex items-center justify-between border-b border-neutral-800 p-4">
          <div>
            <h3 className="text-sm font-black tracking-wide uppercase text-white font-mono">
              Reasoning Inspector
            </h3>
            <p className="text-[10px] text-neutral-400">Autonomous LLM Audit Trail & Evidence Citations</p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close inspector"
            className="rounded-xl border border-neutral-800 bg-neutral-900 px-3 py-1.5 text-xs font-semibold text-neutral-400 transition-all hover:bg-neutral-800 hover:text-white"
          >
            Close
          </button>
        </div>

        {/* Drawer Content */}
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          {meta?.trace_id && (
            <section className="rounded-2xl border border-neutral-800 bg-black/50 p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[10px] font-black uppercase tracking-wider text-purple-400 font-mono">
                  Execution Trace ID
                </span>
                <a
                  href={`http://localhost:8006/audit/events/${meta.trace_id}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-full border border-purple-500/30 bg-purple-500/10 px-2.5 py-0.5 text-[10px] font-mono font-medium text-purple-300 hover:bg-purple-500/20 hover:text-white transition-colors"
                >
                  <span>Audit Service</span>
                </a>
              </div>
              <p className="break-all font-mono text-xs text-neutral-300">{meta.trace_id}</p>
            </section>
          )}

          <section className="rounded-2xl border border-neutral-800 bg-black/50 p-4">
            <div className="mb-2 text-purple-400 border-b border-purple-500/20 pb-1">
              <h4 className="text-xs font-black uppercase tracking-wider font-mono">Step-by-Step Reasoning</h4>
            </div>
            <div className="prose prose-invert prose-xs max-w-none break-words text-neutral-300 leading-relaxed font-sans">
              {meta?.reasoning ? (
                <Markdown
                  components={{
                    h4({ children }) {
                      return (
                        <h4 className="text-xs font-black uppercase tracking-widest text-purple-300 mt-4 mb-2 border-b border-purple-500/30 pb-1 font-mono">
                          {children}
                        </h4>
                      );
                    },
                    p({ children }) {
                      return (
                        <p className="text-justify leading-relaxed text-[11px] text-neutral-300 mb-2 font-sans">
                          {children}
                        </p>
                      );
                    },
                    strong({ children }) {
                      return <strong className="font-bold text-white">{children}</strong>;
                    },
                    li({ children }) {
                      return (
                        <li className="text-justify leading-relaxed text-[11px] text-neutral-300 my-1 font-sans">
                          {children}
                        </li>
                      );
                    },
                  }}
                >
                  {formatReasoning(meta.reasoning)}
                </Markdown>
              ) : (
                <span className="text-neutral-500 italic">No step-by-step reasoning available.</span>
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-neutral-800 bg-black/50 p-4">
            <div className="mb-2 flex items-center justify-between border-b border-neutral-800 pb-2">
              <span className="text-xs font-black uppercase tracking-wider text-white font-mono">
                Action Executed
              </span>
              <span className="inline-flex items-center gap-1 rounded-full border border-purple-500/40 bg-purple-500/10 px-2.5 py-0.5 font-mono text-xs font-bold text-purple-300">
                {isAutoRespond ? 'Direct Knowledge Answer' : actionTaken}
              </span>
            </div>
            {!isAutoRespond && meta?.action_result != null && (
              <div className="mt-3">
                <span className="text-[10px] font-black uppercase tracking-wider text-neutral-400 font-mono">
                  Execution Output / Payload
                </span>
                <pre className="mt-1.5 max-h-56 overflow-auto rounded-xl border border-neutral-800 bg-black p-3 font-mono text-xs text-emerald-400">
                  {typeof meta.action_result === 'string'
                    ? meta.action_result
                    : JSON.stringify(meta.action_result, null, 2)}
                </pre>
              </div>
            )}
          </section>

          <section className="rounded-2xl border border-neutral-800 bg-black/50 p-4">
            <div className="mb-2 text-emerald-400 border-b border-emerald-500/20 pb-1">
              <h4 className="text-xs font-black uppercase tracking-wider font-mono">
                Verified Knowledge & Policy Citations
              </h4>
            </div>
            {isAutoRespond ? (
              chunks.length > 0 ? (
                <div className="space-y-3 mt-3">
                  {chunks.map((chunk, i) => {
                    const scorePct = Math.round((chunk.relevance_score || 0) * 100);
                    const isHighMatch = scorePct >= 85;
                    const isModMatch = scorePct >= 70 && scorePct < 85;

                    return (
                      <div
                        key={`${chunk.chunk_id || i}`}
                        className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs text-neutral-200 space-y-2"
                      >
                        <div className="flex items-center justify-between border-b border-emerald-500/10 pb-1.5">
                          <div className="flex items-center gap-2">
                            <span className="rounded bg-emerald-500/20 px-2 py-0.5 font-mono text-[10px] font-bold uppercase text-emerald-300">
                              {chunk.source}
                            </span>
                            {chunk.document_id && (
                              <span className="font-mono text-[10px] font-semibold text-neutral-300">
                                Doc: {chunk.document_id}
                              </span>
                            )}
                          </div>
                          <span
                            className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded-full ${
                              isHighMatch
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : isModMatch
                                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                                : 'bg-neutral-800 text-neutral-400'
                            }`}
                          >
                            {scorePct}% Match
                          </span>
                        </div>
                        <p className="whitespace-pre-wrap text-justify font-sans text-xs leading-relaxed text-neutral-200 bg-black/40 p-2.5 rounded-lg border border-neutral-800">
                          {chunk.content}
                        </p>
                      </div>
                    );
                  })}
                </div>
              ) : meta?.sources && meta.sources.length > 0 ? (
                <ul className="space-y-2 mt-3">
                  {meta.sources.map((src, i) => (
                    <li
                      key={`${src}-${i}`}
                      className="flex items-start gap-2.5 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs text-neutral-200"
                    >
                      <span className="break-all font-mono text-emerald-300">{src}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="rounded-xl border border-neutral-800/80 bg-neutral-900/50 p-3 text-center text-xs text-neutral-400 mt-2 font-sans italic">
                  No external knowledge documents were cited for this response.
                </div>
              )
            ) : (
              <div className="rounded-xl border border-neutral-800/80 bg-neutral-900/50 p-3 text-center text-xs text-neutral-400 mt-2 font-sans italic">
                No RAG knowledge citations required for direct action execution ({actionTaken}).
              </div>
            )}
          </section>

          {meta?.timestamp && (
            <div className="text-[11px] text-neutral-500 px-1 font-mono">
              <span>Completed at {new Date(meta.timestamp).toLocaleString()}</span>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
