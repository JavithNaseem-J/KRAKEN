import { useState, useRef, useEffect, useCallback, KeyboardEvent } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ArrowUpIcon,
  Bot,
  Paperclip,
  Code2,
  Rocket,
  Loader2,
  FileText,
  Key,
  PanelLeftOpen,
} from "lucide-react";
import type { ChatMessage as ChatMessageType, UserRole } from "@/types/agent";
import type { AgentStreamEvent } from "@/services/api";
import { ChatMessage } from "@/components/ChatMessage";

interface AutoResizeProps {
  minHeight: number;
  maxHeight?: number;
}

function useAutoResizeTextarea({ minHeight, maxHeight }: AutoResizeProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(
    (reset?: boolean) => {
      const textarea = textareaRef.current;
      if (!textarea) return;

      if (reset) {
        textarea.style.height = `${minHeight}px`;
        return;
      }

      textarea.style.height = `${minHeight}px`; // reset first
      const newHeight = Math.max(
        minHeight,
        Math.min(textarea.scrollHeight, maxHeight ?? Infinity)
      );
      textarea.style.height = `${newHeight}px`;
    },
    [minHeight, maxHeight]
  );

  useEffect(() => {
    if (textareaRef.current) textareaRef.current.style.height = `${minHeight}px`;
  }, [minHeight]);

  return { textareaRef, adjustHeight };
}

interface RuixenMoonChatProps {
  disabled: boolean;
  onSend: (message: string) => void;
  messages: ChatMessageType[];
  activeRole: UserRole;
  pendingSessionId: string | null;
  activeSessionId: string;
  sessionTitle?: string;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  onApprovalResolved: (approvalId: string, decision: 'approve' | 'reject') => void;
  onApprovalExpired?: (approvalId: string) => void;
  onInspectReasoning: (message: ChatMessageType) => void;
  onInspectTelemetry?: (message: ChatMessageType) => void;
  streamingSteps?: AgentStreamEvent[];
}

export default function RuixenMoonChat({
  disabled,
  onSend,
  messages,
  activeRole,
  pendingSessionId,
  activeSessionId,
  sessionTitle,
  sidebarOpen,
  onToggleSidebar,
  onApprovalResolved,
  onApprovalExpired,
  onInspectReasoning,
  onInspectTelemetry,
  streamingSteps = [],
}: RuixenMoonChatProps) {
  const [message, setMessage] = useState("");
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: 48,
    maxHeight: 150,
  });

  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, disabled]);

  const handleSend = (textToSend?: string) => {
    const content = (textToSend ?? message).trim();
    if (!content || disabled) return;
    onSend(content);
    setMessage("");
    adjustHeight(true);
  };

  const handlePillClick = (promptText: string) => {
    setMessage(promptText);
    setTimeout(() => {
      adjustHeight();
      textareaRef.current?.focus();
    }, 0);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadNotice, setUploadNotice] = useState<string | null>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !activeRole) return;
    setIsUploading(true);
    setUploadNotice(null);
    try {
      const { uploadKnowledgeDocument } = await import("@/services/api");
      const userRole = activeRole.user_id === "alice" ? "tier1" : activeRole.user_id === "bob" ? "security_lead" : "public";
      const res = await uploadKnowledgeDocument(file, activeRole.api_key, userRole);
      setUploadNotice(`✅ Ingested ${res.filename} (${res.chunks_ingested} chunks)`);
    } catch (err: any) {
      setUploadNotice(`⚠️ Ingestion failed: ${err.message || 'Error uploading'}`);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const latestApprovalMsg = messages.slice().reverse().find((m) => m.approval_id);

  return (
    <div className="relative flex flex-col h-full w-full bg-black overflow-hidden font-sans select-none">
      {/* Background Ambience */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-neutral-900 via-black to-black opacity-80" />
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#1f1f1f10_1px,transparent_1px),linear-gradient(to_bottom,#1f1f1f10_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      {/* Header Bar */}
      <header className="relative z-20 flex h-14 w-full items-center justify-between border-b border-neutral-800/80 bg-black/60 backdrop-blur-xl px-4 md:px-6">
        <div className="flex items-center gap-3">
          {!sidebarOpen && (
            <button
              onClick={onToggleSidebar}
              aria-label="Open Sidebar"
              className="rounded-lg p-1.5 text-neutral-400 hover:bg-neutral-800 hover:text-white transition-colors"
            >
              <PanelLeftOpen size={18} />
            </button>
          )}

          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-purple-500 animate-pulse" />
            <span className="text-xs md:text-sm font-bold tracking-tight text-white">
              {sessionTitle || "KRAKEN Operations Console"}
            </span>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="relative z-10 w-full flex-1 min-h-0 flex flex-col items-center justify-between overflow-hidden">
        {/* Full-width scrollable viewport for far-right scrollbar track */}
        <div ref={scrollRef} className="w-full flex-1 min-h-0 overflow-y-auto px-4 md:px-6 py-4">
          {messages.length === 0 ? (
            <div className="h-full w-full flex flex-col items-center justify-center">
              <div className="text-center max-w-lg">
                <h1 className="text-4xl font-bold text-white drop-shadow-md tracking-tight">
                  KRAKEN
                </h1>
                <p className="mt-3 text-neutral-300 text-sm leading-relaxed drop-shadow-sm">
                  Autonomous Cyber Operations & Security Triage Platform. Enterprise AI assistant with integrated Human-in-the-Loop safety gates.
                </p>
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-6">
              {messages.map((m) => (
                <ChatMessage
                  key={m.id}
                  message={m}
                  isExecuting={
                    pendingSessionId === activeSessionId &&
                    m.approval_id === latestApprovalMsg?.approval_id &&
                    m.approval_state === 'approved'
                  }
                  onApprovalResolved={onApprovalResolved}
                  onApprovalExpired={onApprovalExpired}
                  onInspectReasoning={onInspectReasoning}
                  onInspectTelemetry={onInspectTelemetry}
                />
              ))}
              {disabled && (
                <div className="flex gap-3 my-2 justify-start">
                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl bg-purple-600/30 text-purple-300 ring-1 ring-purple-500/40">
                    <Bot size={15} />
                  </div>
                  <div className="group min-w-0 max-w-[80%] flex flex-col gap-1.5">
                    <div className="relative rounded-2xl px-4 py-3 text-xs md:text-sm bg-black/60 backdrop-blur-md text-neutral-200 rounded-tl-none border border-neutral-800 flex items-center gap-2.5">
                      <span className="font-medium text-neutral-300">Agent Processing</span>
                      <span className="flex items-end gap-0.5 pb-0.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-purple-400 animate-bounce [animation-delay:0ms]" />
                        <span className="h-1.5 w-1.5 rounded-full bg-purple-400 animate-bounce [animation-delay:150ms]" />
                        <span className="h-1.5 w-1.5 rounded-full bg-purple-400 animate-bounce [animation-delay:300ms]" />
                      </span>
                    </div>
                    {streamingSteps.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pl-1">
                        {streamingSteps
                          .filter((s) => s.status === 'start')
                          .filter((s) => {
                            const name = s.node.toLowerCase();
                            return !name.includes('runnable') && !name.includes('__') && name !== 'start' && name !== 'end';
                          })
                          .map((s, i) => {
                            const nodeLabels: Record<string, { icon: string; label: string }> = {
                              retriever: { icon: '🔍', label: 'Retrieving knowledge' },
                              reasoner: { icon: '🧠', label: 'Analyzing context' },
                              decider: { icon: '🛡️', label: 'Evaluating intent' },
                              executor: { icon: '⚙️', label: 'Executing action' },
                              memory_writer: { icon: '📝', label: 'Updating memory' },
                              responder: { icon: '💬', label: 'Generating response' },
                              route_after_decision: { icon: '🔀', label: 'Routing decision' },
                              _route_after_decision: { icon: '🔀', label: 'Routing decision' },
                            };
                            const rawNode = s.node.toLowerCase();
                            const meta = nodeLabels[rawNode] ?? {
                              icon: '●',
                              label: s.node.replace(/^_+/, '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
                            };
                            return (
                              <span
                                key={i}
                                className="inline-flex items-center gap-1 rounded-full bg-purple-900/40 border border-purple-500/30 px-2.5 py-0.5 text-[11px] text-purple-300 font-medium animate-pulse"
                              >
                                <span>{meta.icon}</span>
                                <span>{meta.label}</span>
                                {s.elapsed_ms !== undefined && (
                                  <span className="text-purple-500 ml-0.5">{s.elapsed_ms}ms</span>
                                )}
                              </span>
                            );
                          })}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Input Box Section */}
        <div className="w-full max-w-3xl px-4 md:px-0 mb-4">
          <div className="relative bg-black/75 backdrop-blur-xl rounded-2xl border border-neutral-700/80 shadow-2xl">
            <Textarea
              ref={textareaRef}
              value={message}
              onChange={(e) => {
                setMessage(e.target.value);
                adjustHeight();
              }}
              onKeyDown={onKeyDown}
              disabled={disabled}
              placeholder={disabled ? "Agent processing…" : "Type your security or helpdesk query..."}
              className={cn(
                "w-full px-4 py-3.5 resize-none border-none",
                "bg-transparent text-white text-sm",
                "focus-visible:ring-0 focus-visible:ring-offset-0",
                "placeholder:text-neutral-400 min-h-[48px]"
              )}
              style={{ overflow: "hidden" }}
            />

            {/* Hidden File Input for Knowledge Ingestion */}
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".pdf,.docx,.md,.txt"
              className="hidden"
            />

            {/* Footer Buttons */}
            <div className="flex items-center justify-between p-3 border-t border-white/5">
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={disabled || isUploading}
                  className="text-neutral-400 hover:text-white hover:bg-neutral-800/80 rounded-xl"
                  title="Attach document (.pdf, .docx, .md, .txt) for Knowledge Base ingestion"
                >
                  {isUploading ? <Loader2 className="w-4 h-4 animate-spin text-purple-400" /> : <Paperclip className="w-4 h-4" />}
                </Button>
                {uploadNotice && (
                  <span className="text-[11px] font-mono text-purple-300 bg-purple-950/40 border border-purple-800/50 px-2.5 py-1 rounded-md">
                    {uploadNotice}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                <Button
                  onClick={() => handleSend()}
                  disabled={disabled || !message.trim()}
                  className={cn(
                    "flex items-center gap-1 px-4 py-2 rounded-xl font-medium transition-all shadow-md",
                    disabled || !message.trim()
                      ? "bg-neutral-800 text-neutral-500 cursor-not-allowed"
                      : "bg-purple-600 hover:bg-purple-500 text-white shadow-purple-600/40 hover:shadow-lg"
                  )}
                >
                  {disabled ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <ArrowUpIcon className="w-4 h-4" />
                  )}
                  <span className="text-xs">Send</span>
                </Button>
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="flex items-center justify-center flex-wrap gap-2.5 mt-4">
            <QuickAction
              icon={<FileText className="w-3.5 h-3.5 text-purple-400" />}
              label="SLA Guidelines"
              onClick={() => handlePillClick("What is the SLA for critical security vulnerabilities?")}
            />
            <QuickAction
              icon={<Key className="w-3.5 h-3.5 text-sky-400" />}
              label="VPN Connection"
              onClick={() => handlePillClick("How do I connect to the corporate VPN?")}
            />
            <QuickAction
              icon={<Rocket className="w-3.5 h-3.5 text-emerald-400" />}
              label="Ticket T-1001 Status"
              onClick={() => handlePillClick("What is the status of ticket T-1001?")}
            />
            <QuickAction
              icon={<Code2 className="w-3.5 h-3.5 text-amber-400" />}
              label="Create IT Ticket"
              onClick={() => handlePillClick("Create an IT ticket for a broken monitor replacement for user Alice.")}
            />
          </div>

          {/* Caution / Disclaimer Footer */}
          <div className="mt-3.5 text-center px-4">
            <p className="text-[11px] font-mono tracking-tight text-neutral-400/90 leading-relaxed">
              KRAKEN can make mistakes. Verify important security information.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

interface QuickActionProps {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}

function QuickAction({ icon, label, onClick }: QuickActionProps) {
  return (
    <Button
      variant="outline"
      onClick={onClick}
      className="flex items-center gap-2 rounded-full border-neutral-700/80 bg-black/60 backdrop-blur-md text-neutral-300 hover:text-white hover:bg-neutral-800/80 hover:border-neutral-500 transition-all text-xs py-1 px-3.5 h-auto"
    >
      {icon}
      <span>{label}</span>
    </Button>
  );
}
