import { CampaignStatus, MessageStatus } from "./common/enums";

export interface WaPhone {
  phone_id: string;
  access_token_env_key: string;
  waba_id: string;
  label: string;
}

export interface EcardConfig {
  template_name: string;
  base_public_id: string;
  base_url: string;
  language: string;
  overlay: Record<string, unknown>;
}

export interface Restaurant {
  id: string;
  name: string;
  location: string;
  emoji: string;
  color: string; // tailwind bg color class
  member_categories: string[];
  wa_phone_ids?: string[];
  wa_phones?: WaPhone[];
  ecard_config?: EcardConfig | null;
}

/** Why the send path parked a campaign, when Meta blocked it rather than a human. */
export interface CampaignPauseReason {
  code: string;
  summary: string;
  /** Meta's own wording — shown verbatim so it matches WhatsApp Manager. */
  message: string;
  template_name: string | null;
  paused_at: string | null;
  auto: boolean;
}

export interface Campaign {
  id: string;
  name: string;
  template_id: string;
  template_name: string;
  status: CampaignStatus;
  total_count: number;
  sent_count: number;
  delivered_count: number;
  read_count: number;
  failed_count: number;
  replies_count: number;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_by: string;
  include_unsubscribe: boolean;
  created_at: string;
  parent_campaign_id: string | null;
  has_been_retried: boolean;
  smart_retries: boolean;
  retry_until: string | null;
  pause_reason: CampaignPauseReason | null;
}

export interface MessageLog {
  id: string;
  job_id: string;
  recipient_phone: string;
  recipient_name: string;
  wa_message_id: string | null;
  status: MessageStatus;
  retry_count: number;
  endpoint_used: "primary" | "fallback" | null;
  fallback_used: boolean;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface Conversation {
  from_phone: string;
  sender_name: string | null;
  last_message: string | null;
  last_message_type: string;
  unread_count: number;
  last_received_at: string;
}

export interface InboundMessage {
  id: string;
  wa_message_id: string;
  from_phone: string;
  sender_name: string | null;
  message_type:
    | "text"
    | "image"
    | "document"
    | "location"
    | "sticker"
    | "unknown";
  body: string | null;
  media_url: string | null;
  media_mime_type: string | null;
  location: { lat: number; lng: number; name?: string } | null;
  is_read: boolean;
  received_at: string;
  direction?: "inbound" | "outbound";
  status?: MessageStatus | null;
}

export interface PreflightResult {
  valid_count: number;
  invalid_count: number;
  duplicate_count: number;
  suppressed_count: number;
  valid_rows: Array<{
    name: string;
    phone: string;
    variables: Record<string, string>;
    /** Every non-empty cell of the source row, keyed by column header. */
    row?: Record<string, string>;
  }>;
  invalid_rows: Array<{
    row_number: number;
    raw_phone: string;
    reason: string;
  }>;
  file_ref: string;
  /** Column headers from the sheet, offered as variable sources. */
  headers?: string[];
}

export interface Template {
  name: string;
  status: string;
  category: string;
  language: string;
  media_url?: string;
  components: Array<{
    type: string;
    text?: string;
    format?: string;
    example?: Record<string, unknown>;
    /** BUTTONS components only. Meta's own button types are open-ended, so
     *  `type` stays a plain string. */
    buttons?: Array<{
      type: string;
      text?: string;
      url?: string;
      phone_number?: string;
      example?: string;
    }>;
  }>;
}

export interface CampaignProgress {
  status: string;
  sent: number;
  delivered: number;
  read: number;
  failed: number;
  total: number;
}

/** A behavioural view of the member base, defined by the backend. */
export interface MemberSegment {
  id: string;
  label: string;
  description: string;
}

export interface MemberSegmentsResponse {
  segments: MemberSegment[];
}

export interface Member {
  id: string;
  restaurant_id: string;
  /**
   * The member's category — one of the restaurant's configurable
   * `member_categories`. Never a segment id: "interested" is a tag, not a type.
   */
  type: string;
  name: string;
  phone: string;
  email: string | null;
  card_uid: string | null;
  ecard_code: string | null;
  tags: string[];
  notes: string | null;
  visit_count: number;
  last_visit: string | null;
  is_active: boolean;
  normalized_phone: string | null;
  dormancy_tier: "ACTIVE" | "AT_RISK" | "DORMANT" | "LOST" | "UNKNOWN";
  last_synced_at: string | null;
  /** Backend-computed dormancy status. Optional so older API responses don't crash. */
  activity_status?:
    | "active"
    | "dormant"
    | "unknown"
    | "at_risk"
    | "lost"
    | null;
  /** Provenance of the activity match (uuid_match, phone_match, fallback_internal). */
  activity_source?: string | null;
  joined_at: string;
  /** Set when the member was captured by replying positively to a campaign. */
  interested_at?: string | null;
  interested_campaign_name?: string | null;
  /**
   * Lifetime messaging rollup. Durable counters, NOT derived from message_logs
   * (which expire after 30 days). Optional so older API responses don't crash.
   */
  messages_sent?: number;
  messages_received?: number;
  messages_read?: number;
  last_message_at?: string | null;
}

export interface MemberListResponse {
  items: Member[];
  total: number;
  page: number;
  page_size: number;
}

// ── Email Campaign Types ─────────────────────────────────────────────────────

export interface EmailCampaign {
  id: string;
  restaurant_id: string;
  name: string;
  template_id: string;
  subject: string;
  from_email: string;
  status: string;
  total_count: number;
  sent_count: number;
  delivered_count: number;
  opened_count: number;
  clicked_count: number;
  bounced_count: number;
  failed_count: number;
  complained_count: number;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_by: string;
  created_at: string;
}

export interface EmailLog {
  id: string;
  campaign_id: string;
  recipient_email: string;
  recipient_name: string;
  resend_email_id: string | null;
  status: string;
  status_history: Array<{
    status: string;
    timestamp: string;
    meta: Record<string, unknown>;
  }>;
  retry_count: number;
  error_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmailTemplate {
  id: string;
  restaurant_id: string;
  name: string;
  subject: string;
  html: string;
  text: string | null;
  variables: Array<{
    key: string;
    type: "string" | "number";
    fallback_value: string | number | null;
  }>;
  version: number;
  synced_from: string | null;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

// ── ReserveGo Types ──────────────────────────────────────────────────────────

export interface ReserveGoGuest {
  id: string;
  guest_name: string;
  phone: string;
  email: string | null;
  total_visits: number;
  source: string | null;
  mode: string | null;
  last_visited_date: string | null;
  birthday: string | null;
  anniversary: string | null;
  sheet: string;
  restaurant_id: string;
  uploaded_at: string;
  filename: string;
  data_from?: string | null;
  data_until?: string | null;
}

export interface ReserveGoBill {
  id: string;
  sno: number | null;
  outlet_name: string | null;
  booking_time: string | null;
  seated_time: string | null;
  reserved_time: string | null;
  booking_type: string | null;
  guest_name: string;
  guest_number: string | null;
  guest_email: string | null;
  pax: number | null;
  reserved_by: string | null;
  sections: string | null;
  tables: string | null;
  visit_count: number | null;
  booking_status: string | null;
  bill_amount: number | null;
  bill_number: string | null;
  booking_amount: number | null;
  source_of_booking: string | null;
  tags: string | null;
  guest_comments: string | null;
  outlet_comments: string | null;
  deletion_type: string | null;
  deleted_reason: string | null;
  preferences: string | null;
  booking_amount_tranx_id: string | null;
  booking_amount_payment_status: string | null;
  booking_amount_payment_date: string | null;
  restaurant_id: string;
  uploaded_at: string;
  filename: string;
  data_from?: string | null;
  data_until?: string | null;
}

export interface ReserveGoListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
