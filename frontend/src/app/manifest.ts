import type { MetadataRoute } from "next";

// 홈 화면에 추가(PWA): 휴대폰 홈 화면에 앱처럼 설치된다. 아이폰은 홈 화면 앱이어야 알림을 받는다.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "전역도우미",
    short_name: "전역도우미",
    description: "전역 후 받을 수 있는 혜택, 근거 조문, 신청할 곳을 한 번에 알려드려요.",
    lang: "ko",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#edf0e9",
    theme_color: "#334633",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
