import { Activity, AlertTriangle, CheckCircle2, TrendingUp, XCircle } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "../atoms/EmptyState";
import { SectionCard } from "../atoms/SectionCard";
import { StatCard } from "../atoms/StatCard";
import { StatusBadge } from "../atoms/StatusBadge";
import { TabSkeleton } from "../atoms/TabSkeleton";
import type { CampaignData, CampaignRow } from "../types";

export function CampaignTab({
  data,
  loading,
}: {
  readonly data: CampaignData | null | undefined;
  readonly loading: boolean;
}) {
  if (loading) return <TabSkeleton />;
  if (!data)
    return (
      <EmptyState
        icon={TrendingUp}
        message="No campaign data for this period."
      />
    );

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
                <p className="font-black text-gray-900 text-sm">
                  {summary.best_campaign.name}
                </p>
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
                <p className="font-black text-gray-900 text-sm">
                  {summary.worst_campaign.name}
                </p>
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
                contentStyle={{
                  borderRadius: 12,
                  border: "1px solid #f0f0f0",
                  fontSize: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar
                dataKey="sent"
                name="Sent"
                fill="#c8e8d0"
                radius={[4, 4, 0, 0]}
              />
              <Bar
                dataKey="delivered"
                name="Delivered"
                fill="#3a6b47"
                radius={[4, 4, 0, 0]}
              />
              <Bar
                dataKey="read"
                name="Read/Opened"
                fill="#24422e"
                radius={[4, 4, 0, 0]}
              />
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
                {[
                  "Channel",
                  "Name",
                  "Date",
                  "Status",
                  "Sent",
                  "Delivered",
                  "Delivery%",
                  "Read%",
                  "Failed",
                ].map((h) => (
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
              {campaigns.map((c: CampaignRow) => (
                <tr
                  key={c.id}
                  className="border-b border-gray-50 hover:bg-gray-50/50 transition"
                >
                  <td className="py-3 pr-4">
                    <span className="text-[10px] font-black uppercase tracking-widest bg-gray-100 px-2 py-0.5 rounded-full">
                      {c.channel}
                    </span>
                  </td>
                  <td className="py-3 pr-4 font-medium text-gray-900 max-w-[160px] truncate">
                    {c.name}
                  </td>
                  <td className="py-3 pr-4 text-gray-500 text-xs">
                    {c.created_at.slice(0, 10)}
                  </td>
                  <td className="py-3 pr-4">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="py-3 pr-4 text-gray-700">
                    {c.sent.toLocaleString()}
                  </td>
                  <td className="py-3 pr-4 text-gray-700">
                    {c.delivered.toLocaleString()}
                  </td>
                  <td className="py-3 pr-4 font-black text-emerald-700">
                    {c.delivery_rate}%
                  </td>
                  <td className="py-3 pr-4 font-black text-[#24422e]">
                    {c.read_rate}%
                  </td>
                  <td className="py-3 pr-4 font-black text-red-400">
                    {c.failed}
                  </td>
                </tr>
              ))}
              {campaigns.length === 0 && (
                <tr>
                  <td
                    colSpan={9}
                    className="py-8 text-center text-sm text-gray-400"
                  >
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
