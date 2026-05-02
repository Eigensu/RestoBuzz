export type ReportTab =
  | "campaigns"
  | "members"
  | "inbox"
  | "logs"
  | "billing"
  | "reservego";

export interface CampaignRow {
  id: string;
  channel: string;
  name: string;
  created_at: string;
  status: string;
  sent: number;
  delivered: number;
  delivery_rate: number;
  read_rate: number;
  failed: number;
}

export interface CategoryCount {
  category: string;
  count: number;
}

export interface TopVisitor {
  phone: string;
  name: string;
  type: string;
  visit_count: number;
  last_visit: string | null;
}

export interface CampaignData {
  summary: {
    total_campaigns: number;
    total_sent: number;
    delivery_rate: number;
    read_rate: number;
    failure_rate: number;
    total_failed: number;
    best_campaign: { name: string; read_rate: number; channel: string } | null;
    worst_campaign: {
      name: string;
      failure_rate: number;
      channel: string;
    } | null;
  };
  campaigns: CampaignRow[];
  weekly_trend: {
    week: string;
    sent: number;
    delivered: number;
    read: number;
  }[];
}

export interface MemberData {
  summary: {
    total_members: number;
    active_members: number;
    new_this_month: number;
    dormant_members: number;
    dormant_rate: number;
    top_engaged_customer: {
      name: string;
      _id: string;
      message_count: number;
    } | null;
  };
  monthly_growth: { month: string; new_members: number }[];
  category_split: CategoryCount[];
  top_visitors: TopVisitor[];
}

export interface EngagedCustomer {
  phone: string;
  name: string;
  last_message: string;
  message_count: number;
  last_received_at: string;
}

export interface InboxData {
  summary: {
    total_incoming_messages: number;
    unique_engaged_senders: number;
    avg_messages_per_sender: number;
    top_engaged_customer: {
      name: string;
      _id: string;
      message_count: number;
    } | null;
  };
  engaged_customers: EngagedCustomer[];
}

export interface LogItem {
  id: string;
  channel: string;
  recipient: string;
  recipient_name: string | null;
  campaign_id: string;
  status: string;
  error_reason: string | null;
  retry_count: number;
  created_at: string;
}

export interface LogsResponse {
  items: LogItem[];
  next_cursor?: string | null;
  page_size?: number;
}

export interface BillingCategoryRow {
  category: string;
  spend: number;
  count?: number;
  rate?: number;
}

export interface BillingData {
  summary: {
    total_spend: number;
    total_conversations: number;
    avg_cost_per_message: number;
    currency: string;
  };
  by_category: BillingCategoryRow[];
  daily_trend: { date: string; spend: number }[];
  monthly_breakdown?: { month: string; count: number; spend: number }[];
}

export interface ReserveGoData {
  summary: {
    total_guests: number;
    with_phone: number;
    with_email: number;
    total_bills: number;
    total_revenue: number;
    avg_bill: number;
    bills_with_amount: number;
  };
  monthly_trend: {
    month: string;
    revenue: number;
    bookings: number;
    avg_pax: number;
  }[];
  booking_statuses: { status: string; count: number }[];
  booking_types: { type: string; count: number }[];
  booking_sources: { source: string; count: number; revenue: number }[];
  top_sections: { section: string; count: number; revenue: number }[];
  visit_distribution: { label: string; count: number }[];
}
