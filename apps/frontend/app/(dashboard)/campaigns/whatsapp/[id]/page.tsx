"use client";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSSE } from "@/lib/sse";
import type { Campaign, CampaignProgress } from "@/types";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { Download, Play, Pause, XCircle, Smartphone, Info, RefreshCw, BarChart3 } from "lucide-react";
import { FailureChart } from "@/components/campaigns/molecules/FailureChart";
import { MessageLogsTable } from "@/components/campaigns/molecules/MessageLogsTable";
import { CampaignStatus } from "@/types/common/enums";
import { BRAND_GRADIENT } from "@/lib/brand";
import { cn } from "@/lib/utils";

const ACTIVE_STATUSES = new Set([
  CampaignStatus.QUEUED,
  CampaignStatus.RUNNING,
  CampaignStatus.PAUSED,
]);
const CANCELLABLE_STATUSES = new Set([
  CampaignStatus.DRAFT,
  CampaignStatus.QUEUED,
  CampaignStatus.RUNNING,
  CampaignStatus.PAUSED,
]);
const INACTIVE_STATUSES = new Set([
  CampaignStatus.COMPLETED,
  CampaignStatus.FAILED,
  CampaignStatus.CANCELLED,
  CampaignStatus.DRAFT,
]);

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const isActiveCampaign = (status?: string) =>
    ACTIVE_STATUSES.has(status as CampaignStatus);

  const { data: campaign, isLoading: isCampaignLoading } = useQuery<Campaign>({
    queryKey: ["campaign", id],
    queryFn: () => api.get(`/campaigns/${id}`).then((r) => r.data),
    refetchInterval: (query) => {
      const status = (query.state.data as Campaign | undefined)?.status;
      return isActiveCampaign(status) ? 5000 : false;
    },
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
    campaign && !INACTIVE_STATUSES.has(campaign.status as CampaignStatus)
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
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const cancelMutation = useMutation({
    mutationFn: () => api.post(`/campaigns/${id}/cancel`),
    onSuccess: () => {
      toast.success("Campaign cancelled");
      qc.invalidateQueries({ queryKey: ["campaign", id] });
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
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

  if (isCampaignLoading) {
    return (
        <div className="h-64 flex items-center justify-center">
            <RefreshCw className="w-8 h-8 animate-spin text-[#24422e]" />
        </div>
    );
  }

  const BTN_BASE = "flex items-center gap-2 px-4 py-2 rounded-xl text-[11px] font-black uppercase tracking-widest transition shadow-lg disabled:opacity-50 active:scale-95 whitespace-nowrap";

  return (
    <div className="space-y-8 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-[#eff2f0] rounded-2xl shadow-sm">
            <Smartphone className="w-6 h-6 text-[#24422e]" />
          </div>
          <div>
             <div className="flex items-center gap-3">
                <h1 className="text-2xl font-black text-gray-900 tracking-tight uppercase">
                    {campaign?.name}
                </h1>
                <span className={cn(
                    "px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-wider shadow-sm",
                    campaign?.status === CampaignStatus.COMPLETED ? "bg-green-100 text-green-700" :
                    campaign?.status === CampaignStatus.FAILED ? "bg-red-100 text-red-700" :
                    campaign?.status === CampaignStatus.RUNNING ? "bg-blue-100 text-blue-700 animate-pulse" :
                    "bg-gray-100 text-gray-700"
                )}>
                    {campaign?.status}
                </span>
             </div>
             <p className="text-sm text-gray-500 font-medium flex items-center gap-1.5 mt-0.5">
                Template: <span className="text-[#24422e] font-bold">{campaign?.template_name}</span>
             </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {campaign?.status === CampaignStatus.DRAFT && (
            <button
              onClick={() => startMutation.mutate()}
              disabled={startMutation.isPending}
              className={cn(BTN_BASE, "text-white shadow-green-900/20")}
              style={{ background: BRAND_GRADIENT }}
            >
              <Play className="w-3.5 h-3.5" /> START CAMPAIGN
            </button>
          )}

          {campaign?.status === CampaignStatus.RUNNING && (
            <button
              onClick={() => pauseMutation.mutate()}
              disabled={pauseMutation.isPending}
              className={cn(BTN_BASE, "bg-amber-500 hover:bg-amber-600 text-white shadow-amber-900/20")}
            >
              <Pause className="w-3.5 h-3.5" /> PAUSE
            </button>
          )}

          {CANCELLABLE_STATUSES.has(campaign?.status as CampaignStatus) && (
            <button
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending}
              className={cn(BTN_BASE, "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50 shadow-sm")}
            >
              <XCircle className="w-3.5 h-3.5 text-red-400" /> CANCEL
            </button>
          )}

          {(campaign?.failed_count ?? 0) > 0 &&
            ![CampaignStatus.RUNNING, CampaignStatus.QUEUED].includes(campaign?.status as CampaignStatus) && 
            !campaign?.has_been_retried && (
              <button
                onClick={() => retryMutation.mutate()}
                disabled={retryMutation.isPending}
                className={cn(BTN_BASE, "bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-900/20")}
              >
                <RefreshCw className={cn("w-3.5 h-3.5", retryMutation.isPending && "animate-spin")} /> RETRY FAILED
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
            className={cn(BTN_BASE, "bg-white border border-gray-200 text-[#24422e] hover:bg-gray-50 shadow-sm")}
          >
            <Download className="w-3.5 h-3.5" /> EXPORT FAILED
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Main Progress Card */}
        <div className="xl:col-span-2 space-y-6">
          <div className="bg-white rounded-[32px] border border-gray-100 p-8 shadow-sm">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-[#24422e]" />
                <h3 className="text-sm font-black text-gray-900 uppercase tracking-widest">Delivery Progress</h3>
              </div>
              <div className="px-4 py-1.5 bg-gray-50 rounded-full border border-gray-100">
                <span className="text-xs font-black text-[#24422e]">{live.sent} / {live.total} SENT</span>
                <span className="ml-2 text-[10px] text-gray-400 font-bold uppercase tracking-tighter">{pct}% COMPLETE</span>
              </div>
            </div>

            <div className="relative h-4 bg-gray-100 rounded-full overflow-hidden mb-10 shadow-inner">
                <div 
                    className="absolute top-0 left-0 h-full transition-all duration-1000 ease-out flex items-center justify-end pr-2"
                    style={{ background: BRAND_GRADIENT, width: `${pct}%` }}
                >
                    {pct > 10 && <div className="w-1.5 h-1.5 rounded-full bg-white/40 animate-pulse" />}
                </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: "Sent", value: live.sent, color: "text-blue-600", bg: "bg-blue-50/50" },
                { label: "Delivered", value: live.delivered, color: "text-green-600", bg: "bg-green-50/50" },
                { label: "Read", value: live.read, color: "text-purple-600", bg: "bg-purple-50/50" },
                { label: "Failed", value: live.failed, color: "text-red-500", bg: "bg-red-50/50" },
              ].map(({ label, value, color, bg }) => (
                <div key={label} className={cn("p-5 rounded-[24px] border border-white transition hover:shadow-md", bg)}>
                  <p className={cn("text-3xl font-black tracking-tight", color)}>{value.toLocaleString()}</p>
                  <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mt-1">{label}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-[32px] border border-gray-100 p-8 shadow-sm">
             <div className="flex items-center gap-2 mb-6">
                <Info className="w-5 h-5 text-[#24422e]" />
                <h3 className="text-sm font-black text-gray-900 uppercase tracking-widest">In-Depth Metrics</h3>
             </div>
             <MessageLogsTable
                campaignId={id}
                pollMs={isActiveCampaign(campaign?.status) ? 5000 : false}
            />
          </div>
        </div>

        {/* Sidebar / Failure Breakdown */}
        <div className="space-y-6">
           <div className="bg-white rounded-[32px] border border-gray-100 p-8 shadow-sm h-full">
                <div className="flex items-center gap-2 mb-8">
                    <BarChart3 className="w-5 h-5 text-red-500" />
                    <h3 className="text-sm font-black text-gray-900 uppercase tracking-widest">Failure Analysis</h3>
                </div>
                
                {failureBreakdown && failureBreakdown.length > 0 ? (
                    <div className="space-y-6">
                        <FailureChart data={failureBreakdown} />
                        <div className="space-y-3">
                            {failureBreakdown.map((f, i) => (
                                <div key={i} className="flex items-center justify-between p-3 rounded-xl bg-gray-50 border border-gray-100">
                                    <span className="text-xs font-bold text-gray-600 truncate mr-4">{f.reason}</span>
                                    <span className="text-xs font-black text-red-500">{f.count}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center h-full py-10 text-center space-y-3">
                         <div className="w-16 h-16 bg-green-50 rounded-full flex items-center justify-center text-green-500">
                            <Play className="w-8 h-8 opacity-20" />
                         </div>
                         <p className="text-xs font-bold text-gray-400 uppercase tracking-widest">No failures reported yet</p>
                    </div>
                )}
           </div>
        </div>
      </div>
    </div>
  );
}
