"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { EmailCampaign, EmailLog } from "@/types";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Mail,
  Send,
  CheckCircle2,
  Eye,
  MousePointerClick,
  AlertTriangle,
  XCircle,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";

const METRIC_CARDS = [
  { key: "sent_count", label: "Sent", icon: Send, color: "text-blue-600", bg: "bg-blue-50" },
  { key: "delivered_count", label: "Delivered", icon: CheckCircle2, color: "text-emerald-600", bg: "bg-emerald-50" },
  { key: "opened_count", label: "Opened", icon: Eye, color: "text-violet-600", bg: "bg-violet-50" },
  { key: "clicked_count", label: "Clicked", icon: MousePointerClick, color: "text-purple-600", bg: "bg-purple-50" },
  { key: "bounced_count", label: "Bounced", icon: AlertTriangle, color: "text-amber-600", bg: "bg-amber-50" },
  { key: "failed_count", label: "Failed", icon: XCircle, color: "text-red-600", bg: "bg-red-50" },
] as const;

const LOG_STATUS_COLORS: Record<string, string> = {
  queued: "bg-gray-100 text-gray-600",
  sending: "bg-blue-50 text-blue-700",
  sent: "bg-sky-50 text-sky-700",
  delivered: "bg-emerald-50 text-emerald-700",
  opened: "bg-violet-50 text-violet-700",
  clicked: "bg-purple-50 text-purple-700",
  bounced: "bg-amber-50 text-amber-700",
  failed: "bg-red-50 text-red-700",
  complained: "bg-orange-50 text-orange-700",
  suppressed: "bg-gray-100 text-gray-500",
};

export default function EmailCampaignDetailPage() {
  const params = useParams();
  const campaignId = params.id as string;
  const { restaurant } = useAuthStore();

  const { data: campaign, isLoading: loadingCampaign } = useQuery<EmailCampaign>({
    queryKey: ["email-campaign", campaignId],
    queryFn: () => api.get(`/email-campaigns/${campaignId}`).then((r) => r.data),
    enabled: !!campaignId,
    refetchInterval: (query) => {
      const c = query.state.data;
      return c && ["queued", "sending"].includes(c.status) ? 3000 : false;
    },
  });

  const { data: logsData, isLoading: loadingLogs } = useQuery({
    queryKey: ["email-campaign-logs", campaignId],
    queryFn: () =>
      api.get(`/email-campaigns/${campaignId}/messages?page=1&page_size=100`).then((r) => r.data),
    enabled: !!campaignId,
    refetchInterval: (query) => {
      return campaign && ["queued", "sending"].includes(campaign.status) ? 5000 : false;
    },
  });

  const logs: EmailLog[] = logsData?.items ?? [];

  if (loadingCampaign) {
    return (
      <div className="max-w-[1600px] mx-auto p-4 md:p-8">
        <div className="bg-white rounded-xl border p-12 text-center text-sm text-gray-400">
          Loading campaign...
        </div>
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="max-w-[1600px] mx-auto p-4 md:p-8">
        <div className="bg-white rounded-xl border p-12 text-center text-sm text-red-500">
          Campaign not found
        </div>
      </div>
    );
  }

  const deliveryRate = campaign.sent_count
    ? Math.round((campaign.delivered_count / campaign.sent_count) * 100)
    : 0;
  const openRate = campaign.delivered_count
    ? Math.round((campaign.opened_count / campaign.delivered_count) * 100)
    : 0;

  return (
    <div className="space-y-6 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      {/* Header */}
      <div>
        <Link
          href="/campaigns/email"
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition mb-3"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Email Campaigns
        </Link>
        <div className="flex items-center gap-3">
          <div className="p-2 bg-[#eff2f0] rounded-lg">
            <Mail className="w-6 h-6 text-[#24422e]" />
          </div>
          <div>
            <h1 className="text-2xl font-black text-gray-900 tracking-tight">
              {campaign.name}
            </h1>
            <p className="text-xs text-gray-400 mt-0.5">
              Created {formatDistanceToNow(new Date(campaign.created_at), { addSuffix: true })}
            </p>
          </div>
        </div>
      </div>

      {/* Summary Rates */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500 font-medium">Total Contacts</p>
          <p className="text-2xl font-black text-gray-900 mt-1">{campaign.total_count}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500 font-medium">Delivery Rate</p>
          <p className="text-2xl font-black text-emerald-600 mt-1">{deliveryRate}%</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500 font-medium">Open Rate</p>
          <p className="text-2xl font-black text-violet-600 mt-1">{openRate}%</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500 font-medium">Status</p>
          <p className="text-lg font-bold text-gray-700 mt-1 capitalize">{campaign.status.replace("_", " ")}</p>
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {METRIC_CARDS.map(({ key, label, icon: Icon, color, bg }) => (
          <div key={key} className="bg-white rounded-xl border p-4 flex items-center gap-3">
            <div className={`p-2 rounded-lg ${bg}`}>
              <Icon className={`w-4 h-4 ${color}`} />
            </div>
            <div>
              <p className="text-xs text-gray-500">{label}</p>
              <p className={`text-lg font-bold ${color} tabular-nums`}>
                {campaign[key as keyof EmailCampaign] as number}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Message Logs Table */}
      <div className="bg-white rounded-2xl border overflow-hidden">
        <div className="px-5 py-4 border-b">
          <h2 className="text-sm font-bold text-gray-900">Delivery Log</h2>
          <p className="text-xs text-gray-400 mt-0.5">{logs.length} recipients shown</p>
        </div>
        {loadingLogs ? (
          <div className="p-12 text-center text-sm text-gray-400">Loading logs...</div>
        ) : logs.length === 0 ? (
          <div className="p-12 text-center text-sm text-gray-400">No logs yet</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/50 border-b">
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Recipient</th>
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Resend ID</th>
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Error</th>
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Updated</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} className="border-b last:border-b-0 hover:bg-gray-50/50 transition">
                    <td className="px-5 py-3">
                      <p className="font-medium text-gray-900">{log.recipient_email}</p>
                      {log.recipient_name && (
                        <p className="text-xs text-gray-400">{log.recipient_name}</p>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-bold ${LOG_STATUS_COLORS[log.status] || "bg-gray-100 text-gray-600"}`}>
                        {log.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-xs text-gray-400 font-mono">
                      {log.resend_email_id ? log.resend_email_id.slice(0, 12) + "..." : "—"}
                    </td>
                    <td className="px-5 py-3 text-xs text-red-500 max-w-[200px] truncate">
                      {log.error_reason || "—"}
                    </td>
                    <td className="px-5 py-3 text-xs text-gray-400">
                      {formatDistanceToNow(new Date(log.updated_at), { addSuffix: true })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
