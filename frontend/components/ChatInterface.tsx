'use client';

import { useState, useRef, useEffect } from 'react';
import { Check, Send, Bot, User, FileText } from 'lucide-react';
import { chatService, ChatMessage, StageHistoryItem } from '@/lib/api';
import { createStreamBuffer } from '@/lib/streamBuffer';
import MarkdownMessage from '@/components/MarkdownMessage';
import {
  buildStageViews,
  type StreamStageId,
  type StreamStageView,
} from '@/lib/streamStages';

const STAGE_LABELS: Record<StreamStageId, string> = {
  retrieving: 'Tìm tài liệu liên quan',
  reranking: 'Kiểm tra độ phù hợp',
  generating: 'Soạn câu trả lời',
};

interface ChatInterfaceProps {
  sessionId: string | null;
  onSessionUpdate: (sessionId: string) => void;
}

export default function ChatInterface({ sessionId, onSessionUpdate }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [streamStageViews, setStreamStageViews] = useState<StreamStageView[]>(() => buildStageViews(null));
  const [streamingIntent, setStreamingIntent] = useState<'basic' | 'rag' | null>(null);
  const [streamingAssistantId, setStreamingAssistantId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const stageQueueRef = useRef<StreamStageId[]>([]);
  const activeStageRef = useRef<StreamStageId | null>(null);
  const stageStartedAtRef = useRef(0);
  const stageTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const basicStreamRef = useRef(false);

  const MIN_STAGE_DISPLAY_MS = 700;
  const stageOrder: StreamStageId[] = ['retrieving', 'reranking', 'generating'];

  const clearStageTimer = () => {
    if (stageTimerRef.current !== null) {
      clearTimeout(stageTimerRef.current);
      stageTimerRef.current = null;
    }
  };

  const pumpStageQueue = () => {
    const nextStage = stageQueueRef.current[0];
    if (!nextStage) return;

    const activeIndex = activeStageRef.current
      ? stageOrder.indexOf(activeStageRef.current)
      : -1;
    const nextIndex = stageOrder.indexOf(nextStage);

    if (activeIndex >= nextIndex && activeStageRef.current !== null) {
      stageQueueRef.current.shift();
      pumpStageQueue();
      return;
    }

    const elapsed = performance.now() - stageStartedAtRef.current;
    const wait = Math.max(0, MIN_STAGE_DISPLAY_MS - elapsed);
    if (wait > 0) {
      clearStageTimer();
      stageTimerRef.current = setTimeout(() => {
        stageTimerRef.current = null;
        pumpStageQueue();
      }, wait);
      return;
    }

    stageQueueRef.current.shift();
    activeStageRef.current = nextStage;
    stageStartedAtRef.current = performance.now();
    setStreamStageViews(buildStageViews(nextStage));
    pumpStageQueue();
  };

  const enqueueStage = (stage: StreamStageId) => {
    if (activeStageRef.current === stage && stageQueueRef.current.length === 0) {
      return;
    }
    const alreadyQueued = stageQueueRef.current.some((item) => item === stage);
    if (!alreadyQueued) stageQueueRef.current.push(stage);
    pumpStageQueue();
  };

  useEffect(() => () => clearStageTimer(), []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      return;
    }

    let cancelled = false;
    setIsHistoryLoading(true);
    chatService
      .getSessionMessages(sessionId)
      .then((records) => {
        if (cancelled) return;
        setMessages(
          records.map((record, index) => ({
            id: `${sessionId}-${index}`,
            role: record.role,
            content: record.content,
            sources: record.sources,
            stageHistory: record.stage_history,
          }))
        );
      })
      .catch((error) => {
        console.error('Error loading chat history:', error);
      })
      .finally(() => {
        if (!cancelled) setIsHistoryLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const query = input.trim();
    const userMessageId = `user-${Date.now()}`;
    const assistantMessageId = `assistant-${Date.now()}`;

    const userMessage: ChatMessage = {
      id: userMessageId,
      role: 'user',
      content: query,
    };
    const assistantPlaceholder: ChatMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      sources: [],
      streaming: true,
    };

    setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
    setInput('');
    setIsLoading(true);
    setStreamingAssistantId(assistantMessageId);
    setStreamingIntent(null);
    clearStageTimer();
    stageQueueRef.current = [];
    activeStageRef.current = null;
    stageStartedAtRef.current = performance.now() - MIN_STAGE_DISPLAY_MS;
    setStreamStageViews(buildStageViews(null));
    enqueueStage('retrieving');
    basicStreamRef.current = false;

    const updateAssistant = (update: (message: ChatMessage) => ChatMessage) => {
      setMessages((prev) => {
        return prev.map((message) => (
          message.id === assistantMessageId ? update(message) : message
        ));
      });
    };

    const streamBuffer = createStreamBuffer((delta) => {
      updateAssistant((message) => ({ ...message, content: message.content + delta }));
    });

    try {
      let streamSessionId: string | null = null;
      let streamFailed = false;
      await chatService.streamMessage({
        query,
        session_id: sessionId || undefined,
      }, {
        onStatus: (payload) => {
            enqueueStage(payload.stage);
        },
        onMeta: (payload) => {
          streamSessionId = payload.session_id;
          if (payload.intent === 'basic') {
            basicStreamRef.current = true;
            setStreamingIntent('basic');
            clearStageTimer();
            stageQueueRef.current = [];
            activeStageRef.current = null;
            setStreamStageViews(buildStageViews(null));
          } else {
            setStreamingIntent('rag');
            enqueueStage('generating');
          }
          updateAssistant((message) => ({
            ...message,
            sources: payload.sources || [],
            streaming: true,
          }));
        },
        onToken: (payload) => {
          if (!basicStreamRef.current) {
            enqueueStage('generating');
          }
          streamBuffer.push(payload.text);
        },
        onDone: (payload) => {
          streamBuffer.flush();
          streamSessionId = payload.session_id;
          updateAssistant((message) => ({
            ...message,
            sources: payload.sources || message.sources,
            stageHistory: payload.stages,
            streaming: false,
          }));
        },
        onError: (payload) => {
          streamBuffer.flush();
          streamFailed = true;
          updateAssistant((message) => ({
            ...message,
            content: payload.message || 'Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại sau.',
            streaming: false,
          }));
        },
      });

      if (!streamFailed && streamSessionId) {
        onSessionUpdate(streamSessionId);
      }
    } catch (error) {
      console.error('Error:', error);
      streamBuffer.flush();
      updateAssistant((message) => ({
        ...message,
        content: 'Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại sau.',
        streaming: false,
      }));
    } finally {
      streamBuffer.dispose();
      clearStageTimer();
      stageQueueRef.current = [];
      activeStageRef.current = null;
      setIsLoading(false);
      setStreamingAssistantId(null);
      setStreamingIntent(null);
      setStreamStageViews(buildStageViews(null));
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gradient-to-br from-blue-50 to-green-100">
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-4 py-6">
          {isHistoryLoading ? (
            <div className="text-center py-12 text-gray-400">Đang tải cuộc trò chuyện...</div>
          ) : messages.length === 0 ? (
            <div className="text-center py-12">
              <h2 className="text-xl font-semibold text-gray-700 mb-2">Xin chào! Tôi là Trợ lý ảo học vụ</h2>
              <p className="text-gray-500">Hỏi tôi về quy chế đào tạo, sổ tay sinh viên, học phí, chuẩn đầu ra và các quy định học vụ của trường</p>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((message, index) => (
                <div key={message.id ?? index} className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {message.role === 'assistant' && (
                    <div className="flex-shrink-0">
                      <div className="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center">
                        <Bot className="w-5 h-5 text-white" />
                      </div>
                    </div>
                  )}

                  <div className={`max-w-[70%] rounded-2xl px-4 py-3 ${message.role === 'user' ? 'bg-green-600 text-white' : 'bg-white text-gray-800 shadow-md'}`}>
                    {isLoading && streamingIntent !== 'basic' && message.id === streamingAssistantId && message.streaming && (
                      <div className="mb-3 border-b border-gray-100 pb-3" role="status" aria-live="polite">
                        <ol className="space-y-1.5">
                          {streamStageViews.map((stage) => (
                            <li key={stage.id} className="flex items-center gap-2 text-xs">
                              <span className={`flex h-4 w-4 items-center justify-center rounded-full border ${
                                stage.state === 'done'
                                  ? 'border-green-500 bg-green-500 text-white'
                                  : stage.state === 'active'
                                    ? 'border-green-500 bg-green-50 text-green-600'
                                    : 'border-gray-300 bg-white text-transparent'
                              }`} aria-hidden="true">
                                {stage.state === 'done' && <Check className="h-3 w-3" />}
                                {stage.state === 'active' && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-green-600" />}
                              </span>
                              <span className={stage.state === 'active' ? 'font-medium text-gray-700' : 'text-gray-400'}>
                                {stage.label}
                              </span>
                            </li>
                          ))}
                        </ol>
                      </div>
                    )}

                    {message.role === 'assistant' && message.stageHistory && message.stageHistory.length > 0 && (
                      <details className="mb-3 border-b border-gray-100 pb-2 text-xs text-gray-500">
                        <summary className="cursor-pointer select-none font-medium hover:text-gray-700">
                          Quy trình xử lý
                        </summary>
                        <ol className="mt-2 space-y-1.5">
                          {message.stageHistory.map((stage: StageHistoryItem) => (
                            <li key={stage.id} className="flex items-center gap-2 text-xs">
                              <span className="flex items-center gap-2">
                                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-green-500 text-white" aria-hidden="true">
                                  <Check className="h-3 w-3" />
                                </span>
                                <span>{STAGE_LABELS[stage.id]}</span>
                              </span>
                            </li>
                          ))}
                        </ol>
                      </details>
                    )}

                    <div aria-live={message.role === 'assistant' ? 'polite' : undefined}>
                      {message.role === 'assistant' ? (
                        <MarkdownMessage content={message.content} />
                      ) : (
                        <p className="whitespace-pre-wrap">{message.content}</p>
                      )}
                    </div>

                    {/* Sources arrive in the meta event before generation starts. They
                        remain below the response to preserve the requested order. */}
                    {!message.streaming && message.role === 'assistant' && message.sources && message.sources.length > 0 && (
                      <div className="mt-3 space-y-1.5 border-t border-gray-100 pt-2">
                        <p className="text-xs font-medium text-gray-500">
                          {message.streaming ? 'Nguồn tham khảo đang sử dụng:' : 'Nguồn tham khảo:'}
                        </p>
                        {message.sources.slice(0, 5).map((source, idx) => {
                          const metadata = source.metadata || {};
                          const fileName = metadata.source || 'Tài liệu';
                          const pageNumber = metadata.page ?? metadata.page_number;
                          const page = pageNumber ? `- Trang ${pageNumber}` : '';

                          return (
                            <div key={idx} className="flex items-center gap-2 text-xs text-gray-600 bg-gray-50 rounded-md px-2 py-1.5">
                              <FileText className="w-3.5 h-3.5 flex-shrink-0 text-gray-400" />
                              <span>{fileName} {page}</span>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {message.role === 'user' && (
                    <div className="flex-shrink-0">
                      <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center">
                        <User className="w-5 h-5 text-white" />
                      </div>
                    </div>
                  )}
                </div>
              ))}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      <div className="bg-white border-t border-gray-200">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input type="text" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Nhập câu hỏi của bạn..." className="flex-1 px-4 py-3 border border-gray-300 rounded-full focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent text-gray-800" disabled={isLoading}/>
            <button type="submit" disabled={isLoading || !input.trim()} className="px-6 py-3 bg-green-600 text-white rounded-full hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors flex items-center gap-2">
              <Send className="w-5 h-5" />
              Gửi
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
