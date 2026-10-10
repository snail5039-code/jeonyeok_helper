import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker 이미지를 가볍게: 실행에 필요한 파일만 .next/standalone 에 모은다.
  output: "standalone",
};

export default nextConfig;
