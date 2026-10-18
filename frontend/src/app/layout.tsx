import type { Metadata, Viewport } from "next";
import { Black_Han_Sans, Jua } from "next/font/google";
import "./globals.css";
import "./home.css";
import "./home-dark.css";

export const metadata: Metadata = {
  title: "전역도우미",
  description: "전역 후 받을 수 있는 혜택, 근거 조문, 신청할 곳을 한 번에 알려드려요.",
  icons: { icon: "/images/brand-cap-chat.png", apple: "/icons/apple-touch-icon.png" },
  // 아이폰 홈 화면에 추가했을 때 앱처럼 열리게
  appleWebApp: { capable: true, title: "전역도우미", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#334633",
};

// B급 감성 제목·말풍선 글꼴 (로드맵 화면). 한글 글꼴이라 미리 받지 않고 쓸 때 받는다.
const jua = Jua({ weight: "400", preload: false, display: "swap", variable: "--font-jua" });
// 작전 수첩 제목용 굵은 글씨
const blackHan = Black_Han_Sans({ weight: "400", preload: false, display: "swap", variable: "--font-black-han" });

// 저장된 테마를 그리기 전에 적용해서 화면이 깜빡이지 않게 한다.
const themeScript = `try{var t=localStorage.getItem("jeonyeok.theme");if(t)document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" className={`${jua.variable} ${blackHan.variable}`} suppressHydrationWarning>
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
