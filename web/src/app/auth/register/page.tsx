"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { App, Button, Form, Input, Spin, Typography } from "antd";
import { useAuth } from "@/context/AuthContext";
import { useGuestOnly } from "@/hooks/useGuestOnly";

const { Title, Text, Paragraph } = Typography;

export default function RegisterPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const { register } = useAuth();
  const { ready } = useGuestOnly();
  const [submitting, setSubmitting] = useState(false);

  if (!ready) {
    return (
      <main className="auth-shell">
        <Spin size="large" />
      </main>
    );
  }

  const onFinish = async (values: {
    username: string;
    password: string;
    display_name?: string;
    email?: string;
  }) => {
    setSubmitting(true);
    try {
      await register(
        values.username,
        values.password,
        values.display_name,
        values.email,
      );
      message.success("注册成功，已自动登录");
      router.replace("/");
    } catch (e) {
      message.error(e instanceof Error ? e.message : "注册失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="auth-brand">
          <Image src="/logo.png" alt="智匠 Logo" width={48} height={48} />
          <div>
            <Title level={3} className="kb-brand-title">
              智匠 · 统一身份认证
            </Title>
            <Text type="secondary">注册普通用户账号</Text>
          </div>
        </div>

        <Form layout="vertical" onFinish={(v) => void onFinish(v)} size="large">
          <Form.Item
            label="用户名"
            name="username"
            rules={[
              { required: true, message: "请输入用户名" },
              { min: 3, message: "至少 3 个字符" },
            ]}
          >
            <Input placeholder="3–32 个字符" autoComplete="username" />
          </Form.Item>
          <Form.Item label="显示名称" name="display_name">
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item label="邮箱" name="email">
            <Input placeholder="可选" type="email" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[
              { required: true, message: "请输入密码" },
              { min: 6, message: "至少 6 位" },
            ]}
          >
            <Input.Password placeholder="至少 6 位" autoComplete="new-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={submitting}>
            注册
          </Button>
        </Form>

        <Paragraph className="auth-footer">
          已有账号？<Link href="/auth/login">返回登录</Link>
        </Paragraph>
        <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }}>
          管理员账号由系统初始化，不支持自助注册。
        </Paragraph>
      </section>
    </main>
  );
}
