"use client";
import { useState, useRef, useCallback, useEffect } from "react";
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
  Search,
  ChevronRight,
  Inbox,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Activity,
} from "lucide-react";
import {
  BarChart,
  Bar,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

// ── Types ─────────────────────────────────────────────────────────────────────

type ReportTab = "campaigns" | "members" | "inbox" | "logs";

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

// ── Reusable Components ───────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
  highlight,
  icon: Icon,
  className,
}: {
  label: string;
  value: string | number;
  sub?: string;
  highlight?: "green" | "red" | "amber";
  icon?: React.ElementType;
  className?: string;
}) {
  const colorMap = {
    green: "text-emerald-600",
    red: "text-red-500",
    amber: "text-amber-500",
  };
  return (
    <div className={cn("bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex flex-col gap-2", className)}>
      <div className="flex items-center justify-between">
        <p className={cn("text-[10px] font-black uppercase tracking-widest text-gray-400", className && "text-inherit text-opacity-60")}>
          {label}
        </p>
        {Icon && (
          <div className={cn("p-1.5 bg-[#eff2f0] rounded-lg", className && "bg-white/50")}>
            <Icon className="w-3.5 h-3.5 text-[#24422e]" />
          </div>
        )}
      </div>
      <p
        className={cn(
          "text-2xl font-black tracking-tight truncate",
          highlight ? colorMap[highlight] : "text-gray-900",
        )}
      >
        {value}
      </p>
      {sub && <p className={cn("text-xs text-gray-400 font-medium", className && "text-inherit text-opacity-60")}>{sub}</p>}
    </div>
  );
}

function SectionCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
      <h3 className="text-sm font-black text-gray-700 uppercase tracking-widest mb-4">
        {title}
      </h3>
      {children}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    delivered: "bg-emerald-50 text-emerald-700",
    sent: "bg-blue-50 text-blue-700",
    read: "bg-purple-50 text-purple-700",
    opened: "bg-purple-50 text-purple-700",
    clicked: "bg-indigo-50 text-indigo-700",
    failed: "bg-red-50 text-red-600",
    bounced: "bg-orange-50 text-orange-600",
    queued: "bg-gray-50 text-gray-500",
    sending: "bg-blue-50 text-blue-600",
    completed: "bg-emerald-50 text-emerald-700",
    cancelled: "bg-gray-100 text-gray-500",
  };
  return (
    <span
      className={cn(
        "inline-flex px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-widest",
        map[status] ?? "bg-gray-50 text-gray-500",
      )}
    >
      {status}
    </span>
  );
}

const PIE_COLORS = ["#24422e", "#3a6b47", "#6aab82", "#a8d5b5", "#c8e8d0", "#d4edda"];

// ── Campaign Tab ──────────────────────────────────────────────────────────────

function CampaignTab({ data, loading }: { data: any; loading: boolean }) {
  if (loading) return <TabSkeleton />;
  if (!data) return <EmptyState icon={TrendingUp} message="No campaign data for this period." />;

  const { summary, campaigns, weekly_trend } = data;

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={Activity}
          label="Total Campaigns"
          value={summary.total_campaigns}
          sub="in selected period"
        />
        <StatCard
          icon={CheckCircle2}
          label="Total Sent"
          value={summary.total_sent.toLocaleString()}
          sub={`${summary.delivery_rate}% delivery rate`}
          highlight="green"
        />
        <StatCard
          icon={TrendingUp}
          label="Avg Read Rate"
          value={`${summary.read_rate}%`}
          sub="across all campaigns"
        />
        <StatCard
          icon={XCircle}
          label="Failure Rate"
          value={`${summary.failure_rate}%`}
          sub={`${summary.total_failed.toLocaleString()} failed`}
          highlight={summary.failure_rate > 5 ? "red" : "green"}
        />
      </div>

      {/* Best / Worst */}
      {(summary.best_campaign || summary.worst_campaign) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {summary.best_campaign && (
            <div className="bg-emerald-50 border border-emerald-100 rounded-2xl p-4 flex gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-[10px] font-black uppercase tracking-widest text-emerald-600 mb-0.5">
                  Best Campaign
                </p>
                <p className="font-black text-gray-900 text-sm">{summary.best_campaign.name}</p>
                <p className="text-xs text-gray-500">
                  {summary.best_campaign.read_rate}% read rate ·{" "}
                  {summary.best_campaign.channel.toUpperCase()}
                </p>
              </div>
            </div>
          )}
          {summary.worst_campaign && (
            <div className="bg-red-50 border border-red-100 rounded-2xl p-4 flex gap-3">
              <AlertTriangle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
              <div>
                <p className="text-[10px] font-black uppercase tracking-widest text-red-500 mb-0.5">
                  Highest Failure
                </p>
                <p className="font-black text-gray-900 text-sm">{summary.worst_campaign.name}</p>
                <p className="text-xs text-gray-500">
                  {summary.worst_campaign.failure_rate}% failure rate ·{" "}
                  {summary.worst_campaign.channel.toUpperCase()}
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Weekly Trend Chart */}
      {weekly_trend?.length > 0 && (
        <SectionCard title="Weekly Send Trend">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={weekly_trend} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="week" tick={{ fontSize: 11, fill: "#9ca3af" }} />
              <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} />
              <Tooltip
                contentStyle={{ borderRadius: 12, border: "1px solid #f0f0f0", fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="sent" name="Sent" fill="#c8e8d0" radius={[4, 4, 0, 0]} />
              <Bar dataKey="delivered" name="Delivered" fill="#3a6b47" radius={[4, 4, 0, 0]} />
              <Bar dataKey="read" name="Read/Opened" fill="#24422e" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>
      )}

      {/* Campaign Table */}
      <SectionCard title={`All Campaigns (${campaigns.length})`}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                {["Channel", "Name", "Date", "Status", "Sent", "Delivered", "Delivery%", "Read%", "Failed"].map(
                  (h) => (
                    <th
                      key={h}
                      className="text-[10px] font-black uppercase tracking-widest text-gray-400 text-left pb-3 pr-4"
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {campaigns.map((c: any) => (
                <tr key={c.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition">
                  <td className="py-3 pr-4">
                    <span className="text-[10px] font-black uppercase tracking-widest bg-gray-100 px-2 py-0.5 rounded-full">
                      {c.channel}
                    </span>
                  </td>
                  <td className="py-3 pr-4 font-medium text-gray-900 max-w-[160px] truncate">
                    {c.name}
                  </td>
                  <td className="py-3 pr-4 text-gray-500 text-xs">{c.created_at.slice(0, 10)}</td>
                  <td className="py-3 pr-4">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="py-3 pr-4 text-gray-700">{c.sent.toLocaleString()}</td>
                  <td className="py-3 pr-4 text-gray-700">{c.delivered.toLocaleString()}</td>
                  <td className="py-3 pr-4 font-black text-emerald-700">{c.delivery_rate}%</td>
                  <td className="py-3 pr-4 font-black text-[#24422e]">{c.read_rate}%</td>
                  <td className="py-3 pr-4 font-black text-red-400">{c.failed}</td>
                </tr>
              ))}
              {campaigns.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-sm text-gray-400">
                    No campaigns in this period
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

// ── Member Tab ────────────────────────────────────────────────────────────────

function MemberTab({ data, loading }: { data: any; loading: boolean }) {
  if (loading) return <TabSkeleton />;
  if (!data) return <EmptyState icon={Users} message="No member data available." />;

  const { summary, monthly_growth, category_split, top_visitors } = data;

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={Users}
          label="Total Members"
          value={summary.total_members.toLocaleString()}
          sub={`${summary.active_members.toLocaleString()} active`}
        />
        <StatCard
          icon={TrendingUp}
          label="New This Month"
          value={summary.new_this_month.toLocaleString()}
          highlight="green"
        />
        <StatCard
          icon={CheckCircle2}
          label="Active Members"
          value={summary.active_members.toLocaleString()}
        />
        <StatCard
          icon={Clock}
          label="Dormant"
          value={summary.dormant_members.toLocaleString()}
          sub={`${summary.dormant_rate}% of active`}
          highlight={summary.dormant_rate > 30 ? "red" : summary.dormant_rate > 15 ? "amber" : undefined}
        />
      </div>

      {/* Dormant banner */}
      {summary.dormant_members > 0 && (
        <div className="flex items-center gap-3 bg-amber-50 border border-amber-100 rounded-2xl px-5 py-4">
          <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0" />
          <div>
            <p className="text-sm font-black text-amber-800">
              {summary.dormant_members.toLocaleString()} dormant members — no activity in 30+ days
            </p>
            <p className="text-xs text-amber-600 mt-0.5">
              Consider sending a re-engagement campaign to win them back.
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Growth Chart */}
        <div className="lg:col-span-2">
          <SectionCard title="Monthly Member Growth">
            {monthly_growth?.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={monthly_growth}>
                  <defs>
                    <linearGradient id="memberGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#24422e" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#24422e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#9ca3af" }} />
                  <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} />
                  <Tooltip
                    contentStyle={{ borderRadius: 12, border: "1px solid #f0f0f0", fontSize: 12 }}
                  />
                  <Area
                    type="monotone"
                    dataKey="new_members"
                    name="New Members"
                    stroke="#24422e"
                    strokeWidth={2.5}
                    fill="url(#memberGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-gray-400 text-center py-8">No data in this range</p>
            )}
          </SectionCard>
        </div>

        {/* Category Pie */}
        <SectionCard title="Category Split">
          {category_split?.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie
                    data={category_split}
                    dataKey="count"
                    nameKey="category"
                    cx="50%"
                    cy="50%"
                    outerRadius={65}
                    innerRadius={35}
                    paddingAngle={3}
                  >
                    {category_split.map((_: any, i: number) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ borderRadius: 12, border: "1px solid #f0f0f0", fontSize: 12 }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1.5 mt-2">
                {category_split.map((c: any, i: number) => (
                  <div key={c.category} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ background: PIE_COLORS[i % PIE_COLORS.length] }}
                      />
                      <span className="font-medium text-gray-700 uppercase">{c.category}</span>
                    </div>
                    <span className="font-black text-gray-900">{c.count.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-400 text-center py-8">No data</p>
          )}
        </SectionCard>
      </div>

      {/* Top Visitors */}
      {top_visitors?.length > 0 && (
        <SectionCard title="Top Repeat Visitors">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  {["#", "Name", "Phone", "Type", "Visits", "Last Visit"].map((h) => (
                    <th
                      key={h}
                      className="text-[10px] font-black uppercase tracking-widest text-gray-400 text-left pb-3 pr-4"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {top_visitors.map((v: any, i: number) => (
                  <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/50 transition">
                    <td className="py-3 pr-4 text-gray-400 font-black text-xs">{i + 1}</td>
                    <td className="py-3 pr-4 font-medium text-gray-900">{v.name}</td>
                    <td className="py-3 pr-4 text-gray-500 font-mono text-xs">{v.phone}</td>
                    <td className="py-3 pr-4">
                      <span className="text-[10px] font-black uppercase tracking-widest bg-[#eff2f0] text-[#24422e] px-2 py-0.5 rounded-full">
                        {v.type}
                      </span>
                    </td>
                    <td className="py-3 pr-4 font-black text-[#24422e]">{v.visit_count}</td>
                    <td className="py-3 pr-4 text-gray-400 text-xs">
                      {v.last_visit ? v.last_visit.slice(0, 10) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  );
}

// ── Logs Tab ──────────────────────────────────────────────────────────────────

function LogsTab({
  data,
  loading,
  search,
  onSearch,
  status,
  onStatus,
  onLoadMore,
}: {
  data: any;
  loading: boolean;
  search: string;
  onSearch: (v: string) => void;
  status: string;
  onStatus: (v: string) => void;
  onLoadMore: () => void;
}) {
  return (
    <div className="space-y-4">
      {/* Log-specific filters */}
      <div className="flex flex-wrap gap-3 items-end">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder="Search phone or email..."
            className="w-full border border-gray-200 rounded-xl pl-11 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 focus:border-[#24422e]/30"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-black uppercase tracking-widest text-gray-400">
            Status
          </label>
          <select
            value={status}
            onChange={(e) => onStatus(e.target.value)}
            className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 bg-white min-w-[140px]"
          >
            <option value="">All Statuses</option>
            <option value="sent">Sent</option>
            <option value="delivered">Delivered</option>
            <option value="read">Read</option>
            <option value="opened">Opened</option>
            <option value="clicked">Clicked</option>
            <option value="failed">Failed</option>
            <option value="bounced">Bounced</option>
          </select>
        </div>
      </div>

      {loading ? (
        <TabSkeleton />
      ) : !data?.items?.length ? (
        <EmptyState icon={Inbox} message="No delivery logs found for this filter." />
      ) : (
        <SectionCard title={`Delivery Logs`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  {["Channel", "Recipient", "Name", "Campaign", "Status", "Error", "Retries", "Time"].map(
                    (h) => (
                      <th
                        key={h}
                        className="text-[10px] font-black uppercase tracking-widest text-gray-400 text-left pb-3 pr-4"
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {data.items.map((row: any) => (
                  <tr key={row.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition">
                    <td className="py-3 pr-4">
                      <span className="text-[10px] font-black uppercase tracking-widest bg-gray-100 px-2 py-0.5 rounded-full">
                        {row.channel}
                      </span>
                    </td>
                    <td className="py-3 pr-4 font-mono text-xs text-gray-600 max-w-[140px] truncate">
                      {row.recipient}
                    </td>
                    <td className="py-3 pr-4 text-gray-700 max-w-[100px] truncate">
                      {row.recipient_name || "—"}
                    </td>
                    <td className="py-3 pr-4 text-gray-400 font-mono text-[10px] max-w-[80px] truncate">
                      {row.campaign_id.slice(-8)}
                    </td>
                    <td className="py-3 pr-4">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="py-3 pr-4 text-xs text-red-400 max-w-[140px] truncate">
                      {row.error_reason || "—"}
                    </td>
                    <td className="py-3 pr-4 text-center text-gray-500">{row.retry_count}</td>
                    <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">
                      {row.created_at.slice(0, 16).replace("T", " ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.next_cursor && (
            <button
              onClick={onLoadMore}
              className="mt-4 flex items-center gap-2 text-[11px] font-black uppercase tracking-widest text-[#24422e] hover:underline mx-auto"
            >
              Load More <ChevronRight className="w-3.5 h-3.5" />
            </button>
          )}
        </SectionCard>
      )}
    </div>
  );
}


// ── Inbox Tab ─────────────────────────────────────────────────────────────────

function InboxTab({ data, loading }: { data: any; loading: boolean }) {
  if (loading) return <TabSkeleton />;
  if (!data) return <EmptyState icon={MessageSquare} message="No inbox data available." />;

  const { summary, engaged_customers } = data;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={MessageSquare}
          label="Incoming Messages"
          value={summary.total_incoming_messages.toLocaleString()}
          sub="Total customer responses"
          highlight="green"
        />
        <StatCard
          icon={Users}
          label="Unique Senders"
          value={summary.unique_engaged_senders.toLocaleString()}
          sub="Individual customers"
        />
        <StatCard
          icon={TrendingUp}
          label="Avg Engagement"
          value={`${summary.avg_messages_per_sender}`}
          sub="Messages per sender"
        />
        {summary.top_engaged_customer && (
          <StatCard
            label="Top Customer"
            value={summary.top_engaged_customer.name || summary.top_engaged_customer._id}
            sub={`${summary.top_engaged_customer.message_count} messages sent`}
            icon={Users}
            className="bg-[#eff2f0] text-[#24422e]"
          />
        )}
      </div>

      <SectionCard title="Most Engaged Customers">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                {["Name", "Phone", "Last Message", "Messages Sent", "Last Active"].map((h) => (
                  <th
                    key={h}
                    className="text-[10px] font-black uppercase tracking-widest text-gray-400 text-left pb-3 pr-4"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {engaged_customers.slice(0, 15).map((c: any, i: number) => (
                <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/50 transition">
                  <td className="py-3 pr-4 font-medium text-gray-900">{c.name}</td>
                  <td className="py-3 pr-4 text-gray-500 font-mono text-xs">{c.phone}</td>
                  <td className="py-3 pr-4 text-gray-600 italic text-xs max-w-[200px] truncate">
                    {c.last_message}
                  </td>
                  <td className="py-3 pr-4 font-black text-[#24422e]">
                    {c.message_count.toLocaleString()}
                  </td>
                  <td className="py-3 pr-4 text-gray-400 text-xs">
                    {c.last_received_at.slice(0, 16).replace("T", " ")}
                  </td>
                </tr>
              ))}
              {engaged_customers.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-12 text-center text-sm text-gray-400 font-medium">
                    No engagement data for this period
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

// ── Tab Skeleton & Empty State ────────────────────────────────────────────────

function TabSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-28 bg-gray-100 rounded-2xl" />
        ))}
      </div>
      <div className="h-64 bg-gray-100 rounded-2xl" />
      <div className="h-48 bg-gray-100 rounded-2xl" />
    </div>
  );
}

function EmptyState({
  icon: Icon,
  message,
}: {
  icon: React.ElementType;
  message: string;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-16 flex flex-col items-center gap-4 text-center">
      <div className="p-4 bg-[#eff2f0] rounded-2xl">
        <Icon className="w-8 h-8 text-[#24422e]/50" />
      </div>
      <p className="text-sm text-gray-400 font-medium max-w-xs">{message}</p>
    </div>
  );
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
  const [logCursor, setLogCursor] = useState<string | null>(null);
  const [allLogItems, setAllLogItems] = useState<any[]>([]);

  // Typed shape for logs API response
  interface LogsResponse {
    items: any[];
    next_cursor: string | null;
    page_size: number;
  }

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
    queryKey: ["reports", "campaigns", restaurant?.id, fromDate, toDate, channel],
    queryFn: () => api.get(`/reports/campaigns/summary?${buildParams()}`).then((r) => r.data),
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
    queryKey: ["reports", "logs", restaurant?.id, fromDate, toDate, channel, logStatus, logSearch],
    queryFn: () =>
      api
        .get(`/reports/logs?${buildParams({ status: logStatus, search: logSearch })}`)
        .then((r) => r.data),
    enabled: !!restaurant && tab === "logs",
  });

  // TanStack Query v5 removed onSuccess — sync via useEffect instead
  useEffect(() => {
    const d = logsQuery.data as LogsResponse | undefined;
    if (d?.items) setAllLogItems(d.items);
  }, [logsQuery.data]);

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
      setAllLogItems((prev) => [...prev, ...(res.data.items ?? [])]);
      setLogCursor(res.data.next_cursor);
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

      const endpointMap: Record<ReportTab, string> = {
        campaigns: "/reports/campaigns/export",
        members: "/reports/members/export",
        inbox: "/reports/inbox/export",
        logs: "/reports/logs/export",
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
            <h1 className="text-2xl font-black text-gray-900 tracking-tight">Reports</h1>
          </div>
          <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
            Analytics and exports for {restaurant.name}
          </p>
        </div>
        <div className="flex gap-2">
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
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-end bg-white border border-gray-100 rounded-2xl shadow-sm p-4">
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-black uppercase tracking-widest text-gray-400">
            From
          </label>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 focus:border-[#24422e]/30"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-black uppercase tracking-widest text-gray-400">
            To
          </label>
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 focus:border-[#24422e]/30"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-black uppercase tracking-widest text-gray-400">
            Channel
          </label>
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 bg-white min-w-[140px]"
          >
            <option value="all">All Channels</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="email">Email</option>
          </select>
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
        <CampaignTab data={campaignQuery.data} loading={campaignQuery.isLoading} />
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
              ? { ...(logsQuery.data as LogsResponse | undefined), items: allLogItems }
              : (logsQuery.data as LogsResponse | undefined)
          }
          loading={logsQuery.isLoading}
          search={logSearch}
          onSearch={(v) => {
            setLogSearch(v);
            setAllLogItems([]);
          }}
          status={logStatus}
          onStatus={(v) => {
            setLogStatus(v);
            setAllLogItems([]);
          }}
          onLoadMore={handleLoadMore}
        />
      )}
    </div>
  );
}
