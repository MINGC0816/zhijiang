"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { App, Button, Form, Input, Typography } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useAuth } from "@/context/AuthContext";

const { Title, Text, Paragraph } = Typography;

type Props = {
  onSuccess: () => void;
  onBack?: () => void;
};

export default function AdminLoginPanel({ onSuccess, onBack }: Props) {
  const { message } = App.useApp();
  const { authorizeKbAdmin, user } = useAuth();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      await authorizeKbAdmin(values.username, values.password);
      message.success("管理员验证成功");
      onSuccess();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "管理员验证失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="auth-shell admin-auth-shell">
      <section className="auth-card admin-auth-card">
        {onBack ? (
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={onBack}
            className="admin-auth-back"
          >
            返回问答系统
          </Button>
        ) : null}

        <div className="auth-brand">
          <Image src="/logo.png" alt="智匠 Logo" width={48} height={48} />
          <div>
            <Title level={3} className="kb-brand-title">
              智匠 · 知识库管理
            </Title>
            <Text type="secondary">管理员身份验证</Text>
          </div>
        </div>

        <Paragraph type="secondary" className="admin-auth-tip">
          当前登录为普通用户
          {user?.username ? `（${user.username}）` : ""}
          。进入知识库管理系统需使用管理员账号验证。
        </Paragraph>

        <Form layout="vertical" onFinish={(v) => void onFinish(v)} size="large">
          <Form.Item
            label="管理员用户名"
            name="username"
            rules={[{ required: true, message: "请输入管理员用户名" }]}
          >
            <Input placeholder="管理员用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password placeholder="密码" autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            登录知识库管理
          </Button>
        </Form>

        <Paragraph className="auth-footer">
          <Link href="/">返回问答首页</Link>
        </Paragraph>
      </section>
    </main>
  );
}
