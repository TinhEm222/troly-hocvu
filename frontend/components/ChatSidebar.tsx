'use client';

import { Plus, MessageSquare, Trash2, LogOut } from 'lucide-react';
import { ChatSessionSummary } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

interface ChatSidebarProps {
  sessions: ChatSessionSummary[];
  selectedSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  onDeleteSession: (sessionId: string) => void;
}

export default function ChatSidebar({
  sessions,
  selectedSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
}: ChatSidebarProps) {
  const { user, logout } = useAuth();

  return (
    <div className="w-72 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col h-screen">
      <div className="p-4 border-b border-gray-200">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-medium"
        >
          <Plus className="w-4 h-4" />
          Chat mới
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        <p className="px-2 py-1 text-xs font-medium text-gray-400 uppercase">Lịch sử chat</p>
        {sessions.length === 0 ? (
          <p className="px-2 py-3 text-sm text-gray-400">Chưa có cuộc trò chuyện nào.</p>
        ) : (
          <ul className="space-y-1">
            {sessions.map((session) => (
              <li key={session.id}>
                <div
                  onClick={() => onSelectSession(session.id)}
                  className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
                    selectedSessionId === session.id ? 'bg-green-50 text-green-700' : 'hover:bg-gray-100 text-gray-700'
                  }`}
                >
                  <MessageSquare className="w-4 h-4 flex-shrink-0" />
                  <span className="flex-1 truncate text-sm">{session.title}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteSession(session.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-opacity"
                    title="Xóa chat"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="p-4 border-t border-gray-200">
        <p className="text-sm text-gray-600 truncate mb-2">{user?.full_name || user?.email}</p>
        <button
          onClick={logout}
          className="w-full flex items-center justify-center gap-2 py-2 text-sm text-gray-600 hover:text-red-600 border border-gray-200 rounded-lg hover:border-red-200 transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Đăng xuất
        </button>
      </div>
    </div>
  );
}
