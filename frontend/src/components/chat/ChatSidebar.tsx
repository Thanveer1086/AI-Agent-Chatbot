import React, { useState } from 'react';
import { Plus, MessageSquare, Trash2, PanelLeftClose, PanelLeft, Clock, Pencil, Check } from 'lucide-react';
import { ChatSession } from '../../types/chat';

interface ChatSidebarProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  isOpen: boolean;
  onToggle: () => void;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  onDeleteSession: (sessionId: string, e: React.MouseEvent) => void;
  onRenameSession?: (sessionId: string, newTitle: string) => void;
}

export const ChatSidebar: React.FC<ChatSidebarProps> = ({
  sessions,
  activeSessionId,
  isOpen,
  onToggle,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  onRenameSession,
}) => {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState<string>('');

  const handleStartRename = (session: ChatSession, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(session.id);
    setEditTitle(session.title || 'Conversation');
  };

  const handleSaveRename = (sessionId: string, e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (onRenameSession && editTitle.trim()) {
      onRenameSession(sessionId, editTitle.trim());
    }
    setEditingId(null);
  };

  if (!isOpen) {
    return (
      <div className="border-r border-slate-200 bg-white p-2 flex flex-col items-center">
        <button
          onClick={onToggle}
          title="Open Chat History"
          className="p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors"
        >
          <PanelLeft className="h-5 w-5" />
        </button>
        <button
          onClick={onNewChat}
          title="New Chat"
          className="mt-2 p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
        >
          <Plus className="h-5 w-5" />
        </button>
      </div>
    );
  }

  return (
    <aside className="w-64 sm:w-72 flex-shrink-0 border-r border-slate-200 bg-white flex flex-col h-full transition-all duration-200 z-10">
      {/* Sidebar Header & New Chat Button */}
      <div className="p-3 border-b border-slate-100 flex items-center gap-2">
        <button
          onClick={onNewChat}
          className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold py-2.5 px-3 rounded-lg shadow-sm transition-all"
        >
          <Plus className="h-4 w-4" />
          <span>New Chat</span>
        </button>
        <button
          onClick={onToggle}
          title="Collapse Sidebar"
          className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
        >
          <PanelLeftClose className="h-4 w-4" />
        </button>
      </div>

      {/* Sessions List Header */}
      <div className="px-3 py-2 flex items-center gap-1.5 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
        <Clock className="h-3 w-3" />
        <span>Recent Conversations</span>
      </div>

      {/* Scrollable Conversation List */}
      <div className="flex-1 overflow-y-auto px-2 py-1 space-y-1">
        {sessions.length === 0 ? (
          <div className="text-center py-8 px-4 text-xs text-slate-400">
            No previous conversations found. Start a new chat!
          </div>
        ) : (
          sessions.map((session) => {
            const isActive = activeSessionId === session.id;
            const isEditing = editingId === session.id;

            return (
              <div
                key={session.id}
                onClick={() => !isEditing && onSelectSession(session.id)}
                className={`group flex items-center justify-between px-3 py-2.5 rounded-lg text-xs cursor-pointer transition-colors ${
                  isActive
                    ? 'bg-blue-50 text-blue-700 font-semibold border border-blue-200'
                    : 'text-slate-700 hover:bg-slate-100'
                }`}
              >
                {isEditing ? (
                  <form
                    onSubmit={(e) => handleSaveRename(session.id, e)}
                    className="flex items-center gap-1 w-full"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <input
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onBlur={() => handleSaveRename(session.id)}
                      autoFocus
                      className="flex-1 bg-white border border-blue-400 rounded px-1.5 py-0.5 text-xs text-slate-800 outline-none"
                    />
                    <button
                      type="submit"
                      className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"
                    >
                      <Check className="h-3.5 w-3.5" />
                    </button>
                  </form>
                ) : (
                  <>
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <MessageSquare
                        className={`h-4 w-4 flex-shrink-0 ${
                          isActive ? 'text-blue-600' : 'text-slate-400 group-hover:text-slate-600'
                        }`}
                      />
                      <span className="truncate">{session.title || 'Conversation'}</span>
                    </div>

                    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                      <button
                        onClick={(e) => handleStartRename(session, e)}
                        title="Rename Chat"
                        className="p-1 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded transition-all"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={(e) => onDeleteSession(session.id, e)}
                        title="Delete Chat"
                        className="p-1 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded transition-all"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Sidebar Footer info */}
      <div className="p-3 border-t border-slate-100 text-[11px] text-slate-400 flex items-center justify-between">
        <span>{sessions.length} Saved Chats</span>
        <span className="font-mono text-[10px]">Postgres pg16</span>
      </div>
    </aside>
  );
};
