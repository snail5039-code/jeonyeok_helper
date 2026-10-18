import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker 이미지를 가볍게: 실행에 필요한 파일만 .next/standalone 에 모은다.
  output: "standalone",
  // 서비스 워커는 늘 새로 받아야 바뀐 내용이 바로 적용된다
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
        ],
      },
    ];
  },
};

export default nextConfig;
