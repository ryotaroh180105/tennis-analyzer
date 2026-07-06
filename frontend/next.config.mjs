/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // devではNext.jsからバックエンドAPIへプロキシ（CORS回避）
    return [
      { source: "/api/:path*", destination: `${process.env.BACKEND_URL || "http://backend:8000"}/api/:path*` },
      { source: "/healthz", destination: `${process.env.BACKEND_URL || "http://backend:8000"}/healthz` },
    ];
  },
};

export default nextConfig;
