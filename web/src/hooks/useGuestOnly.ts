"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/context/AuthContext";

/** 已登录用户访问登录/注册页时，在 effect 中跳转（避免 render 期间调用 router） */
export function useGuestOnly(redirectTo = "/") {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading && user) {
      router.replace(redirectTo);
    }
  }, [loading, user, router, redirectTo]);

  return { loading, user, ready: !loading && !user };
}
