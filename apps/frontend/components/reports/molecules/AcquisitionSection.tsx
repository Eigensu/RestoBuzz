import { Info, MessageSquareHeart, Sparkles, UserPlus } from "lucide-react";
import { SectionCard } from "../atoms/SectionCard";
import { StatCard } from "../atoms/StatCard";
import type { AcquisitionCampaignRow, AcquisitionData } from "../types";

/**
 * Where new members came from.
 *
 * Direct and assisted are shown apart on purpose — they are not equally
 * certain, and collapsing them into one "marketing worked" number would
 * overstate what the data supports.
 */
export function AcquisitionSection({
  data,
  loading,
}: {
  readonly data: AcquisitionData | null | undefined;
  readonly loading: boolean;
}) {
  if (loading) {
    return (
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 h-40 animate-pulse" />
    );
  }
  if (!data) return null;

  const { summary, by_campaign, attribution_window_days, tracking_started_at } =
    data;

  const trackingSince = tracking_started_at
    ? new Date(tracking_started_at).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={UserPlus}
          label="New Members"
          value={summary.new_members.toLocaleString()}
          sub="in this date range"
        />
        <StatCard
          icon={Sparkles}
          label="From Marketing"
          value={summary.from_marketing.toLocaleString()}
          sub={`${summary.marketing_share}% of new members`}
          highlight={summary.from_marketing > 0 ? "green" : undefined}
        />
        <StatCard
          icon={MessageSquareHeart}
          label="Replied To A Campaign"
          value={summary.direct.toLocaleString()}
          sub="signed up by replying"
        />
        <StatCard
          icon={Sparkles}
          label="Campaign-Assisted"
          value={summary.assisted.toLocaleString()}
          sub={`joined within ${attribution_window_days}d of a message`}
        />
      </div>

      <div className="flex items-start gap-3 bg-[#eff2f0]/50 border border-[#dfe7e2] rounded-2xl px-5 py-3.5">
        <Info className="w-4 h-4 text-[#24422e] shrink-0 mt-0.5" />
        <p className="text-xs text-gray-600 leading-relaxed">
          <span className="font-bold text-[#24422e]">
            {summary.direct.toLocaleString()} replied
          </span>{" "}
          to a campaign to sign up — that is a direct, causal result.{" "}
          <span className="font-bold text-[#24422e]">
            {summary.assisted.toLocaleString()} assisted
          </span>{" "}
          joined by another route within {attribution_window_days} days of a
          campaign reaching their phone — a strong signal, but correlation, not
          proof. The remaining{" "}
          {summary.organic.toLocaleString()} had no campaign contact before
          joining.
          {trackingSince && (
            <>
              {" "}
              Attribution only sees campaigns sent since{" "}
              <span className="font-semibold">{trackingSince}</span>.
            </>
          )}
        </p>
      </div>

      {by_campaign.length > 0 && (
        <SectionCard title="Members Won Per Campaign">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  {["Campaign", "Replied", "Assisted", "Total"].map((h) => (
                    <th
                      key={h}
                      className="text-[10px] font-black uppercase tracking-widest text-gray-400 text-left pb-3 pr-4"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {by_campaign.map((c: AcquisitionCampaignRow) => (
                  <tr
                    key={c.campaign_id ?? c.campaign_name}
                    className="border-b border-gray-50 hover:bg-gray-50/50 transition"
                  >
                    <td className="py-3 pr-4 font-medium text-gray-900">
                      {c.campaign_name}
                    </td>
                    <td className="py-3 pr-4 font-black text-[#24422e]">
                      {c.direct}
                    </td>
                    <td className="py-3 pr-4 font-medium text-gray-500">
                      {c.assisted}
                    </td>
                    <td className="py-3 pr-4 font-black text-gray-900">
                      {c.total}
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
