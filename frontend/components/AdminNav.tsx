'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, FileText, Users, LogOut } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';

const navItems = [
  { href: '/admin', label: 'Thống kê', icon: LayoutDashboard },
  { href: '/admin/documents', label: 'Quản lý tài liệu', icon: FileText },
  { href: '/admin/users', label: 'Quản lý người dùng', icon: Users },
];

export default function AdminNav() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <div className="w-64 flex-shrink-0 bg-gray-900 text-gray-200 flex flex-col h-screen">
      <div className="p-5 border-b border-gray-800">
        <p className="font-semibold text-white">Admin Dashboard</p>
        <p className="text-xs text-gray-400 truncate mt-1">{user?.email}</p>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive ? 'bg-green-600 text-white' : 'hover:bg-gray-800 text-gray-300'
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-gray-800">
        <button
          onClick={logout}
          className="w-full flex items-center justify-center gap-2 py-2 text-sm text-gray-300 hover:text-white border border-gray-700 rounded-lg hover:border-gray-500 transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Đăng xuất
        </button>
      </div>
    </div>
  );
}
