'use client';

import { ReactNode, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

export default function RequireAuth({
  children,
  role,
}: {
  children: ReactNode;
  role?: 'student' | 'admin';
}) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    if (!user) {
      router.replace('/login');
    } else if (role && user.role !== role) {
      router.replace(user.role === 'admin' ? '/admin' : '/chat');
    }
  }, [user, isLoading, role, router]);

  if (isLoading || !user || (role && user.role !== role)) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50 text-gray-500">
        Đang tải...
      </div>
    );
  }

  return <>{children}</>;
}
