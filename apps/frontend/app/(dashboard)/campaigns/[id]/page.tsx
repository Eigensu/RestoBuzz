"use client";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSSE } from "@/lib/sse";
import type { Campaign, CampaignProgress } from "@/types";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { Download, Play, Pause, XCircle } from "lucide-react";
import { FailureChart } from "@/components/campaigns/molecules/FailureChart";
import { MessageLogsTable } from "@/components/campaigns/molecules/MessageLogsTable";

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const { data: campaign } = useQuery<Campaign>({
    queryKey: ["campaign", id],
    queryFn: () => api.get(`/campaigns/${id}`).then((r) => r.data),
  });

  const { data: failureBreakdown } = useQuery<
    { reason: string; count: number }[]
  >({
    queryKey: ["campaign-failures", id],
    queryFn: () =>
      api.get(`/campaigns/${id}/failure-breakdown`).then((r) => r.data),
    enabled: !!campaign && (campaign.failed_count ?? 0) > 0,
  });

  const { data: progress } = useSSE<CampaignProgress>(
    campaign &&
      !["completed", "failed", "cancelled", "draft"].includes(campaign.status)
      ? `/campaigns/${id}/stream`
      : null,
  );

  const live = progress ?? {
    sent: campaign?.sent_count ?? 0,
    delivered: campaign?.delivered_count ?? 0,
    read: campaign?.read_count ?? 0,
    failed: campaign?.failed_count ?? 0,
    total: campaign?.total_count ?? 0,
  };

  const startMutation = useMutation({
    mutationFn: () => api.post(`/campaigns/${id}/start`),
    onSuccess: () => {
      toast.success("Campaign started");
      qc.invalidateQueries({ queryKey: ["campaign", id] });
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });
  const pauseMutation = useMutation({
    mutationFn: () => api.post(`/campaigns/${id}/pause`),
    onSuccess: () => {
      toast.success("Campaign paused");
      qc.invalidateQueries({ queryKey: ["campaign", id] });
    },
  });
  const cancelMutation = useMutation({
    mutationFn: () => api.post(`/campaigns/${id}/cancel`),
    onSuccess: () => {
      toast.success("Campaign cancelled");
      qc.invalidateQueries({ queryKey: ["campaign", id] });
    },
  });
  const retryMutation = useMutation({
    mutationFn: () => api.post(`/campaigns/${id}/retry-failed`),
    onSuccess: (res) => {
      toast.success(`Retry started — ${res.data.total_count} messages queued`);
      qc.invalidateQueries({ queryKey: ["campaigns"] });
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const pct = live.total > 0 ? Math.round((live.sent / live.total) * 100) : 0;

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">{campaign?.name}</h1>
          <p className="text-sm text-gray-400">
            {campaign?.template_name} · {campaign?.priority}
          </p>
        </div>
        <div className="flex gap-2">
          {campaign?.status === "draft" && (
            <button
              onClick={() => startMutation.mutate()}
              className="flex items-center gap-1.5 bg-green-500 hover:bg-green-600 text-white text-sm px-3 py-1.5 rounded-lg transition"
            >
              <Play className="w-3.5 h-3.5" /> Start
            </button>
          )}
          {campaign?.status === "running" && (
            <button
              onClick={() => pauseMutation.mutate()}
              className="flex items-center gap-1.5 bg-orange-500 hover:bg-orange-600 text-white text-sm px-3 py-1.5 rounded-lg transition"
            >
              <Pause className="w-3.5 h-3.5" /> Pause
            </button>
          )}
          {["draft", "queued", "running", "paused"].includes(
            campaign?.status ?? "",
          ) && (
            <button
              onClick={() => cancelMutation.mutate()}
              className="flex items-center gap-1.5 border text-gray-600 hover:bg-gray-50 text-sm px-3 py-1.5 rounded-lg transition"
            >
              <XCircle className="w-3.5 h-3.5" /> Cancel
            </button>
          )}
          {(campaign?.failed_count ?? 0) > 0 &&
            !["running", "queued"].includes(campaign?.status ?? "") && (
              <button
                onClick={() => retryMutation.mutate()}
                disabled={retryMutation.isPending}
                className="flex items-center gap-1.5 bg-orange-500 hover:bg-orange-600 text-white text-sm px-3 py-1.5 rounded-lg transition disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5" /> Retry Failed
              </button>
            )}
          <button
            onClick={async () => {
              try {
                const res = await api.get(`/campaigns/${id}/export-failed`, {
                  responseType: "blob",
                });
                const url = URL.createObjectURL(new Blob([res.data]));
                const a = document.createElement("a");
                a.href = url;
                a.download = `failed_${id}.csv`;
                a.click();
                URL.revokeObjectURL(url);
              } catch (e) {
                toast.error(parseApiError(e).message);
              }
            }}
            className="flex items-center gap-1.5 border text-gray-600 hover:bg-gray-50 text-sm px-3 py-1.5 rounded-lg transition"
          >
            <Download className="w-3.5 h-3.5" /> Export Failed
          </button>
        </div>
      </div>

      {/* Progress */}
      <div className="bg-white rounded-xl border p-5 space-y-4">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium">Progress</span>
          <span className="text-gray-400">
            {live.sent} / {live.total} sent ({pct}%)
          </span>
        </div>
        <div className="bg-gray-100 rounded-full h-2">
          <div
            className="bg-green-500 h-2 rounded-full transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="grid grid-cols-4 gap-3 text-center">
          {[
            { label: "Sent", value: live.sent, color: "text-blue-600" },
            {
              label: "Delivered",
              value: live.delivered,
              color: "text-green-600",
            },
            { label: "Read", value: live.read, color: "text-purple-600" },
            { label: "Failed", value: live.failed, color: "text-red-600" },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-gray-50 rounded-lg p-3">
              <p className={`text-lg font-bold ${color}`}>{value}</p>
              <p className="text-xs text-gray-400">{label}</p>
            </div>
          ))}
        </div>
      </div>

      {failureBreakdown && failureBreakdown.length > 0 && (
        <FailureChart data={failureBreakdown} />
      )}
      <MessageLogsTable campaignId={id} />
    </div>
  );
}
