import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import type { ReactNode } from 'react';
import type { UserInfo } from '../lib/api';
import * as api from '../lib/api';

interface AuthState {
  user: UserInfo | null;
  loading: boolean;
  login: (loginStr: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const profile = await api.getProfile();
      setUser(profile);
    } catch {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const loginFn = useCallback(async (loginStr: string, password: string) => {
    const resp = await api.login(loginStr, password);
    localStorage.setItem('access_token', resp.access_token);
    localStorage.setItem('refresh_token', resp.refresh_token);
    setUser(resp.user);
  }, []);

  const registerFn = useCallback(
    async (username: string, email: string, password: string) => {
      const resp = await api.register(username, email, password);
      localStorage.setItem('access_token', resp.access_token);
      localStorage.setItem('refresh_token', resp.refresh_token);
      setUser(resp.user);
    },
    [],
  );

  const logout = useCallback(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, loading, login: loginFn, register: registerFn, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}
