"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  RefreshCw,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface RetryChainItem {
  id: string;
  name: string;
  status: string;
  created_at: string;
  total_count: number;
  sent_count: number;
  delivered_count: number;
  failed_count: number;
  is_root: boolean;
}

interface SmartRetryStatusData {
  campaign_id: string;
  campaign_name: string;
  smart_retries_enabled: boolean;
  status: string;
  failed_count: number;
  retry_until: string | null;
  last_auto_retry_at: string | null;
  last_retry_seconds_ago: number | null;
  next_retry_at: string | null;
  next_retry_in_seconds: number | null;
  deadline_in_seconds: number | null;
  is_eligible_for_retry: boolean;
  reason_not_eligible: string | null;
  retry_chain: RetryChainItem[];
  total_retries: number;
}

function formatDuration(seconds: number): string {
  if (seconds <= 0) return "any moment";
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;
  if (remMins === 0) return `${hrs}h`;
  return `${hrs}h ${remMins}m`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface Props {
  campaignId: string;
}

export function SmartRetryStatus({ campaignId }: Props) {
  const { data, isLoading } = useQuery<SmartRetryStatusData>({
    queryKey: ["smart-retry-status", campaignId],
    queryFn: () =>
      api
        .get(`/campaigns/${campaignId}/smart-retry-status`)
        .then((r) => r.data),
    refetchInterval: 60_000, // refresh every minute
  });

  if (isLoading) {
    return (
      <div className="bg-white rounded-[32px] border border-gray-100 p-8 shadow-sm animate-pulse">
        <div className="h-4 bg-gray-100 rounded w-1/3 mb-6" />
        <div className="space-y-3">
          <div className="h-3 bg-gray-100 rounded w-full" />
          <div className="h-3 bg-gray-100 rounded w-2/3" />
        </div>
      </div>
    );
  }

  if (!data) return null;

  const deadlineHours = data.deadline_in_seconds
    ? Math.floor(data.deadline_in_seconds / 3600)
    : null;

  return (
    <div className="bg-white rounded-[32px] border border-gray-100 p-8 shadow-sm space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <RefreshCw className="w-5 h-5 text-indigo-500" />
          <h3 className="text-sm font-black text-gray-900 uppercase tracking-widest">
            Smart Retries
          </h3>
        </div>
        {data.is_eligible_for_retry ? (
          <span className="flex items-center gap-1 px-3 py-1 bg-indigo-50 text-indigo-600 rounded-full text-[10px] font-black uppercase tracking-wider">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse inline-block" />
            Active
          </span>
        ) : (
          <span className="flex items-center gap-1 px-3 py-1 bg-gray-100 text-gray-400 rounded-full text-[10px] font-black uppercase tracking-wider">
            Inactive
          </span>
        )}
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-3 gap-3">
        <div className="p-4 rounded-2xl bg-indigo-50/50 border border-indigo-100/50">
          <p className="text-2xl font-black text-indigo-600">
            {data.total_retries}
          </p>
          <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mt-0.5">
            Auto-retries done
          </p>
        </div>

        <div className="p-4 rounded-2xl bg-amber-50/50 border border-amber-100/50">
          <p className="text-2xl font-black text-amber-600">
            {data.failed_count.toLocaleString()}
          </p>
          <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mt-0.5">
            Still failed
          </p>
        </div>

        <div className="p-4 rounded-2xl bg-gray-50 border border-gray-100">
          <p className="text-2xl font-black text-gray-700">
            {deadlineHours !== null ? `${deadlineHours}h` : "—"}
          </p>
          <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mt-0.5">
            Until deadline
          </p>
        </div>
      </div>

      {/* Next Retry / Status */}
      <div className="rounded-2xl border border-gray-100 bg-gray-50 px-5 py-4 space-y-2">
        {data.is_eligible_for_retry ? (
          <>
            <div className="flex items-center gap-2 text-xs font-bold text-gray-600">
              <Clock className="w-3.5 h-3.5 text-indigo-400" />
              Next retry:{" "}
              <span className="text-indigo-600 font-black">
                {data.next_retry_in_seconds === 0
                  ? "within 15 minutes"
                  : `in ${formatDuration(data.next_retry_in_seconds ?? 0)}`}
              </span>
            </div>
            {data.last_auto_retry_at && (
              <div className="flex items-center gap-2 text-xs text-gray-400 font-medium">
                <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />
                Last retry: {formatDate(data.last_auto_retry_at)}
              </div>
            )}
            {data.retry_until && (
              <div className="flex items-center gap-2 text-xs text-gray-400 font-medium">
                <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
                Deadline: {formatDate(data.retry_until)}
              </div>
            )}
          </>
        ) : (
          <div className="flex items-center gap-2 text-xs font-bold text-gray-500">
            <XCircle className="w-3.5 h-3.5 text-gray-400" />
            {data.reason_not_eligible ?? "Smart retries not active"}
          </div>
        )}
      </div>

      {/* Retry Chain Timeline */}
      {data.retry_chain.length > 1 && (
        <div className="space-y-2">
          <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest">
            Retry History
          </p>
          <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
            {data.retry_chain.map((item, i) => (
              <div
                key={item.id}
                className={cn(
                  "flex items-center gap-3 p-3 rounded-xl text-xs border",
                  item.is_root
                    ? "bg-gray-50 border-gray-100"
                    : "bg-indigo-50/40 border-indigo-100/50",
                )}
              >
                <span
                  className={cn(
                    "w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-black shrink-0",
                    item.is_root
                      ? "bg-gray-200 text-gray-600"
                      : "bg-indigo-500 text-white",
                  )}
                >
                  {item.is_root ? "0" : i}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="font-bold text-gray-700 truncate">
                    {item.is_root ? "Original" : `Retry #${i}`}
                    <span
                      className={cn(
                        "ml-2 text-[10px] font-black uppercase",
                        item.status === "completed"
                          ? "text-green-500"
                          : item.status === "failed"
                            ? "text-red-500"
                            : item.status === "running"
                              ? "text-blue-500"
                              : "text-gray-400",
                      )}
                    >
                      {item.status}
                    </span>
                  </p>
                  <p className="text-gray-400 font-medium">
                    {formatDate(item.created_at)} · {item.total_count}{" "}
                    recipients · {item.failed_count} failed
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
