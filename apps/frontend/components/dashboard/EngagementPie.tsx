import React from "react";
import { ResponsiveContainer, PieChart, Pie, Tooltip, Legend } from "recharts";
import { Eye } from "lucide-react";
import { SectionHeader } from "./ui";
import { DashboardAnalytics } from "@/app/(dashboard)/dashboard/types";

export function EngagementPie({
  data,
}: {
  data: DashboardAnalytics["pieData"];
}) {
  if (!data || data.length === 0 || data.every((d) => d.value === 0)) {
    return (
      <div className="bg-white rounded-3xl border border-gray-100 p-6 shadow-sm lg:col-span-1 flex flex-col relative">
        <SectionHeader
          title="Engagement Split"
          subtitle="Proportions of Sent, Delivered, and Replied"
        />
        <div className="flex-1 flex items-center justify-center min-h-[200px] text-gray-400 text-sm font-medium">
          No engagement data yet
        </div>
      </div>
    );
  }
  return (
    <div className="bg-white rounded-3xl border border-gray-100 p-6 shadow-sm lg:col-span-1 flex flex-col relative">
      <SectionHeader
        title="Engagement Split"
        subtitle="Proportions of Sent, Delivered, and Replied"
      />
      <div className="h-[300px] w-full min-w-0 mt-4">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={130}
              innerRadius={70}
              paddingAngle={3}
              stroke="none"
            >
              {/* Cells styling done via fill property directly */}
            </Pie>
            <Tooltip
              formatter={(value: unknown) =>
                Number(value || 0).toLocaleString()
              }
              contentStyle={{
                borderRadius: "10px",
                border: "none",
                boxShadow: "0 4px 12px rgb(0 0 0 / 0.1)",
              }}
            />
            <Legend
              verticalAlign="bottom"
              height={36}
              iconType="circle"
              formatter={(value) => (
                <span className="text-[11px] text-[#24422e] font-medium ml-1">
                  {value}
                </span>
              )}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-auto w-full space-y-4 pt-4">
        <div className="p-4 rounded-xl flex items-start gap-3 bg-[#eff2f0] border border-[#24422e]/10 text-left w-full">
          <Eye className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
          <p className="text-[11px] leading-relaxed text-[#24422e] font-medium italic">
            <span className="font-bold uppercase tracking-wider not-italic text-xs block mb-1">
              Note on Opened/Read accuracy
            </span>
            The number of &quot;Opened&quot; messages shown here is lower than reality. Because many WhatsApp users disable read receipts in their privacy settings, the actual number of people who have read your message will be much higher than what we can legally record.
          </p>
        </div>
      </div>
    </div>
  );
}
