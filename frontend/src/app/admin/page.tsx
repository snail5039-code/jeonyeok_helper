import type { Metadata } from "next";

import { AdminDashboard } from "@/components/AdminDashboard";

export const metadata: Metadata = {
  title: "운영 대시보드 · 전역도우미",
  // 관리자 화면은 검색에 나오지 않게
  robots: { index: false, follow: false },
};

export default function AdminPage() {
  return <AdminDashboard />;
}
