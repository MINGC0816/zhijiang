"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { Spin } from "antd";
import { useAuth } from "@/context/AuthContext";

export default function AuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/auth/login");
    }
  }, [loading, user, router]);

  if (loading) {
    return (
      <main className="app-shell app-shell-loading">
        <Spin size="large" />
      </main>
    );
  }

  if (!user) {
    return <main className="app-shell app-shell-loading" aria-hidden="true" />;
  }

  return children;
}
