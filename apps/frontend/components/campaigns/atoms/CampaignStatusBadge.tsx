import { CAMPAIGN_STATUS_COLORS } from "@/types/common/constants";
import { CampaignStatus } from "@/types/common/enums";

export function CampaignStatusBadge({ status }: Readonly<{ status: string }>) {
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${CAMPAIGN_STATUS_COLORS[status as CampaignStatus] ?? "bg-gray-100 text-gray-600"}`}
    >
      {status}
    </span>
  );
}
