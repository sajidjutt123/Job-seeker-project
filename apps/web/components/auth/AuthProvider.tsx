"use client";

import { useRouter } from "next/navigation";
import {
  createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode,
} from "react";

import { api, ApiError } from "@/lib/api";
import type { MeResponse, Profile, User } from "@/lib/types";

interface AuthContextValue {
  user: User | null;
  profile: Profile | null;
  stats: MeResponse["stats"];
  loading: boolean;
  isAdmin: boolean;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (input: { email: string; password: string; full_name?: string; city?: string }) => Promise<void>;
  logout: () => Promise<void>;
  setProfile: (profile: Profile) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children, initialUser = null }: { children: ReactNode; initialUser?: User | null }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(initialUser);
  const [profile, setProfileState] = useState<Profile | null>(null);
  const [stats, setStats] = useState<MeResponse["stats"]>({});
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await api.get<MeResponse>("/auth/me", { revalidate: false });
      setUser(me.user);
      setProfileState(me.profile ?? null);
      setStats(me.stats ?? {});
    } catch (error) {
      // 401 simply means "not signed in" — a normal state, not an error to surface.
      if (error instanceof ApiError && error.isUnauthorized) {
        setUser(null);
        setProfileState(null);
        setStats({});
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // A short-lived access token would otherwise expire mid-session; refresh it quietly.
  useEffect(() => {
    if (!user) return;
    const interval = setInterval(
      () => {
        api.post("/auth/refresh", {}).catch(() => undefined);
      },
      20 * 60 * 1000,
    );
    return () => clearInterval(interval);
  }, [user]);

  const login = useCallback(
    async (email: string, password: string) => {
      await api.post("/auth/login", { email, password });
      await refresh();
      router.refresh();
    },
    [refresh, router],
  );

  const register = useCallback(
    async (input: { email: string; password: string; full_name?: string; city?: string }) => {
      await api.post("/auth/register", input);
      await refresh();
      router.refresh();
    },
    [refresh, router],
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout", {});
    } finally {
      setUser(null);
      setProfileState(null);
      setStats({});
      router.push("/");
      router.refresh();
    }
  }, [router]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      profile,
      stats,
      loading,
      isAdmin: user?.role === "admin",
      refresh,
      login,
      register,
      logout,
      setProfile: setProfileState,
    }),
    [user, profile, stats, loading, refresh, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}
