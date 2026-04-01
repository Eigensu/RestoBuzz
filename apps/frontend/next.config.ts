import type { NextConfig } from "next";
import path from "path";
import dotenv from "dotenv";

// Load root .env (two levels up from apps/frontend/)
dotenv.config({ path: path.resolve(__dirname, "../../.env") });

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  turbopack: {
    root: path.resolve(__dirname, "../.."),
  },
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "res.cloudinary.com" },
      { protocol: "https", hostname: "*.fbcdn.net" },
      { protocol: "https", hostname: "*.ngrok-free.app" },
      { protocol: "https", hostname: "*.ngrok-free.dev" },
    ],
  },
  env: {
    NEXT_PUBLIC_API_URL: API_URL,
    NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME ?? "DishPatch",
  },
  /**
   * Server-side proxy rewrites.
   *
   * WHY: ngrok free tier intercepts browser OPTIONS preflight requests and
   * returns an HTML interstitial page (no CORS headers) before the backend
   * ever sees the request. There is no way to add custom headers to the
   * browser's automatic preflight, so the ngrok-skip-browser-warning header
   * trick in axios cannot help the OPTIONS request.
   *
   * HOW THIS FIXES IT: Requests from the browser go to localhost:3000/api/*
   * (same origin → no preflight, no CORS). Next.js server-side forwards
   * them to the backend including the ngrok-skip-browser-warning header.
   * The server-to-server request is never subject to browser CORS rules.
   */
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
