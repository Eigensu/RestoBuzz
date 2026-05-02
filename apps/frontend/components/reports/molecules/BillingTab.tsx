import {
  Activity,
  DollarSign,
  MessageSquare,
  IndianRupee as RupeeIcon,
  TrendingUp,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState } from "../atoms/EmptyState";
import { SectionCard } from "../atoms/SectionCard";
import { StatCard } from "../atoms/StatCard";
import { TabSkeleton } from "../atoms/TabSkeleton";
import type { BillingCategoryRow, BillingData } from "../types";

export function BillingTab({
  data,
  loading,
}: {
  readonly data: BillingData | null | undefined;
  readonly loading: boolean;
}) {
  if (loading) return <TabSkeleton />;
  if (!data)
    return (
      <EmptyState
        icon={DollarSign}
        message="No billing data for this period."
      />
    );

  const { summary, by_category, monthly_breakdown } = data;
  const currency = summary.currency || "INR";
  const fmt = (n: number) => {
    const currency = summary.currency || "INR";
    const locale = currency === "INR" ? "en-IN" : undefined;
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    }).format(n);
  };

  const highestSpendCategory =
    by_category?.length > 0
      ? by_category.reduce((prev, curr) =>
          prev.spend > curr.spend ? prev : curr,
        ).category
      : "N/A";

  return (
    <div className="space-y-6">
      {/* Info banner */}
      <div className="flex items-start gap-3 bg-green-50 border border-green-100 rounded-2xl px-5 py-4">
        <Activity className="w-5 h-5 text-green-600 shrink-0 mt-0.5" />
        <div className="text-sm text-green-800 font-medium">
          <p className="font-bold mb-1">Real-time category-based expenditure tracking</p>
          <p>Costs calculated dynamically based on Meta conversation categories.</p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={RupeeIcon}
          label="Total Amount Billed"
          value={fmt(summary.total_spend)}
          sub={`Currency: ${currency}`}
          highlight="green"
        />
        <StatCard
          icon={MessageSquare}
          label="Total Billable Messages"
          value={summary.total_conversations.toLocaleString()}
          sub="Messages sent (billable)"
        />
        <StatCard
          icon={Activity}
          label="Avg Cost per Message"
          value={fmt(summary.avg_cost_per_message ?? 0)}
          sub="Weighted average using real pricing"
        />
        <StatCard
          icon={TrendingUp}
          label="Highest Spend Category"
          value={highestSpendCategory.toUpperCase()}
          sub="Top cost driver"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Spend Breakdown by Message Type */}
        <SectionCard title="Spend Breakdown by Message Type">
          {by_category?.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-gray-500">
                    <th className="py-3 font-medium">Message Type</th>
                    <th className="py-3 font-medium text-right">Total Messages</th>
                    <th className="py-3 font-medium text-right">Rate Applied</th>
                    <th className="py-3 font-medium text-right">Total Spend</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {by_category.map((c: BillingCategoryRow) => (
                    <tr key={c.category} className="hover:bg-gray-50/50">
                      <td className="py-3 font-medium text-gray-900 uppercase">
                        {c.category}
                      </td>
                      <td className="py-3 text-right text-gray-600">
                        {(c.count ?? 0).toLocaleString()}
                      </td>
                      <td className="py-3 text-right text-gray-600">
                        {fmt(c.rate ?? 0)}
                      </td>
                      <td className="py-3 text-right font-black text-[#24422e]">
                        {fmt(c.spend)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-gray-400 text-center py-8">
              No spend data in this range
            </p>
          )}
        </SectionCard>

        {/* Monthly Expenditure Analytics */}
        <SectionCard title="Monthly Expenditure Analytics">
          {monthly_breakdown && monthly_breakdown.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={monthly_breakdown} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0f0f0" />
                <XAxis 
                  dataKey="month" 
                  tick={{ fontSize: 11, fill: "#9ca3af" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis 
                  yAxisId="left"
                  tick={{ fontSize: 11, fill: "#9ca3af" }}
                  tickFormatter={(v) => fmt(v)}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis 
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 11, fill: "#9ca3af" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  cursor={{ fill: '#f9fafb' }}
                  contentStyle={{
                    borderRadius: 12,
                    border: "1px solid #f0f0f0",
                    fontSize: 12,
                    boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)",
                  }}
                  formatter={(value, name) => [
                    name === "Spend" ? fmt(Number(value)) : Number(value).toLocaleString(),
                    name
                  ]}
                />
                <Bar yAxisId="left" dataKey="spend" name="Spend" fill="#24422e" radius={[4, 4, 0, 0]} barSize={32} />
                <Bar yAxisId="right" dataKey="count" name="Messages Sent" fill="#a8d5b5" radius={[4, 4, 0, 0]} barSize={32} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-400 text-center py-8">
              No monthly data available
            </p>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
