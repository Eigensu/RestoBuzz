"use client";
import { useState, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { BRAND_GRADIENT } from "@/lib/brand";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  BarChart3,
  TrendingUp,
  Users,
  MessageSquare,
  FileText,
  Download,
  FileSpreadsheet,
  Store,
  IndianRupee as RupeeIcon,
} from "lucide-react";

import { CampaignTab } from "@/components/reports/molecules/CampaignTab";
import { MemberTab } from "@/components/reports/molecules/MemberTab";
import { InboxTab } from "@/components/reports/molecules/InboxTab";
import { LogsTab } from "@/components/reports/molecules/LogsTab";
import { BillingTab } from "@/components/reports/molecules/BillingTab";
import { ReserveGoTab } from "@/components/reports/molecules/ReserveGoTab";
import type { LogItem, LogsResponse, ReportTab } from "@/components/reports/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(d: Date) {
  return d.toISOString().slice(0, 10);
}
function defaultFrom() {
  return formatDate(new Date(Date.now() - 30 * 86400000));
}
function defaultTo() {
  return formatDate(new Date());
}

function getPresetDates(preset: "this_month" | "last_month" | "last_3_months" | "all_time") {
  const now = new Date();
  const todayStr = formatDate(now);
  
  if (preset === "this_month") {
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
    return { from: formatDate(firstDay), to: todayStr };
  } else if (preset === "last_month") {
    const firstDay = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const lastDay = new Date(now.getFullYear(), now.getMonth(), 0);
    return { from: formatDate(firstDay), to: formatDate(lastDay) };
  } else if (preset === "last_3_months") {
    const firstDay = new Date(now.getFullYear(), now.getMonth() - 3, 1);
    return { from: formatDate(firstDay), to: todayStr };
  } else if (preset === "all_time") {
    return { from: "2020-01-01", to: todayStr };
  }
  return { from: defaultFrom(), to: defaultTo() };
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ReportsPage() {
  const { restaurant } = useAuthStore();
  const [tab, setTab] = useState<ReportTab>("campaigns");
  const [fromDate, setFromDate] = useState(defaultFrom());
  const [toDate, setToDate] = useState(defaultTo());
  const [channel, setChannel] = useState<string>("all");
  const [logStatus, setLogStatus] = useState("");
  const [logSearch, setLogSearch] = useState("");
  const [extraLogItems, setExtraLogItems] = useState<LogItem[]>([]);

  const buildParams = useCallback(
    (extra: Record<string, string> = {}) => {
      const p = new URLSearchParams({
        from_date: fromDate,
        to_date: toDate,
        restaurant_id: restaurant!.id,
      });
      if (channel !== "all") p.set("channel", channel);
      Object.entries(extra).forEach(([k, v]) => v && p.set(k, v));
      return p.toString();
    },
    [fromDate, toDate, channel, restaurant],
  );

  // Campaign summary
  const campaignQuery = useQuery({
    queryKey: [
      "reports",
      "campaigns",
      restaurant?.id,
      fromDate,
      toDate,
      channel,
    ],
    queryFn: () =>
      api
        .get(`/reports/campaigns/summary?${buildParams()}`)
        .then((r) => r.data),
    enabled: !!restaurant && tab === "campaigns",
  });

  // Member summary
  const memberQuery = useQuery({
    queryKey: ["reports", "members", restaurant?.id, fromDate, toDate],
    queryFn: () =>
      api
        .get(
          `/reports/members/summary?${new URLSearchParams({
            from_date: fromDate,
            to_date: toDate,
            restaurant_id: restaurant!.id,
          })}`,
        )
        .then((r) => r.data),
    enabled: !!restaurant && tab === "members",
  });

  // Inbox summary
  const inboxQuery = useQuery({
    queryKey: ["reports", "inbox", restaurant?.id, fromDate, toDate],
    queryFn: () =>
      api
        .get(
          `/reports/inbox/summary?${new URLSearchParams({
            from_date: fromDate,
            to_date: toDate,
            restaurant_id: restaurant!.id,
          })}`,
        )
        .then((r) => r.data),
    enabled: !!restaurant && tab === "inbox",
  });

  // Logs query (resets items when filters change)
  const logsQuery = useQuery({
    queryKey: [
      "reports",
      "logs",
      restaurant?.id,
      fromDate,
      toDate,
      channel,
      logStatus,
      logSearch,
    ],
    queryFn: () =>
      api
        .get(
          `/reports/logs?${buildParams({ status: logStatus, search: logSearch })}`,
        )
        .then((r) => r.data),
    enabled: !!restaurant && tab === "logs",
  });

  // Billing summary
  const billingQuery = useQuery({
    queryKey: ["reports", "billing", restaurant?.id, fromDate, toDate],
    queryFn: () =>
      api
        .get(
          `/reports/billing/summary?${new URLSearchParams({
            from_date: fromDate,
            to_date: toDate,
            restaurant_id: restaurant!.id,
          })}`,
        )
        .then((r) => r.data),
    enabled: !!restaurant && tab === "billing",
  });

  // ReserveGo analytics
  const reservegoQuery = useQuery({
    queryKey: ["reports", "reservego", restaurant?.id],
    queryFn: () =>
      api
        .get(`/reservego/analytics?restaurant_id=${restaurant!.id}`)
        .then((r) => r.data),
    enabled: !!restaurant && tab === "reservego",
  });

  const handleExportReserveGo = async (type: "guests" | "bills") => {
    if (!restaurant) return;
    try {
      const params = new URLSearchParams({ restaurant_id: restaurant.id });
      const res = await api.get(`/reservego/${type}/export?${params}`, {
        responseType: "blob",
      });
      const safeId = encodeURIComponent(restaurant.id);
      const url = URL.createObjectURL(new Blob([res.data as BlobPart], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `reservego_${type}_${safeId}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Excel downloaded");
    } catch {
      toast.error("Export failed. Try again.");
    }
  };

  // Merge initial query results with any additionally loaded pages
  const allLogItems = useMemo<LogItem[]>(() => {
    const base = (logsQuery.data as LogsResponse | undefined)?.items ?? [];
    return [
      ...base,
      ...extraLogItems.filter((e) => !base.some((b) => b.id === e.id)),
    ];
  }, [logsQuery.data, extraLogItems]);

  const handleLoadMore = async () => {
    const logsData = logsQuery.data as LogsResponse | undefined;
    if (!logsData?.next_cursor) return;
    try {
      const res = await api.get(
        `/reports/logs?${buildParams({
          status: logStatus,
          search: logSearch,
          after_id: logsData.next_cursor,
        })}`,
      );
      setExtraLogItems((prev) => [...prev, ...(res.data.items ?? [])]);
    } catch {
      toast.error("Failed to load more logs");
    }
  };

  const handleExport = async (format: "csv" | "xlsx") => {
    if (!restaurant) return;
    try {
      const base = new URLSearchParams({
        from_date: fromDate,
        to_date: toDate,
        restaurant_id: restaurant.id,
        format,
      });
      if (channel !== "all") base.set("channel", channel);
      if (tab === "logs" && logStatus) base.set("status", logStatus);

      if (tab === "billing" && billingQuery.data) {
        const { summary, by_category } = billingQuery.data;
        const highestSpendCategory = by_category?.length > 0
          ? by_category.reduce((prev: any, curr: any) =>
              prev.spend > curr.spend ? prev : curr,
            ).category
          : "N/A";
        
        base.set("ui_total_billed", summary.total_spend.toString());
        base.set("ui_total_messages", summary.total_conversations.toString());
        base.set("ui_avg_cost", (summary.avg_cost_per_message ?? 0).toString());
        base.set("ui_top_category", highestSpendCategory);
      }

      if (tab === "reservego") {
        throw new Error("ReserveGo uses a different export handler");
      }

      const endpointMap: Record<ReportTab, string> = {
        campaigns: "/reports/campaigns/export",
        members: "/reports/members/export",
        inbox: "/reports/inbox/export",
        logs: "/reports/logs/export",
        billing: "/reports/billing/export",
        reservego: "", // Should not be reached
      };

      const res = await api.get(`${endpointMap[tab]}?${base}`, {
        responseType: "blob",
      });
      const ext = format;
      const url = URL.createObjectURL(new Blob([res.data as BlobPart]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${tab}_report_${fromDate}_${toDate}.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`${format.toUpperCase()} downloaded`);
    } catch {
      toast.error("Export failed. Try again.");
    }
  };

  if (!restaurant) return null;

  const TABS: { key: ReportTab; label: string; icon: React.ElementType }[] = [
    { key: "campaigns", label: "Campaigns", icon: TrendingUp },
    { key: "members", label: "Members", icon: Users },
    { key: "inbox", label: "Inbox Engagement", icon: MessageSquare },
    { key: "logs", label: "Delivery Logs", icon: FileText },
    { key: "billing", label: "Meta Billing", icon: RupeeIcon },
    { key: "reservego", label: "ReserveGo", icon: Store },
  ];

  return (
    <div className="space-y-8 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#eff2f0] rounded-lg">
              <BarChart3 className="w-6 h-6 text-[#24422e]" />
            </div>
            <h1 className="text-2xl font-black text-gray-900 tracking-tight">
              Reports
            </h1>
          </div>
          <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
            Analytics and exports for {restaurant.name}
          </p>
        </div>
        <div className="flex gap-2">
          {tab === "reservego" ? (
            <>
              <button
                onClick={() => handleExportReserveGo("guests")}
                className="flex items-center gap-2 border border-[#24422e]/40 text-[#24422e] hover:bg-[#eff2f0] text-[11px] font-black uppercase tracking-widest px-4 py-2 rounded-xl transition-all whitespace-nowrap"
              >
                <FileSpreadsheet className="w-3.5 h-3.5" /> Export Guests
              </button>
              <button
                onClick={() => handleExportReserveGo("bills")}
                className="flex items-center gap-2 text-white text-[11px] font-black uppercase tracking-widest px-4 py-2 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10 whitespace-nowrap"
                style={{ background: BRAND_GRADIENT }}
              >
                <FileSpreadsheet className="w-3.5 h-3.5" /> Export Bills
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => handleExport("csv")}
                className="flex items-center gap-2 border border-[#24422e]/40 text-[#24422e] hover:bg-[#eff2f0] text-[11px] font-black uppercase tracking-widest px-4 py-2 rounded-xl transition-all whitespace-nowrap"
              >
                <Download className="w-3.5 h-3.5" /> Export CSV
              </button>
              <button
                onClick={() => handleExport("xlsx")}
                className="flex items-center gap-2 text-white text-[11px] font-black uppercase tracking-widest px-4 py-2 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10 whitespace-nowrap"
                style={{ background: BRAND_GRADIENT }}
              >
                <FileSpreadsheet className="w-3.5 h-3.5" /> Export Excel
              </button>
            </>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-end bg-white border border-gray-100 rounded-2xl shadow-sm p-4">
        <div className="flex flex-col gap-1">
          <label
            htmlFor="from-date"
            className="text-[10px] font-black uppercase tracking-widest text-gray-400"
          >
            From
          </label>
          <input
            id="from-date"
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 focus:border-[#24422e]/30"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label
            htmlFor="to-date"
            className="text-[10px] font-black uppercase tracking-widest text-gray-400"
          >
            To
          </label>
          <input
            id="to-date"
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 focus:border-[#24422e]/30"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label
            htmlFor="channel-select"
            className="text-[10px] font-black uppercase tracking-widest text-gray-400"
          >
            Channel
          </label>
          <select
            id="channel-select"
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 bg-white min-w-[140px]"
          >
            <option value="all">All Channels</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="email">Email</option>
          </select>
        </div>
        
        <div className="flex gap-1 ml-auto">
          <button
            onClick={() => {
              const d = getPresetDates("this_month");
              setFromDate(d.from);
              setToDate(d.to);
            }}
            className="text-[10px] font-bold text-gray-500 bg-gray-100 hover:bg-gray-200 px-3 py-2 rounded-lg transition"
          >
            This Month
          </button>
          <button
            onClick={() => {
              const d = getPresetDates("last_month");
              setFromDate(d.from);
              setToDate(d.to);
            }}
            className="text-[10px] font-bold text-gray-500 bg-gray-100 hover:bg-gray-200 px-3 py-2 rounded-lg transition"
          >
            Last Month
          </button>
          <button
            onClick={() => {
              const d = getPresetDates("last_3_months");
              setFromDate(d.from);
              setToDate(d.to);
            }}
            className="text-[10px] font-bold text-gray-500 bg-gray-100 hover:bg-gray-200 px-3 py-2 rounded-lg transition"
          >
            Last 3 Months
          </button>
          <button
            onClick={() => {
              const d = getPresetDates("all_time");
              setFromDate(d.from);
              setToDate(d.to);
            }}
            className="text-[10px] font-bold text-gray-500 bg-gray-100 hover:bg-gray-200 px-3 py-2 rounded-lg transition"
          >
            All Time
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex p-1 bg-[#eff2f0] rounded-xl w-fit flex-wrap gap-0.5">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 text-[11px] font-black uppercase tracking-widest transition-all rounded-lg whitespace-nowrap",
              tab === key
                ? "text-white shadow-sm"
                : "text-[#24422e]/60 hover:text-[#24422e]",
            )}
            style={tab === key ? { background: BRAND_GRADIENT } : undefined}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === "campaigns" && (
        <CampaignTab
          data={campaignQuery.data}
          loading={campaignQuery.isLoading}
        />
      )}
      {tab === "members" && (
        <MemberTab data={memberQuery.data} loading={memberQuery.isLoading} />
      )}
      {tab === "inbox" && (
        <InboxTab data={inboxQuery.data} loading={inboxQuery.isLoading} />
      )}
      {tab === "logs" && (
        <LogsTab
          data={
            allLogItems.length > 0
              ? {
                  ...(logsQuery.data as LogsResponse | undefined),
                  items: allLogItems,
                }
              : (logsQuery.data as LogsResponse | undefined)
          }
          loading={logsQuery.isLoading}
          search={logSearch}
          onSearch={(v) => {
            setLogSearch(v);
            setExtraLogItems([]);
          }}
          status={logStatus}
          onStatus={(v) => {
            setLogStatus(v);
            setExtraLogItems([]);
          }}
          onLoadMore={handleLoadMore}
        />
      )}
      {tab === "billing" && (
        <BillingTab data={billingQuery.data} loading={billingQuery.isLoading} />
      )}
      {tab === "reservego" && (
        <ReserveGoTab
          data={reservegoQuery.data}
          loading={reservegoQuery.isLoading}
        />
      )}
    </div>
  );
}
