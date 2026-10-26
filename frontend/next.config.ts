import type { NextConfig } from "next";

const gateway = process.env.MODEL_ARENA_API_URL || "http://127.0.0.1:8080";
const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${gateway}/api/v1/:path*` }];
  },
};
export default nextConfig;
