"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import {
  clearAllAuth,
  clearKbAdminToken,
  getAccessToken,
  getKbAdminToken,
  setAccessToken,
  setKbAdminToken,
} from "@/lib/auth-storage";
import {
  readCachedUser,
  writeCachedUser,
} from "@/lib/client-cache";
import {
  fetchMe,
  kbAdminLogin,
  login,
  logout,
  register,
  type AuthUser,
} from "@/lib/api";

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (
    username: string,
    password: string,
    displayName?: string,
    email?: string,
  ) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  authorizeKbAdmin: (username: string, password: string) => Promise<void>;
  clearKbAdminAuth: () => void;
  hasKbAdminAccess: () => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    const token = getAccessToken();
    if (!token) {
      writeCachedUser(null);
      setUser(null);
      return;
    }
    try {
      const me = await fetchMe();
      setUser(me);
      writeCachedUser(me);
    } catch {
      clearAllAuth();
      writeCachedUser(null);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      writeCachedUser(null);
      setUser(null);
      setLoading(false);
      return;
    }
    const cached = readCachedUser();
    if (cached) {
      setUser(cached);
      setLoading(false);
      void refreshUser();
      return;
    }
    void refreshUser().finally(() => setLoading(false));
  }, [refreshUser]);

  const handleLogin = useCallback(
    async (username: string, password: string) => {
      const res = await login(username, password);
      setAccessToken(res.access_token);
      setUser(res.user);
      writeCachedUser(res.user);
    },
    [],
  );

  const handleRegister = useCallback(
    async (
      username: string,
      password: string,
      displayName?: string,
      email?: string,
    ) => {
      const res = await register(username, password, displayName, email);
      setAccessToken(res.access_token);
      setUser(res.user);
      writeCachedUser(res.user);
    },
    [],
  );

  const handleLogout = useCallback(async () => {
    try {
      await logout();
    } catch {
      // 忽略登出接口失败，仍清除本地凭证
    }
    clearAllAuth();
    writeCachedUser(null);
    setUser(null);
    router.push("/auth/login");
  }, [router]);

  const authorizeKbAdmin = useCallback(
    async (username: string, password: string) => {
      const res = await kbAdminLogin(username, password);
      setKbAdminToken(res.kb_admin_token);
    },
    [],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isAdmin: user?.role === "admin",
      login: handleLogin,
      register: handleRegister,
      logout: handleLogout,
      refreshUser,
      authorizeKbAdmin,
      clearKbAdminAuth: clearKbAdminToken,
      hasKbAdminAccess: () =>
        user?.role === "admin" || Boolean(getAccessToken() && getKbAdminToken()),
    }),
    [
      user,
      loading,
      handleLogin,
      handleRegister,
      handleLogout,
      refreshUser,
      authorizeKbAdmin,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
