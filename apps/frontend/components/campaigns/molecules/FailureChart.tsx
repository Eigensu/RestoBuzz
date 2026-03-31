import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface FailureChartProps {
  data: { reason: string; count: number }[];
}

export function FailureChart({ data }: FailureChartProps) {
  const chartData = data.map((d) => ({
    ...d,
    label: d.reason.length > 40 ? d.reason.slice(0, 40) + "…" : d.reason,
  }));

  return (
    <div className="bg-white rounded-xl border p-5 space-y-3">
      <h2 className="font-medium text-sm">Failure Reasons</h2>
      <ResponsiveContainer
        width="100%"
        height={Math.max(120, chartData.length * 52)}
      >
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 4, right: 48, left: 8, bottom: 4 }}
        >
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
          <YAxis
            type="category"
            dataKey="label"
            width={260}
            tick={{ fontSize: 11 }}
          />
          <Tooltip
            formatter={(value) => [value, "Count"]}
            labelFormatter={(l) => String(l)}
          />
          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={i === 0 ? "#f87171" : "#fca5a5"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
