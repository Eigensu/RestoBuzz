import {
  Banknote,
  CalendarDays,
  Mail,
  Phone,
  Receipt,
  Store,
  Users,
} from "lucide-react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
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
import type { ReserveGoData } from "../types";

function fmtRev(n: number) {
  const num = Number(n);
  if (!Number.isFinite(num)) return "—";
  const sign = num < 0 ? "-" : "";
  const abs = Math.abs(num);
  let val = abs;
  let suffix = "";
  let digits = 0;

  if (abs >= 10_000_000) {
    val = abs / 10_000_000;
    suffix = "Cr";
    digits = 1;
  } else if (abs >= 100_000) {
    val = abs / 100_000;
    suffix = "L";
    digits = 1;
  } else if (abs >= 1_000) {
    val = abs / 1_000;
    suffix = "K";
    digits = 1;
  } else {
    digits = 2; // sensible for sub-1k
  }

  const formatted = new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(val);

  return `${sign}₹${formatted}${suffix}`;
}

const RG_COLORS = [
  "#24422e",
  "#4a7c59",
  "#7ab893",
  "#a8d5b5",
  "#d4edd9",
  "#1a3022",
  "#6aaa82",
];

export function ReserveGoTab({
  data,
  loading,
}: {
  readonly data: ReserveGoData | null | undefined;
  readonly loading: boolean;
}) {
  if (loading) return <TabSkeleton />;
  if (!data)
    return <EmptyState icon={Store} message="No ReserveGo data available." />;

  const {
    summary,
    monthly_trend,
    booking_statuses,
    booking_types,
    booking_sources,
    top_sections,
    visit_distribution,
  } = data;
  const phoneRate =
    summary.total_guests > 0
      ? Math.round((summary.with_phone / summary.total_guests) * 100)
      : 0;

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={Users}
          label="Total Guests"
          value={summary.total_guests.toLocaleString()}
          sub="across all sheets"
        />
        <StatCard
          icon={Banknote}
          label="Total Revenue"
          value={fmtRev(summary.total_revenue)}
          sub={`${summary.bills_with_amount.toLocaleString()} bills`}
          highlight="green"
        />
        <StatCard
          icon={Receipt}
          label="Avg Bill"
          value={fmtRev(summary.avg_bill)}
          sub="per booking"
        />
        <StatCard
          icon={CalendarDays}
          label="Total Bookings"
          value={summary.total_bills.toLocaleString()}
          sub="all time"
        />
        <StatCard
          icon={Phone}
          label="Phone Coverage"
          value={`${phoneRate}%`}
          sub={`${summary.with_phone.toLocaleString()} guests`}
        />
        <StatCard
          icon={Mail}
          label="With Email"
          value={
            summary.total_guests > 0
              ? `${Math.round((summary.with_email / summary.total_guests) * 100)}%`
              : "0%"
          }
          sub={`${summary.with_email.toLocaleString()} guests`}
        />
      </div>

      {/* Monthly Revenue + Bookings */}
      {monthly_trend?.length > 0 && (
        <SectionCard title="Monthly Revenue & Bookings">
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart
              data={monthly_trend}
              margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
            >
              <defs>
                <linearGradient id="rgRevGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#24422e" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#24422e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#9ca3af" }} />
              <YAxis
                yAxisId="rev"
                tickFormatter={(v) => fmtRev(typeof v === "number" ? v : 0)}
                tick={{ fontSize: 11, fill: "#9ca3af" }}
                width={60}
              />
              <YAxis
                yAxisId="bk"
                orientation="right"
                tick={{ fontSize: 11, fill: "#9ca3af" }}
                width={40}
              />
              <Tooltip
                contentStyle={{
                  borderRadius: 12,
                  border: "1px solid #f0f0f0",
                  fontSize: 12,
                }}
                formatter={(v, name) => {
                  const n = typeof v === "number" ? v : 0;
                  return name === "revenue"
                    ? [fmtRev(n), "Revenue"]
                    : [n.toLocaleString(), "Bookings"];
                }}
              />
              <Area
                yAxisId="rev"
                type="monotone"
                dataKey="revenue"
                stroke="#24422e"
                strokeWidth={2}
                fill="url(#rgRevGrad)"
                name="revenue"
              />
              <Bar
                yAxisId="bk"
                dataKey="bookings"
                fill="#a8d5b5"
                radius={[4, 4, 0, 0]}
                name="bookings"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </SectionCard>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Booking Status */}
        {booking_statuses?.length > 0 && (
          <SectionCard title="Booking Status">
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={booking_statuses}
                  dataKey="count"
                  nameKey="status"
                  cx="50%"
                  cy="50%"
                  outerRadius={75}
                  innerRadius={35}
                  paddingAngle={3}
                >
                  {booking_statuses.map((s, i: number) => (
                    <Cell
                      key={s.status}
                      fill={RG_COLORS[i % RG_COLORS.length]}
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
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </SectionCard>
        )}

        {/* Booking Type */}
        {booking_types?.length > 0 && (
          <SectionCard title="Walk-in vs Reservation">
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={booking_types}
                  dataKey="count"
                  nameKey="type"
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  paddingAngle={3}
                >
                  {booking_types.map((t, i: number) => (
                    <Cell key={t.type} fill={RG_COLORS[i % RG_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    borderRadius: 12,
                    border: "1px solid #f0f0f0",
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </SectionCard>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Booking Sources */}
        {booking_sources?.length > 0 && (
          <SectionCard title="Bookings by Source">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart
                data={booking_sources}
                layout="vertical"
                margin={{ left: 8, right: 16 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#f0f0f0"
                  horizontal={false}
                />
                <XAxis type="number" tick={{ fontSize: 11, fill: "#9ca3af" }} />
                <YAxis
                  type="category"
                  dataKey="source"
                  tick={{ fontSize: 11, fill: "#6b7280" }}
                  width={80}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: 12,
                    border: "1px solid #f0f0f0",
                    fontSize: 12,
                  }}
                />
                <Bar dataKey="count" radius={[0, 4, 4, 0]} fill="#24422e" />
              </BarChart>
            </ResponsiveContainer>
          </SectionCard>
        )}

        {/* Top Sections */}
        {top_sections?.length > 0 && (
          <SectionCard title="Revenue by Section">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart
                data={top_sections}
                layout="vertical"
                margin={{ left: 8, right: 16 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#f0f0f0"
                  horizontal={false}
                />
                <XAxis
                  type="number"
                  tickFormatter={(v) => fmtRev(typeof v === "number" ? v : 0)}
                  tick={{ fontSize: 11, fill: "#9ca3af" }}
                />
                <YAxis
                  type="category"
                  dataKey="section"
                  tick={{ fontSize: 11, fill: "#6b7280" }}
                  width={90}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: 12,
                    border: "1px solid #f0f0f0",
                    fontSize: 12,
                  }}
                  formatter={(v) => [
                    fmtRev(typeof v === "number" ? v : 0),
                    "Revenue",
                  ]}
                />
                <Bar dataKey="revenue" radius={[0, 4, 4, 0]} fill="#4a7c59" />
              </BarChart>
            </ResponsiveContainer>
          </SectionCard>
        )}
      </div>

      {/* Visit Frequency */}
      {visit_distribution?.length > 0 && (
        <SectionCard title="Guest Visit Frequency">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart
              data={visit_distribution}
              margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#9ca3af" }} />
              <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} width={50} />
              <Tooltip
                contentStyle={{
                  borderRadius: 12,
                  border: "1px solid #f0f0f0",
                  fontSize: 12,
                }}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {visit_distribution.map((v, i: number) => (
                  <Cell key={v.label} fill={RG_COLORS[i % RG_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>
      )}
    </div>
  );
}
