import { useState, useRef, useEffect, useCallback, KeyboardEvent } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ArrowUpIcon,
  Bot,
  Clock,
  Paperclip,
  Code2,
  Rocket,
  ShieldCheck,
  Activity,
  Loader2,
  FileText,
  Key,
  PanelLeftOpen,
} from "lucide-react";
import type { ChatMessage as ChatMessageType, UserRole } from "@/types/agent";
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
}

export default function RuixenMoonChat({
  disabled,
  onSend,
  messages,
  activeRole: _activeRole,
  pendingSessionId,
  activeSessionId,
  sessionTitle,
  sidebarOpen,
  onToggleSidebar,
  onApprovalResolved,
  onApprovalExpired,
  onInspectReasoning,
}: RuixenMoonChatProps) {
  const [message, setMessage] = useState("");
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: 48,
    maxHeight: 150,
  });

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages.length]);

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

  const latestApprovalMsg = messages.slice().reverse().find((m) => m.approval_id);
  const isPendingAuthorization =
    pendingSessionId === activeSessionId &&
    (!latestApprovalMsg || latestApprovalMsg.approval_state === "pending");
  const isExecutingAuthorized =
    pendingSessionId === activeSessionId &&
    latestApprovalMsg?.approval_state === "approved";

  return (
    <div
      className="relative w-full h-full bg-cover bg-center flex flex-col items-center overflow-hidden"
      style={{
        backgroundImage:
          "url('https://pub-940ccf6255b54fa799a9b01050e6c227.r2.dev/ruixen_moon_2.png')",
        backgroundAttachment: "fixed",
      }}
    >
      {/* Dark overlay for contrast */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px] pointer-events-none" />

      {/* Top Header Bar */}
      <header className="relative z-10 w-full flex items-center justify-between border-b border-white/10 bg-black/40 px-4 md:px-6 py-3.5 backdrop-blur-md">
        <div className="flex items-center gap-3">
          {!sidebarOpen && (
            <button
              onClick={onToggleSidebar}
              aria-label="Open Sidebar"
              className="rounded-lg p-2 text-neutral-300 hover:bg-white/10 hover:text-white transition-colors"
            >
              <PanelLeftOpen size={18} />
            </button>
          )}

          <div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs font-semibold text-neutral-200">
                {sessionTitle || "New Session"}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-black/40 px-2.5 py-1 text-[10px]">
              <Activity size={12} className="text-emerald-400" />
              <span className="text-neutral-400">Gateway:</span>
              <span className="font-mono text-emerald-400">200 OK</span>
            </div>
            <div className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-black/40 px-2.5 py-1 text-[10px]">
              <ShieldCheck size={12} className="text-sky-400" />
              <span className="text-neutral-400">Orchestrator:</span>
              <span className="font-mono text-sky-400">ONLINE</span>
            </div>
          </div>

          {isPendingAuthorization && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold text-amber-300 border border-amber-500/30 bg-amber-500/10 animate-pulse">
              <Clock size={12} className="text-amber-400" />
              Awaiting Security Authorization…
            </span>
          )}

          {isExecutingAuthorized && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold text-emerald-300 border border-emerald-500/30 bg-emerald-500/10 animate-pulse">
              <Loader2 size={12} className="animate-spin text-emerald-400" />
              Executing Authorized Action…
            </span>
          )}
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
                  Autonomous Knowledge Execution Agent with inline Human-in-the-Loop safety approval gates.
                  Start by typing your security or helpdesk query below.
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
                />
              ))}
              {disabled && (
                <div className="flex gap-3 my-2 justify-start">
                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl bg-purple-600/30 text-purple-300 ring-1 ring-purple-500/40">
                    <Bot size={15} />
                  </div>
                  <div className="group min-w-0 max-w-[80%]">
                    <div className="relative rounded-2xl px-4 py-3 text-xs md:text-sm bg-black/60 backdrop-blur-md text-neutral-200 rounded-tl-none border border-neutral-800 flex items-center gap-2.5">
                      <Loader2 size={15} className="animate-spin text-purple-400" />
                      <span className="font-medium text-neutral-300">Agent is thinking…</span>
                    </div>
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
              placeholder={disabled ? "Agent is thinking…" : "Type your security or helpdesk query..."}
              className={cn(
                "w-full px-4 py-3.5 resize-none border-none",
                "bg-transparent text-white text-sm",
                "focus-visible:ring-0 focus-visible:ring-offset-0",
                "placeholder:text-neutral-400 min-h-[48px]"
              )}
              style={{ overflow: "hidden" }}
            />

            {/* Footer Buttons */}
            <div className="flex items-center justify-between p-3 border-t border-white/5">
              <Button
                variant="ghost"
                size="icon"
                className="text-neutral-400 hover:text-white hover:bg-neutral-800/80 rounded-xl"
              >
                <Paperclip className="w-4 h-4" />
              </Button>

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
              KRAKEN will analyze your request and provide intelligent, secure assistance. KRAKEN can make mistakes. Verify important security information.
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
