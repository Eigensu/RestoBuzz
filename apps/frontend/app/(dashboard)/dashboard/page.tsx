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

/* ─── Shared Styles & Colors ─────────────────────────────────── */
const GREEN_PALETTE = {
  darkest: "#24422e",
  dark: "#3a6b47",
  medium: "#509160",
  light: "#6bb97b",
  lightest: "#a0b9a8",
  muted: "#eff2f0",
};

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
  readRate: number;
  sent: number;
  score: number;
}

interface HourlyStat {
  hour: string;
  rate: number;
  delivered: number;
}

interface PriorityStat {
  name: string;
  read_rate: number;
  delivery_rate: number;
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
    failed: number;
  };
  rates: {
    deliveryRate: number;
    readRate: number;
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
  priorityData: PriorityStat[];
  ttrDistribution: TTRStat[];
  pieData: { name: string; value: number }[];
  timeSeriesData: { date: string; sortKey: number; sent: number; delivered: number; read: number; failed: number }[];
}

/* ─── Main Component ────────────────────────────────────────── */

export default function DashboardPage() {
  const { restaurant } = useAuthStore();

  const { data, isLoading } = useQuery({
    queryKey: ["dashboard-campaigns", restaurant?.id],
    queryFn: () =>
      api
        .get(`/campaigns?restaurant_id=${restaurant?.id}&page=1&page_size=100`)
        .then((r) => r.data),
    enabled: !!restaurant,
  });

  const { data: analyticsData, isLoading: analyticsLoading, isError: analyticsError } = useQuery({
    queryKey: ["dashboard-analytics", restaurant?.id],
    queryFn: () =>
      api
        .get(`/campaigns/analytics?restaurant_id=${restaurant?.id}`)
        .then((r) => r.data),
    enabled: !!restaurant,
  });

  const campaigns: Campaign[] = useMemo(() => data?.items ?? [], [data?.items]);

  // Data Aggregation & Decision Analytics Logic
  const analytics: DashboardAnalytics | null = useMemo(() => {
    if (!campaigns.length) return null;

    const totals = campaigns.reduce(
      (acc, c) => ({
        total: acc.total + c.total_count,
        sent: acc.sent + c.sent_count,
        delivered: acc.delivered + c.delivered_count,
        read: acc.read + c.read_count,
        failed: acc.failed + c.failed_count,
      }),
      { total: 0, sent: 0, delivered: 0, read: 0, failed: 0 },
    );

    // 1. KPI Calculations
    const deliveryRate =
      totals.sent > 0 ? (totals.delivered / totals.sent) * 100 : 0;
    const readRate =
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
        name: "Read",
        display: `Read: ${totals.read.toLocaleString()}`,
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
      { read: number; delivered: number; sent: number; count: number }
    > = {};
    campaigns.forEach((c) => {
      const name = c.template_name || "Unknown";
      if (!templateMap[name])
        templateMap[name] = { read: 0, delivered: 0, sent: 0, count: 0 };
      templateMap[name].read += c.read_count;
      templateMap[name].delivered += c.delivered_count;
      templateMap[name].sent += c.sent_count;
      templateMap[name].count += 1;
    });

    const templateLeaderboard = Object.entries(templateMap)
      .map(([name, stats]) => {
        const rate =
          stats.delivered > 0 ? (stats.read / stats.delivered) * 100 : 0;
        // Impact Score = read_rate * log(total_sent) to surface high-volume, high-performance templates
        const score = rate * Math.log10(stats.sent + 1);
        return { name, readRate: rate, sent: stats.sent, score };
      })
      .sort((a, b) => b.score - a.score)
      .slice(0, 5);

    // 4. Failure Breakdown — real data from /campaigns/analytics
    const failureBreakdown: { reason: string; count: number }[] =
      analyticsData?.failure_breakdown ?? [];

    // 5. Hourly Best Time — real data from /campaigns/analytics
    const hourlyPerformance: HourlyStat[] = analyticsError ? [] :
      (analyticsData?.hourly_performance ??
      Array.from({ length: 24 }, (_, i) => {
        const period = i >= 12 ? "PM" : "AM";
        const displayHour = i % 12 || 12;
        return { hour: `${displayHour} ${period}`, rate: 0, delivered: 0 };
      }));

    // 6. Priority Comparison
    const priorityStats = campaigns.reduce(
      (acc, c) => {
        const p = c.priority || "MARKETING";
        if (!acc[p]) acc[p] = { read: 0, delivered: 0, sent: 0, failed: 0 };
        acc[p].read += c.read_count;
        acc[p].delivered += c.delivered_count;
        acc[p].sent += c.sent_count;
        acc[p].failed += c.failed_count;
        return acc;
      },
      {} as Record<string, { read: number; delivered: number; sent: number; failed: number }>,
    );

    const priorityData = Object.entries(priorityStats).map(([name, s]) => ({
      name,
      read_rate: s.delivered > 0 ? (s.read / s.delivered) * 100 : 0,
      delivery_rate: s.sent > 0 ? (s.delivered / s.sent) * 100 : 0,
    }));

    // 7. Time-to-Read (TTR) — real data from /campaigns/analytics
    const baseTTR: TTRStat[] = analyticsError ? [] : (analyticsData?.ttr_distribution ?? [
      { range: "0-5 min", count: 0 },
      { range: "5-30 min", count: 0 },
      { range: "30-120 min", count: 0 },
      { range: "2h+", count: 0 },
    ]);

    const sumTTR = baseTTR.reduce((acc, d) => acc + d.count, 0);
    const ttrDistribution =
      totals.read > sumTTR
        ? [
            ...baseTTR,
            { range: "Unbucketed/Other", count: totals.read - sumTTR },
          ]
        : baseTTR;

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
    const timeSeriesMap: Record<string, { date: string; sortKey: number; sent: number; delivered: number; read: number; failed: number }> = {};

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
      rates: { deliveryRate, readRate, effectiveReach, failureRate },
      funnelData,
      templateLeaderboard,
      failureBreakdown,
      hourlyPerformance,
      priorityData,
      ttrDistribution,
      pieData,
      timeSeriesData,
    };
  }, [campaigns, analyticsData, analyticsError]);

  if (!restaurant || isLoading || analyticsLoading) {
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
          href="/campaigns/new"
          className="mt-8 text-white text-sm font-bold px-10 py-4 rounded-2xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10"
          style={{ background: "linear-gradient(135deg, #24422e, #3a6b47)" }}
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
        <Link
          href="/campaigns/new"
          className="inline-flex items-center gap-2 text-white text-sm font-bold px-6 py-3 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10"
          style={{ background: "linear-gradient(135deg, #24422e, #3a6b47)" }}
        >
          <Megaphone className="w-4 h-4" />
          LAUNCH CAMPAIGN
        </Link>
      </div>

      {/* TOP ROW: KPI CARDS (3 Per Row) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
        <StatCard
          label="Campaigns"
          value={campaigns.length}
          subtitle="All time"
          icon={Megaphone}
          color="bg-gray-800"
        />
        <StatCard
          label="Total Sent"
          value={totals.sent.toLocaleString()}
          subtitle="Across all lines"
          icon={Send}
          color="bg-[#3a6b47]"
        />
        <StatCard
          label="Delivery Rate"
          value={`${rates.deliveryRate.toFixed(1)}%`}
          subtitle="Sent vs Delivered"
          icon={CheckCheck}
          color="bg-[#509160]"
        />
        <StatCard
          label="Read Rate"
          value={`${rates.readRate.toFixed(1)}%`}
          subtitle="Interaction velocity"
          icon={Eye}
          color="bg-[#24422e]"
        />
        <StatCard
          label="Effective Reach"
          value={`${rates.effectiveReach.toFixed(1)}%`}
          subtitle="Read / Total Audience"
          icon={TrendingUp}
          color="bg-[#6bb97b]"
        />
        <StatCard
          label="Failure Rate"
          value={`${rates.failureRate.toFixed(1)}%`}
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
          <div className="h-[400px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <FunnelChart>
                <Funnel dataKey="value" data={funnelData} isAnimationActive>
                  <LabelList
                    position="inside"
                    fill="#fff"
                    stroke="none"
                    dataKey="display"
                    fontSize={13}
                    fontWeight={900}
                  />
                </Funnel>
              </FunnelChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-8 grid grid-cols-3 gap-4 border-t pt-6">
            <div className="text-center">
              <p className="text-[10px] text-gray-400 font-bold uppercase mb-1">
                Total → Sent
              </p>
              <p
                className={`text-sm font-bold ${funnelData[1].drop > 10 ? "text-red-500" : "text-green-600"}`}
              >
                {funnelData[1].drop.toFixed(1)}% Loss
              </p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-gray-400 font-bold uppercase mb-1">
                Sent → Deliv
              </p>
              <p
                className={`text-sm font-bold ${funnelData[2].drop > 10 ? "text-red-500" : "text-green-600"}`}
              >
                {funnelData[2].drop.toFixed(1)}% Loss
              </p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-gray-400 font-bold uppercase mb-1">
                Deliv → Read
              </p>
              <p
                className={`text-sm font-bold ${funnelData[3].drop > 50 ? "text-red-500" : "text-green-600"}`}
              >
                {funnelData[3].drop.toFixed(1)}% Loss
              </p>
            </div>
          </div>
          <div className="mt-6 p-4 rounded-xl flex items-start gap-3 bg-[#eff2f0] border border-[#24422e]/10">
            <TrendingUp className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
            <p className="text-[11px] leading-relaxed text-[#24422e] font-medium italic">
              <span className="font-bold uppercase tracking-wider not-italic">
                What does this mean?
              </span>
              <br />
              {(() => {
                const techLoss = funnelData[2].drop; // Sent -> Deliv
                const contentLoss = funnelData[3].drop; // Deliv -> Read

                if (techLoss > 10) {
                  return `You have a significant technical delivery gap (${techLoss.toFixed(1)}%). This usually points to invalid numbers or provider-level blocking—consider cleaning your customer list. `;
                }
                if (contentLoss > 50) {
                  return `Messages are landing, but interest is low (${contentLoss.toFixed(1)}% loss). Your "Read Rate" is the primary bottleneck—try more engaging subject lines or direct offers. `;
                }
                return `Your funnel is exceptionally healthy. With only a ${techLoss.toFixed(1)}% delivery loss and strong read-through, your targeting and timing are currently optimal. `;
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
                  Read Rate
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
                    {item.readRate.toFixed(1)}%
                  </td>
                  <td className="py-4 text-right font-medium text-gray-500">
                    {item.sent.toLocaleString()}
                  </td>
                  <td className="py-4 text-right">
                    <div className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-[#eff2f0] rounded-full text-[#24422e] font-black text-xs">
                      {item.score.toFixed(1)}
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
            <span className="font-bold">Read Rate × Logarithmic Volume</span>.
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
            {templateLeaderboard[0]?.readRate.toFixed(1)}% engagement rate
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
          <div className="h-[280px] w-full mt-4">
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
                (failureBreakdown[0]?.count / (totals.failed || 1)) *
                100
              ).toFixed(1)}
              % of all unsuccessful deliveries. Reviewing your contact list for
              accuracy could significantly boost your delivery rate.
            </p>
          </div>
        </div>
      </div>

      {/* SECTION 5: TIME OPTIMIZATION */}
      <div className="grid lg:grid-cols-2 gap-8">
        <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
          <SectionHeader
            title="Engagement Window Analysis"
            icon={Clock}
            subtitle="Interaction density and read rate distribution"
          />
          <div className="h-[280px] w-full mt-4">
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
                  formatter={(value) => [
                    `${Number(value || 0).toFixed(1)}%`,
                    "Read Rate",
                  ]}
                />
                <Bar
                  dataKey="rate"
                  name="rate"
                  fill={GREEN_PALETTE.darkest}
                  radius={[4, 4, 0, 0]}
                >
                  {hourlyPerformance.map((entry: HourlyStat, index: number) => {
                    const avgReadRate = rates.readRate || 0;
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
          <div className="h-[280px] w-full mt-4">
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
                  formatter={(value) => [value as React.ReactNode, "Total Reads"]}
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
                const activeWindows = ttrDistribution.filter(
                  (d) => d.range !== "Delayed (>24h)",
                );
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

      {/* SECTION 6: HISTORICAL TREND (Fixed) */}
      <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
        <SectionHeader
          title="WhatsApp Delivery Trends"
          icon={TrendingUp}
          subtitle="Chronological performance tracking (Last 14 Days)"
        />
        <div className="h-[320px] w-full mt-4">
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
            over the last 7-day tracking period, indicating a healthy engagement
            baseline.
          </p>
        </div>
      </div>
    </div>
  );
}
