import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      // 旧「カウンター」ページ。マスターと話す場所は /chat だけにする
      { source: "/counter", destination: "/chat", permanent: false },
    ];
  },
};

export default nextConfig;
