"use client";
import React, { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { Campaign } from "@/types";
import {
  Send,
  CheckCheck,
  Eye,
  Megaphone,
  AlertTriangle,
  TrendingUp,
  Clock,
  LayoutDashboard,
} from "lucide-react";
import Link from "next/link";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  FunnelChart,
  Funnel,
  LabelList,
  Cell,
  Legend,
  BarChart,
  Bar,
} from "recharts";

import { BRAND_GRADIENT, GREEN as GREEN_PALETTE } from "@/lib/brand";

/* ─── Components ────────────────────────────────────────────── */

function StatCard({
  label,
  value,
  subtitle,
  icon: Icon,
  color,
}: {
  label: string;
  value: string | number;
  subtitle?: string;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="bg-white rounded-xl border p-5 transition-all hover:shadow-lg hover:-translate-y-0.5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-gray-500 font-semibold uppercase tracking-wider">
          {label}
        </span>
        <div
          className={`w-9 h-9 rounded-xl flex items-center justify-center ${color} shadow-sm`}
        >
          <Icon className="w-5 h-5 text-white" />
        </div>
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {subtitle && (
        <p className="text-xs text-gray-400 mt-1 font-medium">{subtitle}</p>
      )}
    </div>
  );
}

function SectionHeader({
  title,
  icon: Icon,
  subtitle,
}: {
  title: string;
  icon?: React.ElementType;
  subtitle?: string;
}) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-1">
        {Icon && <Icon className="w-5 h-5 text-gray-400" />}
        <h2 className="text-lg font-bold text-gray-800">{title}</h2>
      </div>
      {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
    </div>
  );
}

/* ─── Types ────────────────────────────────────────────────── */
interface TemplateStat {
  name: string;
  openRate: number;
  sent: number;
  score: number;
}

interface HourlyStat {
  hour: string;
  rate: number;
  delivered: number;
}

interface TTRStat {
  range: string;
  count: number;
}

interface DashboardAnalytics {
  totals: {
    total: number;
    sent: number;
    delivered: number;
    read: number;
    opened?: number;
    clicked?: number;
    bounced?: number;
    failed: number;
  };
  rates: {
    deliveryRate: number;
    openRate: number;
    clickRate?: number;
    bounceRate?: number;
    effectiveReach: number;
    failureRate: number;
  };
  funnelData: {
    name: string;
    value: number;
    drop: number;
    fill: string;
  }[];
  templateLeaderboard: TemplateStat[];
  failureBreakdown: { reason: string; count: number }[];
  hourlyPerformance: HourlyStat[];
  ttrDistribution: TTRStat[];
  pieData: { name: string; value: number }[];
  timeSeriesData: { date: string; sortKey: number; sent: number; delivered: number; read: number; failed: number }[];
}

/* ─── Main Component ────────────────────────────────────────── */

export default function DashboardPage() {
  const { restaurant } = useAuthStore();
  const [activeChannel, setActiveChannel] = React.useState<"whatsapp" | "email">(
    "whatsapp",
  );

  const { data, isLoading } = useQuery({
    queryKey: ["dashboard-campaigns", restaurant?.id],
    queryFn: () =>
      api
        .get(`/campaigns?restaurant_id=${restaurant?.id}&page=1&page_size=100`)
        .then((r) => r.data),
    enabled: !!restaurant,
  });

  const {
    data: analyticsData,
    isLoading: analyticsLoading,
    isError: analyticsError,
  } = useQuery({
    queryKey: ["dashboard-analytics-wa", restaurant?.id],
    queryFn: () =>
      api
        .get(`/campaigns/analytics?restaurant_id=${restaurant?.id}`)
        .then((r) => r.data),
    enabled: !!restaurant,
  });

  const {
    data: emailAnalyticsData,
    isLoading: emailLoading,
  } = useQuery({
    queryKey: ["dashboard-analytics-email", restaurant?.id],
    queryFn: () =>
      api
        .get(`/email-campaigns/analytics?restaurant_id=${restaurant?.id}`)
        .then((r) => r.data),
    enabled: !!restaurant,
  });

  const campaigns: Campaign[] = useMemo(() => data?.items ?? [], [data?.items]);

  // Data Aggregation & Decision Analytics Logic
  const waAnalytics: DashboardAnalytics | null = useMemo(() => {
    if (!campaigns.length) return null;

    // Group campaigns by retry chains
    const rootCampaigns = campaigns.filter((c) => !c.parent_campaign_id);
    const retryCampaigns = campaigns.filter((c) => c.parent_campaign_id);

    // Build retry chain map
    const retryMap = new Map<string, Campaign[]>();
    retryCampaigns.forEach((c) => {
      const parentId = c.parent_campaign_id!;
      if (!retryMap.has(parentId)) {
        retryMap.set(parentId, []);
      }
      retryMap.get(parentId)!.push(c);
    });

    // Calculate totals considering retry chains
    let totalAudience = 0;
    let totalSent = 0;
    let totalDelivered = 0;
    let totalRead = 0;
    let totalFailed = 0;

    rootCampaigns.forEach((root) => {
      const retries = retryMap.get(root.id) || [];
      const allInChain = [root, ...retries].sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      );

      // For effective reach: use root's total_count as audience
      totalAudience += root.total_count;

      // Sum sent, delivered, read across the entire chain
      allInChain.forEach((c) => {
        totalSent += c.sent_count;
        totalDelivered += c.delivered_count;
        totalRead += c.read_count;
      });

      // For failed: use the last campaign's failed_count (remaining failures)
      const lastCampaign = allInChain.at(-1)!;
      totalFailed += lastCampaign.failed_count;
    });

    const totals = {
      total: totalAudience,
      sent: totalSent,
      delivered: totalDelivered,
      read: totalRead,
      failed: totalFailed,
    };

    // 1. KPI Calculations
    const deliveryRate =
      totals.sent > 0 ? (totals.delivered / totals.sent) * 100 : 0;
    const openRate =
      totals.delivered > 0 ? (totals.read / totals.delivered) * 100 : 0;
    const effectiveReach =
      totals.total > 0 ? (totals.read / totals.total) * 100 : 0;
    const failureRate =
      totals.total > 0 ? (totals.failed / totals.total) * 100 : 0;

    // 2. Enhanced Funnel with Drop-off %
    const funnelData = [
      {
        name: "Total Audience",
        display: `Total Audience: ${totals.total.toLocaleString()}`,
        value: totals.total,
        drop: 0,
        fill: GREEN_PALETTE.light,
      },
      {
        name: "Sent",
        display: `Sent: ${totals.sent.toLocaleString()}`,
        value: totals.sent,
        drop:
          totals.total > 0
            ? ((totals.total - totals.sent) / totals.total) * 100
            : 0,
        fill: GREEN_PALETTE.medium,
      },
      {
        name: "Delivered",
        display: `Delivered: ${totals.delivered.toLocaleString()}`,
        value: totals.delivered,
        drop:
          totals.sent > 0
            ? ((totals.sent - totals.delivered) / totals.sent) * 100
            : 0,
        fill: GREEN_PALETTE.dark,
      },
      {
        name: "Opened",
        display: `Opened: ${totals.read.toLocaleString()}`,
        value: totals.read,
        drop:
          totals.delivered > 0
            ? ((totals.delivered - totals.read) / totals.delivered) * 100
            : 0,
        fill: GREEN_PALETTE.darkest,
      },
    ];

    // 3. Template Leaderboard
    const templateMap: Record<
      string,
      { opened: number; delivered: number; sent: number; count: number }
    > = {};
    campaigns.forEach((c) => {
      const name = c.template_name || "Unknown";
      if (!templateMap[name])
        templateMap[name] = { opened: 0, delivered: 0, sent: 0, count: 0 };
      templateMap[name].opened += c.read_count;
      templateMap[name].delivered += c.delivered_count;
      templateMap[name].sent += c.sent_count;
      templateMap[name].count += 1;
    });

    const templateLeaderboard = Object.entries(templateMap)
      .map(([name, stats]) => {
        const rate =
          stats.delivered > 0 ? (stats.opened / stats.delivered) * 100 : 0;
        // Impact Score = open_rate * log(total_sent) to surface high-volume, high-performance templates
        const score = rate * Math.log10(stats.sent + 1);
        return { name, openRate: rate, sent: stats.sent, score };
      })
      .sort((a, b) => b.score - a.score)
      .slice(0, 5);

    // 4. Failure Breakdown — real data from /campaigns/analytics
    const failureBreakdown: { reason: string; count: number }[] =
      analyticsData?.failure_breakdown ?? [];

    // 5. Hourly Best Time — real data from /campaigns/analytics
    const hourlyPerformance: HourlyStat[] = analyticsError
      ? []
      : (analyticsData?.hourly_performance ??
        Array.from({ length: 24 }, (_, i) => {
          const period = i >= 12 ? "PM" : "AM";
          const displayHour = i % 12 || 12;
          return { hour: `${displayHour} ${period}`, rate: 0, delivered: 0 };
        }));

    // 7. Time-to-Read (TTR) — real data from /campaigns/analytics
    const baseTTR: TTRStat[] = analyticsError
      ? []
      : (analyticsData?.ttr_distribution ?? [
          { range: "0-5 min", count: 0 },
          { range: "5-30 min", count: 0 },
          { range: "30-120 min", count: 0 },
          { range: "2h+", count: 0 },
        ]);

    const ttrDistribution = baseTTR;

    // Status Pie
    const statusCounts = campaigns.reduce(
      (acc, c) => {
        acc[c.status] = (acc[c.status] || 0) + 1;
        return acc;
      },
      {} as Record<string, number>,
    );

    const pieData = Object.entries(statusCounts).map(([status, count]) => ({
      name: status,
      value: count,
    }));

    // Time Series Trend (Ensuring at least 1 week window)
    const timeSeriesMap: Record<
      string,
      {
        date: string;
        sortKey: number;
        sent: number;
        delivered: number;
        read: number;
        failed: number;
      }
    > = {};

    // Pre-fill last 7 days with zeros to ensure window
    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const dateKey = d.toISOString().slice(0, 10);
      const dateLabel = d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      });
      timeSeriesMap[dateKey] = {
        date: dateLabel,
        sortKey: d.getTime(),
        sent: 0,
        delivered: 0,
        read: 0,
        failed: 0,
      };
    }

    campaigns.forEach((c) => {
      if (!c.created_at) return;
      const createdAt = new Date(c.created_at);
      const dateKey = createdAt.toISOString().slice(0, 10);

      if (timeSeriesMap[dateKey]) {
        timeSeriesMap[dateKey].sent += c.sent_count;
        timeSeriesMap[dateKey].delivered += c.delivered_count;
        timeSeriesMap[dateKey].read += c.read_count;
        timeSeriesMap[dateKey].failed += c.failed_count;
      }
    });

    const timeSeriesData = Object.values(timeSeriesMap).sort(
      (a, b) => a.sortKey - b.sortKey,
    );

    return {
      totals,
      rates: { deliveryRate, openRate, effectiveReach, failureRate },
      funnelData,
      templateLeaderboard,
      failureBreakdown,
      hourlyPerformance,
      ttrDistribution,
      pieData,
      timeSeriesData,
    };
  }, [campaigns, analyticsData, analyticsError]);

  const emailAnalytics: DashboardAnalytics | null = useMemo(() => {
    if (!emailAnalyticsData || !emailAnalyticsData.totals) return null;

    const {
      totals,
      delivery_rate,
      open_rate,
      click_rate,
      bounce_rate,
      failure_breakdown,
    } = emailAnalyticsData;

    return {
      totals: {
        total: (totals?.sent ?? 0) + (totals?.failed ?? 0),
        sent: totals?.sent ?? 0,
        delivered: totals?.delivered ?? 0,
        read: totals?.opened ?? 0,
        opened: totals?.opened ?? 0,
        clicked: totals?.clicked ?? 0,
        bounced: totals?.bounced ?? 0,
        failed: totals?.failed ?? 0,
      },
      rates: {
        deliveryRate: delivery_rate ?? 0,
        openRate: open_rate ?? 0,
        clickRate: click_rate ?? 0,
        bounceRate: bounce_rate ?? 0,
        effectiveReach: open_rate ?? 0,
        failureRate:
          ((totals?.failed ?? 0) /
            ((totals?.sent ?? 0) + (totals?.failed ?? 0) || 1)) *
          100,
      },
      funnelData: [
        {
          name: "Sent",
          display: `Sent: ${totals.sent.toLocaleString()}`,
          value: totals.sent,
          drop: 0,
          fill: GREEN_PALETTE.light,
        },
        {
          name: "Delivered",
          display: `Delivered: ${totals.delivered.toLocaleString()}`,
          value: totals.delivered,
          drop:
            totals.sent > 0
              ? ((totals.sent - totals.delivered) / totals.sent) * 100
              : 0,
          fill: GREEN_PALETTE.medium,
        },
        {
          name: "Opened",
          display: `Opened: ${totals.opened.toLocaleString()}`,
          value: totals.opened,
          drop:
            totals.delivered > 0
              ? ((totals.delivered - totals.opened) / totals.delivered) * 100
              : 0,
          fill: GREEN_PALETTE.dark,
        },
        {
          name: "Clicked",
          display: `Clicked: ${totals.clicked.toLocaleString()}`,
          value: totals.clicked,
          drop:
            totals.opened > 0
              ? ((totals.opened - totals.clicked) / totals.opened) * 100
              : 0,
          fill: GREEN_PALETTE.darkest,
        },
      ],
      templateLeaderboard: [],
      failureBreakdown: failure_breakdown || [],
      hourlyPerformance: [],
      ttrDistribution: [],
      pieData: [],
      timeSeriesData: [],
    };
  }, [emailAnalyticsData]);

  const analytics = activeChannel === "whatsapp" ? waAnalytics : emailAnalytics;

  if (!restaurant || isLoading || analyticsLoading || emailLoading) {
    return (
      <div className="h-[80vh] flex flex-col items-center justify-center text-gray-400 gap-4">
        <div className="w-12 h-12 border-4 border-gray-200 border-t-[#24422e] rounded-full animate-spin" />
        <p className="text-sm font-medium animate-pulse">
          Analyzing Campaign Data...
        </p>
      </div>
    );
  }

  if (campaigns.length === 0 || !analytics) {
    return (
      <div className="h-[70vh] flex flex-col items-center justify-center text-center p-8 max-w-lg mx-auto">
        <div className="w-20 h-20 bg-[#eff2f0] rounded-3xl flex items-center justify-center mb-6 shadow-sm">
          <Megaphone className="w-10 h-10 text-[#24422e]" />
        </div>
        <h2 className="text-2xl font-black text-gray-900 tracking-tight">
          No campaign data available for performance analytics
        </h2>
        <p className="text-sm text-gray-500 mt-3 font-medium leading-relaxed">
          It looks like you haven&apos;t launched any WhatsApp campaigns yet.
          Once you start messaging your audience, real-time engagement
          intelligence will appear here.
        </p>
        <Link
          href="/campaigns/whatsapp/new"
          className="mt-8 text-white text-sm font-bold px-10 py-4 rounded-2xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10"
          style={{ background: BRAND_GRADIENT }}
        >
          Launch Your First Campaign
        </Link>
      </div>
    );
  }

  const {
    totals,
    rates,
    funnelData,
    templateLeaderboard,
    failureBreakdown,
    hourlyPerformance,
    ttrDistribution,
    timeSeriesData,
  } = analytics!;

  return (
    <div className="space-y-8 pb-20 max-w-[1800px] mx-auto p-4 md:p-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#eff2f0] rounded-lg">
              <LayoutDashboard className="w-6 h-6 text-[#24422e]" />
            </div>
            <h1 className="text-2xl font-black text-gray-900 tracking-tight">
              Performance Intelligence
            </h1>
          </div>
          <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
            Real-time decision analytics for{" "}
            <span className="text-[#24422e] font-bold">{restaurant.name}</span>
          </p>
        </div>

        <div className="flex bg-[#eff2f0] p-1 rounded-2xl w-fit">
          <button
            onClick={() => setActiveChannel("whatsapp")}
            className={`px-6 py-2.5 rounded-xl text-sm font-bold transition-all ${
              activeChannel === "whatsapp"
                ? "bg-white text-[#24422e] shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            WhatsApp
          </button>
          <button
            onClick={() => setActiveChannel("email")}
            className={`px-6 py-2.5 rounded-xl text-sm font-bold transition-all ${
              activeChannel === "email"
                ? "bg-white text-[#24422e] shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            Email
          </button>
        </div>

        <Link
          href={
            activeChannel === "whatsapp"
              ? "/campaigns/whatsapp/new"
              : "/campaigns/email/new"
          }
          className="inline-flex items-center gap-2 text-white text-sm font-bold px-6 py-3 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10"
          style={{ background: BRAND_GRADIENT }}
        >
          <Megaphone className="w-4 h-4" />
          LAUNCH {activeChannel.toUpperCase()}
        </Link>
      </div>

      {/* TOP ROW: KPI CARDS (3 Per Row) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
        <StatCard
          label={activeChannel === "whatsapp" ? "WA Campaigns" : "Email Campaigns"}
          value={activeChannel === "whatsapp" ? campaigns.length : (emailAnalyticsData?.totals?.sent ? 1 : 0)} // simplified for now
          subtitle="All time"
          icon={Megaphone}
          color="bg-gray-800"
        />
        <StatCard
          label="Total Sent"
          value={totals.sent.toLocaleString()}
          subtitle="Success broadcasts"
          icon={Send}
          color="bg-[#3a6b47]"
        />
        <StatCard
          label="Delivery Rate"
          value={`${rates.deliveryRate.toFixed(1)}%`}
          subtitle="Across network"
          icon={CheckCheck}
          color="bg-[#509160]"
        />
        <StatCard
          label={activeChannel === "whatsapp" ? "Read Rate" : "Open Rate"}
          value={`${(activeChannel === "whatsapp" ? rates.openRate : rates.openRate || 0).toFixed(1)}%`}
          subtitle="Interaction velocity"
          icon={Eye}
          color="bg-[#24422e]"
        />
        <StatCard
          label={activeChannel === "whatsapp" ? "Effective Reach" : "Click Rate"}
          value={`${(activeChannel === "whatsapp" ? rates.effectiveReach : rates.clickRate || 0).toFixed(1)}%`}
          subtitle={activeChannel === "whatsapp" ? "Read / Total Audience" : "Clicks / Sent"}
          icon={TrendingUp}
          color="bg-[#6bb97b]"
        />
        <StatCard
          label={activeChannel === "whatsapp" ? "Failure Rate" : "Bounce Rate"}
          value={`${(activeChannel === "whatsapp" ? rates.failureRate : rates.bounceRate || 0).toFixed(1)}%`}
          subtitle="Critical drops"
          icon={AlertTriangle}
          color="bg-red-900/80"
        />
      </div>

      {/* MIDDLE ROW: FUNNEL */}
      <div className="grid grid-cols-1 gap-8">
        <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
          <SectionHeader
            title="Where are we losing users?"
            subtitle="Conversion funnel analysis with drop-off impact"
          />
          <div className="h-[400px] w-full min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <FunnelChart>
                <Tooltip
                  formatter={(value, _name, props) => [
                    Number(value).toLocaleString(),
                    props?.payload?.name ?? "",
                  ]}
                  contentStyle={{
                    borderRadius: "10px",
                    border: "none",
                    boxShadow: "0 4px 12px rgb(0 0 0 / 0.1)",
                  }}
                />
                <Funnel dataKey="value" data={funnelData} isAnimationActive>
                  <LabelList
                    position="inside"
                    fill="#fff"
                    stroke="none"
                    dataKey="display"
                    fontSize={11}
                    fontWeight={700}
                    formatter={(v) => {
                      // Split "Label: 1,234" → show only the number so it fits narrow segments
                      const s = String(v);
                      const idx = s.indexOf(": ");
                      return idx === -1 ? s : s.slice(idx + 2);
                    }}
                  />
                </Funnel>
              </FunnelChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-8 grid grid-cols-3 gap-4 border-t pt-6">
            {(() => {
              const stages = [
                {
                  label: activeChannel === "whatsapp" ? "Audience → Sent" : "Sent → Deliv",
                  drop: activeChannel === "whatsapp" 
                    ? funnelData.find(s => s.name === "Sent")?.drop 
                    : funnelData.find(s => s.name === "Delivered")?.drop
                },
                {
                  label: activeChannel === "whatsapp" ? "Sent → Deliv" : "Deliv → Opened",
                  drop: activeChannel === "whatsapp"
                    ? funnelData.find(s => s.name === "Delivered")?.drop
                    : funnelData.find(s => s.name === "Opened")?.drop
                },
                {
                  label: activeChannel === "whatsapp" ? "Deliv → Opened" : "Opened → Clicked",
                  drop: activeChannel === "whatsapp"
                    ? funnelData.find(s => s.name === "Opened")?.drop
                    : funnelData.find(s => s.name === "Clicked")?.drop
                }
              ];

              return stages.map((s) => (
                <div key={s.label} className="text-center">
                  <p className="text-[10px] text-gray-400 font-bold uppercase mb-1">
                    {s.label}
                  </p>
                  <p className={`text-sm font-bold ${Number(s.drop) > 10 ? "text-red-500" : "text-green-600"}`}>
                    {Number(s.drop).toFixed(1)}% Loss
                  </p>
                </div>
              ));
            })()}
          </div>
          <div className="mt-6 p-4 rounded-xl flex items-start gap-3 bg-[#eff2f0] border border-[#24422e]/10">
            <TrendingUp className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
            <p className="text-[11px] leading-relaxed text-[#24422e] font-medium italic">
              <span className="font-bold uppercase tracking-wider not-italic">
                What does this mean?
              </span>
              <br />
              {(() => {
                const techLoss = Number(funnelData.find(s => s.name === "Delivered")?.drop || 0); // Sent -> Deliv
                const contentLoss = Number(funnelData.find(s => s.name === "Opened")?.drop || 0); // Deliv -> Opened

                if (techLoss > 10) {
                  return `You have a significant technical delivery gap (${techLoss.toFixed(1)}%). This usually points to invalid numbers or provider-level blocking—consider cleaning your customer list. `;
                }
                if (contentLoss > 50) {
                  return `Messages are landing, but interaction is low (${contentLoss.toFixed(1)}% loss). Your "Open Rate" is the primary bottleneck—try more engaging content or better timing. `;
                }
                return `Your funnel is exceptionally healthy. With only a ${techLoss.toFixed(1)}% delivery loss and strong conversion-through, your targeting is optimal. `;
              })()}
              <span className="font-bold">
                The biggest interaction gap is at the{" "}
                {
                  funnelData.reduce(
                    (prev, curr) => (curr.drop > prev.drop ? curr : prev),
                    funnelData[0],
                  ).name
                }{" "}
                stage.
              </span>
            </p>
          </div>
        </div>
      </div>

      {/* NEW SECTION: TEMPLATE LEADERBOARD */}
      <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
        <SectionHeader
          title="Top Performing Content"
          icon={TrendingUp}
          subtitle="Ranked by Engagement Score (Rate × Volume Impact)"
        />
        <div className="mt-6 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-50">
                <th className="pb-4 text-[11px] font-bold text-gray-400 uppercase tracking-widest">
                  Template Name
                </th>
                <th className="pb-4 text-[11px] font-bold text-gray-400 uppercase tracking-widest text-right">
                  Open Rate
                </th>
                <th className="pb-4 text-[11px] font-bold text-gray-400 uppercase tracking-widest text-right">
                  Total Sent
                </th>
                <th className="pb-4 text-[11px] font-bold text-gray-400 uppercase tracking-widest text-right">
                  Impact Score
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {templateLeaderboard.map((item: TemplateStat, idx: number) => (
                <tr
                  key={item.name}
                  className="group hover:bg-[#eff2f0]/50 transition-colors"
                >
                  <td className="py-4 font-bold text-gray-900 flex items-center gap-3">
                    <span className="w-6 h-6 flex items-center justify-center bg-[#eff2f0] rounded-full text-[10px] text-[#24422e]">
                      {idx + 1}
                    </span>
                    {item.name}
                  </td>
                  <td className="py-4 text-right font-black text-[#509160]">
                    {(item.openRate || 0).toFixed(1)}%
                  </td>
                  <td className="py-4 text-right font-medium text-gray-500">
                    {item.sent.toLocaleString()}
                  </td>
                  <td className="py-4 text-right">
                    <div className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-[#eff2f0] rounded-full text-[#24422e] font-black text-xs">
                      {(item.score || 0).toFixed(1)}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-6 p-4 rounded-xl flex items-start gap-3 bg-[#eff2f0] border border-[#24422e]/10">
          <TrendingUp className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
          <p className="text-[11px] leading-relaxed text-[#24422e] font-medium">
            <span className="font-bold uppercase tracking-wider">
              How is Impact Score calculated?
            </span>
            <br />
            The score is a balanced metric of{" "}
            <span className="font-bold">Open Rate × Logarithmic Volume</span>.
            This surfaces content that consistently performs well while ensuring
            high-volume campaigns that drive significant business results are
            prioritized in the rankings.
          </p>
        </div>
        <div className="mt-3 p-4 rounded-xl flex items-start gap-3 bg-white border border-[#24422e]/20 shadow-sm">
          <Megaphone className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
          <p className="text-[11px] leading-relaxed text-[#24422e] font-medium">
            <span className="font-bold uppercase tracking-wider">
              Best Performing Template:
            </span>
            <br />
            The content{" "}
            <span className="font-bold">
              &quot;{templateLeaderboard[0]?.name}&quot;
            </span>{" "}
            is currently the most effective, maintaining a{" "}
            <span className="text-gray-900 font-bold">
              {(templateLeaderboard[0]?.openRate || 0).toFixed(1)}% engagement rate
            </span>
            across {templateLeaderboard[0]?.sent.toLocaleString()} messages.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8">
        <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
          <SectionHeader
            title="Critical Failure Breakdown"
            icon={AlertTriangle}
            subtitle="Root causes for unsuccessful deliveries"
          />
          <div className="h-[280px] w-full mt-4 min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                layout="vertical"
                data={failureBreakdown}
                margin={{ left: 10, right: 30, top: 10, bottom: 20 }}
              >
                <XAxis
                  type="number"
                  tick={{ fontSize: 10 }}
                  label={{
                    value: "FAILURE COUNT",
                    position: "insideBottom",
                    offset: -10,
                    fontSize: 10,
                    fontWeight: 700,
                    fill: "#9ca3af",
                  }}
                />
                <YAxis
                  dataKey="reason"
                  type="category"
                  width={180}
                  tick={{ fontSize: 11, fontWeight: 600 }}
                  axisLine={false}
                  tickLine={false}
                  label={{
                    value: "REASON",
                    angle: -90,
                    position: "insideLeft",
                    fontSize: 10,
                    fontWeight: 700,
                    fill: "#9ca3af",
                    offset: 10,
                  }}
                />
                <Tooltip
                  cursor={{ fill: "#eff2f0" }}
                  contentStyle={{
                    borderRadius: "12px",
                    border: "none",
                    boxShadow: "0 10px 15px -3px rgb(0 0 0 / 0.1)",
                  }}
                />
                <Bar
                  dataKey="count"
                  radius={[0, 4, 4, 0]}
                  barSize={24}
                  name="Failures"
                >
                  {failureBreakdown.map(
                    (
                      _entry: { reason: string; count: number },
                      index: number,
                    ) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={index === 0 ? "#7f1d1d" : GREEN_PALETTE.dark}
                      />
                    ),
                  )}
                  <LabelList
                    dataKey="count"
                    position="right"
                    style={{ fontSize: 11, fontWeight: 700, fill: "#4b5563" }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-6 p-4 rounded-xl flex items-start gap-3 bg-[#eff2f0] border border-[#24422e]/10">
            <AlertTriangle className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
            <p className="text-[11px] leading-relaxed text-[#24422e] font-medium">
              <span className="font-bold uppercase tracking-wider">
                Failure Insight:
              </span>
              <br />
              <span className="font-bold">
                {failureBreakdown[0]?.reason}
              </span>{" "}
              is responsible for{" "}
              {(
                (failureBreakdown[0]?.count /
                  (failureBreakdown.reduce((acc, f) => acc + f.count, 0) || 1)) *
                100
              ).toFixed(1)}
              % of all unsuccessful deliveries. Reviewing your contact list for
              accuracy could significantly boost your delivery rate.
            </p>
          </div>
        </div>
      </div>

      {/* SECTION 5: TIME OPTIMIZATION */}
      {activeChannel === "whatsapp" && (
        <div className="grid lg:grid-cols-2 gap-8">
          <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
            <SectionHeader
              title="Engagement Window Analysis"
              icon={Clock}
              subtitle="Interaction density and read rate distribution"
            />
            <div className="h-[280px] w-full mt-4 min-w-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={hourlyPerformance}
                  margin={{ top: 20, right: 30, left: 20, bottom: 30 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    vertical={false}
                    stroke="#f3f4f6"
                  />
                  <XAxis
                    dataKey="hour"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 10, fontWeight: 600 }}
                    interval="preserveStartEnd"
                    minTickGap={20}
                    label={{
                      value: "HOUR OF DAY",
                      position: "insideBottom",
                      offset: -20,
                      fontSize: 10,
                      fontWeight: 700,
                      fill: "#9ca3af",
                    }}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 11, fill: "#9ca3af" }}
                    domain={[0, 100]}
                    label={{
                      value: "READ RATE %",
                      angle: -90,
                      position: "insideLeft",
                      offset: -5,
                      fontSize: 10,
                      fontWeight: 700,
                      fill: "#9ca3af",
                    }}
                  />
                  <Tooltip
                    cursor={{ fill: "#eff2f0" }}
                    contentStyle={{
                      borderRadius: "12px",
                      border: "none",
                      boxShadow: "0 10px 15px -3px rgb(0 0 0 / 0.1)",
                    }}
                    formatter={(value: unknown) => {
                      const num = Number(value);
                      return [
                        Number.isFinite(num) ? `${num.toFixed(1)}%` : "0.0%",
                        "Read Rate",
                      ];
                    }}
                  />
                  <Bar
                    dataKey="rate"
                    name="rate"
                    fill={GREEN_PALETTE.darkest}
                    radius={[4, 4, 0, 0]}
                  >
                    {hourlyPerformance.map((entry: HourlyStat, index: number) => {
                      const avgReadRate = rates.openRate || 0;
                      const isWinningPeak =
                        entry.rate >= avgReadRate &&
                        entry.delivered > totals.delivered / 24;
                      return (
                        <Cell
                          key={`cell-${index}`}
                          fill={
                            isWinningPeak
                              ? GREEN_PALETTE.darkest
                              : GREEN_PALETTE.dark
                          }
                        />
                      );
                    })}
                    <LabelList
                      dataKey="delivered"
                      position="top"
                      formatter={(v) =>
                        typeof v === "number" && v > 0
                          ? `${v.toLocaleString()}`
                          : ""
                      }
                      style={{ fontSize: 10, fontWeight: 700, fill: "#6b7280" }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-6 p-4 rounded-xl flex items-start gap-3 bg-[#eff2f0] border border-[#24422e]/10">
              <Clock className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
              <p className="text-[11px] leading-relaxed text-[#24422e] font-medium">
                <span className="font-bold uppercase tracking-wider">
                  Timing Insight:
                </span>
                <br />
                {(() => {
                  // Calculate a Weighted Engagement Score: Rate * Log(Volume + 1)
                  // This ensures we pick hours with high volume AND high interaction.
                  const peak = hourlyPerformance.reduce((prev, curr) => {
                    const prevScore = prev.rate * Math.log10(prev.delivered + 1);
                    const currScore = curr.rate * Math.log10(curr.delivered + 1);
                    return currScore > prevScore ? curr : prev;
                  }, hourlyPerformance[0]);

                  return (
                    <>
                      <span className="font-bold">{peak.hour}</span> is your
                      highest-impact window. This window achieved a
                      <span className="font-bold">
                        {" "}
                        {peak.rate.toFixed(1)}% interaction
                      </span>{" "}
                      across
                      <span className="font-bold">
                        {" "}
                        {peak.delivered.toLocaleString()} delivered messages
                      </span>
                      , making it your most statistically reliable time to
                      broadcast.
                    </>
                  );
                })()}
              </p>
            </div>
          </div>

          <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
            <SectionHeader
              title="Time-to-Read (TTR)"
              icon={Clock}
              subtitle="How fast users interact with messages"
            />
            <div className="h-[280px] w-full mt-4 min-w-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={ttrDistribution}
                  margin={{ top: 20, right: 30, left: 10, bottom: 40 }}
                >
                  <XAxis
                    dataKey="range"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 11, fontWeight: 700 }}
                    label={{
                      value: "TIME RANGE",
                      position: "insideBottom",
                      offset: -25,
                      fontSize: 10,
                      fontWeight: 700,
                      fill: "#9ca3af",
                    }}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 10, fill: "#9ca3af" }}
                    label={{
                      value: "READ COUNT",
                      angle: -90,
                      position: "insideLeft",
                      offset: 10,
                      fontSize: 10,
                      fontWeight: 700,
                      fill: "#9ca3af",
                    }}
                  />
                  <Tooltip
                    cursor={{ fill: "#eff2f0" }}
                    contentStyle={{
                      borderRadius: "12px",
                      border: "none",
                      boxShadow: "0 10px 15px -3px rgb(0 0 0 / 0.1)",
                    }}
                    formatter={(value) => [value, "Total Reads"]}
                  />
                  <Bar dataKey="count" radius={[8, 8, 0, 0]} name="Reads">
                    {ttrDistribution.map((_entry: TTRStat, index: number) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={
                          index === 0
                            ? GREEN_PALETTE.darkest
                            : GREEN_PALETTE.light
                        }
                      />
                    ))}
                    <LabelList
                      dataKey="count"
                      position="top"
                      style={{ fontSize: 11, fontWeight: 800, fill: "#374151" }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-6 p-4 rounded-xl flex items-start gap-3 bg-[#eff2f0] border border-[#24422e]/10">
              <Eye className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
              <p className="text-[11px] leading-relaxed text-[#24422e] font-medium">
                <span className="font-bold uppercase tracking-wider">
                  Interaction Peak Insight:
                </span>
                <br />
                {(() => {
                  const activeWindows = ttrDistribution;
                  const peak = activeWindows.reduce(
                    (prev, curr) => (curr.count > prev.count ? curr : prev),
                    activeWindows[0] || ttrDistribution[0],
                  );
                  const prob = (peak.count / (totals.read || 1)) * 100;
                  return (
                    <>
                      Apart from the delayed reads, the{" "}
                      <span className="font-bold">{peak.range}</span> window shows
                      your highest immediate interaction. This timeframe accounts
                      for <span className="font-bold">{prob.toFixed(1)}%</span> of
                      total interactions, indicating your most effective
                      engagement zone for new broadcasts.
                    </>
                  );
                })()}
              </p>
            </div>
          </div>
        </div>
      )}

      {activeChannel === "whatsapp" && (
        <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
          <SectionHeader
            title="WhatsApp Delivery Trends"
            icon={TrendingUp}
            subtitle="Chronological performance tracking (Last 14 Days)"
          />
          <div className="h-[320px] w-full mt-4 min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={timeSeriesData}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="#f3f4f6"
                />
                <XAxis
                  dataKey="date"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 11, fill: "#9ca3af", fontWeight: 600 }}
                  dy={10}
                  minTickGap={30}
                  label={{
                    value: "DATE",
                    position: "insideBottomRight",
                    offset: -10,
                    fontSize: 10,
                    fontWeight: 700,
                    fill: "#9ca3af",
                  }}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 11, fill: "#9ca3af" }}
                  width={80}
                  label={{
                    value: "MESSAGE COUNT",
                    angle: -90,
                    position: "center",
                    fontSize: 10,
                    fontWeight: 700,
                    fill: "#9ca3af",
                    dx: -35,
                  }}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: "12px",
                    border: "none",
                    boxShadow: "0 10px 15px -3px rgb(0 0 0 / 0.1)",
                  }}
                />
                <Legend
                  iconType="circle"
                  wrapperStyle={{
                    fontSize: "11px",
                    fontWeight: 600,
                    paddingTop: 20,
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="read"
                  stroke={GREEN_PALETTE.darkest}
                  strokeWidth={8}
                  name="Read"
                  dot={{ r: 6, fill: GREEN_PALETTE.darkest, strokeWidth: 0 }}
                  activeDot={{ r: 9, strokeWidth: 0 }}
                />
                <Line
                  type="monotone"
                  dataKey="delivered"
                  stroke={GREEN_PALETTE.medium}
                  strokeWidth={5}
                  strokeDasharray="5 5"
                  name="Delivered"
                  dot={{ r: 4, fill: GREEN_PALETTE.medium, strokeWidth: 0 }}
                  activeDot={{ r: 7, strokeWidth: 0 }}
                />
                <Line
                  type="monotone"
                  dataKey="sent"
                  stroke={GREEN_PALETTE.light}
                  strokeWidth={2}
                  strokeDasharray="2 4"
                  name="Sent"
                  dot={{ r: 2, fill: GREEN_PALETTE.light, strokeWidth: 0 }}
                  activeDot={{ r: 4, strokeWidth: 0 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-6 p-4 rounded-xl flex items-start gap-3 bg-[#eff2f0] border border-[#24422e]/10">
            <TrendingUp className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
            <p className="text-[11px] leading-relaxed text-[#24422e] font-medium">
              <span className="font-bold uppercase tracking-wider">
                Trend Insight:
              </span>
              <br />
              Your campaigns have generated{" "}
              <span className="font-bold">
                {totals.read.toLocaleString()} total interactions
              </span>{" "}
              over the last period, indicating a healthy engagement baseline.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
