export interface Restaurant {
  id: string;
  name: string;
  location: string;
  emoji: string;
  color: string; // tailwind bg color class
}

export const RESTAURANTS: Restaurant[] = [
  {
    id: "r1",
    name: "Downtown Grill",
    location: "Downtown",
    emoji: "🍔",
    color: "bg-orange-500",
  },
  {
    id: "r2",
    name: "Sakura Garden",
    location: "Midtown",
    emoji: "🍣",
    color: "bg-pink-500",
  },
  {
    id: "r3",
    name: "La Piazza",
    location: "West End",
    emoji: "🍕",
    color: "bg-red-500",
  },
  {
    id: "r4",
    name: "Spice Route",
    location: "East Side",
    emoji: "🍛",
    color: "bg-yellow-500",
  },
  {
    id: "r5",
    name: "The Green Bowl",
    location: "Uptown",
    emoji: "🥗",
    color: "bg-green-500",
  },
  {
    id: "r6",
    name: "Harbor Catch",
    location: "Waterfront",
    emoji: "🦞",
    color: "bg-blue-500",
  },
];

export interface Campaign {
  id: string;
  name: string;
  template_id: string;
  template_name: string;
  priority: "MARKETING" | "UTILITY";
  status:
    | "draft"
    | "queued"
    | "running"
    | "paused"
    | "completed"
    | "failed"
    | "cancelled";
  total_count: number;
  sent_count: number;
  delivered_count: number;
  read_count: number;
  failed_count: number;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_by: string;
  include_unsubscribe: boolean;
  created_at: string;
}

export interface MessageLog {
  id: string;
  job_id: string;
  recipient_phone: string;
  recipient_name: string;
  wa_message_id: string | null;
  status: "queued" | "sending" | "sent" | "delivered" | "read" | "failed";
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
  }>;
  invalid_rows: Array<{
    row_number: number;
    raw_phone: string;
    reason: string;
  }>;
  file_ref: string;
}

export interface Template {
  name: string;
  status: string;
  category: string;
  language: string;
  components: Array<{
    type: string;
    text?: string;
    format?: string;
    example?: Record<string, unknown>;
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
