import type { AuthUser, HistoryMessage, ThreadItem } from "@/lib/api";

const USER_KEY = "qizhi_user_profile";
const THREADS_KEY = "qizhi_threads";
const MESSAGES_PREFIX = "qizhi_msgs:";

export function readCachedUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function writeCachedUser(user: AuthUser | null): void {
  if (typeof window === "undefined") return;
  if (!user) {
    sessionStorage.removeItem(USER_KEY);
    return;
  }
  sessionStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function readCachedThreads(): ThreadItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = sessionStorage.getItem(THREADS_KEY);
    return raw ? (JSON.parse(raw) as ThreadItem[]) : [];
  } catch {
    return [];
  }
}

export function writeCachedThreads(threads: ThreadItem[]): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(THREADS_KEY, JSON.stringify(threads));
}

export function readCachedThreadMessages(threadId: string): HistoryMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = sessionStorage.getItem(`${MESSAGES_PREFIX}${threadId}`);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as { messages: HistoryMessage[] };
    return parsed.messages ?? [];
  } catch {
    return [];
  }
}

export function writeCachedThreadMessages(
  threadId: string,
  messages: HistoryMessage[],
): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(
    `${MESSAGES_PREFIX}${threadId}`,
    JSON.stringify({ at: Date.now(), messages }),
  );
}

export function invalidateCachedThreadMessages(threadId: string): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(`${MESSAGES_PREFIX}${threadId}`);
}
