"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  App,
  Button,
  Empty,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Progress,
  Segmented,
  Spin,
  Statistic,
  Tag,
  Typography,
  Upload,
} from "antd";
import {
  CloudUploadOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FolderAddOutlined,
  PieChartOutlined,
  PlusOutlined,
  RightOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import AdminLoginPanel from "@/components/AdminLoginPanel";
import { useAuth } from "@/context/AuthContext";
import { getKbAdminToken } from "@/lib/auth-storage";
import {
  createKnowledgeBase,
  deleteDocument,
  deleteKnowledgeBase,
  getDocumentChunks,
  getDocumentPreview,
  getKbDetailStats,
  getKbStats,
  ingestAllWithProgress,
  listDocuments,
  listKnowledgeBases,
  testRecall,
  updateKnowledgeBase,
  uploadFileWithProgress,
  type DocumentChunk,
  type DocumentItem,
  type KbDetailStats,
  type KbStats,
  type KnowledgeBase,
  type RecallHit,
  type RecallLane,
} from "@/lib/api";

const { Text, Title, Paragraph } = Typography;

type WorkspaceView = "stats" | "docs";
type KbPanelView = "documents" | "recall";

function formatRecallScore(hit: RecallHit): string {
  const kind = hit.score_kind || "distance";
  if (kind === "distance") return `距离 ${hit.score.toFixed(4)}`;
  if (kind === "rrf") return `RRF ${hit.score.toFixed(4)}`;
  if (kind === "rerank") return `Rerank ${hit.score.toFixed(3)}`;
  if (kind === "bm25") return `BM25 ${hit.score.toFixed(2)}`;
  return `分数 ${hit.score.toFixed(4)}`;
}

function channelLabel(channels?: string[]): string | null {
  if (!channels?.length) return null;
  const map: Record<string, string> = { vector: "向量", bm25: "BM25" };
  return channels.map((c) => map[c] || c).join(" + ");
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const val = bytes / 1024 ** i;
  return `${val.toFixed(i === 0 ? 0 : 2)} ${units[i]}`;
}

function formatDate(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export default function AdminPage() {
  const router = useRouter();
  const { user, loading: authLoading, isAdmin } = useAuth();
  const { message } = App.useApp();
  const [kbReady, setKbReady] = useState(false);
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [activeKbId, setActiveKbId] = useState<string | null>(null);
  const [kbListLoading, setKbListLoading] = useState(false);
  const [createKbOpen, setCreateKbOpen] = useState(false);
  const [createKbName, setCreateKbName] = useState("");
  const [createKbDesc, setCreateKbDesc] = useState("");
  const [creatingKb, setCreatingKb] = useState(false);
  const [renameKbOpen, setRenameKbOpen] = useState(false);
  const [renameKbId, setRenameKbId] = useState<string | null>(null);
  const [renameKbName, setRenameKbName] = useState("");
  const [renameKbDesc, setRenameKbDesc] = useState("");
  const [renamingKb, setRenamingKb] = useState(false);
  const [kbDetailStats, setKbDetailStats] = useState<KbDetailStats | null>(null);
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [totalDocCount, setTotalDocCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadFileName, setUploadFileName] = useState("");
  const [ingestProgress, setIngestProgress] = useState<number | null>(null);
  const [ingestStatus, setIngestStatus] = useState("");
  const [activeDoc, setActiveDoc] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewText, setPreviewText] = useState("");
  const [pageCount, setPageCount] = useState(0);
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [chunkCount, setChunkCount] = useState(0);
  const [fromVectorstore, setFromVectorstore] = useState(false);
  const [activeTab, setActiveTab] = useState("preview");
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>("stats");
  const [kbPanelView, setKbPanelView] = useState<KbPanelView>("documents");
  const [docFilterQuery, setDocFilterQuery] = useState("");
  const [appliedDocFilter, setAppliedDocFilter] = useState("");
  const [stats, setStats] = useState<KbStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const [recallQuery, setRecallQuery] = useState("");
  const [recallLimit, setRecallLimit] = useState(10);
  const [recallLoading, setRecallLoading] = useState(false);
  const [recallHits, setRecallHits] = useState<RecallHit[]>([]);
  const [recallLanes, setRecallLanes] = useState<RecallLane[]>([]);
  const [rerankerReady, setRerankerReady] = useState(false);
  const [testedRecallQuery, setTestedRecallQuery] = useState("");

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/auth/login");
      return;
    }
    if (isAdmin || getKbAdminToken()) {
      setKbReady(true);
      return;
    }
    setKbReady(false);
  }, [authLoading, user, isAdmin, router]);

  const loadKbs = useCallback(async () => {
    setKbListLoading(true);
    try {
      const rows = await listKnowledgeBases();
      setKbs(rows);
      setActiveKbId((prev) => {
        if (prev && rows.some((k) => k.kb_id === prev)) return prev;
        return rows[0]?.kb_id ?? null;
      });
      return rows;
    } catch (e) {
      message.error(e instanceof Error ? e.message : "加载知识库列表失败");
      return [] as KnowledgeBase[];
    } finally {
      setKbListLoading(false);
    }
  }, [message]);

  const refresh = useCallback(
    async (filterQuery = appliedDocFilter) => {
      if (!activeKbId) {
        setDocs([]);
        setTotalDocCount(0);
        setActiveDoc(null);
        return [] as DocumentItem[];
      }
      setLoading(true);
      try {
        const [rows, allRows] = await Promise.all([
          listDocuments(activeKbId, filterQuery),
          filterQuery ? listDocuments(activeKbId) : Promise.resolve(null),
        ]);
        setDocs(rows);
        if (allRows) setTotalDocCount(allRows.length);
        else setTotalDocCount(rows.length);

        if (rows.length === 0) {
          setActiveDoc(null);
          return rows;
        }
        setActiveDoc((prev) => {
          if (prev && rows.some((d) => d.filename === prev)) return prev;
          return rows[0].filename;
        });
        return rows;
      } catch (e) {
        message.error(e instanceof Error ? e.message : "加载文档失败");
        return [] as DocumentItem[];
      } finally {
        setLoading(false);
      }
    },
    [activeKbId, appliedDocFilter, message],
  );

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const global = await getKbStats();
      setStats(global);
      if (activeKbId) {
        setKbDetailStats(await getKbDetailStats(activeKbId));
      } else {
        setKbDetailStats(null);
      }
    } catch (e) {
      message.error(e instanceof Error ? e.message : "加载统计失败");
    } finally {
      setStatsLoading(false);
    }
  }, [activeKbId, message]);

  const refreshAll = useCallback(async () => {
    const rows = await refresh();
    await loadStats();
    return rows;
  }, [refresh, loadStats]);

  const loadPreview = useCallback(
    async (filename: string) => {
      if (!activeKbId) return;
      setPreviewLoading(true);
      setPreviewText("");
      setChunks([]);
      setPageCount(0);
      setChunkCount(0);
      setFromVectorstore(false);
      setPreviewError(null);
      try {
        const [previewSettled, chunkSettled] = await Promise.allSettled([
          getDocumentPreview(activeKbId, filename),
          getDocumentChunks(activeKbId, filename),
        ]);

        const errors: string[] = [];

        if (previewSettled.status === "fulfilled") {
          setPreviewText(previewSettled.value.content_preview || "");
          setPageCount(previewSettled.value.page_count || 0);
        } else {
          setPreviewText("");
          setPageCount(0);
          const reason = previewSettled.reason;
          errors.push(
            reason instanceof Error ? reason.message : "原文预览失败",
          );
        }

        if (chunkSettled.status === "fulfilled") {
          setChunks(chunkSettled.value.chunks || []);
          setChunkCount(chunkSettled.value.chunk_count || 0);
          setFromVectorstore(Boolean(chunkSettled.value.from_vectorstore));
        } else {
          setChunks([]);
          setChunkCount(0);
          setFromVectorstore(false);
          const reason = chunkSettled.reason;
          errors.push(
            reason instanceof Error ? reason.message : "切片预览失败",
          );
        }

        if (errors.length) {
          const uniq = [...new Set(errors)];
          setPreviewError(uniq.join("；"));
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : "加载预览失败";
        setPreviewError(msg);
        message.error(msg);
      } finally {
        setPreviewLoading(false);
      }
    },
    [activeKbId, message],
  );

  useEffect(() => {
    setRecallHits([]);
    setTestedRecallQuery("");
  }, [activeKbId]);

  useEffect(() => {
    if (!kbReady) return;
    void loadKbs();
  }, [kbReady, loadKbs]);

  useEffect(() => {
    if (!kbReady || !activeKbId) return;
    void refresh();
    void loadStats();
  }, [kbReady, activeKbId, refresh, loadStats]);

  useEffect(() => {
    if (!activeDoc || workspaceView !== "docs" || kbPanelView !== "documents") {
      if (!activeDoc) {
        setPreviewText("");
        setChunks([]);
      }
      return;
    }
    void loadPreview(activeDoc);
  }, [activeDoc, loadPreview, workspaceView, kbPanelView]);

  const onIngest = async () => {
    if (!activeKbId) return;
    setIngesting(true);
    setIngestProgress(0);
    setIngestStatus("准备重建索引…");
    try {
      const result = await ingestAllWithProgress(activeKbId, (evt) => {
        if (typeof evt.percent === "number") setIngestProgress(evt.percent);
        if (evt.message) setIngestStatus(evt.message);
      });
      if (result.errors?.length) {
        message.warning(`入库完成，但有错误：${result.errors.join("；")}`);
      } else {
        message.success(
          `已入库 ${result.ingested.length} 个文件，共 ${result.chunk_count} 个片段`,
        );
      }
      await refreshAll();
      if (activeDoc) await loadPreview(activeDoc);
    } catch (e) {
      message.error(e instanceof Error ? e.message : "入库失败");
    } finally {
      setIngesting(false);
      window.setTimeout(() => {
        setIngestProgress(null);
        setIngestStatus("");
      }, 800);
    }
  };

  const onDeleteDoc = async (filename: string) => {
    if (!activeKbId) return;
    try {
      await deleteDocument(activeKbId, filename);
      message.success(`已删除 ${filename}`);
      const rows = await refreshAll();
      if (activeDoc === filename) {
        setActiveDoc(rows[0]?.filename ?? null);
        setPreviewText("");
        setChunks([]);
        setPageCount(0);
        setChunkCount(0);
        setPreviewError(null);
      }
    } catch (e) {
      message.error(e instanceof Error ? e.message : "删除失败");
    }
  };

  const onDocSearch = (value?: string) => {
    const q = (value ?? docFilterQuery).trim();
    setAppliedDocFilter(q);
    void refresh(q);
  };

  const onRecallTest = async (value?: string) => {
    if (!activeKbId) return;
    const q = (value ?? recallQuery).trim();
    if (!q) {
      message.warning("请输入测试问题");
      return;
    }
    setRecallLoading(true);
    try {
      const result = await testRecall(activeKbId, q, recallLimit);
      const lanes = result.lanes?.length
        ? result.lanes
        : [{ mode: "vector", label: "仅向量", hits: result.hits }];
      setRecallLanes(lanes);
      setRecallHits(result.hits);
      setRerankerReady(Boolean(result.reranker_ready));
      setTestedRecallQuery(result.query);
      if (result.hit_count === 0) {
        message.info("未召回任何切片，请确认已重建索引");
      }
    } catch (e) {
      setRecallHits([]);
      setRecallLanes([]);
      message.error(e instanceof Error ? e.message : "召回测试失败");
    } finally {
      setRecallLoading(false);
    }
  };

  const openRecallHit = (hit: RecallHit) => {
    setKbPanelView("documents");
    setActiveDoc(hit.source);
    setActiveTab("chunks");
  };

  const onCreateKb = async () => {
    const name = createKbName.trim();
    if (!name) {
      message.warning("请输入知识库名称");
      return;
    }
    setCreatingKb(true);
    try {
      const row = await createKnowledgeBase(name, createKbDesc.trim());
      message.success(`已创建知识库「${row.name}」`);
      setCreateKbOpen(false);
      setCreateKbName("");
      setCreateKbDesc("");
      await loadKbs();
      setActiveKbId(row.kb_id);
      setWorkspaceView("docs");
    } catch (e) {
      message.error(e instanceof Error ? e.message : "创建知识库失败");
    } finally {
      setCreatingKb(false);
    }
  };

  const onDeleteKb = async (kbId: string) => {
    try {
      await deleteKnowledgeBase(kbId);
      message.success("已删除知识库");
      const rows = await loadKbs();
      if (activeKbId === kbId) {
        setActiveKbId(rows[0]?.kb_id ?? null);
      }
      await loadStats();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "删除知识库失败");
    }
  };

  const openRenameKb = (kb: KnowledgeBase) => {
    setRenameKbId(kb.kb_id);
    setRenameKbName(kb.name);
    setRenameKbDesc(kb.description || "");
    setRenameKbOpen(true);
  };

  const onRenameKb = async () => {
    if (!renameKbId) return;
    const name = renameKbName.trim();
    if (!name) {
      message.warning("请输入知识库名称");
      return;
    }
    setRenamingKb(true);
    try {
      await updateKnowledgeBase(renameKbId, {
        name,
        description: renameKbDesc.trim(),
      });
      message.success("知识库已重命名");
      setRenameKbOpen(false);
      setRenameKbId(null);
      setRenameKbName("");
      setRenameKbDesc("");
      await loadKbs();
      await loadStats();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "重命名失败");
    } finally {
      setRenamingKb(false);
    }
  };

  const activeKb = kbs.find((k) => k.kb_id === activeKbId) ?? null;
  const activeMeta = docs.find((d) => d.filename === activeDoc) ?? null;
  const globalStats = stats;
  const displayStats =
    workspaceView === "stats" ? globalStats : kbDetailStats ?? globalStats;

  const kbCards = useMemo(() => {
    const statMap = new Map(
      (stats?.knowledge_bases ?? []).map((item) => [item.kb_id, item]),
    );
    return kbs.map((kb) => {
      const detail = statMap.get(kb.kb_id);
      return {
        ...kb,
        total_documents: detail?.total_documents ?? 0,
        total_size_bytes: detail?.total_size_bytes ?? 0,
        indexed_documents: detail?.indexed_documents ?? 0,
        not_indexed_documents: detail?.not_indexed_documents ?? 0,
        chunk_count: detail?.chunk_count ?? 0,
      };
    });
  }, [kbs, stats]);

  const enterKbWorkspace = (
    kbId: string,
    panel: KbPanelView = "documents",
  ) => {
    setActiveKbId(kbId);
    setActiveDoc(null);
    setDocFilterQuery("");
    setAppliedDocFilter("");
    setKbPanelView(panel);
    setWorkspaceView("docs");
  };
  const docListLabel =
    appliedDocFilter && docs.length !== totalDocCount
      ? `${docs.length} / ${totalDocCount} 个`
      : `${docs.length} 个`;

  if (authLoading || !user) {
    return <main className="admin-shell admin-shell-loading" />;
  }

  if (!kbReady) {
    return (
      <AdminLoginPanel
        onSuccess={() => setKbReady(true)}
        onBack={() => router.push("/")}
      />
    );
  }

  return (
    <main className="admin-shell">
      <header className="admin-header">
        <div className="chat-brand">
          <Image
            src="/logo.png"
            alt="智匠 Logo"
            width={42}
            height={42}
            className="kb-brand-mark"
          />
          <div>
            <Title level={3} className="kb-brand-title">
              智匠 · 知识库管理
            </Title>
            <Text className="kb-brand-sub">
              知识库统计与分库文档管理
            </Text>
          </div>
        </div>
        <div className="admin-header-actions">
          <Button
            type={workspaceView === "stats" ? "primary" : "default"}
            icon={<PieChartOutlined />}
            onClick={() => {
              setWorkspaceView("stats");
              setActiveDoc(null);
            }}
          >
            知识库统计
          </Button>
        </div>
      </header>

      <section
        className={`admin-workspace${
          workspaceView === "stats"
            ? " admin-workspace-stats"
            : kbPanelView === "recall"
              ? " admin-workspace-recall"
              : ""
        }`}
      >
        <aside className="admin-kb-pane">
          <div className="admin-pane-title">
            <Text strong>知识库</Text>
            <Button
              type="text"
              size="small"
              icon={<FolderAddOutlined />}
              onClick={() => setCreateKbOpen(true)}
            />
          </div>
          <div className="admin-kb-list">
            {kbListLoading && kbs.length === 0 ? (
              <div className="admin-center">
                <Spin />
              </div>
            ) : kbs.length === 0 ? (
              <Empty description="暂无知识库" image={Empty.PRESENTED_IMAGE_SIMPLE}>
                <Button type="primary" size="small" onClick={() => setCreateKbOpen(true)}>
                  创建第一个
                </Button>
              </Empty>
            ) : (
              <ul className="admin-kb-ul">
                {kbs.map((kb) => (
                  <li key={kb.kb_id}>
                    <div
                      className={`admin-kb-item${
                        activeKbId === kb.kb_id ? " is-active" : ""
                      }`}
                    >
                      <button
                        type="button"
                        className="admin-kb-select"
                        onClick={() => {
                          setActiveKbId(kb.kb_id);
                          setActiveDoc(null);
                          setDocFilterQuery("");
                          setAppliedDocFilter("");
                          setKbPanelView("documents");
                          setWorkspaceView("docs");
                        }}
                      >
                        <DatabaseOutlined />
                        <span className="admin-kb-name" title={kb.name}>
                          {kb.name}
                        </span>
                      </button>
                      <Button
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        title="重命名"
                        onClick={(e) => {
                          e.stopPropagation();
                          openRenameKb(kb);
                        }}
                      />
                      {kbs.length > 1 ? (
                        <Popconfirm
                          title="删除知识库"
                          description={`将删除「${kb.name}」下全部文档与向量数据，确认？`}
                          okText="删除"
                          cancelText="取消"
                          okButtonProps={{ danger: true }}
                          onConfirm={() => void onDeleteKb(kb.kb_id)}
                        >
                          <Button
                            type="text"
                            danger
                            size="small"
                            icon={<DeleteOutlined />}
                            onClick={(e) => e.stopPropagation()}
                          />
                        </Popconfirm>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        {workspaceView === "docs" && kbPanelView === "documents" ? (
        <aside className="admin-doc-pane">
          <div className="admin-pane-title">
            <Text strong>文档列表</Text>
            <Text type="secondary">
              {activeKb ? `${activeKb.name} · ${docListLabel}` : docListLabel}
            </Text>
          </div>
          <div className="admin-doc-filter">
            <Input.Search
              placeholder="查找知识库文件…"
              value={docFilterQuery}
              allowClear
              enterButton={<SearchOutlined />}
              onChange={(e) => {
                const v = e.target.value;
                setDocFilterQuery(v);
                if (!v.trim()) {
                  setAppliedDocFilter("");
                  void refresh("");
                }
              }}
              onSearch={(v) => onDocSearch(v)}
            />
          </div>
          <div className="admin-doc-list">
            {loading && docs.length === 0 ? (
              <div className="admin-center">
                <Spin />
              </div>
            ) : docs.length === 0 ? (
              <Empty
                description={
                  !activeKbId
                    ? "请先选择或创建知识库"
                    : appliedDocFilter
                      ? "无匹配文件"
                      : "暂无文档，请先上传"
                }
              />
            ) : (
              <ul className="kb-doc-ul">
                {docs.map((item) => (
                  <li key={item.filename}>
                    <div
                      className={`admin-doc-btn${
                        activeDoc === item.filename &&
                        kbPanelView === "documents"
                          ? " is-active"
                          : ""
                      }`}
                    >
                      <button
                        type="button"
                        className="admin-doc-select"
                        onClick={() => {
                          setKbPanelView("documents");
                          setActiveDoc(item.filename);
                        }}
                      >
                        <span className="kb-doc-row">
                          <FileTextOutlined />
                          <span className="admin-doc-name" title={item.filename}>
                            {item.filename}
                          </span>
                        </span>
                        <span className="admin-doc-tags">
                          {item.indexed ? (
                            <Tag color="success">已入库</Tag>
                          ) : (
                            <Tag>未入库</Tag>
                          )}
                          {!item.has_raw ? (
                            <Tag color="warning">无原文</Tag>
                          ) : null}
                        </span>
                      </button>
                      <Popconfirm
                        title="删除文档"
                        description="将同时删除原文与向量库切片，确认？"
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                        onConfirm={() => void onDeleteDoc(item.filename)}
                      >
                        <Button
                          type="text"
                          danger
                          size="small"
                          className="admin-doc-del"
                          icon={<DeleteOutlined />}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </Popconfirm>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
        ) : null}

        <section className="admin-preview-pane">
          {workspaceView === "stats" ? (
            <>
              <div className="admin-preview-head">
                <div>
                  <Title level={4} className="admin-preview-title">
                    知识库统计
                  </Title>
                  <Paragraph type="secondary" className="admin-preview-meta">
                    全部知识库汇总概况 · 下方卡片可查看各库详情并进入管理
                  </Paragraph>
                </div>
              </div>
              <div className="admin-scroll-area">
                {statsLoading && !stats ? (
                  <div className="admin-center">
                    <Spin description="加载统计…" />
                  </div>
                ) : displayStats ? (
                  <>
                    <div className="admin-stats-grid">
                      {"kb_count" in displayStats ? (
                        <article className="admin-stat-card">
                          <Statistic
                            title="知识库数量"
                            value={displayStats.kb_count}
                            suffix="个"
                          />
                          {displayStats.kb_names.length > 0 ? (
                            <Text type="secondary" className="admin-stat-sub">
                              {displayStats.kb_names.join("、")}
                            </Text>
                          ) : null}
                        </article>
                      ) : null}
                      <article className="admin-stat-card">
                        <Statistic
                          title="文档总数"
                          value={displayStats.total_documents}
                          suffix="个"
                        />
                      </article>
                      <article className="admin-stat-card">
                        <Statistic
                          title="文档总大小"
                          value={formatBytes(displayStats.total_size_bytes)}
                        />
                      </article>
                      <article className="admin-stat-card admin-stat-card-success">
                        <Statistic
                          title="已入库文档"
                          value={displayStats.indexed_documents}
                          suffix="个"
                        />
                      </article>
                      <article className="admin-stat-card admin-stat-card-warn">
                        <Statistic
                          title="未入库文档"
                          value={displayStats.not_indexed_documents}
                          suffix="个"
                        />
                      </article>
                      <article className="admin-stat-card">
                        <Statistic
                          title="向量切片总数"
                          value={displayStats.chunk_count}
                          suffix="条"
                        />
                      </article>
                    </div>
                    {kbCards.length > 0 ? (
                      <div className="admin-kb-card-section">
                        <div className="admin-kb-card-section-head">
                          <Title level={5} className="admin-kb-card-section-title">
                            知识库列表
                          </Title>
                          <Button
                            type="primary"
                            size="small"
                            icon={<PlusOutlined />}
                            onClick={() => setCreateKbOpen(true)}
                          >
                            创建知识库
                          </Button>
                        </div>
                        <div className="admin-kb-card-grid">
                          {kbCards.map((item) => (
                            <article
                              key={item.kb_id}
                              className={`admin-kb-card${
                                activeKbId === item.kb_id ? " is-active" : ""
                              }`}
                            >
                              <header className="admin-kb-card-head">
                                <div className="admin-kb-card-icon">
                                  <DatabaseOutlined />
                                </div>
                                <div className="admin-kb-card-titles">
                                  <div className="admin-kb-card-name-row">
                                    <Title level={5} className="admin-kb-card-name">
                                      {item.name}
                                    </Title>
                                    <Button
                                      type="text"
                                      size="small"
                                      icon={<EditOutlined />}
                                      title="重命名"
                                      onClick={() => openRenameKb(item)}
                                    />
                                  </div>
                                  <Text type="secondary" className="admin-kb-card-desc">
                                    {item.description?.trim() || "暂无描述"}
                                  </Text>
                                </div>
                              </header>
                              <dl className="admin-kb-card-meta">
                                <div>
                                  <dt>文档</dt>
                                  <dd>{item.total_documents} 个</dd>
                                </div>
                                <div>
                                  <dt>已入库</dt>
                                  <dd>{item.indexed_documents} 个</dd>
                                </div>
                                <div>
                                  <dt>未入库</dt>
                                  <dd>{item.not_indexed_documents} 个</dd>
                                </div>
                                <div>
                                  <dt>切片</dt>
                                  <dd>{item.chunk_count} 条</dd>
                                </div>
                                <div>
                                  <dt>容量</dt>
                                  <dd>{formatBytes(item.total_size_bytes)}</dd>
                                </div>
                                <div>
                                  <dt>创建</dt>
                                  <dd>{formatDate(item.created_at)}</dd>
                                </div>
                              </dl>
                              {item.not_indexed_documents > 0 ? (
                                <Tag color="warning" className="admin-kb-card-tag">
                                  {item.not_indexed_documents} 个文档待入库
                                </Tag>
                              ) : item.total_documents > 0 ? (
                                <Tag color="success" className="admin-kb-card-tag">
                                  已全部入库
                                </Tag>
                              ) : (
                                <Tag className="admin-kb-card-tag">暂无文档</Tag>
                              )}
                              <footer className="admin-kb-card-foot">
                                <Button
                                  type="primary"
                                  ghost
                                  icon={<RightOutlined />}
                                  iconPlacement="end"
                                  onClick={() => enterKbWorkspace(item.kb_id, "documents")}
                                >
                                  查看详情
                                </Button>
                                <Button
                                  icon={<ExperimentOutlined />}
                                  onClick={() => enterKbWorkspace(item.kb_id, "recall")}
                                >
                                  召回测试
                                </Button>
                              </footer>
                            </article>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {displayStats && displayStats.not_indexed_documents > 0 ? (
                      <div className="admin-stats-tip">
                        <Text type="secondary">
                          有 {displayStats.not_indexed_documents} 个文档尚未写入向量库，请前往「文档管理」点击「重建索引」。
                        </Text>
                        <Button
                          type="link"
                          onClick={() => {
                            const target =
                              stats?.knowledge_bases?.find(
                                (k) => k.not_indexed_documents > 0,
                              )?.kb_id ??
                              activeKbId ??
                              kbs[0]?.kb_id;
                            if (target) enterKbWorkspace(target);
                            else setWorkspaceView("docs");
                          }}
                        >
                          去文档管理
                        </Button>
                      </div>
                    ) : null}
                  </>
                ) : (
                  <Empty description="暂无统计数据" />
                )}
              </div>
            </>
          ) : !activeKb ? (
            <div className="admin-center">
              <Empty description="请从左侧选择或创建一个知识库" />
            </div>
          ) : (
            <>
              <div className="admin-kb-inner-bar">
                <div className="admin-kb-inner-title">
                  <div>
                    <Title level={4} className="admin-preview-title">
                      {activeKb.name}
                    </Title>
                    <Paragraph type="secondary" className="admin-preview-meta">
                      {activeKb.description?.trim() ||
                        "在本知识库内上传文档、重建索引与召回测试"}
                    </Paragraph>
                  </div>
                  <Button
                    type="link"
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => openRenameKb(activeKb)}
                  >
                    重命名
                  </Button>
                </div>
                <div className="admin-kb-inner-actions">
                  <Segmented
                    value={kbPanelView}
                    options={[
                      {
                        label: "文档管理",
                        value: "documents",
                        icon: <FileTextOutlined />,
                      },
                      {
                        label: "召回测试",
                        value: "recall",
                        icon: <ExperimentOutlined />,
                      },
                    ]}
                    onChange={(v) => setKbPanelView(v as KbPanelView)}
                  />
                  <Upload
                    accept=".pdf,.docx,.md,.markdown,.txt"
                    showUploadList={false}
                    disabled={uploading || ingesting}
                    customRequest={async (options) => {
                      if (!activeKbId) return;
                      const file = options.file as File;
                      setUploading(true);
                      setUploadProgress(0);
                      setUploadFileName(file.name);
                      try {
                        const r = await uploadFileWithProgress(
                          activeKbId,
                          file,
                          setUploadProgress,
                        );
                        message.success(
                          `已上传 ${r.saved}，请点击「重建索引」`,
                        );
                        options.onSuccess?.(r);
                        await refreshAll();
                        setKbPanelView("documents");
                        setActiveDoc(r.saved);
                      } catch (e) {
                        const err =
                          e instanceof Error ? e : new Error("上传失败");
                        message.error(err.message);
                        options.onError?.(err);
                      } finally {
                        setUploading(false);
                        window.setTimeout(() => {
                          setUploadProgress(null);
                          setUploadFileName("");
                        }, 800);
                      }
                    }}
                  >
                    <Button
                      icon={<CloudUploadOutlined />}
                      disabled={uploading || ingesting}
                    >
                      上传文档
                    </Button>
                  </Upload>
                  <Button
                    type="primary"
                    icon={<DatabaseOutlined />}
                    loading={ingesting}
                    disabled={uploading || ingesting}
                    onClick={() => void onIngest()}
                  >
                    重建索引
                  </Button>
                </div>
              </div>

              {(uploadProgress !== null || ingestProgress !== null) && (
                <div className="admin-kb-progress-panel">
                  {uploadProgress !== null ? (
                    <div className="admin-kb-progress-item">
                      <div className="admin-kb-progress-head">
                        <Text strong>上传文件</Text>
                        <Text type="secondary">
                          {uploadFileName || "传输中…"}
                        </Text>
                      </div>
                      <Progress
                        percent={uploadProgress}
                        status={uploadProgress >= 100 ? "success" : "active"}
                      />
                    </div>
                  ) : null}
                  {ingestProgress !== null ? (
                    <div className="admin-kb-progress-item">
                      <div className="admin-kb-progress-head">
                        <Text strong>重建索引</Text>
                        <Text type="secondary">
                          {ingestStatus || "处理中…"}
                        </Text>
                      </div>
                      <Progress
                        percent={ingestProgress}
                        status={ingestProgress >= 100 ? "success" : "active"}
                      />
                    </div>
                  ) : null}
                </div>
              )}

              {kbPanelView === "recall" ? (
            <>
              <div className="admin-recall-form">
                <Input.Search
                  placeholder="输入测试问题，如：年假怎么申请？"
                  value={recallQuery}
                  allowClear
                  enterButton="测试召回"
                  loading={recallLoading}
                  disabled={!activeKbId}
                  onChange={(e) => setRecallQuery(e.target.value)}
                  onSearch={(v) => void onRecallTest(v)}
                />
                <div className="admin-recall-options">
                  <Text type="secondary">Top K</Text>
                  <InputNumber
                    min={1}
                    max={50}
                    value={recallLimit}
                    onChange={(v) => setRecallLimit(v ?? 10)}
                  />
                </div>
              </div>

              <div className="admin-scroll-area">
                {recallLoading ? (
                  <div className="admin-center">
                    <Spin description="召回中…" />
                  </div>
                ) : recallLanes.length === 0 && recallHits.length === 0 ? (
                  <Empty description="输入问题并点击「测试召回」查看结果" />
                ) : (
                  <>
                    <Paragraph type="secondary" className="admin-recall-summary">
                      问题「{testedRecallQuery}」· 对比{" "}
                      {recallLanes.length || 1} 路检索
                      {rerankerReady
                        ? " · 已启用 bge-reranker"
                        : " · 未检测到 reranker 权重，第三路暂不可用"}
                    </Paragraph>
                    <div
                      className={`admin-recall-lanes${
                        (recallLanes.length || 1) > 1 ? " is-compare" : ""
                      }`}
                    >
                      {(recallLanes.length
                        ? recallLanes
                        : [{ mode: "vector", label: "仅向量", hits: recallHits }]
                      ).map((lane) => (
                        <section key={lane.mode} className="admin-recall-lane">
                          <header className="admin-recall-lane-head">
                            <Text strong>{lane.label}</Text>
                            <Text type="secondary">{lane.hits.length} 条</Text>
                          </header>
                          <div className="admin-chunk-list">
                            {lane.hits.map((hit, i) => (
                              <article
                                key={`${lane.mode}-${hit.source}-${hit.chunk_id}-${i}`}
                                className="admin-chunk-card"
                              >
                                <header className="admin-chunk-head">
                                  <Tag color="blue">#{i + 1}</Tag>
                                  <Text strong>{hit.source}</Text>
                                  {hit.chunk_id != null && hit.chunk_id >= 0 ? (
                                    <Tag>切片 #{hit.chunk_id}</Tag>
                                  ) : null}
                                  {channelLabel(hit.channels) ? (
                                    <Tag>{channelLabel(hit.channels)}</Tag>
                                  ) : null}
                                  <Text
                                    type="secondary"
                                    className="admin-search-score"
                                  >
                                    {formatRecallScore(hit)}
                                  </Text>
                                  <Button
                                    type="link"
                                    size="small"
                                    style={{ marginLeft: "auto" }}
                                    onClick={() => openRecallHit(hit)}
                                  >
                                    查看文档
                                  </Button>
                                </header>
                                <pre className="admin-chunk-body">
                                  {hit.content}
                                </pre>
                              </article>
                            ))}
                          </div>
                        </section>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </>
              ) : !activeDoc ? (
            <div className="admin-center">
              <Empty description="选择左侧文档以预览" />
            </div>
          ) : (
            <>
              <div className="admin-preview-head">
                <div>
                  <Title level={4} className="admin-preview-title">
                    {activeDoc}
                  </Title>
                  <Paragraph type="secondary" className="admin-preview-meta">
                    {pageCount > 0 ? `${pageCount} 页/段 · ` : ""}
                    {chunkCount} 个切片
                    {fromVectorstore ? " · 来自向量库" : " · 即时分片预览"}
                    {activeMeta && !activeMeta.indexed
                      ? " · 尚未写入向量库"
                      : ""}
                  </Paragraph>
                </div>
              </div>

              <div className="admin-tab-bar" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "preview"}
                  className={`admin-tab-btn${
                    activeTab === "preview" ? " is-active" : ""
                  }`}
                  onClick={() => setActiveTab("preview")}
                >
                  原文预览
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "chunks"}
                  className={`admin-tab-btn${
                    activeTab === "chunks" ? " is-active" : ""
                  }`}
                  onClick={() => setActiveTab("chunks")}
                >
                  切片结果（{chunkCount}）
                </button>
              </div>

              <div className="admin-scroll-area">
                {previewError ? (
                  <div className="admin-error-box">
                    <Text type="danger">{previewError}</Text>
                    <Paragraph type="secondary" style={{ marginTop: 8 }}>
                      当前版本仅支持可复制文字的 PDF（非扫描件）。扫描版 PDF
                      需要 OCR，暂未接入。
                    </Paragraph>
                  </div>
                ) : null}
                {previewLoading ? (
                  <div className="admin-center">
                    <Spin
                      description={
                        activeTab === "preview" ? "加载原文…" : "加载切片…"
                      }
                    />
                  </div>
                ) : activeTab === "preview" ? (
                  previewText ? (
                    <pre className="admin-preview-text">{previewText}</pre>
                  ) : previewError ? null : (
                    <Empty description="无法读取原文（文件可能不在 raw 目录）" />
                  )
                ) : chunks.length === 0 ? (
                  previewError ? null : (
                    <Empty description="暂无切片，请先重建索引或确认文件可解析" />
                  )
                ) : (
                  <div className="admin-chunk-list">
                    {chunks.map((c) => (
                      <article
                        key={`${c.chunk_id}-${c.page}`}
                        className="admin-chunk-card"
                      >
                        <header className="admin-chunk-head">
                          <Text strong>切片 #{c.chunk_id}</Text>
                          {c.page != null ? <Tag>page {c.page}</Tag> : null}
                          <Text type="secondary">{c.content.length} 字</Text>
                        </header>
                        <pre className="admin-chunk-body">{c.content}</pre>
                      </article>
                    ))}
                  </div>
                )}
              </div>
            </>
              )}
            </>
          )}
        </section>
      </section>

      <Modal
        title="创建知识库"
        open={createKbOpen}
        confirmLoading={creatingKb}
        okText="创建"
        cancelText="取消"
        onOk={() => void onCreateKb()}
        onCancel={() => {
          setCreateKbOpen(false);
          setCreateKbName("");
          setCreateKbDesc("");
        }}
      >
        <div className="admin-create-kb-form">
          <label>
            <Text>名称</Text>
            <Input
              placeholder="如：人事制度库、产品手册库"
              value={createKbName}
              maxLength={80}
              onChange={(e) => setCreateKbName(e.target.value)}
            />
          </label>
          <label>
            <Text type="secondary">描述（可选）</Text>
            <Input.TextArea
              placeholder="简要说明该知识库用途"
              value={createKbDesc}
              maxLength={500}
              rows={3}
              onChange={(e) => setCreateKbDesc(e.target.value)}
            />
          </label>
        </div>
      </Modal>

      <Modal
        title="重命名知识库"
        open={renameKbOpen}
        confirmLoading={renamingKb}
        okText="保存"
        cancelText="取消"
        onOk={() => void onRenameKb()}
        onCancel={() => {
          setRenameKbOpen(false);
          setRenameKbId(null);
          setRenameKbName("");
          setRenameKbDesc("");
        }}
      >
        <div className="admin-create-kb-form">
          <label>
            <Text>名称</Text>
            <Input
              placeholder="知识库名称"
              value={renameKbName}
              maxLength={80}
              onChange={(e) => setRenameKbName(e.target.value)}
            />
          </label>
          <label>
            <Text type="secondary">描述（可选）</Text>
            <Input.TextArea
              placeholder="简要说明该知识库用途"
              value={renameKbDesc}
              maxLength={500}
              rows={3}
              onChange={(e) => setRenameKbDesc(e.target.value)}
            />
          </label>
        </div>
      </Modal>
    </main>
  );
}
