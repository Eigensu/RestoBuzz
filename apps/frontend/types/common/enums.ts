export enum MessageStatus {
  QUEUED = "queued",
  SENDING = "sending",
  SENT = "sent",
  DELIVERED = "delivered",
  READ = "read",
  FAILED = "failed",
  CANCELLED = "cancelled",
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

export enum EmailCampaignStatus {
  DRAFT = "draft",
  QUEUED = "queued",
  SENDING = "sending",
  COMPLETED = "completed",
  PARTIAL_FAILURE = "partial_failure",
  FAILED = "failed",
  CANCELLED = "cancelled",
  QUOTA_EXCEEDED = "quota_exceeded",
}

export enum EmailLogStatus {
  QUEUED = "queued",
  SENDING = "sending",
  SENT = "sent",
  DELIVERED = "delivered",
  OPENED = "opened",
  CLICKED = "clicked",
  BOUNCED = "bounced",
  FAILED = "failed",
  COMPLAINED = "complained",
  SUPPRESSED = "suppressed",
}
