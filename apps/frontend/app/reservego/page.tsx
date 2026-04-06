"use client";

import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import axios from "axios";
import { toast } from "sonner";
import {
  Upload,
  LogIn,
  FileSpreadsheet,
  CheckCircle,
  Loader2,
} from "lucide-react";

const api = axios.create({ baseURL: "/api" });

interface UploadResult {
  inserted: number;
  skipped: number;
  filename: string;
  uploaded_at: string;
  sheets: Record<string, { inserted: number; skipped: number; note?: string }>;
}

/* ── Login form ─────────────────────────────────────────────────────────── */
function LoginForm({ onSuccess }: { onSuccess: (token: string) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await api.post<{ access_token: string }>("/reservego/login", {
        username,
        password,
      });
      const token = res.data?.access_token;
      if (!token) throw new Error("No token in response");
      onSuccess(token);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Invalid username or password";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const fieldWrap = "bg-[#eff2f0] px-3 py-2";
  const fieldLabel = "block text-[10px] text-gray-400 font-medium mb-0.5";
  const fieldInput =
    "w-full bg-transparent outline-none text-sm text-[#24422e] placeholder-gray-400";

  return (
    <form onSubmit={handleSubmit} className="space-y-3 w-full max-w-sm">
      <div className={fieldWrap}>
        <label className={fieldLabel}>Username</label>
        <input
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="reservego"
          className={fieldInput}
          required
        />
      </div>
      <div className={fieldWrap}>
        <label className={fieldLabel}>Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          className={fieldInput}
          required
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full bg-[#24422e] hover:bg-[#1a3022] text-white py-3 text-sm font-medium transition-colors disabled:opacity-60 flex items-center justify-center gap-2 rounded-[9px]"
      >
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <LogIn className="w-4 h-4" />
        )}
        {loading ? "Signing in…" : "Sign In"}
      </button>
    </form>
  );
}

/* ── Success screen ─────────────────────────────────────────────────────── */
function SuccessScreen({
  result,
  onReset,
}: {
  result: UploadResult;
  onReset: () => void;
}) {
  return (
    <div className="w-full max-w-sm flex flex-col items-center text-center py-4 animate-in fade-in duration-500">
      {/* Animated tick circle */}
      <div className="relative w-24 h-24 mb-6">
        <svg viewBox="0 0 96 96" className="w-24 h-24 -rotate-90">
          <circle
            cx="48"
            cy="48"
            r="40"
            fill="none"
            stroke="#e8f5e9"
            strokeWidth="6"
          />
          <circle
            cx="48"
            cy="48"
            r="40"
            fill="none"
            stroke="#24422e"
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray="251"
            strokeDashoffset="0"
            className="animate-[dash_0.8s_ease-out_forwards]"
            style={{ animation: "dash 0.8s ease-out forwards" }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <CheckCircle
            className="w-10 h-10 text-[#24422e]"
            style={{ animation: "pop 0.3s ease-out 0.7s both" }}
          />
        </div>
      </div>

      <h2 className="text-2xl font-light text-[#24422e] mb-1">Thank you!</h2>
      <p className="text-sm text-gray-500 mb-1">
        Your data has been uploaded successfully.
      </p>
      <p className="text-xs text-gray-400 mb-4">
        {result.inserted} records saved · {result.skipped} skipped
      </p>

      {/* Per-sheet breakdown */}
      <div className="w-full bg-[#eff2f0] rounded-lg p-3 mb-6 text-left space-y-1">
        {Object.entries(result.sheets).map(([sheet, stats]) => (
          <div key={sheet} className="flex justify-between text-xs">
            <span className="text-[#24422e] font-medium truncate max-w-[60%]">
              {sheet}
            </span>
            <span className="text-gray-500">
              {stats.note ??
                `${stats.inserted} saved · ${stats.skipped} skipped`}
            </span>
          </div>
        ))}
      </div>

      <button
        onClick={onReset}
        className="w-full bg-[#24422e] hover:bg-[#1a3022] text-white py-3 text-sm font-medium transition-colors flex items-center justify-center gap-2 rounded-[9px]"
      >
        <Upload className="w-4 h-4" />
        Upload Again
      </button>

      <style>{`
        @keyframes dash {
          from { stroke-dashoffset: 251; }
          to   { stroke-dashoffset: 0; }
        }
        @keyframes pop {
          from { transform: scale(0); opacity: 0; }
          to   { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  );
}

/* ── Upload form ────────────────────────────────────────────────────────── */
function UploadForm({ token }: { token: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) {
      setFile(accepted[0]);
      setResult(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
        ".xlsx",
      ],
      "application/vnd.ms-excel": [".xls"],
    },
    multiple: false,
  });

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api.post<UploadResult>("/reservego/upload", form, {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "multipart/form-data",
        },
      });
      setResult(res.data);
    } catch {
      toast.error("Upload failed. Please check the file format and try again.");
    } finally {
      setUploading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setResult(null);
  };

  if (result) {
    return <SuccessScreen result={result} onReset={handleReset} />;
  }

  if (uploading) {
    return (
      <div className="w-full max-w-sm flex flex-col items-center text-center py-8">
        <div className="relative w-20 h-20 mb-6">
          <svg
            viewBox="0 0 80 80"
            className="w-20 h-20 -rotate-90 animate-spin"
            style={{ animationDuration: "1.2s" }}
          >
            <circle
              cx="40"
              cy="40"
              r="34"
              fill="none"
              stroke="#eff2f0"
              strokeWidth="6"
            />
            <circle
              cx="40"
              cy="40"
              r="34"
              fill="none"
              stroke="#24422e"
              strokeWidth="6"
              strokeLinecap="round"
              strokeDasharray="213"
              strokeDashoffset="160"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <Upload className="w-7 h-7 text-[#24422e] opacity-70" />
          </div>
        </div>
        <p className="text-sm font-medium text-[#24422e]">
          Uploading your data…
        </p>
        <p className="text-xs text-gray-400 mt-1">
          This may take a moment for large files
        </p>
      </div>
    );
  }

  return (
    <div className="w-full max-w-sm space-y-4">
      {/* Dropzone */}
      <div
        {...getRootProps()}
        className={[
          "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
          isDragActive
            ? "border-[#24422e] bg-[#eff2f0]"
            : "border-gray-300 hover:border-[#24422e] hover:bg-[#eff2f0]/50",
        ].join(" ")}
      >
        <input {...getInputProps()} />
        <FileSpreadsheet className="w-10 h-10 mx-auto mb-3 text-[#24422e] opacity-60" />
        {file ? (
          <p className="text-sm text-[#24422e] font-medium">{file.name}</p>
        ) : (
          <>
            <p className="text-sm text-gray-600">
              {isDragActive
                ? "Drop the file here"
                : "Drag & drop your Excel file here"}
            </p>
            <p className="text-xs text-gray-400 mt-1">
              or click to browse (.xlsx / .xls)
            </p>
          </>
        )}
      </div>

      {/* Expected columns hint */}
      <div className="bg-[#eff2f0] rounded p-3 text-xs text-gray-500 space-y-1">
        <p className="font-medium text-[#24422e]">Expected columns:</p>
        <p>
          Guest Name · Phone Number · Email ID · Total Visits · Source · Mode ·
          Last Visited Date · Birthday · Anniversary
        </p>
      </div>

      {/* Upload button */}
      <button
        onClick={handleUpload}
        disabled={!file || uploading}
        className="w-full bg-[#24422e] hover:bg-[#1a3022] text-white py-3 text-sm font-medium transition-colors disabled:opacity-60 flex items-center justify-center gap-2 rounded-[9px]"
      >
        {uploading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Upload className="w-4 h-4" />
        )}
        {uploading ? "Uploading…" : "Upload Data"}
      </button>
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────────────────── */
export default function ReserveGoPage() {
  const [token, setToken] = useState("");

  return (
    <div className="min-h-screen bg-[#24422e] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-8">
        {/* Header */}
        <div className="flex items-center gap-2 mb-6">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/logo-final.webp"
            alt="DishPatch"
            className="w-8 h-8 rounded object-cover"
          />
          <span className="text-lg font-semibold text-[#24422e]">
            DishPatch
          </span>
        </div>

        {!token ? (
          <>
            <h1 className="text-2xl font-light text-[#24422e] mb-1">
              ReserveGo Upload Portal
            </h1>
            <p className="text-xs text-gray-500 mb-6">
              Sign in to upload your guest data.
            </p>
            <LoginForm onSuccess={setToken} />
          </>
        ) : (
          <>
            <h1 className="text-2xl font-light text-[#24422e] mb-1">
              Upload Guest Data
            </h1>
            <p className="text-xs text-gray-500 mb-6">
              Upload your ReserveGo Excel export. Existing records will be
              updated by phone number.
            </p>
            <UploadForm token={token} />
          </>
        )}
      </div>
    </div>
  );
}
