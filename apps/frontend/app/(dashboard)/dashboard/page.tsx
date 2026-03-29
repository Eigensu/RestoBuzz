"use client";
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
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

/* ─── Metric Card Component ────────────────────────────────── */
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
    <div className="bg-white rounded-xl border p-5 transition-shadow hover:shadow-md">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-gray-500 font-medium">{label}</span>
        <div
          className={`w-8 h-8 rounded-lg flex items-center justify-center ${color}`}
        >
          <Icon className="w-4 h-4 text-white" />
        </div>
      </div>
      <p className="text-2xl font-bold">{value}</p>
      {subtitle && <p className="text-xs text-gray-400 mt-1">{subtitle}</p>}
    </div>
  );
}

const PIE_COLORS: Record<string, string> = {
  draft: "#a0b9a8",
  queued: "#6bb97b",
  running: "#509160",
  paused: "#88db97",
  completed: "#24422e",
  failed: "#3a6b47",
  cancelled: "#c1d0c5",
};

const FUNNEL_COLORS = ["#6bb97b", "#509160", "#3a6b47", "#24422e"];

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

  const campaigns: Campaign[] = data?.items ?? [];

  // Aggregations
  const totals = campaigns.reduce(
    (acc, c) => ({
      totalMsg: acc.totalMsg + c.total_count,
      sent: acc.sent + c.sent_count,
      delivered: acc.delivered + c.delivered_count,
      read: acc.read + c.read_count,
      failed: acc.failed + c.failed_count,
    }),
    { totalMsg: 0, sent: 0, delivered: 0, read: 0, failed: 0 }
  );

  const deliveryRate =
    totals.sent > 0 ? ((totals.delivered / totals.sent) * 100).toFixed(1) : "0";
  const readRate =
    totals.delivered > 0
      ? ((totals.read / totals.delivered) * 100).toFixed(1)
      : "0";
  const failureRate =
    totals.totalMsg > 0
      ? ((totals.failed / totals.totalMsg) * 100).toFixed(1)
      : "0";

  // Funnel Data
  const funnelData = [
    { name: "Total Processed", value: totals.totalMsg, fill: FUNNEL_COLORS[0] },
    { name: "Sent", value: totals.sent, fill: FUNNEL_COLORS[1] },
    { name: "Delivered", value: totals.delivered, fill: FUNNEL_COLORS[2] },
    { name: "Read", value: totals.read, fill: FUNNEL_COLORS[3] },
  ];

  // Pie Chart Data
  const statusCounts = campaigns.reduce((acc, c) => {
    acc[c.status] = (acc[c.status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const pieData = Object.entries(statusCounts).map(([status, count]) => ({
    name: status,
    value: count,
  }));

  // Time Series Data (Group by Day)
  const timeSeriesMap = campaigns.reduce((acc, c) => {
    if (!c.created_at) return acc;
    const createdAt = new Date(c.created_at);
    const dateKey = createdAt.toISOString().slice(0, 10); // YYYY-MM-DD — stable grouping key
    const dateLabel = createdAt.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    });
    if (!acc[dateKey]) {
      acc[dateKey] = {
        date: dateLabel,
        sortKey: createdAt.getTime(),
        sent: 0,
        delivered: 0,
        read: 0,
        failed: 0,
      };
    }
    acc[dateKey].sent += c.sent_count;
    acc[dateKey].delivered += c.delivered_count;
    acc[dateKey].read += c.read_count;
    acc[dateKey].failed += c.failed_count;
    return acc;
  }, {} as Record<string, any>);

  // Sort dates chronologically using stable numeric epoch
  const timeSeriesData = Object.values(timeSeriesMap).sort(
    (a, b) => a.sortKey - b.sortKey
  );

  if (!restaurant || isLoading) {
    return <div className="p-8 text-center text-gray-400">Loading Dashboard...</div>;
  }

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[#24422e]">Overview</h1>
          <p className="text-xs text-gray-400 mt-0.5">
            Performance analytics for {restaurant.name}
          </p>
        </div>
        <Link
          href="/campaigns/new"
          className="text-white text-sm font-medium px-4 py-2 rounded-lg transition hover:opacity-90"
          style={{ background: "linear-gradient(135deg, #24422e, #3a6b47)" }}
        >
          New Campaign
        </Link>
      </div>

      {/* Top Row: KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-6 gap-4">
        <div className="md:col-span-3 lg:col-span-2">
          <StatCard
            label="Total Campaigns"
            value={campaigns.length}
            subtitle="All time"
            icon={Megaphone}
            color="bg-[#24422e]"
          />
        </div>
        <div className="md:col-span-3 lg:col-span-2">
          <StatCard
            label="Total Sent"
            value={totals.sent.toLocaleString()}
            subtitle="Messages shipped"
            icon={Send}
            color="bg-[#24422e]"
          />
        </div>
        <div className="md:col-span-3 lg:col-span-2">
          <StatCard
            label="Delivery Rate"
            value={`${deliveryRate}%`}
            subtitle="Delivered / Sent"
            icon={CheckCheck}
            color="bg-[#24422e]"
          />
        </div>
        <div className="md:col-span-3 lg:col-span-3">
          <StatCard
            label="Read Rate"
            value={`${readRate}%`}
            subtitle="Read / Delivered"
            icon={Eye}
            color="bg-[#24422e]"
          />
        </div>
        <div className="md:col-span-6 lg:col-span-3">
          <StatCard
            label="Failure Rate"
            value={`${failureRate}%`}
            subtitle="Failed / Total"
            icon={AlertTriangle}
            color="bg-[#24422e]"
          />
        </div>
      </div>

      {/* Middle Row: Funnel & Pie Chart */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Core Funnel */}
        <div className="lg:col-span-2 bg-white rounded-xl border p-5">
          <h2 className="font-semibold text-sm mb-4">Core Conversion Funnel</h2>
          {totals.totalMsg === 0 ? (
            <div className="h-64 flex items-center justify-center text-sm text-gray-400">
              No data yet to visualize
            </div>
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <FunnelChart>
                  <Tooltip
                    formatter={(val: any) => val?.toLocaleString()}
                    contentStyle={{ borderRadius: "8px", fontSize: "12px" }}
                  />
                  <Funnel dataKey="value" data={funnelData} isAnimationActive>
                    <LabelList
                      position="right"
                      fill="#000"
                      stroke="none"
                      dataKey="name"
                      fontSize={12}
                    />
                  </Funnel>
                </FunnelChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Status Distribution */}
        <div className="bg-white rounded-xl border p-5">
          <h2 className="font-semibold text-sm mb-4">Campaign Status</h2>
          {pieData.length === 0 ? (
            <div className="h-64 flex items-center justify-center text-sm text-gray-400">
              No campaigns
            </div>
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {pieData.map((entry) => (
                      <Cell
                        key={`cell-${entry.name}`}
                        fill={PIE_COLORS[entry.name] || PIE_COLORS.draft}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(val: any) => val?.toLocaleString()}
                    contentStyle={{ borderRadius: "8px", fontSize: "12px" }}
                  />
                  <Legend
                    verticalAlign="bottom"
                    iconType="circle"
                    wrapperStyle={{ fontSize: "12px" }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Row: Time Series Trend */}
      <div className="bg-white rounded-xl border p-5">
        <h2 className="flex items-center gap-2 font-semibold text-sm mb-4">
          <TrendingUp className="w-4 h-4 text-gray-500" /> WhatsApp Delivery Trends
        </h2>
        {timeSeriesData.length === 0 ? (
          <div className="h-72 flex items-center justify-center text-sm text-gray-400">
            Not enough data over time
          </div>
        ) : (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={timeSeriesData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="date"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 11, fill: "#6b7280" }}
                  dy={10}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 11, fill: "#6b7280" }}
                  width={40}
                />
                <Tooltip
                  contentStyle={{ borderRadius: "8px", fontSize: "12px" }}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: "12px" }} />
                <Line
                  type="monotone"
                  dataKey="sent"
                  stroke="#6bb97b"
                  strokeWidth={2}
                  name="Sent"
                  dot={false}
                  activeDot={{ r: 4 }}
                />
                <Line
                  type="monotone"
                  dataKey="delivered"
                  stroke="#3a6b47"
                  strokeWidth={2}
                  name="Delivered"
                  dot={false}
                  activeDot={{ r: 4 }}
                />
                <Line
                  type="monotone"
                  dataKey="read"
                  stroke="#24422e"
                  strokeWidth={2}
                  name="Read"
                  dot={false}
                  activeDot={{ r: 4 }}
                />
                <Line
                  type="monotone"
                  dataKey="failed"
                  stroke="#a0b9a8"
                  strokeWidth={2}
                  name="Failed"
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}
