import { useMemo } from 'react';
import {
  MessageSquare,
  PanelLeftClose,
  Plus,
  Trash2,
  UserCheck,
} from 'lucide-react';

import type { ChatSession, UserRole } from '../types/agent';

interface SessionSidebarProps {
  sessions: ChatSession[];
  activeSessionId: string;
  roles: UserRole[];
  activeRole: UserRole;
  isOpen: boolean;
  onToggleOpen: () => void;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  onDeleteSession: (sessionId: string) => void;
  onSelectRole: (role: UserRole) => void;
}

interface GroupedSessions {
  today: ChatSession[];
  yesterday: ChatSession[];
  last7Days: ChatSession[];
  older: ChatSession[];
}

function groupSessionsByDate(sessions: ChatSession[]): GroupedSessions {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 86400000;
  const startOf7Days = startOfToday - 6 * 86400000;

  const grouped: GroupedSessions = {
    today: [],
    yesterday: [],
    last7Days: [],
    older: [],
  };

  for (const s of sessions) {
    const time = new Date(s.updated_at).getTime();
    if (time >= startOfToday) {
      grouped.today.push(s);
    } else if (time >= startOfYesterday) {
      grouped.yesterday.push(s);
    } else if (time >= startOf7Days) {
      grouped.last7Days.push(s);
    } else {
      grouped.older.push(s);
    }
  }

  return grouped;
}

export function SessionSidebar({
  sessions,
  activeSessionId,
  roles,
  activeRole,
  isOpen,
  onToggleOpen,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  onSelectRole,
}: SessionSidebarProps) {
  const grouped = useMemo(() => groupSessionsByDate(sessions), [sessions]);

  if (!isOpen) return null;

  const renderSessionItem = (s: ChatSession) => {
    const active = s.session_id === activeSessionId;
    return (
      <div
        key={s.session_id}
        onClick={() => onSelectSession(s.session_id)}
        className={`group relative flex items-center justify-between gap-2.5 rounded-lg px-3 py-2 text-xs transition-all duration-150 cursor-pointer ${
          active
            ? 'bg-white/15 text-white font-semibold'
            : 'text-neutral-300 hover:bg-white/5 hover:text-white'
        }`}
      >
        <div className="flex items-center gap-2.5 min-w-0 flex-1">
          <MessageSquare size={14} className={active ? 'text-purple-400' : 'text-neutral-400'} />
          <span className="truncate">{s.title || 'New Chat'}</span>
        </div>

        <button
          aria-label="Delete session"
          onClick={(e) => {
            e.stopPropagation();
            onDeleteSession(s.session_id);
          }}
          className="rounded p-1 text-neutral-400 opacity-0 hover:bg-neutral-800 hover:text-red-400 group-hover:opacity-100 transition-opacity"
        >
          <Trash2 size={13} />
        </button>
      </div>
    );
  };

  return (
    <aside className="relative flex h-full w-72 flex-col justify-between border-r border-white/10 bg-black/85 backdrop-blur-xl z-20 transition-all duration-300">
      {/* Top Header & New Chat Button */}
      <div className="flex flex-col gap-3 p-3 border-b border-white/10">
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-extrabold tracking-widest text-white uppercase">KRAKEN</span>
          </div>

          <button
            onClick={onToggleOpen}
            aria-label="Close Sidebar"
            className="rounded-lg p-1.5 text-neutral-400 hover:bg-white/10 hover:text-white transition-colors"
          >
            <PanelLeftClose size={18} />
          </button>
        </div>

        <button
          onClick={onNewSession}
          className="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-white transition-all hover:bg-white/10 hover:border-white/20 active:scale-[0.98]"
        >
          <span className="flex items-center gap-2">
            <Plus size={15} className="text-purple-400" />
            New Chat
          </span>
          <span className="text-[10px] font-mono text-neutral-400">Ctrl+K</span>
        </button>
      </div>

      {/* Session History List (ChatGPT / Gemini Recency Sections) */}
      <div className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
        {sessions.length === 0 && (
          <p className="px-3 py-6 text-center text-xs text-neutral-500">No chat history yet.</p>
        )}

        {grouped.today.length > 0 && (
          <div>
            <h4 className="px-3 mb-1 text-[10px] font-semibold text-neutral-500 uppercase tracking-wider">
              Today
            </h4>
            <div className="space-y-0.5">{grouped.today.map(renderSessionItem)}</div>
          </div>
        )}

        {grouped.yesterday.length > 0 && (
          <div>
            <h4 className="px-3 mb-1 text-[10px] font-semibold text-neutral-500 uppercase tracking-wider">
              Yesterday
            </h4>
            <div className="space-y-0.5">{grouped.yesterday.map(renderSessionItem)}</div>
          </div>
        )}

        {grouped.last7Days.length > 0 && (
          <div>
            <h4 className="px-3 mb-1 text-[10px] font-semibold text-neutral-500 uppercase tracking-wider">
              Previous 7 Days
            </h4>
            <div className="space-y-0.5">{grouped.last7Days.map(renderSessionItem)}</div>
          </div>
        )}

        {grouped.older.length > 0 && (
          <div>
            <h4 className="px-3 mb-1 text-[10px] font-semibold text-neutral-500 uppercase tracking-wider">
              Older
            </h4>
            <div className="space-y-0.5">{grouped.older.map(renderSessionItem)}</div>
          </div>
        )}
      </div>

      {/* Bottom Identity Role Switcher */}
      <div className="p-3 border-t border-white/10 bg-black/40">
        <div className="mb-2 px-1 flex items-center justify-between text-[10px] uppercase font-bold tracking-wider text-neutral-400">
          <span title="In production, user identities are authenticated via SAML SSO / Okta JWT tokens">
            Dev Test Personas
          </span>
          <span className="text-purple-400 font-mono text-[9px]">DEV ONLY</span>
        </div>
        <div className="grid grid-cols-3 gap-1">
          {roles.map((role) => {
            const isActive = role.user_id === activeRole.user_id;
            return (
              <button
                key={role.user_id}
                onClick={() => onSelectRole(role)}
                className={`flex flex-col items-center justify-center rounded-lg py-1.5 px-1 text-center transition-all ${
                  isActive
                    ? 'bg-purple-600/30 text-white border border-purple-500/50 shadow-sm'
                    : 'text-neutral-400 hover:bg-white/5 hover:text-white border border-transparent'
                }`}
              >
                <UserCheck size={14} className={isActive ? 'text-purple-400' : 'text-neutral-500'} />
                <span className="text-[11px] font-medium mt-0.5">{role.label}</span>
                <span className="text-[8px] text-neutral-400 truncate max-w-full">{role.title}</span>
              </button>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
