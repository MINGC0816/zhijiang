"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { App, Button, Empty, Typography } from "antd";
import {
  AuditOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  LogoutOutlined,
  MessageOutlined,
  PlusOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import type { ThreadItem } from "@/lib/api";
import { deleteThread } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const { Text, Title } = Typography;

type Props = {
  threads: ThreadItem[];
  activeId: string | null;
  loading?: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDeleted: () => void;
};

function formatTime(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export default function SessionSidebar({
  threads,
  activeId,
  loading,
  onSelect,
  onCreate,
  onDeleted,
}: Props) {
  const router = useRouter();
  const { message } = App.useApp();
  const { user, isAdmin, logout } = useAuth();

  const onDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await deleteThread(id);
      message.success("已删除会话");
      onDeleted();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "删除失败");
    }
  };

  return (
    <aside className="chat-sidebar">
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
            智匠
          </Title>
          <Text className="kb-brand-sub">员工知识问答</Text>
        </div>
      </div>

      <Button
        type="primary"
        block
        icon={<PlusOutlined />}
        onClick={onCreate}
        className="chat-new-btn"
      >
        新对话
      </Button>

      <Text type="secondary" className="kb-section-label">
        功能模块
      </Text>
      <div className="chat-module-list">
        <Button
          block
          icon={<DatabaseOutlined />}
          onClick={() => router.push("/admin")}
        >
          知识库管理
        </Button>
        {isAdmin ? (
          <>
            <Button
              block
              icon={<TeamOutlined />}
              onClick={() => router.push("/manage")}
            >
              用户管理
            </Button>
            <Button
              block
              icon={<AuditOutlined />}
              onClick={() => router.push("/manage?tab=audit")}
            >
              审计日志
            </Button>
          </>
        ) : null}
      </div>

      <Text type="secondary" className="kb-section-label">
        历史会话
      </Text>

      <div className="chat-thread-list">
        {threads.length === 0 && !loading ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无会话"
            style={{ marginTop: 32 }}
          />
        ) : (
          <ul className="kb-doc-ul">
            {threads.map((t) => (
              <li key={t.thread_id}>
                <button
                  type="button"
                  className={`chat-thread-item${
                    activeId === t.thread_id ? " is-active" : ""
                  }`}
                  onClick={() => onSelect(t.thread_id)}
                >
                  <span className="chat-thread-main">
                    <MessageOutlined />
                    <span className="chat-thread-text">
                      <span className="chat-thread-title">{t.title}</span>
                      <span className="chat-thread-meta">
                        {formatTime(t.updated_at)}
                      </span>
                    </span>
                  </span>
                  <span
                    className="chat-thread-del"
                    role="button"
                    tabIndex={0}
                    onClick={(e) => void onDelete(e, t.thread_id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void onDelete(e as unknown as React.MouseEvent, t.thread_id);
                    }}
                  >
                    <DeleteOutlined />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="chat-sidebar-foot">
        <Text type="secondary" className="chat-user-label">
          {user?.display_name || user?.username}
          {isAdmin ? " · 管理员" : " · 普通用户"}
        </Text>
        <Button
          type="text"
          danger
          icon={<LogoutOutlined />}
          onClick={() => void logout()}
        >
          退出登录
        </Button>
      </div>
    </aside>
  );
}
