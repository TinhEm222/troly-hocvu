'use client';

import { useCallback, useEffect, useState } from 'react';
import RequireAuth from '@/components/RequireAuth';
import AdminNav from '@/components/AdminNav';
import { adminService, AdminUserRecord } from '@/lib/api';
import { Trash2 } from 'lucide-react';

function UsersContent() {
  const [users, setUsers] = useState<AdminUserRecord[]>([]);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const loadUsers = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await adminService.listUsers();
      setUsers(data);
    } catch {
      setError('Không thể tải danh sách người dùng.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const handleDelete = async (user: AdminUserRecord) => {
    if (!window.confirm(`Bạn có chắc muốn xóa tài khoản "${user.email}"?`)) return;

    setError('');
    try {
      await adminService.deleteUser(user.id);
      await loadUsers();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Không thể xóa người dùng.');
    }
  };

  return (
    <div className="flex flex-1">
      <AdminNav />
      <main className="flex-1 p-8 bg-gray-50 overflow-y-auto">
        <h1 className="text-xl font-semibold text-gray-800 mb-6">Quản lý người dùng</h1>

        {error && <p className="text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-2 mb-4 text-sm">{error}</p>}

        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-4 py-3 font-medium">Họ và tên</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Vai trò</th>
                <th className="px-4 py-3 font-medium">Ngày tạo</th>
                <th className="px-4 py-3 font-medium text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-500" role="status">
                    Đang tải danh sách người dùng...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                    Chưa có người dùng nào.
                  </td>
                </tr>
              ) : users.map((u) => (
                <tr key={u.id} className="border-t border-gray-100">
                  <td className="px-4 py-3 text-gray-800">{u.full_name || '-'}</td>
                  <td className="px-4 py-3 text-gray-600">{u.email}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-1 rounded-full text-xs font-medium ${
                        u.role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'
                      }`}
                    >
                      {u.role === 'admin' ? 'Quản trị viên' : 'Sinh viên'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{new Date(u.created_at).toLocaleString('vi-VN')}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleDelete(u)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-red-200 px-2.5 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
                      aria-label={`Xóa ${u.email}`}
                    >
                      <Trash2 className="h-4 w-4" />
                      Xóa
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}

export default function AdminUsersPage() {
  return (
    <RequireAuth role="admin">
      <UsersContent />
    </RequireAuth>
  );
}
