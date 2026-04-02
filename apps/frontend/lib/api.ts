import axios from "axios";
import { parseApiError } from "./errors";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const isBrowser = globalThis.window !== undefined;

// In-memory access token — avoids repeated localStorage reads and is cleared
// on tab close (more secure than persisting in localStorage long-term).
let volatileAccessToken: string | null = null;

// Deduplication: if a refresh is already in flight, all concurrent 401s wait
// for the same promise instead of each firing their own refresh request.
let refreshInFlight: Promise<string> | null = null;

export const api = axios.create({
  baseURL: isBrowser ? "/api" : `${API_URL}/api`,
  headers: { "Content-Type": "application/json" },
});

// ── Request interceptor: attach access token ──────────────────────────────
api.interceptors.request.use((config) => {
  if (isBrowser) {
    const token = volatileAccessToken ?? localStorage.getItem("access_token");
    if (token) {
      volatileAccessToken = token; // cache in memory after first read
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  config.headers["ngrok-skip-browser-warning"] = "1";
  return config;
});

// ── Response interceptor: refresh on 401 ─────────────────────────────────
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;

    // Only attempt refresh once per request, and only on 401
    if (error.response?.status !== 401 || original._retry) {
      throw parseApiError(error);
    }

    original._retry = true;

    if (!isBrowser) throw parseApiError(error);

    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) {
      // No refresh token stored — send to login
      _redirectToLogin();
      throw parseApiError(error);
    }

    try {
      // Deduplicate: reuse an in-flight refresh if one is already running
      if (!refreshInFlight) {
        refreshInFlight = axios
          .post<{ access_token: string; refresh_token: string }>(
            `/api/auth/refresh`,
            { refresh_token: refreshToken },
            {
              headers: {
                "Content-Type": "application/json",
                "ngrok-skip-browser-warning": "1",
              },
            },
          )
          .then((r) => {
            const { access_token, refresh_token: newRefresh } = r.data;
            // Persist both new tokens
            volatileAccessToken = access_token;
            localStorage.setItem("access_token", access_token);
            localStorage.setItem("refresh_token", newRefresh);
            return access_token;
          })
          .catch((err) => {
            // Refresh itself failed — clear everything and redirect
            _redirectToLogin();
            throw err;
          })
          .finally(() => {
            refreshInFlight = null;
          });
      }

      const newAccessToken = await refreshInFlight;
      original.headers.Authorization = `Bearer ${newAccessToken}`;
      return api(original);
    } catch (refreshError) {
      throw parseApiError(refreshError);
    }
  },
);

function _redirectToLogin() {
  volatileAccessToken = null;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  globalThis.window.location.href = "/login";
}

/** Call this on logout to clear the in-memory token cache. */
export function clearVolatileToken() {
  volatileAccessToken = null;
}
