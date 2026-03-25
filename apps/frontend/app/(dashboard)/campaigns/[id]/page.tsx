"use client";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSSE } from "@/lib/sse";
import type { Campaign, MessageLog, CampaignProgress } from "@/types";
import { toast } from "sonner";
import { Download, Play, Pause, XCircle } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

const STATUS_COLORS: Record<string, string> = {
  queued: "bg-blue-100 text-blue-700",
  sending: "bg-yellow-100 text-yellow-700",
  sent: "bg-green-100 text-green-700",
  delivered: "bg-emerald-100 text-emerald-700",
  read: "bg-purple-100 text-purple-700",
  failed: "bg-red-100 text-red-700",
};

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const { data: campaign } = useQuery<Campaign>({
    queryKey: ["campaign", id],
    queryFn: () => api.get(`/campaigns/${id}`).then((r) => r.data),
  });

  const { data: messages } = useQuery({
    queryKey: ["campaign-messages", id],
    queryFn: () =>
      api
        .get(`/campaigns/${id}/messages?page=1&page_size=50`)
        .then((r) => r.data),
  });

  const { data: failureBreakdown } = useQuery<
    { reason: string; count: number }[]
  >({
    queryKey: ["campaign-failures", id],
    queryFn: () =>
      api.get(`/campaigns/${id}/failure-breakdown`).then((r) => r.data),
    enabled: !!campaign && (campaign.failed_count ?? 0) > 0,
  });

  // Live progress via SSE
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
    onError: () => toast.error("Failed to start campaign"),
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
    onError: () => toast.error("No failed messages to retry"),
  });

  const pct = live.total > 0 ? Math.round((live.sent / live.total) * 100) : 0;
  const logs: MessageLog[] = messages?.items ?? [];

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
              } catch {
                toast.error("Export failed");
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

      {/* Failure breakdown chart */}
      {failureBreakdown && failureBreakdown.length > 0 && (
        <FailureChart data={failureBreakdown} />
      )}

      {/* Message logs */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <div className="px-5 py-4 border-b">
          <h2 className="font-medium text-sm">Message Logs</h2>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-4 py-2.5 font-medium text-gray-500">
                Phone
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-500">
                Name
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-500">
                Status
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-500">
                Retries
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-500">
                Error
              </th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {logs.map((m) => (
              <tr key={m.id} className="hover:bg-gray-50">
                <td className="px-4 py-2.5 font-mono text-xs">
                  {m.recipient_phone}
                </td>
                <td className="px-4 py-2.5 text-gray-600">
                  {m.recipient_name || "—"}
                </td>
                <td className="px-4 py-2.5">
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[m.status] ?? "bg-gray-100 text-gray-600"}`}
                  >
                    {m.status}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-gray-400">{m.retry_count}</td>
                <td className="px-4 py-2.5 text-red-500 text-xs">
                  {m.error_code ? `${m.error_code}: ${m.error_message}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FailureChart({ data }: { data: { reason: string; count: number }[] }) {
  // Shorten long labels for the Y axis
  const chartData = data.map((d) => ({
    ...d,
    label: d.reason.length > 40 ? d.reason.slice(0, 40) + "…" : d.reason,
  }));

  return (
    <div className="bg-white rounded-xl border p-5 space-y-3">
      <h2 className="font-medium text-sm">Failure Reasons</h2>
      <ResponsiveContainer
        width="100%"
        height={Math.max(120, chartData.length * 52)}
      >
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 4, right: 48, left: 8, bottom: 4 }}
        >
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
          <YAxis
            type="category"
            dataKey="label"
            width={260}
            tick={{ fontSize: 11 }}
          />
          <Tooltip
            formatter={(value) => [value, "Count"]}
            labelFormatter={(label) => String(label)}
          />
          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={i === 0 ? "#f87171" : "#fca5a5"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
