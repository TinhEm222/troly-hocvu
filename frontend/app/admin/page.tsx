'use client';

import { useCallback, useEffect, useState } from 'react';
import RequireAuth from '@/components/RequireAuth';
import AdminNav from '@/components/AdminNav';
import { adminService, StatsResponse } from '@/lib/api';
import { Users, FileText, MessageSquare, Database } from 'lucide-react';

function StatCard({ icon: Icon, label, value }: { icon: any; label: string; value: number | string }) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 flex items-center gap-4">
      <div className="w-11 h-11 rounded-lg bg-green-50 flex items-center justify-center">
        <Icon className="w-5 h-5 text-green-600" />
      </div>
      <div>
        <p className="text-2xl font-semibold text-gray-800">{value}</p>
        <p className="text-sm text-gray-500">{label}</p>
      </div>
    </div>
  );
}

function DashboardContent() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const loadStats = useCallback(async () => {
    setIsLoading(true);
    setError('');
    try {
      setStats(await adminService.getStats());
    } catch {
      setError('Không thể tải thống kê.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  return (
    <div className="flex flex-1">
      <AdminNav />
      <main className="flex-1 p-8 bg-gray-50 overflow-y-auto">
        <h1 className="text-xl font-semibold text-gray-800 mb-6">Thống kê tổng quan</h1>

        {error && (
          <div className="flex items-center gap-3 text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3 mb-4 text-sm">
            <p>{error}</p>
            <button onClick={() => void loadStats()} className="font-medium underline hover:no-underline">
              Thử lại
            </button>
          </div>
        )}

        {isLoading && (
          <p className="text-gray-500" role="status" aria-live="polite">
            Đang tải thống kê...
          </p>
        )}

        {!isLoading && stats && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard icon={Users} label="Tổng người dùng" value={stats.total_users} />
            <StatCard icon={Users} label="Sinh viên" value={stats.total_students} />
            <StatCard icon={FileText} label="Tài liệu đã index" value={stats.total_documents} />
            <StatCard icon={MessageSquare} label="Cuộc trò chuyện" value={stats.total_chat_sessions} />
            <StatCard icon={MessageSquare} label="Tổng tin nhắn" value={stats.total_messages} />
            <StatCard icon={Users} label="Quản trị viên" value={stats.total_admins} />
            <StatCard
              icon={Database}
              label="Vector đã lập chỉ mục"
              value={stats.qdrant_points_count ?? 'N/A'}
            />
          </div>
        )}
      </main>
    </div>
  );
}

export default function AdminDashboardPage() {
  return (
    <RequireAuth role="admin">
      <DashboardContent />
    </RequireAuth>
  );
}
