import {
  Activity,
  DollarSign,
  MessageSquare,
  IndianRupee as RupeeIcon,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
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

const CATEGORY_COLORS: Record<string, string> = {
  MARKETING: "#24422e",
  UTILITY: "#3a6b47",
  AUTHENTICATION: "#6aab82",
  SERVICE: "#a8d5b5",
};

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

  const { summary, by_category, daily_trend } = data;
  const currency = summary.currency || "INR";
  const fmt = (n: number) => {
    const locale = currency === "INR" ? "en-IN" : undefined;
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    }).format(n);
  };

  return (
    <div className="space-y-6">
      {/* Info banner */}
      <div className="flex items-start gap-3 bg-amber-50 border border-amber-100 rounded-2xl px-5 py-4">
        <RupeeIcon className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
        <p className="text-sm text-amber-700 font-medium">
          Spend figures are <span className="font-black">estimates</span> based
          on ₹0.95 per billable conversation (from Meta&apos;s webhook). Actual
          charges on your Meta account may differ.
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <StatCard
          icon={RupeeIcon}
          label="Est. Total Spend"
          value={fmt(summary.total_spend)}
          sub={`Currency: ${currency} · estimated`}
          highlight="green"
        />
        <StatCard
          icon={MessageSquare}
          label="Billable Conversations"
          value={summary.total_conversations.toLocaleString()}
          sub="Messages sent (billable)"
        />
        <StatCard
          icon={Activity}
          label="Est. Avg Cost / Message"
          value={
            summary.total_conversations > 0
              ? fmt(summary.total_spend / summary.total_conversations)
              : fmt(0)
          }
          sub="₹0.95 flat rate applied"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Daily Spend Chart */}
        <div className="lg:col-span-2">
          <SectionCard title="Est. Daily Spend Trend">
            {daily_trend?.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={daily_trend}>
                  <defs>
                    <linearGradient
                      id="billingGradient"
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
                    dataKey="date"
                    tick={{ fontSize: 10, fill: "#9ca3af" }}
                    tickFormatter={(v) =>
                      typeof v === "string" ? v.slice(5) : ""
                    }
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: "#9ca3af" }}
                    tickFormatter={(v) => fmt(typeof v === "number" ? v : 0)}
                  />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 12,
                      border: "1px solid #f0f0f0",
                      fontSize: 12,
                    }}
                    formatter={(v) =>
                      [fmt(Number((v as number | string) ?? 0)), "Spend"] as [
                        string,
                        string,
                      ]
                    }
                  />
                  <Area
                    type="monotone"
                    dataKey="spend"
                    name="Spend"
                    stroke="#24422e"
                    strokeWidth={2.5}
                    fill="url(#billingGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-gray-400 text-center py-8">
                No spend data in this range
              </p>
            )}
          </SectionCard>
        </div>

        {/* By Category Pie */}
        <SectionCard title="Spend by Category">
          {by_category?.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie
                    data={by_category}
                    dataKey="spend"
                    nameKey="category"
                    cx="50%"
                    cy="50%"
                    outerRadius={65}
                    innerRadius={35}
                    paddingAngle={3}
                  >
                    {by_category.map((c: BillingCategoryRow) => (
                      <Cell
                        key={c.category}
                        fill={CATEGORY_COLORS[c.category] ?? "#c8e8d0"}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      borderRadius: 12,
                      border: "1px solid #f0f0f0",
                      fontSize: 12,
                    }}
                    formatter={(v) =>
                      [fmt(Number((v as number | string) ?? 0)), "Spend"] as [
                        string,
                        string,
                      ]
                    }
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-2 mt-2">
                {by_category.map((c: BillingCategoryRow) => (
                  <div
                    key={c.category}
                    className="flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className="w-2.5 h-2.5 rounded-full"
                        style={{
                          background: CATEGORY_COLORS[c.category] ?? "#c8e8d0",
                        }}
                      />
                      <span className="font-medium text-gray-700 uppercase">
                        {c.category}
                      </span>
                      <span className="text-gray-400">
                        ({(c.count ?? 0).toLocaleString()})
                      </span>
                    </div>
                    <span className="font-black text-gray-900">
                      {fmt(c.spend)}
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
    </div>
  );
}
