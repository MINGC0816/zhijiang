"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { App, Button, Form, Input, Spin, Typography } from "antd";
import { useAuth } from "@/context/AuthContext";
import { useGuestOnly } from "@/hooks/useGuestOnly";

const { Title, Text, Paragraph } = Typography;

export default function LoginPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const { login } = useAuth();
  const { ready } = useGuestOnly();
  const [submitting, setSubmitting] = useState(false);

  if (!ready) {
    return (
      <main className="auth-shell">
        <Spin size="large" />
      </main>
    );
  }

  const onFinish = async (values: { username: string; password: string }) => {
    setSubmitting(true);
    try {
      await login(values.username, values.password);
      message.success("登录成功");
      router.replace("/");
    } catch (e) {
      message.error(e instanceof Error ? e.message : "登录失败");
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
            <Text type="secondary">登录知识问答系统</Text>
          </div>
        </div>

        <Form layout="vertical" onFinish={(v) => void onFinish(v)} size="large">
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: "请输入用户名" }]}
          >
            <Input placeholder="用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password placeholder="密码" autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={submitting}>
            登录
          </Button>
        </Form>

        <Paragraph className="auth-footer">
          还没有账号？<Link href="/auth/register">立即注册</Link>
          （仅支持注册普通用户）
        </Paragraph>
      </section>
    </main>
  );
}
