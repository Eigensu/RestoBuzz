import React from "react";
import { ResponsiveContainer, FunnelChart, Funnel, Tooltip, LabelList } from "recharts";
import { TrendingUp } from "lucide-react";
import { SectionHeader } from "./ui";
import { DashboardAnalytics } from "@/app/(dashboard)/dashboard/types";

export function ConversionFunnel({
  data,
}: {
  data: DashboardAnalytics["funnelData"];
}) {
  return (
    <div className="bg-white rounded-3xl border border-gray-100 p-6 shadow-sm lg:col-span-2 flex flex-col">
      <SectionHeader
        title="Where are we losing users?"
        subtitle="Conversion funnel analysis with drop-off impact"
      />
      <div className="h-[300px] w-full min-w-0 mt-4">
        <ResponsiveContainer width="100%" height="100%">
          <FunnelChart>
            <Tooltip
              formatter={(value, _name, props) => [
                Number(value).toLocaleString(),
                props?.payload?.name ?? "",
              ]}
              contentStyle={{
                borderRadius: "10px",
                border: "none",
                boxShadow: "0 4px 12px rgb(0 0 0 / 0.1)",
              }}
            />
            <Funnel dataKey="value" data={data} isAnimationActive>
              <LabelList
                position="inside"
                fill="#fff"
                stroke="none"
                dataKey="display"
                fontSize={11}
                fontWeight={700}
                formatter={(v) => {
                  const s = String(v);
                  const idx = s.indexOf(": ");
                  return idx === -1 ? s : s.slice(idx + 2);
                }}
              />
            </Funnel>
          </FunnelChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-auto pt-6 w-full">
        <div className="p-4 rounded-xl flex items-start gap-3 bg-[#eff2f0] border border-[#24422e]/10 w-full">
          <TrendingUp className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
          <p className="text-[11px] leading-relaxed text-[#24422e] font-medium italic">
            <span className="font-bold uppercase tracking-wider not-italic">
              What does this mean?
            </span>
            <br />
            {(() => {
              if (!data.length) return null;
              
              const techLoss = Number(
                data.find((s) => s.name === "Delivered")?.drop || 0,
              );
              const contentLoss = Number(
                data.find((s) => s.name === "Opened")?.drop || 0,
              );

              if (techLoss > 10) {
                return `You have a significant technical delivery gap (${techLoss.toFixed(1)}%). This usually points to invalid numbers or provider-level blocking—consider cleaning your customer list. `;
              }
              if (contentLoss > 50) {
                return `Messages are landing, but interaction is low (${contentLoss.toFixed(1)}% loss). Your "Open Rate" is the primary bottleneck—try more engaging content or better timing. `;
              }
              return `Your funnel is exceptionally healthy. With only a ${techLoss.toFixed(1)}% delivery loss and strong conversion-through, your targeting is optimal. `;
            })()}
            {data.length > 0 && (
              <span className="font-bold">
                The biggest interaction gap is at the{" "}
                {
                  data.reduce(
                    (prev, curr) => (curr.drop > prev.drop ? curr : prev),
                    data[0],
                  ).name
                }{" "}
                stage.
              </span>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
