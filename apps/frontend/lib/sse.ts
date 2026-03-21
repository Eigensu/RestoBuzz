"use client";
import { useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function useSSE<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!path) return;
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    const url = `${API_URL}/api${path}${token ? `?token=${token}` : ""}`;

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
