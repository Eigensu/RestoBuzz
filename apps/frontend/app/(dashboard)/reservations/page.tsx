"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import {
  CalendarDays,
  Users,
  Phone,
  Mail,
  Banknote,
  TrendingUp,
  Receipt,
  BarChart3,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
  LineChart,
  Line,
  ComposedChart,
  Area,
} from "recharts";

// ── Palette ───────────────────────────────────────────────────────────────────
const COLORS = [
  "#24422e",
  "#4a7c59",
  "#7ab893",
  "#a8d5b5",
  "#d4edd9",
  "#f0f7f2",
  "#1a3022",
  "#6aaa82",
];

const LegendLabel = (v: string) => <span className="text-xs text-gray-600">{v}</span>;
const ChartTooltipFormatter = (v: any) => (typeof v === "number" ? v.toLocaleString("en-IN") : String(v ?? ""));

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmt(n: number) {
  if (n >= 10_000_000) return `₹${(n / 10_000_000).toFixed(1)}Cr`;
  if (n >= 100_000) return `₹${(n / 100_000).toFixed(1)}L`;
  if (n >= 1_000) return `₹${(n / 1_000).toFixed(1)}K`;
  return `₹${n}`;
}

function fmtNum(n: number) {
  return n.toLocaleString("en-IN");
}

// ── Stat Card ─────────────────────────────────────────────────────────────────
function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  color = "#24422e",
}: {
  readonly icon: React.ElementType;
  readonly label: string;
  readonly value: string;
  readonly sub?: string;
  readonly color?: string;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex items-start gap-4">
      <div className="p-2.5 rounded-xl" style={{ background: `${color}15` }}>
        <Icon className="w-5 h-5" style={{ color }} />
      </div>
      <div>
        <p className="text-[11px] font-bold text-gray-400 uppercase tracking-widest">
          {label}
        </p>
        <p className="text-2xl font-black text-gray-900 mt-0.5">{value}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// ── Chart Card ────────────────────────────────────────────────────────────────
function ChartCard({
  title,
  children,
}: {
  readonly title: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
      <h3 className="text-sm font-black text-gray-700 uppercase tracking-widest mb-4">
        {title}
      </h3>
      {children}
    </div>
  );
}

// ── Custom Tooltip ────────────────────────────────────────────────────────────
function RevenueTooltip({
  active,
  payload,
  label,
}: {
  readonly active?: boolean;
  readonly payload?: ReadonlyArray<{ value: number; name: string }>;
  readonly label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-gray-100 rounded-xl shadow-lg px-3 py-2 text-sm">
      <p className="font-bold text-gray-700">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="text-[#24422e] font-semibold">
          {p.name === "revenue" ? fmt(p.value) : `${fmtNum(p.value)} bookings`}
        </p>
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function ReservationsPage() {
  const { restaurant } = useAuthStore();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["reservego-analytics", restaurant?.id],
    queryFn: () =>
      api.get(`/reservego/analytics?restaurant_id=${restaurant!.id}`).then(
        (r) =>
          r.data as {
            summary: {
              total_guests: number;
              with_phone: number;
              with_email: number;
              total_bills: number;
              total_revenue: number;
              avg_bill: number;
              bills_with_amount: number;
            };
            monthly_trend: {
              month: string;
              revenue: number;
              bookings: number;
              avg_pax: number;
            }[];
            booking_statuses: { status: string; count: number }[];
            booking_types: { type: string; count: number }[];
            booking_sources: {
              source: string;
              count: number;
              revenue: number;
            }[];
            top_sections: { section: string; count: number; revenue: number }[];
            visit_distribution: { label: string; count: number }[];
            guest_sources: { source: string; count: number }[];
          },
      ),
    enabled: !!restaurant,
  });

  if (!restaurant) return null;

  if (isLoading) {
    return (
      <div className="max-w-[1600px] mx-auto p-4 md:p-8">
        <div className="flex items-center gap-3 mb-8">
          <div className="p-2 bg-[#eff2f0] rounded-lg">
            <CalendarDays className="w-6 h-6 text-[#24422e]" />
          </div>
          <h1 className="text-2xl font-black text-gray-900 tracking-tight">
            Reservations
          </h1>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={`stat-skel-${i}`}
              className="bg-white rounded-2xl border border-gray-100 h-24 animate-pulse"
            />
          ))}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={`chart-skel-${i}`}
              className="bg-white rounded-2xl border border-gray-100 h-64 animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="max-w-[1600px] mx-auto p-4 md:p-8 text-center py-20">
        <p className="text-red-500 font-medium">Failed to load analytics</p>
      </div>
    );
  }

  const {
    summary,
    monthly_trend,
    booking_statuses,
    booking_types,
    booking_sources,
    top_sections,
    visit_distribution,
    guest_sources,
  } = data;
  const phoneRate =
    summary.total_guests > 0
      ? Math.round((summary.with_phone / summary.total_guests) * 100)
      : 0;
  const completionRate =
    summary.total_bills > 0
      ? Math.round(
          ((booking_statuses.find(
            (s) =>
              s.status.toLowerCase().includes("finish") ||
              s.status.toLowerCase().includes("check"),
          )?.count ?? 0) /
            summary.total_bills) *
            100,
        )
      : 0;

  return (
    <div className="space-y-6 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-2 bg-[#eff2f0] rounded-lg">
          <CalendarDays className="w-6 h-6 text-[#24422e]" />
        </div>
        <div>
          <h1 className="text-2xl font-black text-gray-900 tracking-tight">
            Reservations
          </h1>
          <p className="text-sm text-gray-500 font-medium">
            Analytics from ReserveGo data
          </p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={Users}
          label="Total Guests"
          value={fmtNum(summary.total_guests)}
          sub="across all sheets"
        />
        <StatCard
          icon={Banknote}
          label="Total Revenue"
          value={fmt(summary.total_revenue)}
          sub={`${fmtNum(summary.bills_with_amount)} bills`}
          color="#1a6b3a"
        />
        <StatCard
          icon={Receipt}
          label="Avg Bill Value"
          value={fmt(summary.avg_bill)}
          sub="per booking"
          color="#2d5a8e"
        />
        <StatCard
          icon={CalendarDays}
          label="Total Bookings"
          value={fmtNum(summary.total_bills)}
          sub={`${completionRate}% completed`}
          color="#7c3aed"
        />
        <StatCard
          icon={Phone}
          label="With Phone"
          value={`${phoneRate}%`}
          sub={`${fmtNum(summary.with_phone)} guests`}
          color="#d97706"
        />
        <StatCard
          icon={Mail}
          label="With Email"
          value={summary.total_guests > 0 ? `${Math.round((summary.with_email / summary.total_guests) * 100)}%` : "0%"}
          sub={`${fmtNum(summary.with_email)} guests`}
          color="#0891b2"
        />
        <StatCard
          icon={TrendingUp}
          label="Avg Pax / Booking"
          value={(
            monthly_trend.reduce((s, m) => s + m.avg_pax, 0) /
            (monthly_trend.length || 1)
          ).toFixed(1)}
          sub="guests per table"
          color="#059669"
        />
        <StatCard
          icon={BarChart3}
          label="Booking Sources"
          value={String(booking_sources.length)}
          sub="platforms tracked"
          color="#dc2626"
        />
      </div>

      {/* Revenue + Bookings Trend */}
      <ChartCard title="Monthly Revenue & Bookings">
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart
            data={monthly_trend}
            margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#24422e" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#24422e" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#9ca3af" }} />
            <YAxis
              yAxisId="rev"
              tickFormatter={(v) => fmt(v)}
              tick={{ fontSize: 11, fill: "#9ca3af" }}
              width={60}
            />
            <YAxis
              yAxisId="bk"
              orientation="right"
              tick={{ fontSize: 11, fill: "#9ca3af" }}
              width={40}
            />
            <Tooltip content={<RevenueTooltip />} />
            <Area
              yAxisId="rev"
              type="monotone"
              dataKey="revenue"
              stroke="#24422e"
              strokeWidth={2}
              fill="url(#revGrad)"
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
      </ChartCard>

      {/* Row 2: Booking Status + Booking Type */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard title="Booking Status">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={booking_statuses}
                dataKey="count"
                nameKey="status"
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={({ name, percent }) =>
                  `${(name as string).split(" ")[0]} ${((percent ?? 0) * 100).toFixed(0)}%`
                }
                labelLine={false}
              >
                {booking_statuses.map((s, i) => (
                  <Cell key={s.status} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => typeof v === "number" ? fmtNum(v) : String(v ?? "")} />
              <Legend
                formatter={(v) => (
                  <span className="text-xs text-gray-600">{v}</span>
                )}
              />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Walk-in vs Reservation">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={booking_types}
                dataKey="count"
                nameKey="type"
                cx="50%"
                cy="50%"
                innerRadius={55}
                outerRadius={85}
                paddingAngle={3}
              >
                {booking_types.map((t, i) => (
                  <Cell key={t.type} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => typeof v === "number" ? fmtNum(v) : String(v ?? "")} />
              <Legend
                formatter={(v) => (
                  <span className="text-xs text-gray-600">{v}</span>
                )}
              />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Row 3: Booking Sources + Top Sections */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard title="Bookings by Source">
          <ResponsiveContainer width="100%" height={220}>
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
              <Tooltip formatter={(v) => typeof v === "number" ? fmtNum(v) : String(v ?? "")} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} fill="#24422e" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Revenue by Section">
          <ResponsiveContainer width="100%" height={220}>
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
                tickFormatter={(v) => fmt(v)}
                tick={{ fontSize: 11, fill: "#9ca3af" }}
              />
              <YAxis
                type="category"
                dataKey="section"
                tick={{ fontSize: 11, fill: "#6b7280" }}
                width={90}
              />
              <Tooltip formatter={(v) => typeof v === "number" ? fmt(v) : String(v ?? "")} />
              <Bar dataKey="revenue" radius={[0, 4, 4, 0]} fill="#4a7c59" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Row 4: Visit Frequency + Guest Source */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard title="Guest Visit Frequency">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={visit_distribution}
              margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#9ca3af" }} />
              <YAxis
                tickFormatter={(v) => fmtNum(v)}
                tick={{ fontSize: 11, fill: "#9ca3af" }}
                width={55}
              />
              <Tooltip formatter={ChartTooltipFormatter} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {visit_distribution.map((v, i) => (
                  <Cell key={`visit-${v.label}`} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Guest Acquisition Source">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={guest_sources}
                dataKey="count"
                nameKey="source"
                cx="50%"
                cy="50%"
                outerRadius={85}
                label={({ name, percent }) =>
                  `${name} ${((percent ?? 0) * 100).toFixed(0)}%`
                }
                labelLine={false}
              >
                {guest_sources.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => typeof v === "number" ? fmtNum(v) : String(v ?? "")} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Avg Pax trend */}
      <ChartCard title="Average Party Size per Month">
        <ResponsiveContainer width="100%" height={200}>
          <LineChart
            data={monthly_trend}
            margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#9ca3af" }} />
            <YAxis
              domain={[0, 8]}
              tick={{ fontSize: 11, fill: "#9ca3af" }}
              width={30}
            />
            <Tooltip formatter={(v) => typeof v === "number" ? `${v} guests` : String(v ?? "")} />
            <Line
              type="monotone"
              dataKey="avg_pax"
              stroke="#24422e"
              strokeWidth={2.5}
              dot={{ fill: "#24422e", r: 4 }}
              name="Avg Pax"
            />
          </LineChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}
