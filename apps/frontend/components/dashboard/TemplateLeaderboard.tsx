import React from "react";
import { TrendingUp, Megaphone } from "lucide-react";
import { SectionHeader } from "./ui";
import { TemplateStat } from "@/app/(dashboard)/dashboard/types";

export function TemplateLeaderboard({
  data,
}: {
  data: TemplateStat[];
}) {
  if (!data || data.length === 0) return null;

  return (
    <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
      <SectionHeader
        title="Top Performing Content"
        icon={TrendingUp}
        subtitle="Ranked by Engagement Score (Rate × Volume Impact)"
      />
      <div className="mt-6 overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-gray-50">
              <th className="pb-4 text-[11px] font-bold text-gray-400 uppercase tracking-widest">
                Template Name
              </th>
              <th className="pb-4 text-[11px] font-bold text-gray-400 uppercase tracking-widest text-right">
                Open Rate
              </th>
              <th className="pb-4 text-[11px] font-bold text-gray-400 uppercase tracking-widest text-right">
                Total Sent
              </th>
              <th className="pb-4 text-[11px] font-bold text-gray-400 uppercase tracking-widest text-right">
                Impact Score
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {data.map((item: TemplateStat, idx: number) => (
              <tr
                key={item.name}
                className="group hover:bg-[#eff2f0]/50 transition-colors"
              >
                <td className="py-4 font-bold text-gray-900 flex items-center gap-3">
                  <span className="w-6 h-6 flex items-center justify-center bg-[#eff2f0] rounded-full text-[10px] text-[#24422e]">
                    {idx + 1}
                  </span>
                  {item.name}
                </td>
                <td className="py-4 text-right font-black text-[#509160]">
                  {(item.openRate || 0).toFixed(1)}%
                </td>
                <td className="py-4 text-right font-medium text-gray-500">
                  {item.sent.toLocaleString()}
                </td>
                <td className="py-4 text-right">
                  <div className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-[#eff2f0] rounded-full text-[#24422e] font-black text-xs">
                    {(item.score || 0).toFixed(1)}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-6 p-4 rounded-xl flex items-start gap-3 bg-[#eff2f0] border border-[#24422e]/10">
        <TrendingUp className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
        <p className="text-[11px] leading-relaxed text-[#24422e] font-medium">
          <span className="font-bold uppercase tracking-wider">
            How is Impact Score calculated?
          </span>
          <br />
          The score is a balanced metric of{" "}
          <span className="font-bold">Open Rate × Logarithmic Volume</span>.
          This surfaces content that consistently performs well while ensuring
          high-volume campaigns that drive significant business results are
          prioritized in the rankings.
        </p>
      </div>
      {data[0] && (
        <div className="mt-3 p-4 rounded-xl flex items-start gap-3 bg-white border border-[#24422e]/20 shadow-sm">
          <Megaphone className="w-4 h-4 text-[#24422e] mt-0.5 shrink-0" />
          <p className="text-[11px] leading-relaxed text-[#24422e] font-medium">
            <span className="font-bold uppercase tracking-wider">
              Best Performing Template:
            </span>
            <br />
            The content{" "}
            <span className="font-bold">
              &quot;{data[0].name}&quot;
            </span>{" "}
            is currently the most effective, maintaining a{" "}
            <span className="text-gray-900 font-bold">
              {(data[0].openRate || 0).toFixed(1)}% engagement
              rate
            </span>{" "}
            across {data[0].sent.toLocaleString()} messages.
          </p>
        </div>
      )}
    </div>
  );
}
