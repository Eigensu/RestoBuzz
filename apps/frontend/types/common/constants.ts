import { CampaignStatus, MessageStatus } from "./enums";

export const CAMPAIGN_STATUS_COLORS: Record<CampaignStatus, string> = {
  [CampaignStatus.DRAFT]: "bg-gray-100 text-gray-600",
  [CampaignStatus.QUEUED]: "bg-blue-100 text-blue-700",
  [CampaignStatus.RUNNING]: "bg-yellow-100 text-yellow-700",
  [CampaignStatus.PAUSED]: "bg-orange-100 text-orange-700",
  [CampaignStatus.COMPLETED]: "bg-green-100 text-green-700",
  [CampaignStatus.FAILED]: "bg-red-100 text-red-700",
  [CampaignStatus.CANCELLED]: "bg-gray-100 text-gray-500",
};

export const MESSAGE_STATUS_COLORS: Record<MessageStatus, string> = {
  [MessageStatus.QUEUED]: "bg-blue-100 text-blue-700",
  [MessageStatus.SENDING]: "bg-yellow-100 text-yellow-700",
  [MessageStatus.SENT]: "bg-green-100 text-green-700",
  [MessageStatus.DELIVERED]: "bg-emerald-100 text-emerald-700",
  [MessageStatus.READ]: "bg-purple-100 text-purple-700",
  [MessageStatus.FAILED]: "bg-red-100 text-red-700",
};
