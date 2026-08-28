'use client';

import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import {
  AuthUser,
  authService,
  clearAuth,
  getStoredUser,
  TOKEN_STORAGE_KEY,
  storeAuth,
} from './api';

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  register: (email: string, password: string, fullName: string) => Promise<AuthUser>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const bootstrapAuth = async () => {
      const stored = getStoredUser();
      const token = typeof window !== 'undefined' ? localStorage.getItem(TOKEN_STORAGE_KEY) : null;

      if (!stored || !token) {
        clearAuth();
        setUser(null);
        setIsLoading(false);
        return;
      }

      try {
        const me = await authService.me();
        setUser(me);
      } catch {
        clearAuth();
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    void bootstrapAuth();
  }, []);

  const login = async (email: string, password: string) => {
    const { access_token, user: authUser } = await authService.login(email, password);
    storeAuth(access_token, authUser);
    setUser(authUser);
    return authUser;
  };

  const register = async (email: string, password: string, fullName: string) => {
    const { access_token, user: authUser } = await authService.register(email, password, fullName);
    storeAuth(access_token, authUser);
    setUser(authUser);
    return authUser;
  };

  const logout = () => {
    clearAuth();
    setUser(null);
    router.push('/login');
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}
