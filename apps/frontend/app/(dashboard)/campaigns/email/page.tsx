"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { EmailCampaign } from "@/types";
import { BRAND_GRADIENT, GREEN } from "@/lib/brand";
import Link from "next/link";
import { Plus, Mail, Play, XCircle, Trash2, Download, Eye } from "lucide-react";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { EmptyState } from "@/components/ui/EmptyState";
import { EmailCampaignStatus } from "@/types/common/enums";
import { formatDistanceToNow } from "date-fns";

const ACTIVE_STATUSES = new Set([
  EmailCampaignStatus.QUEUED,
  EmailCampaignStatus.SENDING,
]);

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  draft: { bg: "bg-gray-100", text: "text-gray-600", label: "Draft" },
  queued: { bg: "bg-amber-50", text: "text-amber-700", label: "Queued" },
  sending: { bg: "bg-blue-50", text: "text-blue-700", label: "Sending" },
  completed: { bg: "bg-emerald-50", text: "text-emerald-700", label: "Completed" },
  partial_failure: { bg: "bg-orange-50", text: "text-orange-700", label: "Partial Failure" },
  failed: { bg: "bg-red-50", text: "text-red-700", label: "Failed" },
  cancelled: { bg: "bg-gray-100", text: "text-gray-500", label: "Cancelled" },
  quota_exceeded: { bg: "bg-red-50", text: "text-red-600", label: "Quota Exceeded" },
};

export default function EmailCampaignsPage() {
  const qc = useQueryClient();
  const { restaurant } = useAuthStore();

  const { data, isLoading } = useQuery({
    queryKey: ["email-campaigns", restaurant?.id],
    queryFn: () =>
      api
        .get(`/email-campaigns?restaurant_id=${restaurant!.id}&page=1&page_size=50`)
        .then((r) => r.data),
    enabled: !!restaurant,
    refetchInterval: (query) => {
      const campaigns: EmailCampaign[] = query.state.data?.items ?? [];
      const hasActive = campaigns.some((c) =>
        ACTIVE_STATUSES.has(c.status as EmailCampaignStatus),
      );
      return hasActive ? 5000 : false;
    },
  });

  const startMutation = useMutation({
    mutationFn: (id: string) => api.post(`/email-campaigns/${id}/start`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["email-campaigns", restaurant?.id] });
      toast.success("Campaign started");
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const cancelMutation = useMutation({
    mutationFn: (id: string) => api.post(`/email-campaigns/${id}/cancel`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["email-campaigns", restaurant?.id] });
      toast.success("Campaign cancelled");
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/email-campaigns/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["email-campaigns", restaurant?.id] });
      toast.success("Campaign deleted");
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const campaigns: EmailCampaign[] = data?.items ?? [];

  return (
    <div className="space-y-8 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#eff2f0] rounded-lg">
              <Mail className="w-6 h-6 text-[#24422e]" />
            </div>
            <h1 className="text-2xl font-black text-gray-900 tracking-tight">
              Email Campaigns
            </h1>
          </div>
          <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
            Broadcast email messages to your audience via Resend
          </p>
        </div>
        <Link
          href="/campaigns/email/new"
          className="inline-flex items-center gap-2 text-white text-sm font-bold px-6 py-3 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10"
          style={{ background: BRAND_GRADIENT }}
        >
          <Plus className="w-4 h-4" />
          NEW EMAIL CAMPAIGN
        </Link>
      </div>

      {isLoading ? (
        <div className="bg-white rounded-xl border p-12 text-center text-sm text-gray-400">
          Loading...
        </div>
      ) : campaigns.length === 0 ? (
        <div className="bg-white rounded-xl border">
          <EmptyState
            icon={Mail}
            title="No email campaigns yet"
            description="Create your first email campaign to start reaching your audience."
          />
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-gray-100 shadow-sm bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50/50">
                <th className="text-left px-5 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wider">Campaign</th>
                <th className="text-left px-5 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wider">Status</th>
                <th className="text-center px-5 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wider">Sent</th>
                <th className="text-center px-5 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wider">Delivered</th>
                <th className="text-center px-5 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wider">Opened</th>
                <th className="text-center px-5 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wider">Clicked</th>
                <th className="text-center px-5 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wider">Bounced</th>
                <th className="text-right px-5 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((c) => {
                const st = STATUS_STYLES[c.status] || STATUS_STYLES.draft;
                return (
                  <tr key={c.id} className="border-b last:border-b-0 hover:bg-gray-50/50 transition">
                    <td className="px-5 py-4">
                      <Link href={`/campaigns/email/${c.id}`} className="hover:underline">
                        <p className="font-semibold text-gray-900">{c.name}</p>
                        <p className="text-xs text-gray-400 mt-0.5">
                          {formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}
                        </p>
                      </Link>
                    </td>
                    <td className="px-5 py-4">
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold ${st.bg} ${st.text}`}>
                        {st.label}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-center font-medium tabular-nums">
                      {c.sent_count}/{c.total_count}
                    </td>
                    <td className="px-5 py-4 text-center font-medium tabular-nums text-emerald-600">
                      {c.delivered_count}
                    </td>
                    <td className="px-5 py-4 text-center font-medium tabular-nums text-blue-600">
                      {c.opened_count}
                    </td>
                    <td className="px-5 py-4 text-center font-medium tabular-nums text-purple-600">
                      {c.clicked_count}
                    </td>
                    <td className="px-5 py-4 text-center font-medium tabular-nums text-red-500">
                      {c.bounced_count}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center justify-end gap-1">
                        {c.status === "draft" && (
                          <button
                            onClick={() => startMutation.mutate(c.id)}
                            className="p-1.5 rounded-lg hover:bg-emerald-50 text-emerald-600 transition"
                            title="Start"
                          >
                            <Play className="w-4 h-4" />
                          </button>
                        )}
                        {["draft", "queued", "sending"].includes(c.status) && (
                          <button
                            onClick={() => cancelMutation.mutate(c.id)}
                            className="p-1.5 rounded-lg hover:bg-amber-50 text-amber-600 transition"
                            title="Cancel"
                          >
                            <XCircle className="w-4 h-4" />
                          </button>
                        )}
                        <Link
                          href={`/campaigns/email/${c.id}`}
                          className="p-1.5 rounded-lg hover:bg-blue-50 text-blue-600 transition"
                          title="View"
                        >
                          <Eye className="w-4 h-4" />
                        </Link>
                        {["failed", "bounced", "partial_failure"].includes(c.status) && (
                          <a
                            href={`/api/email-campaigns/${c.id}/export-failed`}
                            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition"
                            title="Export failed"
                          >
                            <Download className="w-4 h-4" />
                          </a>
                        )}
                        {c.status !== "sending" && (
                          <button
                            onClick={() => {
                              if (globalThis.confirm("Delete this campaign?"))
                                deleteMutation.mutate(c.id);
                            }}
                            className="p-1.5 rounded-lg hover:bg-red-50 text-red-500 transition"
                            title="Delete"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
