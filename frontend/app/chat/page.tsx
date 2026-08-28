'use client';

import { useCallback, useEffect, useState } from 'react';
import RequireAuth from '@/components/RequireAuth';
import ChatSidebar from '@/components/ChatSidebar';
import ChatInterface from '@/components/ChatInterface';
import { chatService, ChatSessionSummary } from '@/lib/api';

function ChatPageContent() {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  const refreshSessions = useCallback(async () => {
    try {
      const data = await chatService.listSessions();
      setSessions(data);
    } catch (error) {
      console.error('Error loading chat sessions:', error);
    }
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  const handleNewChat = () => {
    setSelectedSessionId(null);
  };

  const handleSelectSession = (sessionId: string) => {
    setSelectedSessionId(sessionId);
  };

  const handleSessionUpdate = async (sessionId: string) => {
    setSelectedSessionId(sessionId);
    await refreshSessions();
  };

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await chatService.deleteSession(sessionId);
      if (selectedSessionId === sessionId) {
        setSelectedSessionId(null);
      }
      await refreshSessions();
    } catch (error) {
      console.error('Error deleting chat session:', error);
    }
  };

  return (
    <div className="flex">
      <ChatSidebar
        sessions={sessions}
        selectedSessionId={selectedSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
      />
      <div className="flex-1">
        <ChatInterface
          key={selectedSessionId ?? 'new'}
          sessionId={selectedSessionId}
          onSessionUpdate={handleSessionUpdate}
        />
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <RequireAuth role="student">
      <ChatPageContent />
    </RequireAuth>
  );
}
