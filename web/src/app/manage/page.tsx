"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  App,
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import {
  ArrowLeftOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { useAuth } from "@/context/AuthContext";
import {
  deleteManagedUser,
  listAuditLogs,
  listManagedUsers,
  resetManagedUserPassword,
  updateManagedUser,
  type AuditLogItem,
  type ManagedUser,
} from "@/lib/api";

const { Title, Text } = Typography;

const ACTION_LABELS: Record<string, string> = {
  login: "登录",
  logout: "登出",
  register: "注册",
  login_failed: "登录失败",
  kb_admin_login: "知识库授权",
  kb_admin_login_failed: "知识库授权失败",
  user_update: "用户更新",
  user_delete: "用户删除",
  password_reset: "重置密码",
};

export default function ManagePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const defaultTab = searchParams.get("tab") === "audit" ? "audit" : "users";
  const { message } = App.useApp();
  const { user, loading, isAdmin } = useAuth();
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [logsLoading, setLogsLoading] = useState(false);
  const [editUser, setEditUser] = useState<ManagedUser | null>(null);
  const [resetUser, setResetUser] = useState<ManagedUser | null>(null);
  const [editForm] = Form.useForm();
  const [resetForm] = Form.useForm();

  const loadUsers = useCallback(async () => {
    setUsersLoading(true);
    try {
      setUsers(await listManagedUsers());
    } catch (e) {
      message.error(e instanceof Error ? e.message : "加载用户失败");
    } finally {
      setUsersLoading(false);
    }
  }, [message]);

  const loadLogs = useCallback(async () => {
    setLogsLoading(true);
    try {
      setLogs(await listAuditLogs({ limit: 200 }));
    } catch (e) {
      message.error(e instanceof Error ? e.message : "加载审计日志失败");
    } finally {
      setLogsLoading(false);
    }
  }, [message]);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/auth/login");
      return;
    }
    if (!loading && user && !isAdmin) {
      router.replace("/");
    }
  }, [loading, user, isAdmin, router]);

  useEffect(() => {
    if (isAdmin) {
      void loadUsers();
      void loadLogs();
    }
  }, [isAdmin, loadUsers, loadLogs]);

  if (loading || !user || !isAdmin) {
    return <main className="manage-shell manage-loading" />;
  }

  const openEdit = (record: ManagedUser) => {
    setEditUser(record);
    editForm.setFieldsValue({
      display_name: record.display_name,
      email: record.email,
      status: record.status,
    });
  };

  const onSaveEdit = async () => {
    if (!editUser) return;
    const values = await editForm.validateFields();
    try {
      await updateManagedUser(editUser.user_id, values);
      message.success("用户信息已更新");
      setEditUser(null);
      await loadUsers();
      await loadLogs();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "更新失败");
    }
  };

  const onResetPassword = async () => {
    if (!resetUser) return;
    const values = await resetForm.validateFields();
    try {
      await resetManagedUserPassword(resetUser.user_id, values.new_password);
      message.success("密码已重置");
      setResetUser(null);
      resetForm.resetFields();
      await loadLogs();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "重置失败");
    }
  };

  const onDelete = async (record: ManagedUser) => {
    try {
      await deleteManagedUser(record.user_id);
      message.success(`已删除用户 ${record.username}`);
      await loadUsers();
      await loadLogs();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "删除失败");
    }
  };

  return (
    <main className="manage-shell">
      <header className="manage-header">
        <div>
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => router.push("/")}
          >
            返回问答
          </Button>
          <Title level={3} style={{ margin: "8px 0 0" }}>
            系统管理
          </Title>
          <Text type="secondary">用户管理与审计日志（管理员）</Text>
        </div>
        <Button
          icon={<ReloadOutlined />}
          onClick={() => {
            void loadUsers();
            void loadLogs();
          }}
        >
          刷新
        </Button>
      </header>

      <Tabs
        className="manage-tabs"
        defaultActiveKey={defaultTab}
        items={[
          {
            key: "users",
            label: "用户管理",
            children: (
              <Table
                rowKey="user_id"
                loading={usersLoading}
                dataSource={users}
                pagination={{ pageSize: 10 }}
                columns={[
                  { title: "用户名", dataIndex: "username" },
                  { title: "显示名称", dataIndex: "display_name" },
                  { title: "邮箱", dataIndex: "email" },
                  {
                    title: "状态",
                    dataIndex: "status",
                    render: (v: string) =>
                      v === "active" ? (
                        <Tag color="success">启用</Tag>
                      ) : (
                        <Tag color="warning">冻结</Tag>
                      ),
                  },
                  {
                    title: "注册时间",
                    dataIndex: "created_at",
                    render: (v: string) => new Date(v).toLocaleString("zh-CN"),
                  },
                  {
                    title: "操作",
                    key: "actions",
                    render: (_, record) => (
                      <Space wrap>
                        <Button size="small" onClick={() => openEdit(record)}>
                          编辑
                        </Button>
                        <Button
                          size="small"
                          onClick={() => {
                            setResetUser(record);
                            resetForm.resetFields();
                          }}
                        >
                          重置密码
                        </Button>
                        <Popconfirm
                          title="确认删除该用户？"
                          onConfirm={() => void onDelete(record)}
                        >
                          <Button size="small" danger>
                            删除
                          </Button>
                        </Popconfirm>
                      </Space>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: "audit",
            label: "审计日志",
            children: (
              <Table
                rowKey="id"
                loading={logsLoading}
                dataSource={logs}
                pagination={{ pageSize: 15 }}
                columns={[
                  {
                    title: "时间",
                    dataIndex: "created_at",
                    width: 180,
                    render: (v: string) => new Date(v).toLocaleString("zh-CN"),
                  },
                  {
                    title: "动作",
                    dataIndex: "action",
                    width: 120,
                    render: (v: string) => ACTION_LABELS[v] || v,
                  },
                  { title: "用户", dataIndex: "username", width: 120 },
                  { title: "详情", dataIndex: "detail", ellipsis: true },
                  { title: "IP", dataIndex: "ip_address", width: 140 },
                ]}
              />
            ),
          },
        ]}
      />

      <Modal
        title="编辑用户"
        open={Boolean(editUser)}
        onCancel={() => setEditUser(null)}
        onOk={() => void onSaveEdit()}
        okText="保存"
      >
        <Form form={editForm} layout="vertical">
          <Form.Item label="显示名称" name="display_name">
            <Input />
          </Form.Item>
          <Form.Item label="邮箱" name="email">
            <Input />
          </Form.Item>
          <Form.Item label="账号状态" name="status">
            <Select
              options={[
                { label: "启用", value: "active" },
                { label: "冻结", value: "frozen" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`重置密码 · ${resetUser?.username ?? ""}`}
        open={Boolean(resetUser)}
        onCancel={() => setResetUser(null)}
        onOk={() => void onResetPassword()}
        okText="确认重置"
      >
        <Form form={resetForm} layout="vertical">
          <Form.Item
            label="新密码"
            name="new_password"
            rules={[
              { required: true, message: "请输入新密码" },
              { min: 6, message: "至少 6 位" },
            ]}
          >
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </main>
  );
}
