'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { UserResponse } from '@/types';
import { authApi } from '@/lib/api';

interface AuthContextType {
  user: UserResponse | null;
  role: string | null;
  login: (email: string, pass: string) => Promise<void>;
  logout: () => Promise<void>;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    if (!token) {
      setLoading(false);
      return;
    }
    authApi.me().then(data => {
      setUser(data);
    }).catch(() => {
      setUser(null);
      if (typeof window !== 'undefined') {
        localStorage.removeItem('token'); // Clear invalid token
      }
    }).finally(() => {
      setLoading(false);
    });
  }, []);

  const login = async (email: string, pass: string) => {
    await authApi.login(email, pass);
    const data = await authApi.me();
    setUser(data);
  };

  const logout = async () => {
    await authApi.logout();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, role: user?.role || null, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
