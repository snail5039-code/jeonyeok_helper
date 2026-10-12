import type { Metadata, Viewport } from "next";
import { Jua } from "next/font/google";
import "./globals.css";

export const metadata: Metadata = {
  title: "전역도우미",
  description: "전역 후 받을 수 있는 혜택, 근거 조문, 신청할 곳을 한 번에 알려드려요.",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

// B급 감성 제목·말풍선 글꼴 (로드맵 화면). 한글 글꼴이라 미리 받지 않고 쓸 때 받는다.
const jua = Jua({ weight: "400", preload: false, display: "swap", variable: "--font-jua" });

// 저장된 테마를 그리기 전에 적용해서 화면이 깜빡이지 않게 한다.
const themeScript = `try{var t=localStorage.getItem("jeonyeok.theme");if(t)document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" className={jua.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
