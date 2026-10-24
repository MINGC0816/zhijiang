"use client";

import { useEffect, useRef, useState } from "react";
import { App, Button, Input, Spin, Typography } from "antd";
import { SendOutlined } from "@ant-design/icons";
import MarkdownContent from "@/components/MarkdownContent";
import { chatStream, getThreadMessages, type ChatStreamEvent } from "@/lib/api";
import { readCachedThreadMessages } from "@/lib/client-cache";

const { Text, Paragraph, Title } = Typography;

type TimelineStep = {
  id: string;
  name: string;
  label: string;
  status: "running" | "done";
  detail?: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  steps?: TimelineStep[];
  streaming?: boolean;
};

type Props = {
  threadId: string | null;
  onChatted?: () => void;
};

const TOOL_LABELS: Record<string, string> = {
  rewrite_query: "改写检索词",
  search_knowledge: "检索知识库",
  list_documents: "列出文档",
};

function newId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function toolLabel(name: string) {
  return TOOL_LABELS[name] || name;
}

function toChatMessages(rows: { role: "user" | "assistant"; content: string }[]) {
  return rows.map((m) => ({
    id: newId(),
    role: m.role,
    content: m.content,
  }));
}

export default function ChatPanel({ threadId, onChatted }: Props) {
  const { message } = App.useApp();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  useEffect(() => {
    if (!threadId) {
      setMessages([]);
      return;
    }

    const cached = readCachedThreadMessages(threadId);
    if (cached.length > 0) {
      setMessages(toChatMessages(cached));
      setLoadingHistory(false);
    } else {
      setMessages([]);
      setLoadingHistory(true);
    }

    let cancelled = false;
    void getThreadMessages(threadId)
      .then((rows) => {
        if (cancelled) return;
        setMessages(toChatMessages(rows));
      })
      .catch((e) => {
        if (!cancelled) {
          message.error(e instanceof Error ? e.message : "加载历史失败");
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [threadId, message]);

  const patchAssistant = (
    assistantId: string,
    updater: (msg: ChatMessage) => ChatMessage,
  ) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === assistantId ? updater(m) : m)),
    );
  };

  const applyStreamEvent = (assistantId: string, evt: ChatStreamEvent) => {
    if (evt.type === "status") {
      patchAssistant(assistantId, (m) => {
        const steps = [...(m.steps || [])];
        const last = steps[steps.length - 1];
        if (last && last.name === "status" && last.status === "running") {
          steps[steps.length - 1] = { ...last, label: evt.message };
        } else {
          steps.push({
            id: newId(),
            name: "status",
            label: evt.message,
            status: "running",
          });
        }
        return { ...m, steps };
      });
      return;
    }
    if (evt.type === "tool_start") {
      patchAssistant(assistantId, (m) => {
        const steps = (m.steps || []).map((s) =>
          s.name === "status" && s.status === "running"
            ? { ...s, status: "done" as const }
            : s,
        );
        steps.push({
          id: newId(),
          name: evt.name,
          label: `调用 ${toolLabel(evt.name)}`,
          status: "running",
          detail: evt.input || undefined,
        });
        return { ...m, steps };
      });
      return;
    }
    if (evt.type === "tool_end") {
      patchAssistant(assistantId, (m) => {
        const steps = [...(m.steps || [])];
        for (let i = steps.length - 1; i >= 0; i -= 1) {
          if (steps[i].name === evt.name && steps[i].status === "running") {
            steps[i] = {
              ...steps[i],
              status: "done",
              label: `完成 ${toolLabel(evt.name)}`,
              detail: evt.preview || steps[i].detail,
            };
            break;
          }
        }
        return { ...m, steps };
      });
      return;
    }
    if (evt.type === "token") {
      patchAssistant(assistantId, (m) => ({
        ...m,
        content: `${m.content}${evt.text}`,
      }));
      return;
    }
    if (evt.type === "done") {
      patchAssistant(assistantId, (m) => ({
        ...m,
        content: evt.answer || m.content || "（空响应）",
        streaming: false,
        steps: (m.steps || []).map((s) => ({ ...s, status: "done" as const })),
      }));
    }
  };

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || sending || !threadId) return;

    const assistantId = newId();
    setInput("");
    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", content },
      {
        id: assistantId,
        role: "assistant",
        content: "",
        steps: [
          {
            id: newId(),
            name: "status",
            label: "正在分析问题…",
            status: "running",
          },
        ],
        streaming: true,
      },
    ]);
    setSending(true);
    try {
      await chatStream(content, threadId, (evt) => {
        applyStreamEvent(assistantId, evt);
      });
      onChatted?.();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "问答失败");
      patchAssistant(assistantId, (m) => ({
        ...m,
        streaming: false,
        content:
          m.content ||
          "抱歉，请求失败。请确认后端已启动，且已连接 VPN / 模型服务。",
        steps: (m.steps || []).map((s) => ({ ...s, status: "done" as const })),
      }));
    } finally {
      setSending(false);
    }
  };

  return (
    <section className="kb-chat">
      <header className="kb-chat-header">
        <Title level={4} className="kb-chat-title">
          知识问答
        </Title>
      </header>

      <div className="kb-chat-body">
        {loadingHistory ? (
          <div className="kb-typing">
            <Spin size="small" />
            <Text type="secondary">加载会话…</Text>
          </div>
        ) : null}

        {!loadingHistory && messages.length === 0 && !sending ? (
          <div className="kb-chat-empty">
            <Title level={2} className="kb-chat-hero">
              有制度问题，先问智匠
            </Title>
            <Paragraph type="secondary">
              可询问休假、报销、入职等规定。回答会标注文档来源。
            </Paragraph>
            <div className="kb-examples chat-quick">
              {["公司年休假有几天？", "报销流程是什么？", "试用期多久？"].map(
                (q) => (
                  <button
                    key={q}
                    type="button"
                    className="kb-example"
                    disabled={!threadId || sending}
                    onClick={() => void send(q)}
                  >
                    {q}
                  </button>
                ),
              )}
            </div>
          </div>
        ) : null}

        {!loadingHistory && (messages.length > 0 || sending) ? (
          <div className="kb-messages">
            {messages.map((m) => (
              <article
                key={m.id}
                className={`kb-bubble kb-bubble-${m.role}`}
              >
                <Text className="kb-bubble-role">
                  {m.role === "user" ? "我" : "智匠"}
                </Text>
                {m.role === "assistant" && m.steps && m.steps.length > 0 ? (
                  <ol className="kb-timeline">
                    {m.steps.map((step) => (
                      <li
                        key={step.id}
                        className={`kb-timeline-step${
                          step.status === "running" ? " is-run" : ""
                        }`}
                      >
                        <span className="kb-timeline-name">{step.label}</span>
                        {step.detail ? (
                          <span className="kb-timeline-detail">{step.detail}</span>
                        ) : null}
                      </li>
                    ))}
                  </ol>
                ) : null}
                <div className="kb-bubble-content">
                  {m.role === "assistant" ? (
                    m.content ? (
                      <MarkdownContent content={m.content} />
                    ) : m.streaming ? (
                      <Text type="secondary">正在生成…</Text>
                    ) : null
                  ) : (
                    m.content
                  )}
                </div>
              </article>
            ))}
            <div ref={bottomRef} />
          </div>
        ) : null}
      </div>

      <footer className="kb-chat-input">
        <Input.TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            threadId ? "输入制度相关问题…" : "请先新建或选择左侧会话"
          }
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={sending || !threadId}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              void send(input);
            }
          }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          loading={sending}
          disabled={!threadId}
          onClick={() => void send(input)}
        >
          发送
        </Button>
      </footer>
    </section>
  );
}
