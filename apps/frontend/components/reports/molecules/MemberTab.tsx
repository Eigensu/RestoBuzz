import { AlertTriangle, CheckCircle2, Clock, TrendingUp, Users } from "lucide-react";
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "../atoms/EmptyState";
import { SectionCard } from "../atoms/SectionCard";
import { StatCard } from "../atoms/StatCard";
import { TabSkeleton } from "../atoms/TabSkeleton";
import type { CategoryCount, MemberData, TopVisitor } from "../types";

const PIE_COLORS = [
  "#24422e",
  "#3a6b47",
  "#6aab82",
  "#a8d5b5",
  "#c8e8d0",
  "#d4edda",
];

export function MemberTab({
  data,
  loading,
}: {
  readonly data: MemberData | null | undefined;
  readonly loading: boolean;
}) {
  if (loading) return <TabSkeleton />;
  if (!data)
    return <EmptyState icon={Users} message="No member data available." />;

  const { summary, monthly_growth, category_split, top_visitors } = data;

  let dormantHighlight: "red" | "amber" | undefined = undefined;
  if (summary.dormant_rate > 30) dormantHighlight = "red";
  else if (summary.dormant_rate > 15) dormantHighlight = "amber";

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
          highlight={dormantHighlight}
        />
      </div>

      {/* Dormant banner */}
      {summary.dormant_members > 0 && (
        <div className="flex items-center gap-3 bg-amber-50 border border-amber-100 rounded-2xl px-5 py-4">
          <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0" />
          <div>
            <p className="text-sm font-black text-amber-800">
              {summary.dormant_members.toLocaleString()} dormant members — no
              activity in 30+ days
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
                    <linearGradient
                      id="memberGradient"
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop
                        offset="5%"
                        stopColor="#24422e"
                        stopOpacity={0.15}
                      />
                      <stop offset="95%" stopColor="#24422e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis
                    dataKey="month"
                    tick={{ fontSize: 11, fill: "#9ca3af" }}
                  />
                  <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 12,
                      border: "1px solid #f0f0f0",
                      fontSize: 12,
                    }}
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
              <p className="text-sm text-gray-400 text-center py-8">
                No data in this range
              </p>
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
                    {category_split.map((c: CategoryCount, i: number) => (
                      <Cell
                        key={c.category}
                        fill={PIE_COLORS[i % PIE_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      borderRadius: 12,
                      border: "1px solid #f0f0f0",
                      fontSize: 12,
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1.5 mt-2">
                {category_split.map((c: CategoryCount, i: number) => (
                  <div
                    key={c.category}
                    className="flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className="w-2.5 h-2.5 rounded-full"
                        style={{
                          background: PIE_COLORS[i % PIE_COLORS.length],
                        }}
                      />
                      <span className="font-medium text-gray-700 uppercase">
                        {c.category}
                      </span>
                    </div>
                    <span className="font-black text-gray-900">
                      {c.count.toLocaleString()}
                    </span>
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
                  {["#", "Name", "Phone", "Type", "Visits", "Last Visit"].map(
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
                {top_visitors.map((v: TopVisitor, i: number) => (
                  <tr
                    key={v.phone}
                    className="border-b border-gray-50 hover:bg-gray-50/50 transition"
                  >
                    <td className="py-3 pr-4 text-gray-400 font-black text-xs">
                      {i + 1}
                    </td>
                    <td className="py-3 pr-4 font-medium text-gray-900">
                      {v.name}
                    </td>
                    <td className="py-3 pr-4 text-gray-500 font-mono text-xs">
                      {v.phone}
                    </td>
                    <td className="py-3 pr-4">
                      <span className="text-[10px] font-black uppercase bg-[#eff2f0] text-[#24422e] px-2 py-0.5 rounded-full">
                        {v.type}
                      </span>
                    </td>
                    <td className="py-3 pr-4 font-black text-[#24422e]">
                      {v.visit_count}
                    </td>
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
