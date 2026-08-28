'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import RequireAuth from '@/components/RequireAuth';
import AdminNav from '@/components/AdminNav';
import { adminService, DocumentRecord, ReindexStatus } from '@/lib/api';
import {
  getReindexStatusMessage,
  isReindexFinished,
  shouldStopReindexPolling,
  uploadFilesSequentially,
} from '@/lib/adminUi';
import { Upload, Trash2, RefreshCw, FileText } from 'lucide-react';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const statusLabel: Record<string, string> = {
  pending: 'Chờ index',
  indexed: 'Đã index',
  failed: 'Lỗi',
};

const statusColor: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-700',
  indexed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
};

const lifecycleLabel: Record<string, string> = {
  draft: 'Bản nháp',
  active: 'Đang hiệu lực',
  superseded: 'Đã thay thế',
};

const lifecycleColor: Record<string, string> = {
  draft: 'bg-yellow-100 text-yellow-700',
  active: 'bg-blue-100 text-blue-700',
  superseded: 'bg-gray-100 text-gray-600',
};

function DocumentsContent() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [uploadMode, setUploadMode] = useState<'new' | 'update'>('new');
  const [replacesDocumentId, setReplacesDocumentId] = useState<number | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isReindexing, setIsReindexing] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [reindexStatus, setReindexStatus] = useState<ReindexStatus | null>(null);
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number; filename: string } | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isMountedRef = useRef(false);
  const reindexPollingRef = useRef(false);

  const loadDocuments = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await adminService.listDocuments();
      setDocuments(data);
    } catch {
      setError('Không thể tải danh sách tài liệu.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const pollReindexStatus = useCallback(async () => {
    if (reindexPollingRef.current) return;
    reindexPollingRef.current = true;
    const startedAt = Date.now();

    try {
      while (isMountedRef.current) {
        const status = await adminService.getReindexStatus();
        if (!isMountedRef.current) return;

        setReindexStatus(status);
        setIsReindexing(status.running);
        if (isReindexFinished(status)) {
          if (status.last_error) {
            setMessage('');
            setError(getReindexStatusMessage(status));
          } else if (status.stage === 'completed') {
            setError('');
            setMessage(getReindexStatusMessage(status));
          }
          return;
        }

        if (shouldStopReindexPolling(startedAt, Date.now())) {
          setError('Re-index chưa hoàn tất sau 5 phút. Vui lòng kiểm tra lại trạng thái.');
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    } catch (err: any) {
      if (isMountedRef.current) {
        setError(err?.response?.data?.detail || 'Không thể cập nhật trạng thái re-index.');
      }
    } finally {
      reindexPollingRef.current = false;
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;

    const syncReindexStatus = async () => {
      try {
        const status = await adminService.getReindexStatus();
        if (!isMountedRef.current) return;
        setReindexStatus(status);
        setIsReindexing(status.running);
        if (status.running) void pollReindexStatus();
      } catch {
        // The document page remains usable if the optional status refresh fails.
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') void syncReindexStatus();
    };

    void syncReindexStatus();
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      isMountedRef.current = false;
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [pollReindexStatus]);

  const triggerReindex = useCallback(async () => {
    setIsReindexing(true);
    setError('');
    setMessage('');
    setReindexStatus({
      running: true,
      stage: 'extracting',
      message: 'Đang chuẩn bị re-index...',
      current_step: 1,
      total_steps: 4,
      progress_percent: 25,
      last_started_at: new Date().toISOString(),
    });
    try {
      const result = await adminService.reindex();
      setMessage(result.message);
      await pollReindexStatus();
      await loadDocuments();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Re-index thất bại.');
    } finally {
      setIsReindexing(false);
    }
  }, [loadDocuments, pollReindexStatus]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    if (uploadMode === 'update' && replacesDocumentId === null) {
      setError('Hãy chọn tài liệu đang hiệu lực cần cập nhật.');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }
    if (uploadMode === 'update' && files.length !== 1) {
      setError('Mỗi lần cập nhật chỉ được chọn một file PDF.');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    setIsUploading(true);
    setError('');
    setMessage('');
    try {
      const result = await uploadFilesSequentially(files, (file, index) => {
        setUploadProgress({ current: index + 1, total: files.length, filename: file.name });
        return adminService.uploadDocument(file, {
          uploadMode,
          replacesDocumentId: uploadMode === 'update' ? replacesDocumentId ?? undefined : undefined,
        });
      });

      if (result.uploaded.length > 0) {
        setMessage(`Đã tải lên ${result.uploaded.length}/${files.length} tài liệu. Hệ thống sẽ tự động re-index.`);
      }
      if (result.failed.length > 0) {
        const failures = result.failed.map(({ file, error }) => {
          const detail = (error as any)?.response?.data?.detail || 'Tải lên thất bại.';
          return `${file.name}: ${detail}`;
        });
        setError(failures.join(' '));
      }
      await loadDocuments();
      if (result.uploaded.length > 0) {
        await triggerReindex();
        if (uploadMode === 'update') setReplacesDocumentId(null);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Tải lên thất bại.');
    } finally {
      setIsUploading(false);
      setUploadProgress(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = async (id: number) => {
    const document = documents.find((item) => item.id === id);
    if (!document || !window.confirm(`Bạn có chắc muốn xóa "${document.original_filename}"?`)) return;

    try {
      await adminService.deleteDocument(id);
      await loadDocuments();
      await triggerReindex();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Xóa tài liệu thất bại.');
    }
  };

  const handleReindex = triggerReindex;
  const activeDocuments = documents.filter((document) => document.lifecycle_status === 'active');

  return (
    <div className="flex flex-1">
      <AdminNav />
      <main className="flex-1 p-8 bg-gray-50 overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold text-gray-800">Quản lý tài liệu</h1>
          <div className="flex flex-wrap justify-end gap-2">
            <select
              value={uploadMode}
              onChange={(event) => {
                setUploadMode(event.target.value as 'new' | 'update');
                setReplacesDocumentId(null);
                setError('');
              }}
              className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700"
              aria-label="Loại tài liệu tải lên"
              disabled={isUploading || isReindexing}
            >
              <option value="new">Tài liệu mới</option>
              <option value="update">Cập nhật phiên bản</option>
            </select>
            {uploadMode === 'update' && (
              <select
                value={replacesDocumentId ?? ''}
                onChange={(event) => setReplacesDocumentId(event.target.value ? Number(event.target.value) : null)}
                className="max-w-72 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700"
                aria-label="Tài liệu đang hiệu lực cần thay thế"
                disabled={isUploading || isReindexing || activeDocuments.length === 0}
              >
                <option value="">Chọn tài liệu cần cập nhật</option>
                {activeDocuments.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.original_filename} (v{document.version_number})
                  </option>
                ))}
              </select>
            )}
            <label className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg cursor-pointer hover:bg-green-700 transition-colors text-sm font-medium">
              <Upload className="w-4 h-4" />
              {isUploading && uploadProgress
                ? `Đang tải ${uploadProgress.current}/${uploadProgress.total}...`
                : isReindexing
                  ? 'Đang re-index...'
                  : 'Upload PDF'}
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                multiple={uploadMode === 'new'}
                className="hidden"
                onChange={handleUpload}
                disabled={
                  isUploading
                  || isReindexing
                  || (uploadMode === 'update' && replacesDocumentId === null)
                }
              />
            </label>
            
          </div>
        </div>

        {message && <p className="text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-2 mb-4 text-sm">{message}</p>}
        {error && <p className="text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-2 mb-4 text-sm">{error}</p>}
        {reindexStatus?.running && (() => {
          const progress = Math.min(Math.max(reindexStatus.progress_percent ?? 0, 0), 100);
          return (
            <div className="text-gray-700 bg-gray-100 border border-gray-200 rounded-lg px-4 py-3 mb-4 text-sm" role="status" aria-live="polite">
              <div className="flex items-center justify-between gap-4 mb-2">
                <span>{reindexStatus.message || 'Đang re-index dữ liệu...'}</span>
                <span className="font-medium tabular-nums">{progress}%</span>
              </div>
              <div
                className="h-2 w-full overflow-hidden rounded-full bg-gray-200"
                role="progressbar"
                aria-label="Tiến độ re-index"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={progress}
              >
                <div className="h-full rounded-full bg-blue-600 transition-all duration-500" style={{ width: `${progress}%` }} />
              </div>
              <p className="mt-2 text-xs text-gray-500">
                Bước {reindexStatus.current_step ?? 0}/{reindexStatus.total_steps ?? 4}
              </p>
            </div>
          );
        })()}
        {uploadProgress && (
          <p className="text-gray-700 bg-gray-100 border border-gray-200 rounded-lg px-4 py-2 mb-4 text-sm" role="status" aria-live="polite">
            Đang upload tuần tự {uploadProgress.current}/{uploadProgress.total}: {uploadProgress.filename}
          </p>
        )}

        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-x-auto">
          <table className="min-w-[1120px] w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-4 py-3 font-medium">Tên tài liệu</th>
                <th className="px-4 py-3 font-medium">Mã tài liệu</th>
                <th className="px-4 py-3 font-medium text-center">Phiên bản</th>
                <th className="px-4 py-3 font-medium">Kích thước</th>
                <th className="px-4 py-3 font-medium">Lập chỉ mục</th>
                <th className="px-4 py-3 font-medium">Hiệu lực</th>
                <th className="px-4 py-3 font-medium">Ngày tải lên</th>
                <th className="px-4 py-3 font-medium text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-500" role="status">
                    Đang tải danh sách tài liệu...
                  </td>
                </tr>
              ) : documents.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                    Chưa có tài liệu nào.
                  </td>
                </tr>
              ) : (
                documents.map((doc) => (
                  <tr key={doc.id} className="border-t border-gray-100">
                    <td className="px-4 py-3 text-gray-800 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-gray-400 flex-shrink-0" />
                      {doc.original_filename}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-600">{doc.document_code}</td>
                    <td className="px-4 py-3 text-center font-medium text-gray-700">v{doc.version_number}</td>
                    <td className="px-4 py-3 text-gray-600">{formatSize(doc.size_bytes)}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusColor[doc.status] || 'bg-gray-100 text-gray-600'}`}>
                        {statusLabel[doc.status] || doc.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${lifecycleColor[doc.lifecycle_status] || 'bg-gray-100 text-gray-600'}`}>
                        {lifecycleLabel[doc.lifecycle_status] || doc.lifecycle_status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{new Date(doc.uploaded_at).toLocaleString('vi-VN')}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleDelete(doc.id)}
                        className="inline-flex items-center gap-1.5 rounded-md border border-red-200 px-2.5 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                        title="Xóa"
                        aria-label={`Xóa ${doc.original_filename}`}
                        disabled={isUploading || isReindexing}
                      >
                        <Trash2 className="w-4 h-4" />
                        Xóa
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}

export default function AdminDocumentsPage() {
  return (
    <RequireAuth role="admin">
      <DocumentsContent />
    </RequireAuth>
  );
}
