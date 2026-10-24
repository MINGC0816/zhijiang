import type { Metadata } from "next";
import { AntdRegistry } from "@ant-design/nextjs-registry";
import { App, ConfigProvider } from "antd";
import { AuthProvider } from "@/context/AuthContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "智匠 · 企业内部知识问答",
  description: "基于本地制度文档的企业员工知识问答智能体",
  icons: {
    icon: [{ url: "/logo.png", type: "image/png", sizes: "any" }],
    shortcut: "/logo.png",
    apple: "/logo.png",
  },
};

const FONT_STACK =
  '"Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif';

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <AntdRegistry>
          <ConfigProvider
            theme={{
              token: {
                colorPrimary: "#0B6E4F",
                colorInfo: "#0B6E4F",
                colorSuccess: "#2F9E6B",
                colorBgBase: "#F4F7F9",
                colorTextBase: "#1B2420",
                borderRadius: 10,
                fontFamily: FONT_STACK,
              },
              components: {
                Button: {
                  controlHeight: 40,
                },
                Input: {
                  controlHeight: 40,
                },
              },
            }}
          >
            <App>
              <AuthProvider>{children}</AuthProvider>
            </App>
          </ConfigProvider>
        </AntdRegistry>
      </body>
    </html>
  );
}
