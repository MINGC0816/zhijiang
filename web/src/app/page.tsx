"use client";

import { useCallback, useEffect, useState } from "react";
import { App } from "antd";
import AuthGuard from "@/components/AuthGuard";
import ChatPanel from "@/components/ChatPanel";
import SessionSidebar from "@/components/SessionSidebar";
import {
  readCachedThreads,
  writeCachedThreads,
} from "@/lib/client-cache";
import {
  createThread,
  listThreads,
  type ThreadItem,
} from "@/lib/api";

const STORAGE_KEY = "qizhi_active_thread_id";

function pickActiveId(rows: ThreadItem[]): string | null {
  if (rows.length === 0) return null;
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved && rows.some((t) => t.thread_id === saved)) return saved;
  return rows[0].thread_id;
}

function HomeContent() {
  const { message } = App.useApp();
  const [threads, setThreads] = useState<ThreadItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshThreads = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await listThreads();
      setThreads(rows);
      writeCachedThreads(rows);
      return rows;
    } catch (e) {
      message.error(e instanceof Error ? e.message : "加载会话失败");
      return [] as ThreadItem[];
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    let cancelled = false;

    const cached = readCachedThreads();
    if (cached.length > 0) {
      setThreads(cached);
      const cachedActiveId = pickActiveId(cached);
      if (cachedActiveId) setActiveId(cachedActiveId);
      setLoading(false);
    }

    void (async () => {
      try {
        const rows = await listThreads();
        if (cancelled) return;
        setThreads(rows);
        writeCachedThreads(rows);
        const nextId = pickActiveId(rows);
        if (nextId) {
          setActiveId(nextId);
          localStorage.setItem(STORAGE_KEY, nextId);
        } else {
          const t = await createThread();
          if (cancelled) return;
          const created = [t];
          setThreads(created);
          writeCachedThreads(created);
          setActiveId(t.thread_id);
          localStorage.setItem(STORAGE_KEY, t.thread_id);
        }
      } catch (e) {
        if (!cancelled) {
          message.error(e instanceof Error ? e.message : "加载会话失败");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [message]);

  const onSelect = (id: string) => {
    setActiveId(id);
    localStorage.setItem(STORAGE_KEY, id);
  };

  const onCreate = async () => {
    try {
      const t = await createThread();
      await refreshThreads();
      setActiveId(t.thread_id);
      localStorage.setItem(STORAGE_KEY, t.thread_id);
    } catch (e) {
      message.error(e instanceof Error ? e.message : "创建会话失败");
    }
  };

  const onDeleted = async () => {
    const rows = await refreshThreads();
    if (activeId && !rows.some((t) => t.thread_id === activeId)) {
      if (rows[0]) {
        setActiveId(rows[0].thread_id);
        localStorage.setItem(STORAGE_KEY, rows[0].thread_id);
      } else {
        const t = await createThread();
        setThreads([t]);
        writeCachedThreads([t]);
        setActiveId(t.thread_id);
        localStorage.setItem(STORAGE_KEY, t.thread_id);
      }
    }
  };

  return (
    <main className="app-shell">
      <SessionSidebar
        threads={threads}
        activeId={activeId}
        loading={loading}
        onSelect={onSelect}
        onCreate={() => void onCreate()}
        onDeleted={() => void onDeleted()}
      />
      <ChatPanel
        threadId={activeId}
        onChatted={() => void refreshThreads()}
      />
    </main>
  );
}

export default function HomePage() {
  return (
    <AuthGuard>
      <HomeContent />
    </AuthGuard>
  );
}
