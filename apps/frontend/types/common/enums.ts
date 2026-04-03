export enum MessageStatus {
  QUEUED = "queued",
  SENDING = "sending",
  SENT = "sent",
  DELIVERED = "delivered",
  READ = "read",
  FAILED = "failed",
}

export enum CampaignStatus {
  DRAFT = "draft",
  QUEUED = "queued",
  RUNNING = "running",
  PAUSED = "paused",
  COMPLETED = "completed",
  FAILED = "failed",
  CANCELLED = "cancelled",
}
