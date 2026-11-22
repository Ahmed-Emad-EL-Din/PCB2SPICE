/** @type {import('next').NextConfig} */
const WORKER_URL = process.env.WORKER_URL || 'http://127.0.0.1:8000';
module.exports = {
  reactStrictMode: true,
  output: 'standalone', // self-contained Node server for Docker/compose; Vercel ignores this
  async rewrites() {
    return [
      { source: '/api/:path*', destination: `${WORKER_URL}/api/:path*` },
      { source: '/health', destination: `${WORKER_URL}/health` },
    ];
  },
};
