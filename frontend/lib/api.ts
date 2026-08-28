import axios from 'axios';
import type { StreamStageId } from '@/lib/streamStages';
import { parseSseFrame } from '@/lib/sseParser';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const TOKEN_STORAGE_KEY = 'nmk_access_token';
export const USER_STORAGE_KEY = 'nmk_user';

export interface AuthUser {
  id: number;
  email: string;
  full_name?: string | null;
  role: 'student' | 'admin';
}

export interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  streaming?: boolean;
  stageHistory?: StageHistoryItem[];
}

export interface StageHistoryItem {
  id: StreamStageId;
  status: 'done';
}

export interface Source {
  text: string;
  metadata: {
    type?: string;
    chunk_type?: string;
    source?: string;
    doc_type?: string;
    page?: number;
    page_number?: number;
    [key: string]: any;
  };
  score: number;
}

export interface ChatRequest {
  query: string;
  session_id?: string;
}

export interface ChatResponse {
  answer: string;
  sources?: Source[];
  session_id: string;
}

export interface ChatStreamHandlers {
  onStatus?: (payload: { stage: 'retrieving' | 'reranking' | 'generating'; message: string }) => void;
  onMeta?: (payload: { session_id: string; sources: Source[]; intent?: 'basic' | 'rag' }) => void;
  onToken?: (payload: { text: string }) => void;
  onDone?: (payload: { session_id: string; sources?: Source[]; stages?: StageHistoryItem[] }) => void;
  onError?: (payload: { message: string }) => void;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessageRecord {
  role: 'user' | 'assistant';
  content: string;
  sources: Source[];
  stage_history?: StageHistoryItem[];
  created_at: string;
}

export interface DocumentRecord {
  id: number;
  filename: string;
  original_filename: string;
  size_bytes: number;
  status: 'pending' | 'indexed' | 'failed';
  uploaded_by?: number | null;
  uploaded_at: string;
  document_code: string;
  version_number: number;
  lifecycle_status: 'draft' | 'active' | 'superseded';
  replaces_document_id?: number | null;
}

export interface DocumentUploadOptions {
  uploadMode?: 'new' | 'update';
  replacesDocumentId?: number;
}

export interface AdminUserRecord {
  id: number;
  email: string;
  full_name?: string | null;
  role: 'student' | 'admin';
  created_at: string;
}

export interface StatsResponse {
  total_users: number;
  total_students: number;
  total_admins: number;
  total_documents: number;
  total_chat_sessions: number;
  total_messages: number;
  qdrant_points_count?: number | null;
}

export interface ReindexStatus {
  running: boolean;
  last_started_at?: string | null;
  last_finished_at?: string | null;
  last_error?: string | null;
  stage?: string | null;
  message?: string | null;
  current_step?: number;
  total_steps?: number;
  progress_percent?: number;
}

const apiClient = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
});

const AUTH_PATH_PREFIX = '/api/auth';

function redirectToLogin() {
  if (typeof window === 'undefined') return;
  if (window.location.pathname !== '/login') {
    window.location.href = '/login';
  }
}

apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const requestUrl: string = error?.config?.url || '';
    const isAuthRoute = requestUrl.startsWith(AUTH_PATH_PREFIX);

    if (status === 401 && !isAuthRoute) {
      clearAuth();
      redirectToLogin();
    }

    return Promise.reject(error);
  }
);

export function getStoredUser(): AuthUser | null {
  if (typeof window === 'undefined') return null;
  const raw = localStorage.getItem(USER_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function storeAuth(token: string, user: AuthUser) {
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
  localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(USER_STORAGE_KEY);
}

export const authService = {
  async register(email: string, password: string, full_name: string) {
    const response = await apiClient.post('/api/auth/register', { email, password, full_name });
    return response.data as { access_token: string; token_type: string; user: AuthUser };
  },

  async login(email: string, password: string) {
    const response = await apiClient.post('/api/auth/login', { email, password });
    return response.data as { access_token: string; token_type: string; user: AuthUser };
  },

  async me() {
    const response = await apiClient.get('/api/auth/me');
    return response.data as AuthUser;
  },
};

export const chatService = {
  async sendMessage(request: ChatRequest): Promise<ChatResponse> {
    const response = await apiClient.post<ChatResponse>('/api/chat', request);
    return response.data;
  },

  async streamMessage(request: ChatRequest, handlers: ChatStreamHandlers): Promise<void> {
    const token = typeof window !== 'undefined' ? localStorage.getItem(TOKEN_STORAGE_KEY) : null;
    const response = await fetch(`${API_URL}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Streaming request failed with status ${response.status}`);
    }
    if (!response.body) {
      throw new Error('Streaming response body is unavailable');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    const processFrame = (frame: string) => {
      const parsedFrame = parseSseFrame(frame);
      if (!parsedFrame) return;

      const { eventName, payload } = parsedFrame;
      if (eventName === 'status') {
        handlers.onStatus?.(payload as Parameters<NonNullable<ChatStreamHandlers['onStatus']>>[0]);
      }
      if (eventName === 'meta') {
        handlers.onMeta?.(payload as Parameters<NonNullable<ChatStreamHandlers['onMeta']>>[0]);
      }
      if (eventName === 'token') {
        const tokenPayload = typeof payload === 'string' ? { text: payload } : payload;
        handlers.onToken?.(tokenPayload as Parameters<NonNullable<ChatStreamHandlers['onToken']>>[0]);
      }
      if (eventName === 'done') {
        handlers.onDone?.(payload as Parameters<NonNullable<ChatStreamHandlers['onDone']>>[0]);
      }
      if (eventName === 'error') {
        handlers.onError?.(payload as Parameters<NonNullable<ChatStreamHandlers['onError']>>[0]);
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const frames = buffer.split('\n\n');
      buffer = frames.pop() || '';
      frames.forEach(processFrame);
      if (done) break;
    }
    if (buffer.trim()) processFrame(buffer);
  },

  async listSessions(): Promise<ChatSessionSummary[]> {
    const response = await apiClient.get<ChatSessionSummary[]>('/api/chat/sessions');
    return response.data;
  },

  async getSessionMessages(sessionId: string): Promise<ChatMessageRecord[]> {
    const response = await apiClient.get<ChatMessageRecord[]>(`/api/chat/sessions/${sessionId}/messages`);
    return response.data;
  },

  async deleteSession(sessionId: string): Promise<void> {
    await apiClient.delete(`/api/chat/sessions/${sessionId}`);
  },

  async healthCheck(): Promise<boolean> {
    try {
      const response = await apiClient.get('/health');
      return response.status === 200;
    } catch {
      return false;
    }
  },
};

export const adminService = {
  async getStats(): Promise<StatsResponse> {
    const response = await apiClient.get<StatsResponse>('/api/admin/stats');
    return response.data;
  },

  async listDocuments(): Promise<DocumentRecord[]> {
    const response = await apiClient.get<DocumentRecord[]>('/api/admin/documents');
    return response.data;
  },

  async uploadDocument(file: File, options: DocumentUploadOptions = {}): Promise<DocumentRecord> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('upload_mode', options.uploadMode || 'new');
    if (options.replacesDocumentId !== undefined) {
      formData.append('replaces_document_id', String(options.replacesDocumentId));
    }
    const response = await apiClient.post<DocumentRecord>('/api/admin/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  async deleteDocument(documentId: number): Promise<void> {
    await apiClient.delete(`/api/admin/documents/${documentId}`);
  },

  async reindex(): Promise<{ message: string }> {
    const response = await apiClient.post('/api/admin/documents/reindex');
    return response.data;
  },

  async getReindexStatus(): Promise<ReindexStatus> {
    const response = await apiClient.get<ReindexStatus>('/api/admin/documents/reindex/status');
    return response.data;
  },

  async listUsers(): Promise<AdminUserRecord[]> {
    const response = await apiClient.get<AdminUserRecord[]>('/api/admin/users');
    return response.data;
  },

  async deleteUser(userId: number): Promise<void> {
    await apiClient.delete(`/api/admin/users/${userId}`);
  },
};

export default apiClient;
