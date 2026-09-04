import type { CampaignPauseReason } from "@/types";

/** List-view marker for a campaign Meta blocked, so it reads without drilling in. */
export function BlockedByMetaChip({
  reason,
}: Readonly<{ reason: CampaignPauseReason }>) {
  return (
    <span
      title={reason.message}
      className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700"
    >
      ⚠️ Blocked by Meta
    </span>
  );
}
