import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  LabelList,
  CartesianGrid,
  LineChart,
  Line,
  Legend,
} from "recharts";
import { AlertTriangle, Clock, TrendingUp, Eye } from "lucide-react";
import { SectionHeader } from "./ui";
import { DashboardAnalytics, HourlyStat, TTRStat } from "@/app/(dashboard)/dashboard/types";
import { GREEN as GREEN_PALETTE } from "@/lib/brand";


const TOOLTIP_STYLE = {
  borderRadius: "12px",
  border: "none",
  boxShadow: "0 10px 15px -3px rgb(0 0 0 / 0.1)",
};

const TOOLTIP_CURSOR = { fill: "#eff2f0" };

const EngagementTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { color?: string; payload: { rate?: string | number; delivered?: string | number } }[];
  label?: string;
}) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    const num = Number(data.rate);
    const rateStr = Number.isFinite(num) ? `${num.toFixed(1)}%` : "0.0%";
    const deliveredStr =
      typeof data.delivered === "number"
        ? data.delivered.toLocaleString()
        : data.delivered;

    return (
      <div
        className="bg-white p-3 text-sm whitespace-nowrap"
        style={TOOLTIP_STYLE}
      >
        <p className="text-gray-600 mb-2 m-0">{label}</p>
        <ul className="p-0 m-0 list-none">
          <li className="pb-1" style={{ color: payload[0].color || "#1a2f21" }}>
            Read Rate : {rateStr}
          </li>
          <li style={{ color: payload[0].color || "#1a2f21" }}>
            Messages Delivered : {deliveredStr}
          </li>
        </ul>
      </div>
    );
  }
  return null;
};

export function TimePerformanceCharts({
  analytics,
  activeChannel,
}: {
  analytics: DashboardAnalytics;
  activeChannel: "whatsapp" | "email";
}) {
  const {
    totals,
    rates,
    failureBreakdown,
    hourlyPerformance,
    ttrDistribution,
    timeSeriesData,
  } = analytics;

  return (
    <>
      <div className="grid grid-cols-1 gap-8">
        <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
          <SectionHeader
            title="Critical Failure Breakdown"
            icon={AlertTriangle}
            subtitle="Root causes for unsuccessful deliveries"
          />
          <div className="h-[280px] w-full mt-4 min-w-0">
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
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
                  cursor={TOOLTIP_CURSOR}
                  contentStyle={TOOLTIP_STYLE}
                />
                <Bar
                  dataKey="count"
                  radius={[0, 4, 4, 0]}
                  barSize={24}
                  name="Failures"
                >
                  {failureBreakdown.map(
                    (_entry: { reason: string; count: number }, index: number) => (
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
          {failureBreakdown.length > 0 && (
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
                  (failureBreakdown[0]?.count /
                    (failureBreakdown.reduce((acc, f) => acc + f.count, 0) || 1)) *
                  100
                ).toFixed(1)}
                % of all unsuccessful deliveries. Reviewing your contact list for
                accuracy could significantly boost your delivery rate.
              </p>
            </div>
          )}
        </div>
      </div>

      {activeChannel === "whatsapp" && (
        <div className="grid lg:grid-cols-2 gap-8">
          <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
            <SectionHeader
              title="Engagement Window Analysis"
              icon={Clock}
              subtitle="Interaction density and read rate distribution (IST)"
            />
            <div className="h-[280px] w-full mt-4 min-w-0">
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
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
                      value: "HOUR OF DAY (IST)",
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
                  <Tooltip cursor={TOOLTIP_CURSOR} content={<EngagementTooltip />} />
                  <Bar
                    dataKey="rate"
                    name="rate"
                    fill={GREEN_PALETTE.darkest}
                    radius={[4, 4, 0, 0]}
                  >
                    {hourlyPerformance.map((entry: HourlyStat, index: number) => {
                      const avgReadRate = rates.openRate || 0;
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

                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            {hourlyPerformance.length > 0 && (
              <div className="mt-6 p-4 rounded-xl flex items-start gap-3 bg-[#eff2f0] border border-[#24422e]/10">
                <Clock className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
                <p className="text-[11px] leading-relaxed text-[#24422e] font-medium">
                  <span className="font-bold uppercase tracking-wider">
                    Timing Insight:
                  </span>
                  <br />
                  {(() => {
                    const peak = hourlyPerformance.reduce((prev, curr) => {
                      const prevScore = prev.rate * Math.log10(prev.delivered + 1);
                      const currScore = curr.rate * Math.log10(curr.delivered + 1);
                      return currScore > prevScore ? curr : prev;
                    }, hourlyPerformance[0]);

                    return (
                      <>
                        <span className="font-bold">{peak?.hour}</span> is your
                        highest-impact window. This window achieved a
                        <span className="font-bold">
                          {" "}
                          {(peak?.rate || 0).toFixed(1)}% interaction
                        </span>{" "}
                        across
                        <span className="font-bold">
                          {" "}
                          {(peak?.delivered || 0).toLocaleString()} delivered messages
                        </span>
                        , making it your most statistically reliable time to
                        broadcast.
                      </>
                    );
                  })()}
                </p>
              </div>
            )}
          </div>

          <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
            <SectionHeader
              title="Time-to-Read (TTR)"
              icon={Clock}
              subtitle="How fast users interact with messages"
            />
            <div className="h-[280px] w-full mt-4 min-w-0">
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
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
                    cursor={TOOLTIP_CURSOR}
                    contentStyle={TOOLTIP_STYLE}
                    formatter={(value) => [value, "Total Reads"]}
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
            {ttrDistribution.length > 0 && (
              <div className="mt-6 p-4 rounded-xl flex items-start gap-3 bg-[#eff2f0] border border-[#24422e]/10">
                <Eye className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
                <p className="text-[11px] leading-relaxed text-[#24422e] font-medium">
                  <span className="font-bold uppercase tracking-wider">
                    Interaction Peak Insight:
                  </span>
                  <br />
                  {(() => {
                    const activeWindows = ttrDistribution;
                    const peak = activeWindows.reduce(
                      (prev, curr) => (curr.count > prev.count ? curr : prev),
                      activeWindows[0] || ttrDistribution[0],
                    );
                    const prob = (peak.count / (totals.read || 1)) * 100;
                    return (
                      <>
                        Apart from the delayed reads, the{" "}
                        <span className="font-bold">{peak.range}</span> window
                        shows your highest immediate interaction. This timeframe
                        accounts for{" "}
                        <span className="font-bold">{prob.toFixed(1)}%</span> of
                        total interactions, indicating your most effective
                        engagement zone for new broadcasts.
                      </>
                    );
                  })()}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {activeChannel === "whatsapp" && (
        <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
          <SectionHeader
            title="WhatsApp Delivery Trends"
            icon={TrendingUp}
            subtitle="Chronological performance tracking (Last 14 Days)"
          />
          <div className="h-[320px] w-full mt-4 min-w-0">
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
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
                <Tooltip contentStyle={TOOLTIP_STYLE} />
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
              over the last period, indicating a healthy engagement baseline.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
