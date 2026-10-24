const API_BASE = "/api-proxy";

import {
  clearAccessToken,
  getAccessToken,
  getKbAdminToken,
} from "@/lib/auth-storage";
import {
  invalidateCachedThreadMessages,
  writeCachedThreadMessages,
} from "@/lib/client-cache";

export type AuthUser = {
  user_id: string;
  username: string;
  role: "user" | "admin";
  status: "active" | "frozen";
  display_name: string;
  email: string;
};

export type AuthTokenResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export type KbAdminTokenResponse = {
  kb_admin_token: string;
  token_type: string;
  expires_in_minutes: number;
};

export type ManagedUser = AuthUser & {
  created_at: string;
  updated_at: string;
};

export type AuditLogItem = {
  id: number;
  user_id: string | null;
  username: string | null;
  action: string;
  detail: string;
  ip_address: string;
  created_at: string;
};

export type ChatResponse = {
  answer: string;
  thread_id: string;
};

export type ThreadItem = {
  thread_id: string;
  title: string;
  preview: string;
  user_id: string;
  kb_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type HistoryMessage = {
  role: "user" | "assistant";
  content: string;
};

export type IngestResult = {
  ingested: string[];
  chunk_count: number;
  errors: string[];
};

export type DocumentItem = {
  filename: string;
  indexed: boolean;
  has_raw: boolean;
};

export type DocumentPreviewPage = {
  page: number | null;
  content: string;
};

export type DocumentPreviewResult = {
  filename: string;
  page_count: number;
  content_preview: string;
  pages: DocumentPreviewPage[];
};

export type DocumentChunk = {
  chunk_id: number;
  page: number | null;
  content: string;
};

export type DocumentChunksResult = {
  filename: string;
  from_vectorstore: boolean;
  chunk_count: number;
  chunks: DocumentChunk[];
};

export type RecallHit = {
  source: string;
  page: number | null;
  chunk_id: number | null;
  content: string;
  score: number;
  score_kind?: "distance" | "rrf" | "rerank" | "bm25" | string;
  channels?: string[];
};

export type RecallLane = {
  mode: string;
  label: string;
  hits: RecallHit[];
};

export type RecallResult = {
  query: string;
  limit: number;
  hit_count: number;
  hits: RecallHit[];
  lanes?: RecallLane[];
  reranker_ready?: boolean;
};

export type ChatStreamEvent =
  | { type: "status"; message: string }
  | { type: "tool_start"; name: string; input?: string }
  | { type: "tool_end"; name: string; preview?: string }
  | { type: "token"; text: string }
  | { type: "done"; answer: string; thread_id: string }
  | { type: "error"; message: string };

type ApiFetchOptions = RequestInit & {
  auth?: boolean;
  kbAdmin?: boolean;
};

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    return JSON.stringify(data);
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

async function apiFetch(
  path: string,
  options: ApiFetchOptions = {},
): Promise<Response> {
  const { auth = true, kbAdmin = false, headers, ...rest } = options;
  const reqHeaders = new Headers(headers);
  if (auth) {
    const token = getAccessToken();
    if (token) reqHeaders.set("Authorization", `Bearer ${token}`);
  }
  if (kbAdmin) {
    const kbToken = getKbAdminToken();
    if (kbToken) reqHeaders.set("X-KB-Admin-Token", kbToken);
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: reqHeaders,
  });
  if (res.status === 401 && auth) {
    clearAccessToken();
  }
  return res;
}

// ---------- 认证 ----------

export async function register(
  username: string,
  password: string,
  displayName = "",
  email = "",
): Promise<AuthTokenResponse> {
  const res = await apiFetch("/api/v1/auth/register", {
    method: "POST",
    auth: false,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username,
      password,
      display_name: displayName,
      email,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<AuthTokenResponse>;
}

export async function login(
  username: string,
  password: string,
): Promise<AuthTokenResponse> {
  const res = await apiFetch("/api/v1/auth/login", {
    method: "POST",
    auth: false,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<AuthTokenResponse>;
}

export async function logout(): Promise<void> {
  const res = await apiFetch("/api/v1/auth/logout", { method: "POST" });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function fetchMe(): Promise<AuthUser> {
  const res = await apiFetch("/api/v1/auth/me");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<AuthUser>;
}

export async function kbAdminLogin(
  username: string,
  password: string,
): Promise<KbAdminTokenResponse> {
  const res = await apiFetch("/api/v1/auth/kb-admin-login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<KbAdminTokenResponse>;
}

// ---------- 管理员：用户与审计 ----------

export async function listManagedUsers(): Promise<ManagedUser[]> {
  const res = await apiFetch("/api/v1/admin/users", { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  const data = (await res.json()) as { users: ManagedUser[] };
  return data.users ?? [];
}

export async function updateManagedUser(
  userId: string,
  patch: Partial<Pick<AuthUser, "display_name" | "email" | "status">>,
): Promise<ManagedUser> {
  const res = await apiFetch(`/api/v1/admin/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<ManagedUser>;
}

export async function resetManagedUserPassword(
  userId: string,
  newPassword: string,
): Promise<void> {
  const res = await apiFetch(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/reset-password`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password: newPassword }),
    },
  );
  if (!res.ok) throw new Error(await parseError(res));
}

export async function deleteManagedUser(userId: string): Promise<void> {
  const res = await apiFetch(
    `/api/v1/admin/users/${encodeURIComponent(userId)}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(await parseError(res));
}

export async function listAuditLogs(params?: {
  action?: string;
  user_id?: string;
  limit?: number;
}): Promise<AuditLogItem[]> {
  const search = new URLSearchParams();
  if (params?.action) search.set("action", params.action);
  if (params?.user_id) search.set("user_id", params.user_id);
  if (params?.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  const res = await apiFetch(
    `/api/v1/admin/audit-logs${qs ? `?${qs}` : ""}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error(await parseError(res));
  const data = (await res.json()) as { logs: AuditLogItem[] };
  return data.logs ?? [];
}

// ---------- 问答会话 ----------

export async function listThreads(): Promise<ThreadItem[]> {
  const res = await apiFetch("/api/v1/threads");
  if (!res.ok) throw new Error(await parseError(res));
  const data = (await res.json()) as { threads: ThreadItem[] };
  return data.threads ?? [];
}

export async function createThread(
  title = "新对话",
  kbId?: string,
): Promise<ThreadItem> {
  const res = await apiFetch("/api/v1/threads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, kb_id: kbId ?? null }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<ThreadItem>;
}

const threadMessagesInflight = new Map<string, Promise<HistoryMessage[]>>();

export async function getThreadMessages(
  threadId: string,
): Promise<HistoryMessage[]> {
  const inflight = threadMessagesInflight.get(threadId);
  if (inflight) return inflight;

  const task = (async () => {
    const res = await apiFetch(
      `/api/v1/threads/${encodeURIComponent(threadId)}/messages`,
    );
    if (!res.ok) throw new Error(await parseError(res));
    const data = (await res.json()) as { messages: HistoryMessage[] };
    const messages = data.messages ?? [];
    writeCachedThreadMessages(threadId, messages);
    return messages;
  })();

  threadMessagesInflight.set(threadId, task);
  try {
    return await task;
  } finally {
    threadMessagesInflight.delete(threadId);
  }
}

export async function deleteThread(threadId: string): Promise<void> {
  const res = await apiFetch(
    `/api/v1/threads/${encodeURIComponent(threadId)}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(await parseError(res));
}

export async function chat(
  message: string,
  threadId: string,
): Promise<ChatResponse> {
  invalidateCachedThreadMessages(threadId);
  const res = await apiFetch("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<ChatResponse>;
}

export async function chatStream(
  message: string,
  threadId: string,
  onEvent: (event: ChatStreamEvent) => void,
): Promise<ChatResponse> {
  invalidateCachedThreadMessages(threadId);
  const res = await fetch(`${API_BASE}/api/v1/chat/stream`, {
    method: "POST",
    headers: {
      ...authHeaders(false),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message, thread_id: threadId }),
  });
  if (res.status === 401) clearAccessToken();
  if (!res.ok) throw new Error(await parseError(res));
  if (!res.body) throw new Error("无法读取流式回答");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let doneEvent: ChatResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const evt = JSON.parse(line) as ChatStreamEvent;
      onEvent(evt);
      if (evt.type === "done") {
        doneEvent = { answer: evt.answer, thread_id: evt.thread_id };
      }
      if (evt.type === "error") {
        throw new Error(evt.message || "问答失败");
      }
    }
  }

  if (!doneEvent) throw new Error("问答未完成");
  return doneEvent;
}

// ---------- 知识库管理（需 KB 管理员权限） ----------

export type KnowledgeBase = {
  kb_id: string;
  name: string;
  description: string;
  collection_name?: string;
  created_at?: string;
  updated_at?: string;
};

export type KbDetailStats = {
  kb_id: string;
  name: string;
  total_documents: number;
  total_size_bytes: number;
  indexed_documents: number;
  not_indexed_documents: number;
  chunk_count: number;
};

export type KbStats = {
  kb_count: number;
  kb_names: string[];
  total_documents: number;
  total_size_bytes: number;
  indexed_documents: number;
  not_indexed_documents: number;
  chunk_count: number;
  knowledge_bases?: KbDetailStats[];
};

export async function listKnowledgeBases(): Promise<KnowledgeBase[]> {
  const res = await apiFetch("/api/v1/admin/kbs", {
    cache: "no-store",
    kbAdmin: true,
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data = (await res.json()) as { knowledge_bases: KnowledgeBase[] };
  return data.knowledge_bases ?? [];
}

export async function createKnowledgeBase(
  name: string,
  description = "",
): Promise<KnowledgeBase> {
  const res = await apiFetch("/api/v1/admin/kbs", {
    method: "POST",
    kbAdmin: true,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<KnowledgeBase>;
}

export async function deleteKnowledgeBase(kbId: string): Promise<void> {
  const res = await apiFetch(
    `/api/v1/admin/kbs/${encodeURIComponent(kbId)}`,
    { method: "DELETE", kbAdmin: true },
  );
  if (!res.ok) throw new Error(await parseError(res));
}

export async function updateKnowledgeBase(
  kbId: string,
  patch: { name?: string; description?: string },
): Promise<KnowledgeBase> {
  const res = await apiFetch(
    `/api/v1/admin/kbs/${encodeURIComponent(kbId)}`,
    {
      method: "PATCH",
      kbAdmin: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    },
  );
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<KnowledgeBase>;
}

export async function getKbDetailStats(kbId: string): Promise<KbDetailStats> {
  const res = await apiFetch(
    `/api/v1/admin/kbs/${encodeURIComponent(kbId)}/stats`,
    { cache: "no-store", kbAdmin: true },
  );
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<KbDetailStats>;
}

export async function listChatKnowledgeBases(): Promise<
  Pick<KnowledgeBase, "kb_id" | "name" | "description">[]
> {
  const res = await apiFetch("/api/v1/kbs", { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  const data = (await res.json()) as {
    knowledge_bases: Pick<KnowledgeBase, "kb_id" | "name" | "description">[];
  };
  return data.knowledge_bases ?? [];
}

export async function getKbStats(): Promise<KbStats> {
  const res = await apiFetch("/api/v1/admin/stats", {
    cache: "no-store",
    kbAdmin: true,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<KbStats>;
}

export async function listDocuments(kbId: string, query = ""): Promise<DocumentItem[]> {
  const params = new URLSearchParams();
  if (query.trim()) params.set("query", query.trim());
  const qs = params.toString();
  const res = await apiFetch(
    `/api/v1/admin/kbs/${encodeURIComponent(kbId)}/documents${qs ? `?${qs}` : ""}`,
    { cache: "no-store", kbAdmin: true },
  );
  if (!res.ok) throw new Error(await parseError(res));
  const data = (await res.json()) as { documents: unknown };
  const rows = data.documents ?? [];
  return rows.map((item) => {
    if (typeof item === "string") {
      return { filename: item, indexed: true, has_raw: true };
    }
    const row = item as DocumentItem;
    return {
      filename: row.filename,
      indexed: Boolean(row.indexed),
      has_raw: Boolean(row.has_raw),
    };
  });
}

export type IngestProgressEvent = {
  phase: "start" | "processing" | "done" | "error";
  percent?: number;
  total?: number;
  current?: number;
  filename?: string;
  message?: string;
  result?: IngestResult;
};

function authHeaders(kbAdmin = false): HeadersInit {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (kbAdmin) {
    const kbToken = getKbAdminToken();
    if (kbToken) headers["X-KB-Admin-Token"] = kbToken;
  }
  return headers;
}

export async function ingestAllWithProgress(
  kbId: string,
  onProgress: (event: IngestProgressEvent) => void,
): Promise<IngestResult> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/kbs/${encodeURIComponent(kbId)}/ingest/stream`,
    {
      method: "POST",
      headers: {
        ...authHeaders(true),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ replace: true }),
    },
  );
  if (res.status === 401) clearAccessToken();
  if (!res.ok) throw new Error(await parseError(res));
  if (!res.body) throw new Error("无法读取入库进度");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: IngestResult | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const evt = JSON.parse(line) as IngestProgressEvent;
      onProgress(evt);
      if (evt.phase === "done" && evt.result) result = evt.result;
      if (evt.phase === "error") {
        throw new Error(evt.message || "入库失败");
      }
    }
  }

  if (!result) throw new Error("入库未完成");
  return result;
}

export async function ingestAll(kbId: string): Promise<IngestResult> {
  const res = await apiFetch(
    `/api/v1/admin/kbs/${encodeURIComponent(kbId)}/ingest`,
    {
      method: "POST",
      kbAdmin: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ replace: true }),
    },
  );
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<IngestResult>;
}

export function uploadFileWithProgress(
  kbId: string,
  file: File,
  onProgress: (percent: number) => void,
): Promise<{ saved: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(
      "POST",
      `${API_BASE}/api/v1/admin/kbs/${encodeURIComponent(kbId)}/upload`,
    );
    const headers = authHeaders(true);
    Object.entries(headers).forEach(([key, value]) => {
      xhr.setRequestHeader(key, value);
    });
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
    };
    xhr.onload = () => {
      if (xhr.status === 401) clearAccessToken();
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText) as { saved: string };
          onProgress(100);
          resolve(data);
        } catch {
          reject(new Error("上传响应解析失败"));
        }
        return;
      }
      try {
        const data = JSON.parse(xhr.responseText) as { detail?: string };
        reject(new Error(data.detail || `上传失败 HTTP ${xhr.status}`));
      } catch {
        reject(new Error(`上传失败 HTTP ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("上传网络错误"));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export async function uploadFile(
  kbId: string,
  file: File,
): Promise<{ saved: string }> {
  return uploadFileWithProgress(kbId, file, () => {});
}

export async function getDocumentPreview(
  kbId: string,
  filename: string,
): Promise<DocumentPreviewResult> {
  const res = await apiFetch(
    `/api/v1/admin/kbs/${encodeURIComponent(kbId)}/documents/${encodeURIComponent(filename)}/preview`,
    { cache: "no-store", kbAdmin: true },
  );
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<DocumentPreviewResult>;
}

export async function getDocumentChunks(
  kbId: string,
  filename: string,
): Promise<DocumentChunksResult> {
  const res = await apiFetch(
    `/api/v1/admin/kbs/${encodeURIComponent(kbId)}/documents/${encodeURIComponent(filename)}/chunks`,
    { cache: "no-store", kbAdmin: true },
  );
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<DocumentChunksResult>;
}

export async function deleteDocument(
  kbId: string,
  filename: string,
): Promise<{ ok: boolean; filename: string }> {
  const res = await apiFetch(
    `/api/v1/admin/kbs/${encodeURIComponent(kbId)}/documents/${encodeURIComponent(filename)}`,
    { method: "DELETE", kbAdmin: true },
  );
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<{ ok: boolean; filename: string }>;
}

export async function testRecall(
  kbId: string,
  query: string,
  limit = 10,
): Promise<RecallResult> {
  const params = new URLSearchParams({ query, limit: String(limit) });
  const res = await apiFetch(
    `/api/v1/admin/kbs/${encodeURIComponent(kbId)}/recall?${params}`,
    { cache: "no-store", kbAdmin: true },
  );
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<RecallResult>;
}
