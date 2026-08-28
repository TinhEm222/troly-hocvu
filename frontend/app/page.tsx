'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

export default function Home() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    if (!user) {
      router.replace('/login');
    } else if (user.role === 'admin') {
      router.replace('/admin');
    } else {
      router.replace('/chat');
    }
  }, [user, isLoading, router]);

  return (
    <div className="flex h-screen items-center justify-center bg-gray-50 text-gray-500">
      Đang tải...
    </div>
  );
}
