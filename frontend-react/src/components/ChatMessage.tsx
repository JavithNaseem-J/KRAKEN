import { Bot, BrainCircuit, Check, Copy, User } from 'lucide-react';
import { useState } from 'react';
import Markdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

import type { ChatMessage as ChatMessageType } from '../types/agent';
import { InlineApprovalCard } from './InlineApprovalCard';

interface ChatMessageProps {
  message: ChatMessageType;
  isExecuting?: boolean;
  onApprovalResolved: (approvalId: string, decision: 'approve' | 'reject') => void;
  onApprovalExpired?: (approvalId: string) => void;
  onInspectReasoning: (message: ChatMessageType) => void;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button
      onClick={copy}
      aria-label="Copy to clipboard"
      className="rounded p-1 text-neutral-400 opacity-0 transition-opacity hover:text-white group-hover:opacity-100"
    >
      {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
    </button>
  );
}

export function ChatMessage({
  message,
  isExecuting,
  onApprovalResolved,
  onApprovalExpired,
  onInspectReasoning,
}: ChatMessageProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  if (isSystem) {
    return (
      <div className="my-3 flex justify-center">
        <div className="inline-flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-300">
          <span>{message.content}</span>
        </div>
      </div>
    );
  }

  // If this message represents an Inline Approval Request, render the card cleanly without nested double-boxes
  if (message.approval_id && message.approval_state) {
    return (
      <div className="flex gap-3 my-2 justify-start w-full">
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl bg-purple-600/30 text-purple-300 ring-1 ring-purple-500/40">
          <Bot size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <InlineApprovalCard
            approvalId={message.approval_id}
            state={message.approval_state}
            createdAt={message.timestamp}
            isExecuting={isExecuting}
            onResolved={onApprovalResolved}
            onExpired={onApprovalExpired}
          />
          <div className="mt-1 flex items-center gap-2 text-[10px] text-neutral-500">
            <span>{new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 my-2 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar Icon */}
      <div
        className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl font-bold text-xs ${
          isUser
            ? 'bg-neutral-800 text-white border border-white/10'
            : 'bg-purple-600/30 text-purple-300 ring-1 ring-purple-500/40'
        }`}
      >
        {isUser ? <User size={15} /> : <Bot size={15} />}
      </div>

      {/* Bubble Container */}
      <div className={`group min-w-0 max-w-[80%] ${isUser ? 'text-right' : ''}`}>
        <div
          className={`relative rounded-2xl px-4 py-3 text-xs md:text-sm leading-relaxed ${
            isUser
              ? 'bg-neutral-800 text-white rounded-tr-none border border-white/10'
              : 'bg-black/60 backdrop-blur-md text-neutral-200 rounded-tl-none border border-neutral-800'
          }`}
        >
          <div className="absolute top-2 right-2">
            <CopyButton text={message.content} />
          </div>

          <div className="prose prose-invert prose-sm max-w-none break-words text-neutral-200">
            <Markdown
              components={{
                h3({ children }) {
                  return (
                    <h3 className="text-xs font-black uppercase tracking-widest text-purple-300 mt-5 mb-2 border-b-2 border-purple-500/40 pb-1 font-mono">
                      {children}
                    </h3>
                  );
                },
                h4({ children }) {
                  return (
                    <h4 className="text-xs font-black uppercase tracking-wider text-white mt-4 mb-1.5 font-mono">
                      {children}
                    </h4>
                  );
                },
                p({ children }) {
                  return (
                    <p className="text-justify leading-relaxed text-neutral-200 mb-2 font-sans">
                      {children}
                    </p>
                  );
                },
                li({ children }) {
                  return (
                    <li className="text-justify leading-relaxed text-neutral-200 my-1 font-sans">
                      {children}
                    </li>
                  );
                },
                strong({ children }) {
                  return <strong className="font-black text-white">{children}</strong>;
                },
                code({ className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className ?? '');
                  const codeText = String(children).replace(/\n$/, '');
                  return match ? (
                    <div className="group/code relative my-2 overflow-hidden rounded-xl border border-neutral-800 bg-black">
                      <div className="flex items-center justify-between border-b border-neutral-800 bg-neutral-900 px-3 py-1 text-[10px] font-mono text-neutral-400">
                        <span>{match[1]}</span>
                        <CopyButton text={codeText} />
                      </div>
                      <SyntaxHighlighter
                        style={vscDarkPlus}
                        language={match[1]}
                        PreTag="div"
                        customStyle={{
                          margin: 0,
                          padding: '0.75rem',
                          background: 'transparent',
                          fontSize: '0.75rem',
                        }}
                      >
                        {codeText}
                      </SyntaxHighlighter>
                    </div>
                  ) : (
                    <code
                      className="rounded bg-neutral-800 px-1 py-0.5 font-mono text-xs text-purple-300"
                      {...props}
                    >
                      {children}
                    </code>
                  );
                },
              }}
            >
              {message.content}
            </Markdown>
          </div>
        </div>

        {/* Footer Meta Bar */}
        <div
          className={`mt-1 flex items-center gap-2 px-1 text-[10px] text-neutral-500 ${
            isUser ? 'justify-end' : 'justify-start'
          }`}
        >
          <span>{new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          {message.metadata &&
            (message.metadata.reasoning ||
              (message.metadata.retrieved_chunks && message.metadata.retrieved_chunks.length > 0) ||
              (message.metadata.sources && message.metadata.sources.length > 0) ||
              message.metadata.action_taken) && (
              <button
                onClick={() => onInspectReasoning(message)}
                className="flex items-center gap-1 rounded border border-white/10 px-1.5 py-0.5 text-neutral-400 hover:text-white hover:bg-white/10 transition-colors"
              >
                <BrainCircuit size={11} />
                Reasoning
              </button>
            )}
        </div>
      </div>
    </div>
  );
}
