"use client";
import { useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function useSSE<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!path) return;
    const token =
      typeof globalThis.window !== "undefined"
        ? localStorage.getItem("access_token")
        : null;
    const params = new URLSearchParams();
    if (token) params.set("token", token);
    // ngrok free tier blocks requests without this header; query param works for EventSource
    params.set("ngrok-skip-browser-warning", "1");
    const url = `${API_URL}/api${path}?${params.toString()}`;

    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        setData(JSON.parse(e.data));
      } catch {
        setData(e.data as T);
      }
    };

    es.onerror = () => {
      setError("SSE connection error");
      es.close();
    };

    return () => {
      es.close();
    };
  }, [path]);

  return { data, error };
}
