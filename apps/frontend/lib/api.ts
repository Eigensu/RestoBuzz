import axios from "axios";
import { parseApiError } from "./errors";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const isBrowser = typeof globalThis.window !== "undefined";

// In the browser, use a relative path so requests go to the Next.js dev server
// (/api/*) which is rewritten server-side to the real backend. This avoids
// browser CORS preflights and ngrok interstitial pages. On the server we use
// the absolute API URL.
export const api = axios.create({
  baseURL: isBrowser ? "/api" : `${API_URL}/api`,
  headers: { "Content-Type": "application/json" },
});

// Attach access token + ngrok bypass header
api.interceptors.request.use((config) => {
  if (isBrowser) {
    const token = localStorage.getItem("access_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  // ngrok free tier shows a browser warning page — this header skips it
  config.headers["ngrok-skip-browser-warning"] = "1";
  return config;
});

// Auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      if (isBrowser) {
        const refresh = localStorage.getItem("refresh_token");
        if (refresh) {
          try {
            // Use the global axios (no interceptors) to avoid recursive
            // interceptor calls. Use relative path so the request is same-origin
            // and forwarded by Next.js to the real backend.
            const { data } = await axios.post(`/api/auth/refresh`, {
              refresh_token: refresh,
            }, {
              headers: { "ngrok-skip-browser-warning": "1" }
            });
            localStorage.setItem("access_token", data.access_token);
            localStorage.setItem("refresh_token", data.refresh_token);
            original.headers.Authorization = `Bearer ${data.access_token}`;
            return api(original);
          } catch {
            localStorage.clear();
            globalThis.window.location.href = "/login";
          }
        }
      } else {
        // Server-side: call backend directly
        try {
          await axios.post(`${API_URL}/api/auth/refresh`, {
            refresh_token: error.config?.headers?.["refresh_token"] ?? null,
          }, {
            headers: { "ngrok-skip-browser-warning": "1" }
          });
          // No localStorage on server — just return original request failure
        } catch {
          // ignore on server
        }
      }
    }
    throw parseApiError(error);
  },
);
