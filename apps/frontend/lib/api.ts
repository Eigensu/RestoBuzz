import axios from "axios";
import { parseApiError } from "./errors";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const isBrowser = globalThis.window !== undefined;

let volatileAccessToken: string | null = null;

// Single shared promise for any in-flight refresh — prevents concurrent
// 401s from each firing their own refresh request.
let refreshInFlight: Promise<string> | null = null;

export const api = axios.create({
  baseURL: isBrowser ? "/api" : `${API_URL}/api`,
  headers: { "Content-Type": "application/json" },
});

// ── Request: attach current access token ─────────────────────────────────
api.interceptors.request.use((config) => {
  if (isBrowser) {
    const token = volatileAccessToken ?? localStorage.getItem("access_token");
    if (token) {
      volatileAccessToken = token;
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  config.headers["ngrok-skip-browser-warning"] = "1";
  return config;
});

// ── Response: on 401, refresh once then retry ─────────────────────────────
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;

    if (error.response?.status !== 401 || original._retry) {
      throw parseApiError(error);
    }
    original._retry = true;

    if (!isBrowser) throw parseApiError(error);

    const storedRefreshToken = localStorage.getItem("refresh_token");
    if (!storedRefreshToken) {
      _redirectToLogin();
      throw parseApiError(error);
    }

    try {
      // Start a refresh only if one isn't already running.
      // IMPORTANT: don't clear refreshInFlight until the promise fully
      // settles so concurrent waiters all get the same resolved value.
      if (!refreshInFlight) {
        refreshInFlight = _doRefresh(storedRefreshToken);
      }

      const newAccessToken = await refreshInFlight;

      // Patch the original request with the fresh token and replay it.
      // Set it directly — don't rely on the request interceptor re-reading
      // volatileAccessToken, because the config object may be stale.
      original.headers = original.headers ?? {};
      original.headers.Authorization = `Bearer ${newAccessToken}`;
      return api(original);
    } catch (refreshError) {
      // Refresh failed (expired refresh token, network error, etc.)
      // Only redirect if the refresh token itself was rejected (401/422).
      // Don't redirect on transient network errors.
      const status = (refreshError as { response?: { status?: number } })
        ?.response?.status;
      if (status === 401 || status === 422 || status === 403) {
        _redirectToLogin();
      }
      throw parseApiError(refreshError);
    }
  },
);

async function _doRefresh(refreshToken: string): Promise<string> {
  try {
    const res = await axios.post<{
      access_token: string;
      refresh_token: string;
    }>(
      `${isBrowser ? "" : API_URL}/api/auth/refresh`,
      { refresh_token: refreshToken },
      {
        headers: {
          "Content-Type": "application/json",
          "ngrok-skip-browser-warning": "1",
        },
      },
    );

    const { access_token, refresh_token: newRefresh } = res.data;
    volatileAccessToken = access_token;
    localStorage.setItem("access_token", access_token);
    localStorage.setItem("refresh_token", newRefresh);
    return access_token;
  } finally {
    // Clear only after the promise resolves/rejects so all concurrent
    // waiters have already received the value.
    refreshInFlight = null;
  }
}

function _redirectToLogin() {
  volatileAccessToken = null;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  if (isBrowser) globalThis.window.location.href = "/login";
}

export function clearVolatileToken() {
  volatileAccessToken = null;
}
