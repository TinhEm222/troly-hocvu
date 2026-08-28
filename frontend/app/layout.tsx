import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";

export const metadata: Metadata = {
  title: "Trợ lý ảo học vụ",
  description: "Hệ thống trợ lý ảo RAG hỗ trợ sinh viên tra cứu thông tin học vụ - Trường Đại học Kỹ thuật",
};

export default function RootLayout({children}: Readonly<{ children: React.ReactNode; }>) {
  return (
    <html lang="vi">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
